"""
Composant partagé — table read-only et éditeur de décisions par PN.
Utilisé par precheck.py et reunion.py.
"""
import pandas as pd
import streamlit as st

from db import queries
from services import svc3_options, svc1_for_svc3, svc4_options, svc1_to_svc4_all
from config import PRECHECK_FLAGS


# ── Constantes ────────────────────────────────────────────────────────────────

_SVC3_OPTS = [""] + svc3_options()

_BLDG_OPTS   = ["", "LSO", "MF"]
_BLDG_TO_SVC1 = {
    "LSO": "SAESB LSO - B118 - ENGINE MX / REP",
    "MF":  "SAESB MF - B24 - MODULE MX / REP",
}
_SVC1_TO_BLDG = {v: k for k, v in _BLDG_TO_SVC1.items()}

_STATUS_PRECHECK = ["EN COURS", "PRÉ-CHECK"]
_STATUS_REUNION  = ["VALIDÉ", "EN ATTENTE"]
_PRECHECK_OPTS   = [""] + PRECHECK_FLAGS[:3]


# ── Table read-only (cliquable) ───────────────────────────────────────────────

def render_readonly_table(
    active_df: pd.DataFrame,
    show_svc: bool = False,
    show_loc: bool = False,
    selectable: bool = False,
    key: str = "deca_tbl",
):
    """
    Table read-only des infos outil.
    Si selectable=True, cliquer sur une ligne ouvre la fiche détail.
    """
    from components.deca_detail import show_deca_detail

    if active_df.empty:
        return

    cols = ["marquage", "ref_constructeur"]
    cfg = {
        "marquage":         st.column_config.TextColumn("Marquage", width="small"),
        "ref_constructeur": st.column_config.TextColumn("Ref. constructeur", width="medium"),
    }
    if show_svc:
        for i in range(1, 6):
            k = f"service{i}"
            cols.append(k)
            cfg[k] = st.column_config.TextColumn(f"Svc {i}", width="small")
    if show_loc:
        for i in range(1, 4):
            k = f"localisation{i}"
            cols.append(k)
            cfg[k] = st.column_config.TextColumn(f"Loc {i}", width="small")

    available = [c for c in cols if c in active_df.columns]
    display_df = active_df[available].fillna("")

    if selectable:
        event = st.dataframe(
            display_df,
            column_config=cfg,
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            key=key,
        )
        rows = event.selection.rows if hasattr(event, "selection") else []
        if rows:
            marquage = active_df.iloc[rows[0]]["marquage"]
            show_deca_detail(marquage)
    else:
        st.dataframe(
            display_df,
            column_config=cfg,
            hide_index=True,
            use_container_width=True,
        )


# ── Éditeur de décisions sous forme de table ─────────────────────────────────

def render_deca_table_editor(
    active_df: pd.DataFrame,
    mode: str,
    key_prefix: str = "pc",
) -> list[dict]:
    """
    Affiche tous les DECAs d'un PN dans une table éditable compacte.
    Retourne une liste de dicts (même interface que l'ancienne boucle render_deca_form).

    mode : "precheck" ou "reunion"
    """
    from components.deca_detail import show_deca_detail

    if active_df.empty:
        return []

    svc4_all = sorted({s for lst in svc1_to_svc4_all().values() for s in lst})

    # ── Construire les lignes ─────────────────────────────────────────────────
    orig_locked: dict[str, bool] = {}
    rows = []
    for _, row in active_df.iterrows():
        marquage = row["marquage"]
        dec = queries.get_decision(marquage)
        dec = dict(dec) if dec else {}
        locked = dec.get("decision") in ("VALIDÉ", "EN ATTENTE")
        orig_locked[marquage] = locked

        svc1_full = dec.get("n_service1") or ""
        bldg = _SVC1_TO_BLDG.get(svc1_full, "")
        if not bldg and svc1_full:
            bldg = "LSO" if "LSO" in svc1_full else ("MF" if "MF" in svc1_full or "B24" in svc1_full else "")

        if mode == "reunion":
            dec_default = dec.get("decision") if dec.get("decision") in _STATUS_REUNION else "VALIDÉ"
        else:
            dec_default = dec.get("decision") if dec.get("decision") in _STATUS_PRECHECK else "EN COURS"

        label = f"🔒 {marquage}" if locked else marquage

        rows.append({
            "marquage":    label,
            "_raw_mq":     marquage,
            "ref":         (row.get("ref_constructeur") or "")[:25],
            "n_service3":  dec.get("n_service3") or "",
            "batiment":    bldg,
            "n_service4":  dec.get("n_service4") or "",
            "pre_check":   dec.get("pre_check") or "",
            "decision":    dec_default,
            "commentaire": dec.get("commentaire") or "",
        })

    df = pd.DataFrame(rows)

    # ── Boutons 🔍 par marquage ───────────────────────────────────────────────
    btn_cols = st.columns(len(rows))
    for i, r in enumerate(rows):
        if btn_cols[i].button(
            f"🔍 {r['_raw_mq']}",
            key=f"{key_prefix}_{r['_raw_mq']}_open_tbl",
            use_container_width=True,
        ):
            show_deca_detail(r["_raw_mq"])

    # ── Config colonnes selon mode ────────────────────────────────────────────
    if mode == "precheck":
        pre_cfg = st.column_config.SelectboxColumn(
            "Pré-check", options=_PRECHECK_OPTS, width="small"
        )
        disabled_cols = ["marquage", "ref", "decision"]
    else:
        pre_cfg = st.column_config.TextColumn(
            "Pré-check", disabled=True, width="small"
        )
        disabled_cols = ["marquage", "ref", "pre_check"]

    col_cfg = {
        "marquage":    st.column_config.TextColumn("Marquage", disabled=True, width="small"),
        "ref":         st.column_config.TextColumn("Référence", disabled=True, width="medium"),
        "n_service3":  st.column_config.SelectboxColumn(
                           "N.Service3", options=_SVC3_OPTS, width="large"
                       ),
        "batiment":    st.column_config.SelectboxColumn(
                           "Bât.", options=_BLDG_OPTS, width="small",
                           help="LSO = B118, MF = B24. Auto si Service3 non ambigu."
                       ),
        "n_service4":  st.column_config.SelectboxColumn(
                           "N.Service4", options=[""] + svc4_all, width="large"
                       ),
        "pre_check":   pre_cfg,
        "decision":    st.column_config.SelectboxColumn(
                           "Décision",
                           options=_STATUS_REUNION if mode == "reunion" else _STATUS_PRECHECK,
                           width="small",
                       ),
        "commentaire": st.column_config.TextColumn("Commentaire", width="large"),
    }

    display_cols = ["marquage", "ref", "n_service3", "batiment", "n_service4",
                    "pre_check", "decision", "commentaire"]

    edited = st.data_editor(
        df[display_cols],
        column_config=col_cfg,
        disabled=disabled_cols,
        hide_index=True,
        use_container_width=True,
        key=f"{key_prefix}_tbl_editor_{rows[0]['_raw_mq'] if rows else 'x'}",
        num_rows="fixed",
    )

    # ── Convertir en liste de dicts ───────────────────────────────────────────
    forms: list[dict] = []
    for i, (_, erow) in enumerate(edited.iterrows()):
        raw_mq  = rows[i]["_raw_mq"]
        locked  = orig_locked.get(raw_mq, False)
        svc3    = erow.get("n_service3") or ""
        bldg    = erow.get("batiment") or ""
        svc1    = _BLDG_TO_SVC1.get(bldg, "")
        if not svc1 and svc3:
            candidates = svc1_for_svc3(svc3)
            svc1 = candidates[0] if len(candidates) == 1 else ""

        decision = ("PRÉ-CHECK" if svc3 else "EN COURS") if mode == "precheck" else (erow.get("decision") or "VALIDÉ")

        forms.append({
            "marquage":    raw_mq,
            "svc3":        svc3,
            "svc1":        svc1,
            "svc4":        erow.get("n_service4") or "",
            "pre_check":   erow.get("pre_check") or "",
            "decision":    decision,
            "commentaire": erow.get("commentaire") or "",
            "_locked":     locked,
        })

    return forms


# ── Alias conservé pour rétro-compatibilité ───────────────────────────────────

def render_deca_form(row: dict, mode: str, key_prefix: str = "pc") -> dict:
    """Wrapper single-row — préférer render_deca_table_editor pour plusieurs DECAs."""
    import pandas as pd
    single_df = pd.DataFrame([row])
    forms = render_deca_table_editor(single_df, mode, key_prefix)
    return forms[0] if forms else {"marquage": row.get("marquage", ""), "_locked": False}
