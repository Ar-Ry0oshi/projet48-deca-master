"""
Script one-shot : génère un extract plat avec colonne 1A/1B.

Sources :
  - Exports complets Excel générés par l'appli (un ou plusieurs fichiers)
  - CSV DECA brut (pour ct_string8/9 → 1A/1B et colonne etat)

Usage :
  python scripts/extract_1a1b.py

Editer les chemins dans la section CONFIG ci-dessous avant de lancer.
"""

import sys
from pathlib import Path
import pandas as pd

# ══════════════════════════════════════════════════════════════════════
#  CONFIG — à adapter avant de lancer
# ══════════════════════════════════════════════════════════════════════

# Fichiers exports complets générés par l'appli (xlsx)
EXPORT_FILES = [
    r"U:\DIR_TECH\01 - PSO\3 - Tooling\01 - Projet\48 - DECA standardisation\Standardisation Service\02_TOOLS_DEFINITIONS\Extracts\export_complet_MM03.xlsx",
    r"U:\DIR_TECH\01 - PSO\3 - Tooling\01 - Projet\48 - DECA standardisation\Standardisation Service\02_TOOLS_DEFINITIONS\Extracts\export_complet_SM57.xlsx",
    r"U:\DIR_TECH\01 - PSO\3 - Tooling\01 - Projet\48 - DECA standardisation\Standardisation Service\02_TOOLS_DEFINITIONS\Extracts\export_complet_SM58.xlsx",
    r"U:\DIR_TECH\01 - PSO\3 - Tooling\01 - Projet\48 - DECA standardisation\Standardisation Service\02_TOOLS_DEFINITIONS\Extracts\export_complet_SM59.xlsx",
]

# CSV brut DECA (celui dans 01_DATA_SOURCES/DECA_Extracts/CSV)
DECA_CSV = r"U:\DIR_TECH\01 - PSO\3 - Tooling\01 - Projet\48 - DECA standardisation\Standardisation Service\01_DATA_SOURCES\DECA_Extracts\CSV\Extract_DECA_02-Aug.csv"

# Fichier de sortie
OUTPUT = r"U:\DIR_TECH\01 - PSO\3 - Tooling\01 - Projet\48 - DECA standardisation\Standardisation Service\02_TOOLS_DEFINITIONS\Extracts\extract_1a1b.xlsx"

# Décalage des ct_string (0 = pas de décalage, 1 = décalé d'une colonne, etc.)
# Lancer d'abord avec DIAGNOSTIC=True pour vérifier
CT_OFFSET = 0

# Mettre True pour afficher les valeurs uniques et aider au débogage
DIAGNOSTIC = True

# ══════════════════════════════════════════════════════════════════════


def load_deca_csv(path: str) -> pd.DataFrame:
    raw = Path(path).read_bytes()
    sep = ";" if b";" in raw[:2000] else ","
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(
                path, dtype=str, encoding=enc, sep=sep,
                on_bad_lines="skip", engine="python"
            ).fillna("")
            df.columns = df.columns.str.strip()
            return df
        except Exception:
            continue
    raise ValueError(f"Impossible de lire {path}")


def detect_ct_columns(df: pd.DataFrame):
    """Retourne les noms de colonnes ct_string dans l'ordre."""
    return [c for c in df.columns if c.lower().startswith("ct_string")]


def compute_1a1b(df: pd.DataFrame, ct_cols: list[str], offset: int) -> pd.Series:
    """
    ct_string8 (index 7 dans ct_cols) + offset → 1B (GC / LEAP 1B)
    ct_string9 (index 8 dans ct_cols) + offset → 1A (GD / LEAP 1A)
    """
    idx_1b = 7 + offset   # ct_string8
    idx_1a = 8 + offset   # ct_string9

    def _flag(row):
        has_1b = (idx_1b < len(ct_cols) and
                  str(row.get(ct_cols[idx_1b], "")).strip().upper() == "O")
        has_1a = (idx_1a < len(ct_cols) and
                  str(row.get(ct_cols[idx_1a], "")).strip().upper() == "O")
        if has_1a and has_1b:
            return "1A+1B"
        if has_1a:
            return "1A"
        if has_1b:
            return "1B"
        return ""

    return df.apply(_flag, axis=1)


def main():
    # ── 1. Charger les exports appli ─────────────────────────────────
    app_frames = []
    for f in EXPORT_FILES:
        p = Path(f)
        if not p.exists():
            print(f"[WARN] Fichier introuvable, ignoré : {p}")
            continue
        print(f"  Chargement export appli : {p.name}")
        app_frames.append(pd.read_excel(p, dtype=str).fillna(""))

    if not app_frames:
        sys.exit("[ERREUR] Aucun export appli trouvé. Vérifier les chemins dans CONFIG.")

    df_app = pd.concat(app_frames, ignore_index=True)
    print(f"  → {len(df_app)} lignes chargées depuis les exports appli")

    # Colonnes attendues dans l'export appli
    keep_app = ["Marquage", "PN", "Réf constructeur", "Modules",
                "Statut", "N.Service 1", "N.Service 2", "N.Service 3", "N.Service 4"]
    missing = [c for c in keep_app if c not in df_app.columns]
    if missing:
        print(f"[WARN] Colonnes manquantes dans l'export appli : {missing}")
        for c in missing:
            df_app[c] = ""
    df_app = df_app[keep_app].copy()

    # ── 2. Charger le CSV DECA brut ──────────────────────────────────
    print(f"\n  Chargement CSV DECA brut : {Path(DECA_CSV).name}")
    df_raw = load_deca_csv(DECA_CSV)
    print(f"  → {len(df_raw)} lignes, {len(df_raw.columns)} colonnes")

    # Identifier la colonne marquage dans le CSV brut
    marq_col_raw = next(
        (c for c in df_raw.columns if "marquage" in c.lower()), None
    )
    if not marq_col_raw:
        sys.exit("[ERREUR] Colonne 'marquage' introuvable dans le CSV brut.")

    # Colonne etat (colonne AD = index 29, 0-based)
    all_cols = list(df_raw.columns)
    if len(all_cols) > 29:
        etat_col = all_cols[29]   # colonne AD
        print(f"  Colonne etat détectée : '{etat_col}' (position AD)")
    else:
        etat_col = next((c for c in all_cols if "etat" in c.lower()), None)
        print(f"  Colonne etat détectée par nom : '{etat_col}'")

    ct_cols = detect_ct_columns(df_raw)
    print(f"  Colonnes ct_string trouvées ({len(ct_cols)}) : {ct_cols}")

    if DIAGNOSTIC:
        print("\n══ DIAGNOSTIC ══════════════════════════════════════")
        if etat_col:
            print(f"\nValeurs uniques dans '{etat_col}' :")
            for v, n in df_raw[etat_col].value_counts().items():
                print(f"  {repr(v):30s}  {n}")
        print(f"\nColonnes ct_string (index 0-based) :")
        for i, c in enumerate(ct_cols):
            uniq = df_raw[c].value_counts().to_dict()
            print(f"  [{i:2d}] {c:15s}  {uniq}")
        print(f"\n→ Avec CT_OFFSET={CT_OFFSET} :")
        print(f"   1B = ct_cols[{7+CT_OFFSET}] = {ct_cols[7+CT_OFFSET] if 7+CT_OFFSET < len(ct_cols) else 'hors limites'}")
        print(f"   1A = ct_cols[{8+CT_OFFSET}] = {ct_cols[8+CT_OFFSET] if 8+CT_OFFSET < len(ct_cols) else 'hors limites'}")
        print("════════════════════════════════════════════════════\n")

    # ── 3. Extraire etat + 1A/1B depuis CSV brut ─────────────────────
    df_raw["_marquage"] = df_raw[marq_col_raw].str.strip().str.upper()
    df_raw["_etat"]     = df_raw[etat_col].str.strip() if etat_col else ""
    df_raw["_1a1b"]     = compute_1a1b(df_raw, ct_cols, CT_OFFSET)

    df_lookup = df_raw[["_marquage", "_etat", "_1a1b"]].drop_duplicates("_marquage")

    # ── 4. Jointure ──────────────────────────────────────────────────
    df_app["_marquage"] = df_app["Marquage"].str.strip().str.upper()
    df_out = df_app.merge(df_lookup, on="_marquage", how="left")
    df_out["Etat"]      = df_out["_etat"].fillna("")
    df_out["1A ou 1B"]  = df_out["_1a1b"].fillna("")
    df_out.drop(columns=["_marquage", "_etat", "_1a1b"], inplace=True)

    n_matched = df_out["Etat"].ne("").sum()
    print(f"  Jointure : {n_matched}/{len(df_out)} lignes matchées dans le CSV brut")

    # ── 5. Export Excel ──────────────────────────────────────────────
    final_cols = ["Marquage", "PN", "Réf constructeur", "Modules",
                  "Statut", "N.Service 1", "N.Service 2", "N.Service 3", "N.Service 4",
                  "Etat", "1A ou 1B"]
    out = Path(OUTPUT) if OUTPUT else Path(__file__).parent.parent / "extract_1a1b.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    df_out[final_cols].to_excel(out, index=False)
    print(f"\n✓ Export terminé → {out}")
    print(f"  {len(df_out)} lignes  ·  {df_out['1A ou 1B'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
