"""
Reload all source files into the tools table.
Run this whenever source files are refreshed (2-3x/month).
Decisions table is never touched — only tools is rebuilt.

Usage:
    python -m scripts.reload_sources [--data-dir <path>]
"""
import re
import sys
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DATA_DIR, EXCLUDED_ETATS, EXCLUDED_SERVICE_KEYWORDS,
    SRC_DECA_PATTERNS, SRC_PANOPLY_PATTERNS, SRC_DMC_PATTERNS, SRC_ICV_PATTERNS,
)
from db.db import init_schema, get_connection

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_file(data_dir: Path, patterns: list[str]) -> Path | None:
    for pat in patterns:
        matches = sorted(data_dir.glob(pat), key=lambda p: p.stat().st_mtime, reverse=True)
        if matches:
            return matches[0]
    return None


def _pn_short(pn: str | None) -> str | None:
    """956A1309G01 → 956A1309  (strips trailing G-suffix and variant codes)."""
    if not pn or pd.isna(pn):
        return None
    pn = str(pn).strip().upper()
    pn = re.sub(r"G\d+$", "", pn)
    return pn or None


def _norm_assy(flag: str | None) -> str | None:
    if not flag or pd.isna(flag):
        return None
    flag = str(flag).strip().upper()
    flag = flag.replace("DYSASSY", "DISASSY")
    return flag


def _is_excluded_by_service(row: pd.Series, svc_cols: list[str]) -> str | None:
    for col in svc_cols:
        val = str(row.get(col, "") or "").upper()
        for kw in EXCLUDED_SERVICE_KEYWORDS:
            if kw in val:
                return val
    return None


# ---------------------------------------------------------------------------
# DECA loader — auto-detects Feb (21 cols, comma) vs May (208 cols, semi-colon)
# ---------------------------------------------------------------------------

# Canonical internal column names → (feb_col, may_col)
_DECA_COL_MAP = {
    "marquage":         ("Marquage",         "marquage"),
    "ref_constructeur": ("Réf. Constructeur", "ref_constructeur"),
    "etat":             ("Etat",              "etat"),
    "disponible":       (None,                "disponible"),
    "famille":          ("Famille",           "famille"),
    "sous_famille":     (None,                "sous_famille"),
    "type_outil":       ("Type",              "type"),
    "application":      (None,                "application"),
    "commentaire":      (None,                "commentaire"),
    "procop":           (None,                "procop"),
    "constructeur":     ("Constructeur",      "constructeur"),
    "nserie":           ("N Série",           "nserie"),
    "service1":         ("Service1",          "service1"),
    "service2":         ("Service2",          "service2"),
    "service3":         ("Service3",          "service3"),
    "service4":         ("Service4",          "service4"),
    "service5":         ("Service5",          "service5"),
    "localisation1":    ("Localisation1",     "localisation1"),
    "localisation2":    ("Localisation2",     "localisation2"),
    "localisation3":    ("Localisation3",     "localisation3"),
    "localisation4":    ("Localisation4",     "localisation4"),
    "localisation5":    ("Localisation5",     "localisation5"),
}

SVC_COLS_INTERNAL = ["service1", "service2", "service3", "service4", "service5"]


def _load_deca(path: Path) -> tuple[pd.DataFrame, str]:
    """Returns (normalised dataframe, format_name)."""
    raw = path.read_bytes()[:8000]
    import chardet
    enc = chardet.detect(raw)["encoding"] or "latin-1"

    # Detect separator by trying both
    df = None
    for sep in [";", ","]:
        try:
            candidate = pd.read_csv(path, sep=sep, encoding=enc, dtype=str,
                                    low_memory=False, on_bad_lines="skip")
            if len(candidate.columns) > 5:
                df = candidate
                break
        except Exception:
            continue
    if df is None:
        raise ValueError(f"Could not parse DECA file: {path}")

    cols = set(df.columns.str.strip().str.lower())
    is_may = "ref_constructeur" in cols  # only May format has this exact name

    fmt = "may_full" if is_may else "feb_light"
    col_idx = 1 if is_may else 0  # index into _DECA_COL_MAP tuples

    out = pd.DataFrame()
    for internal, (feb_col, may_col) in _DECA_COL_MAP.items():
        src_col = may_col if is_may else feb_col
        if src_col and src_col in df.columns:
            out[internal] = df[src_col].str.strip()
        elif src_col:
            # Try case-insensitive match
            match = next((c for c in df.columns if c.strip().lower() == src_col.lower()), None)
            if match:
                out[internal] = df[match].str.strip()
            else:
                out[internal] = None
        else:
            out[internal] = None

    out["source_file"] = path.name
    out["source_format"] = fmt
    log.info("Loaded DECA: %s — %d rows, format=%s", path.name, len(out), fmt)
    return out, fmt


# ---------------------------------------------------------------------------
# Panoply loader
# ---------------------------------------------------------------------------

def _load_panoply(path: Path) -> dict[str, dict]:
    """Returns {pn_short: {modules: [str], assy_flag: str}}."""
    df = pd.read_excel(path, dtype=str)
    df.columns = df.columns.str.strip()

    result: dict[str, dict] = {}
    for _, row in df.iterrows():
        pn = _pn_short(row.get("PN_Short"))
        if not pn:
            continue
        module = str(row.get("Module", "")).strip().upper()
        flag = _norm_assy(row.get("ASSY_FLAG"))

        if pn not in result:
            result[pn] = {"modules": [], "assy_flag": flag}
        if module and module not in result[pn]["modules"]:
            result[pn]["modules"].append(module)
        if flag and result[pn]["assy_flag"] != flag:
            result[pn]["assy_flag"] = "ASSY AND DISASSY"

    log.info("Loaded Panoply: %d unique PNs", len(result))
    return result


# ---------------------------------------------------------------------------
# DMC/ESM loader
# ---------------------------------------------------------------------------

def _load_dmc(path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """
    Returns:
        pn_modules : {pn_short: [module, ...]}
        pn_opcodes : {pn_short: [opcode, ...]}
    """
    xl = pd.ExcelFile(path)

    # Prefer PN_Type_Module sheet (has MM/SM columns already decoded)
    preferred = ["PN_Type_Module", "Pn-Module", "DMC_1A+B (2)", "DMC_1A", "DMC_1B"]
    sheet = next((s for s in preferred if s in xl.sheet_names), xl.sheet_names[0])
    df = pd.read_excel(path, sheet_name=sheet, dtype=str)
    df.columns = df.columns.str.strip()

    pn_modules: dict[str, list[str]] = {}
    pn_opcodes: dict[str, list[str]] = {}

    for _, row in df.iterrows():
        pn = _pn_short(row.get("PN"))
        if not pn:
            continue

        # Extract module
        module = None
        sm = str(row.get("SM", "") or "").strip().upper()
        mm = str(row.get("MM", "") or "").strip().upper()
        if re.match(r"SM\d+", sm):
            module = sm
        elif re.match(r"MM\d+", mm):
            module = mm

        if module:
            if pn not in pn_modules:
                pn_modules[pn] = []
            if module not in pn_modules[pn]:
                pn_modules[pn].append(module)

        # Store raw opcode
        opcode = str(row.get("OpCode", "") or "").strip()
        if opcode and opcode != "nan":
            if pn not in pn_opcodes:
                pn_opcodes[pn] = []
            if opcode not in pn_opcodes[pn]:
                pn_opcodes[pn].append(opcode)

    log.info("Loaded DMC sheet [%s]: %d unique PNs with modules", sheet, len(pn_modules))
    return pn_modules, pn_opcodes


# ---------------------------------------------------------------------------
# ICV loader
# ---------------------------------------------------------------------------

def _load_icv(path: Path) -> dict[str, str]:
    """Returns {ic_code: information_name}.

    Tries the sheet named 'ICV_Translation' first, then falls back to the
    first sheet — handles workbooks where that sheet is not sheet 0.
    """
    xl = pd.ExcelFile(path)
    target = next(
        (s for s in xl.sheet_names if "icv" in s.lower() or "translation" in s.lower()),
        xl.sheet_names[0],
    )
    df = xl.parse(target, dtype=str)
    df.columns = df.columns.str.strip()

    ic_col = next((c for c in df.columns if "ic" in c.lower()), None)
    name_col = next((c for c in df.columns if "information" in c.lower() or "name" in c.lower()), None)
    if not ic_col or not name_col:
        log.warning("ICV file column detection failed (sheet=%s): %s", target, list(df.columns))
        return {}

    result = {}
    for _, row in df.iterrows():
        ic = str(row.get(ic_col, "") or "").strip().upper()
        name = str(row.get(name_col, "") or "").strip()
        if ic and name and ic != "NAN":
            result[ic] = name

    log.info("Loaded ICV: %d codes", len(result))
    return result


def _translate_opcodes(opcodes: list[str], icv: dict[str, str]) -> str:
    """Extract IC codes from DMC opcodes and translate them."""
    seen, parts = set(), []
    for op in opcodes:
        # DMC format: LEAP-1A-72-09-90-01A-664F-C
        # IC code is the 6th segment (index 5 after split on -)
        segments = op.split("-")
        if len(segments) >= 6:
            ic = segments[5].upper()
            if ic not in seen:
                seen.add(ic)
                label = icv.get(ic)
                parts.append(f"{ic} — {label}" if label else ic)
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Module resolution with conflict detection
# ---------------------------------------------------------------------------

def _resolve_modules(
    pn: str,
    panoply: dict[str, dict],
    dmc_modules: dict[str, list[str]],
) -> tuple[list[str], str, str]:
    """
    Returns (effective_modules, module_source, conflict_detail).
    module_source: 'panoply_only' | 'esm_only' | 'both' | 'conflict' | 'none'
    """
    pan_mods = sorted(panoply.get(pn, {}).get("modules", []))
    esm_mods = sorted(dmc_modules.get(pn, []))

    if not pan_mods and not esm_mods:
        return [], "none", ""

    if pan_mods and not esm_mods:
        return pan_mods, "panoply_only", ""

    if esm_mods and not pan_mods:
        return esm_mods, "esm_only", ""

    # Both have data — compare
    if set(pan_mods) == set(esm_mods):
        return pan_mods, "both", ""

    # Conflict — Panoply takes priority (more operationally reliable)
    conflict_detail = f"Panoply: {', '.join(pan_mods)} | ESM: {', '.join(esm_mods)}"
    return pan_mods, "conflict", conflict_detail


# ---------------------------------------------------------------------------
# Exclusion logic
# ---------------------------------------------------------------------------

def _get_exclusion_reason(row: pd.Series) -> str | None:
    etat = str(row.get("etat", "") or "").strip().upper()
    if etat in EXCLUDED_ETATS:
        return etat

    svc_reason = _is_excluded_by_service(row, SVC_COLS_INTERNAL)
    if svc_reason:
        return svc_reason

    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def reload(data_dir: Path | None = None) -> dict:
    data_dir = data_dir or DATA_DIR
    init_schema()

    # --- Find source files ---
    deca_path = _find_file(data_dir, SRC_DECA_PATTERNS)
    panoply_path = _find_file(data_dir, SRC_PANOPLY_PATTERNS)
    dmc_path = _find_file(data_dir, SRC_DMC_PATTERNS)
    icv_path = _find_file(data_dir, SRC_ICV_PATTERNS)

    missing = [n for n, p in [("DECA", deca_path), ("Panoply", panoply_path), ("DMC", dmc_path)] if not p]
    if missing:
        raise FileNotFoundError(f"Missing source files: {missing}. Place them in {data_dir}")

    log.info("Sources found: DECA=%s Panoply=%s DMC=%s ICV=%s",
             deca_path.name, panoply_path.name, dmc_path.name,
             icv_path.name if icv_path else "MISSING (optional)")

    # --- Load sources ---
    deca_df, deca_fmt = _load_deca(deca_path)
    panoply = _load_panoply(panoply_path)
    dmc_modules, dmc_opcodes = _load_dmc(dmc_path)
    icv = _load_icv(icv_path) if icv_path else {}

    # --- Normalize marquage: preserve leading zeros as text ---
    deca_df["marquage"] = deca_df["marquage"].apply(
        lambda x: str(x).strip().zfill(5) if pd.notna(x) and str(x).strip() else None
    )
    deca_df = deca_df.dropna(subset=["marquage"])
    deca_df = deca_df[deca_df["marquage"] != "nan"]
    dups = deca_df["marquage"].duplicated().sum()
    if dups:
        log.warning("Dropping %d duplicate marquage rows (keeping last)", dups)
        deca_df = deca_df.drop_duplicates(subset=["marquage"], keep="last")

    # --- Derive pn_short from ref_constructeur ---
    deca_df["pn_short"] = deca_df["ref_constructeur"].apply(_pn_short)

    # --- Pre-compute DECA count per PN (active only) ---
    active_mask = deca_df["etat"].apply(
        lambda e: str(e or "").strip().upper() not in EXCLUDED_ETATS
    )
    deca_counts = (
        deca_df[active_mask & deca_df["pn_short"].notna()]
        .groupby("pn_short")["marquage"]
        .count()
        .to_dict()
    )

    # --- Build rows ---
    rows = []
    loaded_at = datetime.now(timezone.utc).isoformat()

    for _, row in deca_df.iterrows():
        marquage = row["marquage"]
        pn = row.get("pn_short")

        exclusion = _get_exclusion_reason(row)

        eff_modules, mod_source, conflict = _resolve_modules(pn or "", panoply, dmc_modules)
        pan_entry = panoply.get(pn or "", {})
        assy = pan_entry.get("assy_flag") or _norm_assy(None)

        esm_mods = sorted(dmc_modules.get(pn or "", []))
        pan_mods = pan_entry.get("modules", [])

        opcodes = dmc_opcodes.get(pn or "", [])
        opcodes_translated = _translate_opcodes(opcodes, icv) if opcodes else None

        deca_count = deca_counts.get(pn or "", 0)
        eff_mod_count = len(eff_modules)

        # Complexity flag — based on active DECAs and effective modules for this PN.
        # Excluded tools still carry the flag so they appear correctly in search results.
        if not eff_modules:
            complexity = "no_match"
        elif eff_mod_count > 1:
            complexity = "multi_module"
        elif deca_count > 1:
            complexity = "multi_deca"
        else:
            complexity = "unique"

        rows.append((
            marquage,
            pn,
            row.get("ref_constructeur"),
            row.get("etat"),
            row.get("disponible"),
            row.get("famille"),
            row.get("sous_famille"),
            row.get("type_outil"),
            row.get("application"),
            row.get("commentaire"),
            row.get("procop"),
            row.get("constructeur"),
            row.get("nserie"),
            row.get("service1"), row.get("service2"), row.get("service3"),
            row.get("service4"), row.get("service5"),
            row.get("localisation1"), row.get("localisation2"), row.get("localisation3"),
            row.get("localisation4"), row.get("localisation5"),
            ", ".join(pan_mods) if pan_mods else None,
            assy,
            ", ".join(esm_mods) if esm_mods else None,
            ", ".join(eff_modules) if eff_modules else None,
            mod_source,
            conflict or None,
            ", ".join(opcodes) if opcodes else None,
            opcodes_translated,
            1 if exclusion else 0,
            exclusion,
            complexity,
            deca_count,
            eff_mod_count,
            row.get("source_file"),
            row.get("source_format"),
            loaded_at,
        ))

    # --- Write to DB (replace tools entirely) ---
    conn = get_connection()
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("DELETE FROM tools")
        conn.executemany("""
            INSERT INTO tools (
                marquage, pn_short, ref_constructeur, etat, disponible,
                famille, sous_famille, type_outil, application, commentaire,
                procop, constructeur, nserie,
                service1, service2, service3, service4, service5,
                localisation1, localisation2, localisation3, localisation4, localisation5,
                modules_panoply, assy_flag, modules_esm, modules_effective,
                module_source, module_conflict_detail,
                opcodes_raw, opcodes_translated,
                is_excluded, exclusion_reason, complexity_flag,
                deca_count, eff_mod_count,
                source_file, source_format, loaded_at
            ) VALUES (
                ?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?
            )
        """, rows)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()
    finally:
        conn.close()

    stats = {
        "total": len(rows),
        "excluded": sum(1 for r in rows if r[31]),
        "unique": sum(1 for r in rows if r[33] == "unique"),
        "multi_deca": sum(1 for r in rows if r[33] == "multi_deca"),
        "multi_module": sum(1 for r in rows if r[33] == "multi_module"),
        "no_match": sum(1 for r in rows if r[33] == "no_match"),
        "conflict": sum(1 for r in rows if r[28]),
        "panoply_only": sum(1 for r in rows if r[27] == "panoply_only"),
        "esm_only": sum(1 for r in rows if r[27] == "esm_only"),
    }
    log.info("Done. %s", stats)
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=None)
    args = parser.parse_args()
    reload(args.data_dir)
