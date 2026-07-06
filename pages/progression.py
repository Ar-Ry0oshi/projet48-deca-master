"""
Page Progression — KPI transfert de services DECA vers la nouvelle arborescence SAESB.

Compare deux extraits CSV DECA et mesure, niveau par niveau, le taux d'outils
dont la combinaison service1…serviceN existe dans le référentiel SERVICES_EXTRACT.xlsx.

Entonnoir :
  S1     — service1 valide dans le référentiel
  S1-2   — (service1, service2) valides
  S1-3   — (service1, service2, service3) valides
  S1-4   — les 4 niveaux valides (arborescence complète)
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from datetime import datetime
from functools import lru_cache

import pandas as pd
import streamlit as st

from config import DECA_EXTRACTS_DIR, SERVICES_REF_PATH

# ── Constantes ────────────────────────────────────────────────────────────────

_LEVELS = ["S1", "S1-2", "S1-3", "S1-4"]
_SVC_COLS = ["service1", "service2", "service3", "service4"]

_BAT_KEYWORDS = {
    "MF":  "MF",
    "LSO": "LSO",
}


# ── Référentiel ───────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def _load_ref() -> dict[str, set[tuple]]:
    """Charge SERVICES_EXTRACT.xlsx et construit les ensembles de tuples valides."""
    if not SERVICES_REF_PATH.exists():
        return {}
    df = pd.read_excel(SERVICES_REF_PATH, dtype=str).fillna("")
    df.columns = df.columns.str.strip().str.lower()
    for c in _SVC_COLS:
        if c not in df.columns:
            df[c] = ""
    df = df[_SVC_COLS].apply(lambda col: col.str.strip())
    return {
        "S1":   set(zip(df["service1"])),
        "S1-2": set(zip(df["service1"], df["service2"])),
        "S1-3": set(zip(df["service1"], df["service2"], df["service3"])),
        "S1-4": set(zip(df["service1"], df["service2"], df["service3"], df["service4"])),
    }


# ── Chargement CSV ────────────────────────────────────────────────────────────

def _parse_date_from_name(name: str) -> datetime:
    """Extrait une date approximative depuis le nom de fichier pour tri."""
    # Essaie d'extraire YYYYMMDD, DD-MM-YYYY, DDMon, etc.
    m = re.search(r"(\d{4})[_\-]?(\d{2})[_\-]?(\d{2})", name)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            pass
    # Fallback: date de modification du fichier (non dispo en session), on retourne epoch
    return datetime.min


def _scan_csv_dir() -> list[Path]:
    """Scanne le dossier d'extraits et retourne les CSV triés du plus récent au plus ancien."""
    if not DECA_EXTRACTS_DIR.exists():
        return []
    files = sorted(
        DECA_EXTRACTS_DIR.glob("*.csv"),
        key=lambda p: (p.stat().st_mtime if p.exists() else 0),
        reverse=True,
    )
    return files


def _read_deca_csv(raw: bytes) -> pd.DataFrame:
    sep = ";" if b";" in raw[:2000] else ","
    df = None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(
                io.BytesIO(raw), dtype=str, encoding=enc, sep=sep,
                on_bad_lines="skip", engine="python",
            ).fillna("")
            break
        except (UnicodeDecodeError, Exception):
            continue
    if df is None:
        raise ValueError("Impossible de décoder le fichier CSV (encodage non reconnu).")
    df.columns = df.columns.str.strip().str.lower()
    for c in _SVC_COLS:
        if c not in df.columns:
            df[c] = ""
    keep = [c for c in ["marquage"] + _SVC_COLS if c in df.columns]
    df = df[keep]
    for c in _SVC_COLS:
        df[c] = df[c].str.strip()
    return df


@st.cache_data(ttl=600, show_spinner=False)
def _load_csv(path_str: str) -> pd.DataFrame:
    return _read_deca_csv(Path(path_str).read_bytes())


def _load_uploaded(uploaded) -> pd.DataFrame:
    return _read_deca_csv(uploaded.read())


# ── Calcul KPI ────────────────────────────────────────────────────────────────

def _compute_kpi(df: pd.DataFrame, ref: dict[str, set], bat: str) -> dict:
    """Retourne {level: {"n": int, "total": int, "pct": float}} pour un extrait."""
    # Filtre bâtiment
    if bat != "ALL":
        kw = _BAT_KEYWORDS[bat]
        df = df[df["service1"].str.contains(kw, case=False, na=False)]

    total = len(df)
    if total == 0:
        return {lv: {"n": 0, "total": 0, "pct": 0.0} for lv in _LEVELS}

    results = {}

    # S1
    mask_s1 = df["service1"].apply(lambda v: (v,) in ref.get("S1", set())) & df["service1"].ne("")
    results["S1"] = {"n": int(mask_s1.sum()), "total": total, "pct": mask_s1.mean() * 100}

    # S1-2
    mask_s12 = (
        mask_s1
        & df["service2"].ne("")
        & df.apply(lambda r: (r["service1"], r["service2"]) in ref.get("S1-2", set()), axis=1)
    )
    results["S1-2"] = {"n": int(mask_s12.sum()), "total": total, "pct": mask_s12.mean() * 100}

    # S1-3
    mask_s13 = (
        mask_s12
        & df["service3"].ne("")
        & df.apply(lambda r: (r["service1"], r["service2"], r["service3"]) in ref.get("S1-3", set()), axis=1)
    )
    results["S1-3"] = {"n": int(mask_s13.sum()), "total": total, "pct": mask_s13.mean() * 100}

    # S1-4
    mask_s14 = (
        mask_s13
        & df["service4"].ne("")
        & df.apply(lambda r: (r["service1"], r["service2"], r["service3"], r["service4"]) in ref.get("S1-4", set()), axis=1)
    )
    results["S1-4"] = {"n": int(mask_s14.sum()), "total": total, "pct": mask_s14.mean() * 100}

    return results


# ── Graphique ─────────────────────────────────────────────────────────────────

def _render_chart(kpi_a: dict, kpi_b: dict, label_a: str, label_b: str):
    try:
        import plotly.graph_objects as go
    except ImportError:
        st.warning("plotly non installé — graphique indisponible.")
        return

    levels = list(reversed(_LEVELS))  # S1-4 en haut, S1 en bas
    pct_a = [kpi_a[lv]["pct"] for lv in levels]
    pct_b = [kpi_b[lv]["pct"] for lv in levels]
    delta = [b - a for a, b in zip(pct_a, pct_b)]

    bar_colors_delta = ["#2ecc71" if d >= 0 else "#e74c3c" for d in delta]

    fig = go.Figure()

    # Version A — barre bleue de base
    fig.add_trace(go.Bar(
        name=label_a,
        y=levels,
        x=pct_a,
        orientation="h",
        marker_color="#3b82f6",
        text=[f"{v:.1f}%" for v in pct_a],
        textposition="inside",
        insidetextanchor="middle",
    ))

    # Delta B-A — empilé dessus, couleur verte/rouge
    fig.add_trace(go.Bar(
        name=f"Δ {label_b} - {label_a}",
        y=levels,
        x=[abs(d) for d in delta],
        base=pct_a,
        orientation="h",
        marker_color=bar_colors_delta,
        text=[f"{d:+.1f}%" for d in delta],
        textposition="outside",
    ))

    fig.update_layout(
        barmode="stack",
        title=f"{label_a} vs {label_b} — Entonnoir transfert de services",
        xaxis=dict(title="% outils transférés", ticksuffix="%", range=[0, 105]),
        yaxis=dict(title=""),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        height=320,
        margin=dict(l=60, r=40, t=60, b=40),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )

    st.plotly_chart(fig, use_container_width=True)


# ── Tableau KPI ───────────────────────────────────────────────────────────────

def _render_kpi_table(kpi_a: dict, kpi_b: dict, label_a: str, label_b: str):
    rows = []
    for lv in _LEVELS:
        a = kpi_a[lv]
        b = kpi_b[lv]
        delta_n   = b["n"] - a["n"]
        delta_pct = b["pct"] - a["pct"]
        bar_filled = int(b["pct"] / 5)
        bar = "█" * bar_filled + "░" * (20 - bar_filled)
        rows.append({
            "Niveau":      lv,
            f"{label_a} (n)": a["n"],
            f"{label_a} (%)": f"{a['pct']:.1f}%",
            f"{label_b} (n)": b["n"],
            f"{label_b} (%)": f"{b['pct']:.1f}%",
            "Δ n":         f"{delta_n:+d}",
            "Δ %":         f"{delta_pct:+.1f}%",
            f"Progression {label_b}": bar,
        })

    df_kpi = pd.DataFrame(rows)
    st.dataframe(
        df_kpi,
        hide_index=True,
        width="stretch",
        column_config={
            "Niveau": st.column_config.TextColumn("Niveau", width="small"),
            f"Progression {label_b}": st.column_config.TextColumn("Progression", width="large"),
        },
    )


# ── Sélecteur de version ──────────────────────────────────────────────────────

def _version_selector(label: str, csv_files: list[Path], key_prefix: str) -> tuple[pd.DataFrame | None, str]:
    """Retourne (dataframe, label_court) pour une version."""
    st.markdown(f"**{label}**")
    use_upload = st.checkbox("Charger un fichier manuellement", key=f"{key_prefix}_upload_toggle")

    if use_upload:
        uploaded = st.file_uploader(
            "Fichier CSV DECA", type=["csv"], key=f"{key_prefix}_uploader"
        )
        if uploaded:
            df = _load_uploaded(uploaded)
            # Extraire date du nom
            date_str = re.sub(r"[^0-9A-Za-z]", "", Path(uploaded.name).stem)[-8:]
            return df, uploaded.name
        return None, ""

    if not csv_files:
        st.warning(f"Aucun CSV trouvé dans {DECA_EXTRACTS_DIR}")
        return None, ""

    options = {p.name: p for p in csv_files}
    chosen = st.selectbox(
        "Extrait", list(options.keys()), key=f"{key_prefix}_select"
    )
    path = options[chosen]
    mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
    st.caption(f"Modifié le {mtime}")
    df = _load_csv(str(path))
    return df, Path(chosen).stem


# ── Point d'entrée ────────────────────────────────────────────────────────────

def render():
    st.markdown("## Progression — Transfert de services")
    st.caption(
        "Mesure le taux d'outils DECA dont la combinaison service1…serviceN "
        "est valide dans le référentiel SERVICES_EXTRACT.xlsx."
    )

    # ── Référentiel ──────────────────────────────────────────────────────────
    if not SERVICES_REF_PATH.exists():
        st.error(f"Référentiel introuvable : `{SERVICES_REF_PATH}`")
        return

    with st.spinner("Chargement référentiel…"):
        ref = _load_ref()

    if not ref:
        st.error("Impossible de charger le référentiel.")
        return

    st.caption(f"Référentiel : {len(next(iter(ref.values())))} combinaisons S1 · {SERVICES_REF_PATH.name}")

    # ── Scan dossier extraits ─────────────────────────────────────────────────
    csv_files = _scan_csv_dir()

    # ── Filtres ───────────────────────────────────────────────────────────────
    col_bat, col_spacer = st.columns([1, 4])
    bat = col_bat.radio("Bâtiment", ["ALL", "MF", "LSO"], horizontal=True, key="prog_bat")

    st.divider()

    # ── Sélecteurs versions ───────────────────────────────────────────────────
    col_a, col_sep, col_b = st.columns([5, 0.3, 5])
    with col_a:
        df_a, lbl_a = _version_selector("Version A (référence)", csv_files, "ver_a")
    col_sep.markdown("<div style='border-left:1px solid #ccc;height:200px;margin:auto'></div>",
                     unsafe_allow_html=True)
    with col_b:
        df_b, lbl_b = _version_selector("Version B (comparaison)", csv_files, "ver_b")

    if df_a is None or df_b is None:
        st.info("Sélectionne deux extraits pour afficher la comparaison.")
        return

    # Raccourcit les labels si trop longs
    lbl_a_short = lbl_a[:20] if len(lbl_a) > 20 else lbl_a
    lbl_b_short = lbl_b[:20] if len(lbl_b) > 20 else lbl_b

    # ── Calcul ────────────────────────────────────────────────────────────────
    with st.spinner("Calcul en cours…"):
        kpi_a = _compute_kpi(df_a.copy(), ref, bat)
        kpi_b = _compute_kpi(df_b.copy(), ref, bat)

    if bat == "ALL":
        total_a, total_b = len(df_a), len(df_b)
    else:
        kw = _BAT_KEYWORDS[bat]
        total_a = df_a[df_a["service1"].str.contains(kw, case=False, na=False)].shape[0]
        total_b = df_b[df_b["service1"].str.contains(kw, case=False, na=False)].shape[0]

    col_ta, col_tb, col_empty = st.columns([1, 1, 4])
    col_ta.metric(f"Total {lbl_a_short}", total_a)
    col_tb.metric(f"Total {lbl_b_short}", total_b, delta=total_b - total_a)

    st.divider()

    # ── Graphique ─────────────────────────────────────────────────────────────
    _render_chart(kpi_a, kpi_b, lbl_a_short, lbl_b_short)

    st.divider()

    # ── Tableau ───────────────────────────────────────────────────────────────
    _render_kpi_table(kpi_a, kpi_b, lbl_a_short, lbl_b_short)

    # ── Détail par bâtiment (si ALL sélectionné) ─────────────────────────────
    if bat == "ALL":
        with st.expander("Détail par bâtiment", expanded=False):
            for b_code in ["MF", "LSO"]:
                st.markdown(f"**{b_code}**")
                kpi_a_b = _compute_kpi(df_a.copy(), ref, b_code)
                kpi_b_b = _compute_kpi(df_b.copy(), ref, b_code)
                _render_kpi_table(kpi_a_b, kpi_b_b, lbl_a_short, lbl_b_short)
