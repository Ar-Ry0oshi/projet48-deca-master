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

    col_mod, col_assy, col_deca, col_warn = st.columns([3, 1.5, 1, 2])

    col_mod.markdown(f"**Modules** : {', '.join(modules) if modules else '—'}")

    col_assy.caption("**ASSY flag**")
    col_assy.caption(assy)

    col_deca.metric("DECAs", n_active)

    if n_modules > 1 and n_active < n_modules:
        col_warn.warning(f"⚠ {n_modules} modules, {n_active} DECAs")
    elif n_modules > 1:
        col_warn.info(f"ℹ {n_modules} modules")

    if mod_source == "conflict":
        st.caption(f"⚠️ Conflit sources — {conflict}")
    elif mod_source == "panoply_only":
        st.caption("Source : Panoply uniquement (absent du DMC)")
    elif mod_source == "esm_only":
        st.caption("Source : DMC/ESM uniquement (absent de Panoply)")

    if opcodes:
        with st.expander(f"ICV ({opcodes.count('|') + 1} code(s))", expanded=False):
            for part in opcodes.split(" | "):
                st.caption(part.strip())
