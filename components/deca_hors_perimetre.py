"""
Composant partagé — section « Hors périmètre ».
Utilisé par precheck.py et reunion.py.
"""
import pandas as pd
import streamlit as st


def render_excluded(excluded_df: pd.DataFrame):
    """Affiche les DECAs hors périmètre dans un expander."""
    if excluded_df.empty:
        return
    with st.expander(f"Hors périmètre — même PN ({len(excluded_df)} DECAs)", expanded=False):
        display_cols = [c for c in [
            "marquage", "ref_constructeur", "exclusion_reason",
            "service1", "service2", "service3", "etat",
        ] if c in excluded_df.columns]
        st.dataframe(excluded_df[display_cols], hide_index=True, width='stretch')
