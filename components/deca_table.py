"""
Composant partagé — table read-only et formulaire de décision par DECA.
Utilisé par precheck.py et reunion.py.
"""
import pandas as pd
import streamlit as st

from db import queries
from services import svc3_options, svc1_for_svc3, svc4_options
from config import PRECHECK_FLAGS


# ── Constantes ────────────────────────────────────────────────────────────────

_SVC3_OPTS = [""] + svc3_options()
_SVC1_LABELS = {
    "SAESB LSO - B118 - ENGINE MX / REP": "B118 — LSO",
    "SAESB MF - B24 - MODULE MX / REP":   "B24 — MF",
}
_STATUS_PRECHECK = ["EN COURS", "PRÉ-CHECK"]
_STATUS_REUNION  = ["VALIDÉ", "EN ATTENTE"]
_PRECHECK_OPTS   = [""] + PRECHECK_FLAGS[:3]


# ── Table read-only ───────────────────────────────────────────────────────────

def render_readonly_table(active_df: pd.DataFrame, show_svc: bool = False, show_loc: bool = False):
    """Table st.dataframe read-only des infos outil."""
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
    st.dataframe(
        active_df[available].fillna(""),
        column_config=cfg,
        hide_index=True,
        use_container_width=True,
    )


# ── Formulaire de décision par DECA ──────────────────────────────────────────

def _form_key(marquage: str, field: str, key_prefix: str) -> str:
    return f"{key_prefix}_{marquage}_{field}"


def _init_form_state(marquage: str, dec: dict | None, key_prefix: str, mode: str):
    """Initialise les valeurs du formulaire depuis la DB si pas encore en session."""
    if mode == "reunion":
        dec_default = (dec["decision"] if dec else "VALIDÉ") if dec and dec["decision"] in _STATUS_REUNION else "VALIDÉ"
    else:
        dec_default = dec["decision"] if dec else "EN COURS"

    for field, default in [
        ("svc3", (dec["n_service3"] if dec else "") or ""),
        ("bldg", ""),
        ("svc4", (dec["n_service4"] if dec else "") or ""),
        ("pre",  (dec["pre_check"]  if dec else "") or ""),
        ("dec",  dec_default),
        ("comm", (dec["commentaire"] if dec else "") or ""),
    ]:
        k = _form_key(marquage, field, key_prefix)
        if k not in st.session_state:
            st.session_state[k] = default


def render_deca_form(row: dict, mode: str, key_prefix: str = "pc") -> dict:
    """
    Affiche le formulaire de décision pour un DECA.

    mode      : "precheck" ou "reunion"
    key_prefix: préfixe de session state ("pc" pour precheck, "reu" pour reunion)

    Retourne un dict avec les valeurs actuelles.
    """
    marquage = row["marquage"]
    dec = queries.get_decision(marquage)
    locked = bool(dec and dec["decision"] in ("VALIDÉ", "EN ATTENTE"))

    _init_form_state(marquage, dec, key_prefix, mode)

    with st.container(border=True):
        header_col, badge_col = st.columns([3, 1])
        header_col.markdown(f"**`{marquage}`** — {row.get('ref_constructeur','')}")
        if locked:
            badge_col.success(dec["decision"])
        elif dec and dec.get("decision") == "PRÉ-CHECK":
            badge_col.warning("Pré-check")
        else:
            badge_col.info("En cours")

        # En mode réunion : afficher le pré-check en lecture seule (même si non locked)
        pre_check_val = (dec["pre_check"] if dec else "") or ""
        if mode == "reunion" and pre_check_val:
            st.caption(f"Pré-check : **{pre_check_val}**")

        if locked:
            # Affichage read-only
            if mode == "reunion":
                c1, c2, c3 = st.columns(3)
                c1.markdown(f"**N.Service3** : {dec.get('n_service3') or '—'}")
                c2.markdown(f"**Bâtiment** : {_SVC1_LABELS.get(dec.get('n_service1',''), dec.get('n_service1','') or '—')}")
                c3.markdown(f"**N.Service4** : {dec.get('n_service4') or '—'}")
            else:
                c1, c2, c3, c4 = st.columns(4)
                c1.markdown(f"**N.Service3** : {dec.get('n_service3') or '—'}")
                c2.markdown(f"**Bâtiment** : {_SVC1_LABELS.get(dec.get('n_service1',''), dec.get('n_service1','') or '—')}")
                c3.markdown(f"**N.Service4** : {dec.get('n_service4') or '—'}")
                c4.markdown(f"**Commentaire** : {dec.get('commentaire') or '—'}")
            return {"marquage": marquage, "_locked": True,
                    "pre_check": pre_check_val if mode == "reunion" else (dec["pre_check"] if dec else "")}

        # ── Service 3 ─────────────────────────────────────────────────────────
        k_svc3 = _form_key(marquage, "svc3", key_prefix)
        svc3 = st.selectbox(
            "N.Service3",
            options=_SVC3_OPTS,
            key=k_svc3,
            disabled=locked,
        )

        # ── Dériver Service 1 ─────────────────────────────────────────────────
        svc1_candidates = svc1_for_svc3(svc3) if svc3 else []
        svc1 = ""

        if not svc3:
            st.caption("Sélectionner un Service3 pour voir le bâtiment.")
        elif len(svc1_candidates) == 1:
            svc1 = svc1_candidates[0]
            label = _SVC1_LABELS.get(svc1, svc1)
            st.info(f"Bâtiment : **{label}**", icon="🏭")
        else:
            # Service3 ambigu → l'utilisateur choisit le bâtiment
            k_bldg = _form_key(marquage, "bldg", key_prefix)
            bldg_options = [_SVC1_LABELS.get(s, s) for s in svc1_candidates]
            bldg_labels = {_SVC1_LABELS.get(s, s): s for s in svc1_candidates}
            chosen_label = st.radio(
                "Ce Service3 existe dans les 2 bâtiments — choisir :",
                options=bldg_options,
                key=k_bldg,
                horizontal=True,
            )
            svc1 = bldg_labels.get(chosen_label, "")

        # ── Service 4 (filtré par bâtiment) ───────────────────────────────────
        k_svc4 = _form_key(marquage, "svc4", key_prefix)
        svc4_opts = [""] + svc4_options(svc1, svc3) if svc1 else [""]
        current_svc4 = st.session_state.get(k_svc4, "")
        if current_svc4 and current_svc4 not in svc4_opts:
            svc4_opts = svc4_opts + [current_svc4]

        svc4 = st.selectbox(
            "N.Service4",
            options=svc4_opts,
            key=k_svc4,
            disabled=locked or not svc1,
        )

        # ── Pré-check + Décision + Commentaire ───────────────────────────────
        c1, c2, c3 = st.columns([1, 1, 3])

        if mode == "precheck":
            pre = c1.selectbox(
                "Pré-check",
                options=_PRECHECK_OPTS,
                key=_form_key(marquage, "pre", key_prefix),
                disabled=locked,
            )
            # Décision auto en precheck
            auto_dec = "PRÉ-CHECK" if svc3 else "EN COURS"
            c2.caption("Décision (auto)")
            c2.markdown(f"**{auto_dec}**")
            final_dec = auto_dec
        else:
            # En réunion : pré-check read-only
            pre = c1.selectbox(
                "Pré-check",
                options=_PRECHECK_OPTS,
                key=_form_key(marquage, "pre", key_prefix),
                disabled=True,
                help="Lecture seule en mode réunion",
            )
            final_dec = c2.selectbox(
                "Décision",
                options=_STATUS_REUNION,
                key=_form_key(marquage, "dec", key_prefix),
                disabled=locked,
            )

        comm = c3.text_input(
            "Commentaire",
            key=_form_key(marquage, "comm", key_prefix),
            disabled=locked,
        )

    return {
        "marquage": marquage,
        "svc3": svc3,
        "svc1": svc1,
        "svc4": svc4,
        "pre_check": pre if mode == "precheck" else pre_check_val,
        "decision": final_dec,
        "commentaire": comm,
        "_locked": locked,
    }
