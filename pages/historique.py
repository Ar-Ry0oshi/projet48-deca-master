"""
Page Historique — journal global des modifications, filtrable.
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta

from config import MODULES
from db import db


def _load_changelog(
    module: str | None = None,
    marquage: str | None = None,
    since_days: int | None = None,
) -> pd.DataFrame:
    conditions = []
    params: list = []

    if module:
        conditions.append("c.marquage IN (SELECT marquage FROM tools WHERE modules_effective LIKE ?)")
        params.append(f"%{module}%")

    if marquage:
        conditions.append("c.marquage LIKE ?")
        params.append(f"%{marquage.strip().upper()}%")

    if since_days:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=since_days)).isoformat()
        conditions.append("c.changed_at >= ?")
        params.append(cutoff)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    rows = db.fetchall(f"""
        SELECT
            c.changed_at,
            c.marquage,
            c.pn_short,
            c.field_changed,
            c.old_value,
            c.new_value,
            c.changed_by
        FROM changelog c
        {where}
        ORDER BY c.changed_at DESC
        LIMIT 2000
    """, tuple(params))

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame([dict(r) for r in rows])
    df["changed_at"] = pd.to_datetime(df["changed_at"], utc=True, errors="coerce")
    df["changed_at"] = df["changed_at"].dt.strftime("%d/%m/%Y %H:%M")
    return df


def render():
    st.title("Historique")

    # ── Filtres ───────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns([1.5, 1.5, 1.5, 1])

    module_sel = c1.selectbox(
        "Module",
        options=["Tous"] + MODULES,
        key="hist_module",
    )
    module = None if module_sel == "Tous" else module_sel

    marquage_sel = c2.text_input(
        "Marquage",
        placeholder="06019…",
        key="hist_marquage",
    ).strip() or None

    period_label = c3.selectbox(
        "Période",
        options=["Tout", "7 derniers jours", "30 derniers jours", "Aujourd'hui"],
        key="hist_period",
    )
    since_days = {"Tout": None, "7 derniers jours": 7, "30 derniers jours": 30, "Aujourd'hui": 1}[period_label]

    c4.markdown("&nbsp;")
    refresh = c4.button("🔄 Actualiser", use_container_width=True)

    st.divider()

    # ── Données ───────────────────────────────────────────────────────────────
    df = _load_changelog(module=module, marquage=marquage_sel, since_days=since_days)

    if df.empty:
        st.info("Aucune modification trouvée pour ces filtres.")
        return

    st.caption(f"{len(df)} entrée(s) — {'' if len(df) < 2000 else 'limité à 2000, affiner les filtres'}")

    st.dataframe(
        df,
        column_config={
            "changed_at":   st.column_config.TextColumn("Date", width="medium"),
            "marquage":     st.column_config.TextColumn("Marquage", width="small"),
            "pn_short":     st.column_config.TextColumn("PN", width="small"),
            "field_changed":st.column_config.TextColumn("Champ", width="small"),
            "old_value":    st.column_config.TextColumn("Ancienne valeur", width="medium"),
            "new_value":    st.column_config.TextColumn("Nouvelle valeur", width="medium"),
            "changed_by":   st.column_config.TextColumn("Par", width="small"),
        },
        hide_index=True,
        use_container_width=True,
    )

    # ── Export CSV ────────────────────────────────────────────────────────────
    csv = df.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        label="Télécharger (.csv)",
        data=csv,
        file_name=f"historique_DECA_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )
