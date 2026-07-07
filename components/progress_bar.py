"""Barre de progression bicolore : pré-check (orange) + validé (vert)."""
import streamlit as st


def render_progress_bar(stats: dict):
    """
    Affiche une barre bicolore à partir d'un dict get_stats_for_module().
    Orange = pré-check fait (pre_check renseigné, pas encore validé en réunion)
    Vert   = validé ou en attente (décision finale prise)
    """
    total = stats.get("total") or 0
    if not total:
        return

    valide    = stats.get("valide", 0) + stats.get("en_attente", 0)
    precheck  = stats.get("precheck", 0)
    en_cours  = max(0, total - valide - precheck)

    pct_v  = valide   / total
    pct_p  = precheck / total
    pct_e  = en_cours / total

    pct_v_pct  = round(pct_v  * 100)
    pct_p_pct  = round(pct_p  * 100)

    st.caption(
        f"**{valide}** validé/attente · "
        f"**{precheck}** pré-check · "
        f"**{en_cours}** en cours "
        f"— {pct_v_pct}% finalisé · {pct_v_pct + pct_p_pct}% pré-checké"
    )

    # Barre HTML bicolore — gris prend le reste via flex:1 pour éviter les gaps d'arrondi
    bar_html = f"""
    <div style="
        display:flex; height:10px; border-radius:5px; overflow:hidden;
        background:#e0e0e0; margin-bottom:8px;
    ">
        <div style="width:{pct_v*100:.2f}%; background:#21c354; flex-shrink:0;"></div>
        <div style="width:{pct_p*100:.2f}%; background:#f0a500; flex-shrink:0;"></div>
        <div style="flex:1; background:#e0e0e0;"></div>
    </div>
    <div style="display:flex; gap:16px; font-size:0.75em; margin-bottom:4px;">
        <span><span style="color:#21c354;">■</span> Validé/Attente ({valide})</span>
        <span><span style="color:#f0a500;">■</span> Pré-check ({precheck})</span>
        <span><span style="color:#aaa;">■</span> En cours ({en_cours})</span>
    </div>
    """
    st.markdown(bar_html, unsafe_allow_html=True)
