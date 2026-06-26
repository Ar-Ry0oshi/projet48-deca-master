"""
Composant partagé — bandeau d'infos PN.
Utilisé par precheck.py et reunion.py.
"""
import pandas as pd
import streamlit as st


def render_pn_info(pn_short: str, active_df: pd.DataFrame):
    """Affiche modules, ASSY flag, nb DECAs actifs, source conflict, opcodes ICV."""
    if active_df.empty:
        return
    row = active_df.iloc[0]
    modules = [m.strip() for m in (row.get("modules_effective") or "").split(",") if m.strip()]
    assy = row.get("assy_flag") or "—"
    mod_source = row.get("module_source") or "none"
    conflict = row.get("module_conflict_detail") or ""
    opcodes = row.get("opcodes_translated") or ""
    n_active = len(active_df)
    n_modules = len(modules)

    chips = st.columns([1, 1, 1, 1, 3])
    chips[0].metric("Modules", ", ".join(modules) if modules else "—")
    chips[1].metric("ASSY flag", assy)
    chips[2].metric("DECAs actifs", n_active)
    if n_modules > 1 and n_active < n_modules:
        chips[3].warning(f"⚠ {n_modules} modules, {n_active} DECAs")
    elif n_modules > 1:
        chips[3].info(f"ℹ {n_modules} modules")
    else:
        chips[3].empty()

    if mod_source == "conflict":
        st.caption(f"⚠️ Conflit sources — {conflict}")
    elif mod_source == "panoply_only":
        st.caption("Source : Panoply uniquement (absent du DMC)")
    elif mod_source == "esm_only":
        st.caption("Source : DMC/ESM uniquement (absent de Panoply)")
    if opcodes:
        st.caption(f"ICV : {opcodes}")
