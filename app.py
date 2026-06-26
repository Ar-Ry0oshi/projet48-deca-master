import sys
from pathlib import Path

# Vendor folder — librairies locales, pas besoin de pip install
_vendor = Path(__file__).parent / "vendor"
if _vendor.exists() and str(_vendor) not in sys.path:
    sys.path.insert(0, str(_vendor))

import streamlit as st
from db.db import init_schema

st.set_page_config(
    page_title="DECA_Master",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_schema()

# Masque la navigation automatique Streamlit multipage (on utilise le radio ci-dessous)
st.markdown("""
<style>
[data-testid="stSidebarNav"] { display: none; }
</style>
""", unsafe_allow_html=True)

# ── Sidebar navigation ────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### DECA_Master")
    st.caption("PSO Tooling — SAESB")
    st.divider()

    page = st.radio(
        "Navigation",
        ["Dashboard", "Pré-check", "Réunion", "Données", "Historique"],
        label_visibility="collapsed",
    )
    st.divider()
    st.caption("Safran Aircraft Engine Services Brussels")

# ── Page routing ──────────────────────────────────────────────────────────────
if page == "Dashboard":
    from pages.dashboard import render
    render()
elif page == "Pré-check":
    from pages.precheck import render
    render()
elif page == "Réunion":
    from pages.reunion import render
    render()
elif page == "Données":
    from pages.data_management import render
    render()
elif page == "Historique":
    from pages.historique import render
    render()
