"""
Composant partagé — bandeau d'infos PN.
Utilisé par precheck.py et reunion.py.
"""
import pandas as pd
import streamlit as st

# Nb moteurs par module (WIP document)
_MOTEURS: dict[str, int] = {
    "MM01": 4,  "MM02": 49,  "MM03": 57,
    "SM21": 43, "SM22": 43,  "SM23": 0,  "SM24": 11, "SM61": 24,
    "SM30": 109,"SM31": 109, "SM32": 109,
    "SM41": 45,
    "SM51": 45, "SM52": 243, "SM53": 219,"SM54": 45, "SM55": 6,
    "SM56": 18, "SM57": 15,  "SM58": 36, "SM59": 32,
}


def render_pn_info(pn_short: str, active_df: pd.DataFrame):
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

    # ── Ligne principale ──────────────────────────────────────────────────────
    col_mod, col_assy, col_deca, col_warn = st.columns([4, 1.5, 0.8, 2])
    col_mod.markdown(f"<small><b>Modules :</b> {', '.join(modules) if modules else '—'}</small>",
                     unsafe_allow_html=True)
    col_assy.markdown(f"<small><b>ASSY</b><br>{assy}</small>", unsafe_allow_html=True)
    col_deca.metric("DECAs", n_active)
    if n_modules > 1 and n_active < n_modules:
        col_warn.warning(f"⚠ {n_modules} modules, {n_active} DECAs")
    elif n_modules > 1:
        col_warn.info(f"ℹ {n_modules} modules")

    if mod_source == "conflict":
        st.caption(f"⚠️ Conflit sources — {conflict}")
    elif mod_source == "panoply_only":
        st.caption("Source : Panoply uniquement")
    elif mod_source == "esm_only":
        st.caption("Source : DMC/ESM uniquement")

    # ── ICV (gauche) + Moteurs (droite) ──────────────────────────────────────
    mot_rows = [(m, _MOTEURS.get(m, 0)) for m in modules if m in _MOTEURS]
    show_motors = bool(mot_rows)
    show_icv = bool(opcodes)

    if show_icv or show_motors:
        col_icv, col_mot = st.columns([3, 2])

        if show_icv:
            with col_icv:
                st.caption("**Codes ICV**")
                for part in opcodes.split(" | "):
                    st.caption(f"• {part.strip()}")

        if show_motors:
            total = sum(n for _, n in mot_rows)
            df_mot = pd.DataFrame([
                {"Module": m, "Nb": n, "%": f"{100*n/total:.0f}%" if total else "—"}
                for m, n in mot_rows
            ])
            with col_mot:
                st.dataframe(
                    df_mot,
                    column_config={
                        "Module": st.column_config.TextColumn("Module", width="small"),
                        "Nb":     st.column_config.NumberColumn("Nb",   width="small"),
                        "%":      st.column_config.TextColumn("%",      width="small"),
                    },
                    hide_index=True,
                    use_container_width=True,
                )
