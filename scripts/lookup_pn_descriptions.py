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
    # "PN-123456",
    # "PN-789012",
    # ...  colle tes PNs ici, un par ligne entre guillemets
]

# Chemin vers l'extract ESM (.xlsx)
ESM_PATH = Path(r"C:\chemin\vers\ton\fichier_ESM.xlsx")

# Chemin vers l'extract DECA (.csv ou .xlsx) — pour le comptage
DECA_PATH = Path(r"C:\chemin\vers\ton\fichier_DECA.csv")

# ── SCRIPT ────────────────────────────────────────────────────────────────────

def load_esm(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    engine = "xlrd" if suffix == ".xls" else "openpyxl"
    try:
        df = pd.read_excel(path, dtype=str, engine=engine).fillna("")
    except Exception:
        # Dernier recours : laisser pandas choisir
        df = pd.read_excel(path, dtype=str, engine="xlrd").fillna("")
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
