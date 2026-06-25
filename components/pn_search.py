"""
Composant recherche PN — utilisable depuis precheck et reunion.
Quand le PN trouvé couvre plusieurs modules, propose un picker avant de naviguer.

Usage:
    from components.pn_search import pn_search_widget
    result = pn_search_widget()
    if result:
        # result = {"pn_short": ..., "module": ..., "complexity_flag": ...}
        st.session_state["nav_pn"] = result["pn_short"]
        st.session_state["nav_module"] = result["module"]
        st.rerun()
"""
import streamlit as st
from db.queries import search_pn
from config import COMPLEXITY_FLAGS


_COMPLEXITY_LABELS = {
    "unique":       "1 DECA · 1 module",
    "multi_deca":   "N DECAs · 1 module",
    "multi_module": "N modules",
    "no_match":     "Aucun module",
}

_COMPLEXITY_COLORS = {
    "unique":       "🟢",
    "multi_deca":   "🟡",
    "multi_module": "🟠",
    "no_match":     "🔴",
}


def pn_search_widget(key_prefix: str = "search") -> dict | None:
    """
    Renders an inline PN search box.
    Returns a dict {pn_short, module, complexity_flag, deca_active}
    when the user has picked a result, else None.
    """
    query = st.text_input(
        "Rechercher un PN",
        key=f"{key_prefix}_query",
        placeholder="956A1309…",
        label_visibility="collapsed",
    )

    if not query or len(query.strip()) < 3:
        return None

    results = search_pn(query.strip())

    if not results:
        st.caption("Aucun PN trouvé.")
        return None

    st.caption(f"{len(results)} résultat(s)")

    for row in results:
        pn = row["pn_short"]
        modules_str = row["modules_effective"] or ""
        modules = [m.strip() for m in modules_str.split(",") if m.strip()]
        flag = row["complexity_flag"] or "no_match"
        deca_active = row["deca_active"] or 0
        source = row["module_source"] or "none"
        conflict = row["module_conflict_detail"]

        icon = _COMPLEXITY_COLORS.get(flag, "⚪")
        label = _COMPLEXITY_LABELS.get(flag, flag)

        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"**`{pn}`** &nbsp; {icon} {label}")
                if modules:
                    st.caption(f"Modules : {', '.join(modules)}  ·  {deca_active} DECA(s) actif(s)")
                else:
                    st.caption(f"{deca_active} DECA(s) actif(s) — pas de module associé")

                if source == "conflict" and conflict:
                    st.caption(f"⚠️ Conflit sources — {conflict}")
                elif source == "panoply_only":
                    st.caption("Source : Panoply uniquement")
                elif source == "esm_only":
                    st.caption("Source : ESM/DMC uniquement")

            with c2:
                if flag == "no_match" or not modules:
                    if st.button("Ouvrir", key=f"{key_prefix}_open_{pn}", disabled=True):
                        pass
                    st.caption("Pas de module")
                elif len(modules) == 1:
                    if st.button("Ouvrir →", key=f"{key_prefix}_open_{pn}", type="primary"):
                        return {"pn_short": pn, "module": modules[0], "complexity_flag": flag, "deca_active": deca_active}
                else:
                    # Multi-module: propose a picker inline
                    chosen = st.selectbox(
                        "Module",
                        options=modules,
                        key=f"{key_prefix}_mod_{pn}",
                        label_visibility="collapsed",
                    )
                    if st.button("Ouvrir →", key=f"{key_prefix}_open_{pn}", type="primary"):
                        return {"pn_short": pn, "module": chosen, "complexity_flag": flag, "deca_active": deca_active}

    return None
