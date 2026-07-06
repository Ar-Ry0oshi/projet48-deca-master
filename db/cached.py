"""Streamlit-cached wrappers for heavy DB queries."""
import streamlit as st
from . import queries


@st.cache_data(ttl=60, show_spinner=False)
def get_tools_for_module(module: str, include_excluded: bool = False) -> list[dict]:
    return [dict(r) for r in queries.get_tools_for_module(module, include_excluded)]
