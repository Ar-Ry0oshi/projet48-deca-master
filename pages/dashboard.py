"""
Page Dashboard — avancement global par module.
Vue d'ensemble de la campagne DECA en un coup d'œil.
"""
import streamlit as st
import pandas as pd

from config import MODULES
from db import queries


_COMPLEXITY_WEIGHTS = {
    "n_deca":          0.20,   # volume pur
    "n_pn":            0.15,   # nb PN distincts
    "n_complex":       0.35,   # cas non-uniques (débat nécessaire)
    "n_svc3_distinct": 0.15,   # éventail service3
    "n_svc4_internal": 0.15,   # éventail service4 hors stockage externe (décisions débattables)
}

def _get_complexity_df() -> pd.DataFrame:
    rows = []
    for module in MODULES:
        c = queries.get_complexity_stats_for_module(module)
        if not c or c.get("n_deca", 0) == 0:
            continue
        s = queries.get_stats_for_module(module)
        traites = s.get("valide", 0) + s.get("en_attente", 0)
        restant = max(0, c["n_deca"] - traites)
        rows.append({
            "Module":          module,
            "DECAs restants":  restant,
            "PN":              c["n_pn"],
            "Cas complexes":   c["n_complex"],
            "Svc3 ≠":          c["n_svc3_distinct"],
            "Svc4 int. ≠":     c["n_svc4_internal"],
            "Stockage ext.":   c["n_ext_storage"],
            "_n_deca":         c["n_deca"],
            "_n_pn":           c["n_pn"],
            "_n_complex":      c["n_complex"],
            "_n_svc3":         c["n_svc3_distinct"],
            "_n_svc4i":        c["n_svc4_internal"],
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Normalise chaque facteur [0-1] sur le max du jeu
    for col in ("_n_deca", "_n_pn", "_n_complex", "_n_svc3", "_n_svc4i"):
        mx = df[col].max() or 1
        df[col] = df[col] / mx
    df["_score"] = (
        df["_n_deca"]   * _COMPLEXITY_WEIGHTS["n_deca"] +
        df["_n_pn"]     * _COMPLEXITY_WEIGHTS["n_pn"] +
        df["_n_complex"]* _COMPLEXITY_WEIGHTS["n_complex"] +
        df["_n_svc3"]   * _COMPLEXITY_WEIGHTS["n_svc3_distinct"] +
        df["_n_svc4i"]  * _COMPLEXITY_WEIGHTS["n_svc4_internal"]
    )
    df["Score"] = (df["_score"] * 4 + 1).round(1)
    df["Complexité"] = df["Score"].apply(
        lambda s: "★★★★★" if s >= 4.5 else
                  "★★★★☆" if s >= 3.5 else
                  "★★★☆☆" if s >= 2.5 else
                  "★★☆☆☆" if s >= 1.5 else "★☆☆☆☆"
    )
    return (df[["Module","DECAs restants","PN","Cas complexes","Svc3 ≠","Svc4 int. ≠","Stockage ext.","Score","Complexité"]]
              .sort_values("Score", ascending=False)
              .reset_index(drop=True))


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

    from components.progress_bar import render_progress_bar
    render_progress_bar({"total": total_g, "valide": valide_g, "en_attente": attente_g, "precheck": precheck_g})
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

    # ── Score de complexité ───────────────────────────────────────────────────
    st.subheader("Charge estimée par module")
    st.caption(
        "Score basé sur : volume DECAs · nb PN · cas non-uniques (multi-DECA / multi-module) · "
        "éventail de services. Trié du plus chargé au plus simple. "
        "Seuls les modules avec DECAs restants à traiter sont affichés."
    )

    df_cx = _get_complexity_df()
    df_cx_restant = df_cx[df_cx["DECAs restants"] > 0]
    if not df_cx_restant.empty:
        st.dataframe(
            df_cx_restant,
            hide_index=True,
            width="stretch",
            column_config={
                "Module":          st.column_config.TextColumn("Module", width="small"),
                "DECAs restants":  st.column_config.NumberColumn("Restants", width="small"),
                "PN":              st.column_config.NumberColumn("PN", width="small"),
                "Cas complexes":   st.column_config.NumberColumn("Cas complexes", width="small"),
                "Svc3 ≠":         st.column_config.NumberColumn("Svc3 ≠", width="small"),
                "Svc4 int. ≠":    st.column_config.NumberColumn("Svc4 ≠ (int.)", width="small",
                                      help="Nb de service4 internes distincts (hors stockage externe)"),
                "Stockage ext.":   st.column_config.NumberColumn("Stk ext.", width="small",
                                      help="DECAs vers Zoersel / Expeditors — décisions simples"),
                "Score":           st.column_config.NumberColumn("Score /5", width="small", format="%.1f"),
                "Complexité":      st.column_config.TextColumn("Complexité", width="medium"),
            },
        )
        # Top 3 modules les plus chargés
        top3 = df_cx_restant.head(3)["Module"].tolist()
        st.caption(f"Modules prioritaires (charge estimée la plus élevée) : **{'  ·  '.join(top3)}**")
    else:
        st.success("Tous les modules sont traités !")

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
        with col_bar:
            from components.progress_bar import render_progress_bar
            render_progress_bar({
                "total":      total,
                "valide":     row["Validé"],
                "en_attente": row["En attente"],
                "precheck":   row["Pré-check"],
            })
