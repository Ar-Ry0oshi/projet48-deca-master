"""
Page Dashboard — avancement global par module.
Vue d'ensemble de la campagne DECA en un coup d'œil.
"""
import streamlit as st
import pandas as pd

from config import MODULES
from db import queries


def _get_all_stats() -> pd.DataFrame:
    rows = []
    for module in MODULES:
        s = queries.get_stats_for_module(module)
        total = s.get("total", 0)
        if total == 0:
            continue
        valide    = s.get("valide", 0)
        en_attente = s.get("en_attente", 0)
        precheck  = s.get("precheck", 0)
        en_cours  = s.get("en_cours", 0)
        traites   = valide + en_attente
        pct       = round(100 * traites / total) if total else 0
        rows.append({
            "Module":      module,
            "Total":       total,
            "Validé":      valide,
            "En attente":  en_attente,
            "Pré-check":   precheck,
            "En cours":    en_cours,
            "% traité":    pct,
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def render():
    st.title("Dashboard")

    df = _get_all_stats()

    if df.empty:
        st.info("Aucune donnée en base — rechargez les sources dans la page Données.")
        return

    # ── Métriques globales ────────────────────────────────────────────────────
    total_g    = df["Total"].sum()
    valide_g   = df["Validé"].sum()
    attente_g  = df["En attente"].sum()
    precheck_g = df["Pré-check"].sum()
    en_cours_g = df["En cours"].sum()
    traites_g  = valide_g + attente_g
    pct_g      = round(100 * traites_g / total_g) if total_g else 0

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Total DECAs",  total_g)
    c2.metric("Validés",      valide_g)
    c3.metric("En attente",   attente_g)
    c4.metric("Pré-check",    precheck_g)
    c5.metric("En cours",     en_cours_g)

    st.progress(pct_g / 100, text=f"**{pct_g}%** traités ({traites_g} / {total_g})")
    st.divider()

    # ── Tableau par module ────────────────────────────────────────────────────
    st.subheader("Avancement par module")

    col_cfg = {
        "Module":     st.column_config.TextColumn("Module", width="small"),
        "Total":      st.column_config.NumberColumn("Total", width="small"),
        "Validé":     st.column_config.NumberColumn("Validé ✅", width="small"),
        "En attente": st.column_config.NumberColumn("En attente ⏳", width="small"),
        "Pré-check":  st.column_config.NumberColumn("Pré-check 🔵", width="small"),
        "En cours":   st.column_config.NumberColumn("En cours ⚪", width="small"),
        "% traité":   st.column_config.ProgressColumn(
                          "% traité", min_value=0, max_value=100, format="%d%%", width="medium"
                      ),
    }

    st.dataframe(
        df,
        column_config=col_cfg,
        hide_index=True,
        width='stretch',
    )

    st.divider()

    # ── Barres par module ─────────────────────────────────────────────────────
    st.subheader("Progression détaillée")

    for _, row in df.iterrows():
        module = row["Module"]
        total  = row["Total"]
        if total == 0:
            continue

        col_lbl, col_bar = st.columns([1, 5])
        col_lbl.markdown(f"**{module}**")

        # Barre empilée simulée avec du texte coloré
        pct_v  = row["Validé"] / total
        pct_a  = row["En attente"] / total
        pct_p  = row["Pré-check"] / total
        pct_e  = row["En cours"] / total
        pct_done = pct_v + pct_a

        col_bar.progress(pct_done, text=(
            f"✅ {row['Validé']}  ⏳ {row['En attente']}  "
            f"🔵 {row['Pré-check']}  ⚪ {row['En cours']}"
        ))
