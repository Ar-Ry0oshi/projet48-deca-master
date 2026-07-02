"""
Lookup descriptions ESM + comptage DECA pour une liste de PNs.

Usage :
    python scripts/lookup_pn_descriptions.py

Renseigne les 3 variables ci-dessous avant de lancer.
"""
from pathlib import Path
import pandas as pd

# ── À CONFIGURER ──────────────────────────────────────────────────────────────

# Liste de PNs à rechercher
PNS = [
"956A1022",
"956A1034",
"956A1036",
"956A1076",
"956A1077",
"956A1120",
"956A1142",
"956A1161",
"956A1176",
"956A1178",
"956A1192",
"956A1238",
"956A1254",
"956A1297",
"956A1323",
"956A1529",
"956A1563",
"956A1611",
"956A1639",
"956A1803",
"956A1810",
"956A1812",
"956A1816",
"956A3022",
"956A3029",
"956A3034",
"956A3037",
"956A3074",
"956A3122",
"956A3173",
"956A3177",
"956A3249",
"956A3323",
"956A3512",
"956A3543",
"956A3549",
"956A3559",
"956A3562",
"956A3567",
"956A3805",
"956A3809",
"956A3810",
"956A6077",
"956A6086",
"956A6146",
"956A6341",
"956A6343",
"956A6433",
"956A6460",
"956A6518",
"956A6536",
"956A6552",
"956A6605",
"956A6627",
"956A6645",
"956A6647",
"956A6848",
"956A6849",
"956A6869",
"956A7006",
"956A7304",
"956A7332",
"956A7409",
"956A7410",
"956A7622",
"956A7644",
"956A7646",
"956A8056",
"956A8305",
"956A8325",
"956A8330",
"956A8478",
"956A8600",
"956A8814",
"956A8840",
"956A8841",
"956A8869",
]

# Chemin vers l'extract ESM (.xlsx)
ESM_PATH = Path(r"C:\Users\sat90930\Downloads\export lk (1).csv")

# Chemin vers l'extract DECA (.csv ou .xlsx) — pour le comptage
DECA_PATH = Path(r"U:\DIR_TECH\01 - PSO\3 - Tooling\01 - Projet\48 - DECA standardisation\Standardisation Service\01_DATA_SOURCES\DECA_Extracts\CSV\Extract_DECA_29-Jun.csv")

# ── SCRIPT ────────────────────────────────────────────────────────────────────

def load_esm(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, dtype=str).fillna("")
    df.columns = df.columns.str.strip()
    return df


def load_deca(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, dtype=str).fillna("")
    else:
        import chardet
        raw = path.read_bytes()
        enc = chardet.detect(raw)["encoding"] or "utf-8"
        sep = ";" if b";" in raw[:2000] else ","
        df = pd.read_csv(path, dtype=str, encoding=enc, sep=sep).fillna("")
    df.columns = df.columns.str.strip()
    return df


def main():
    if not PNS:
        print("⚠  Ajoute des PNs dans la variable PNS du script.")
        return

    # ── Chargement ESM ────────────────────────────────────────────────────────
    print(f"Chargement ESM : {ESM_PATH.name} …")
    esm = load_esm(ESM_PATH)

    # Détection colonne PN dans l'ESM
    pn_col_esm = next((c for c in esm.columns if "PART" in c.upper() and "NUM" in c.upper()), None)
    desc_col   = next((c for c in esm.columns if "DESIGN" in c.upper()), None)
    if not pn_col_esm or not desc_col:
        print(f"Colonnes détectées : {list(esm.columns)}")
        print("❌ Impossible de trouver les colonnes PART NUMBER / DESIGNATION dans l'ESM.")
        return

    print(f"  → colonnes ESM utilisées : '{pn_col_esm}' (PN) · '{desc_col}' (description)")

    # ── Chargement DECA ───────────────────────────────────────────────────────
    print(f"Chargement DECA : {DECA_PATH.name} …")
    deca = load_deca(DECA_PATH)

    pn_col_deca = next(
        (c for c in deca.columns if c.upper() in ("PART NUMBER", "PART_NUMBER", "PN", "P/N", "PARTNUMBER")),
        None,
    )
    if not pn_col_deca:
        # fallback : chercher une colonne qui ressemble
        pn_col_deca = next((c for c in deca.columns if "PART" in c.upper()), None)
    if not pn_col_deca:
        print(f"Colonnes DECA détectées : {list(deca.columns)}")
        print("❌ Impossible de trouver la colonne PN dans le DECA. Ajuste pn_col_deca manuellement.")
        return

    print(f"  → colonne DECA utilisée : '{pn_col_deca}'")

    # Comptage occurrences dans DECA
    deca_counts = deca[pn_col_deca].str.strip().value_counts()

    # ── Résultats ─────────────────────────────────────────────────────────────
    rows = []
    for pn in PNS:
        pn = pn.strip()
        # Cherche dans ESM (première occurrence)
        match = esm[esm[pn_col_esm].str.strip() == pn]
        if match.empty:
            # Essai sans sensibilité casse
            match = esm[esm[pn_col_esm].str.strip().str.upper() == pn.upper()]

        description = match.iloc[0][desc_col] if not match.empty else "— NON TROUVÉ —"
        count_deca  = int(deca_counts.get(pn, 0))

        rows.append({
            "PN":           pn,
            "Description":  description,
            "Nb dans DECA": count_deca,
        })

    result = pd.DataFrame(rows)

    # ── Affichage ─────────────────────────────────────────────────────────────
    print("\n" + "="*80)
    print(result.to_string(index=False))
    print("="*80)

    # Export Excel optionnel
    out = Path("pn_descriptions_result.xlsx")
    result.to_excel(out, index=False)
    print(f"\n✅ Résultat exporté dans : {out.resolve()}")


if __name__ == "__main__":
    main()
