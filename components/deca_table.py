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

_BLDG_TO_SVC1 = {
    "LSO": "SAESB LSO - B118 - ENGINE MX / REP",
    "MF":  "SAESB MF - B24 - MODULE MX / REP",
}
_SVC1_TO_BLDG = {v: k for k, v in _BLDG_TO_SVC1.items()}

_STATUS_PRECHECK = ["EN COURS", "PRÉ-CHECK"]
_STATUS_REUNION  = ["VALIDÉ", "EN ATTENTE"]
_PRECHECK_OPTS   = [""] + PRECHECK_FLAGS[:3]

# Largeurs des colonnes (ligne info / ligne saisie)
_W_INFO  = [1.2, 2.5, 2.5, 2.0]          # Marquage | Réf | Svc3 actuel | État
_W_EDIT  = [0.7, 2.0, 2.0, 1.0, 1.0, 2.5] # Bât | N.Svc3 | N.Svc4 | Pre | Déc | Comm


# ── Table read-only (cliquable pour ouvrir fiche) ─────────────────────────────

def render_readonly_table(
    active_df: pd.DataFrame,
    show_svc: bool = False,
    show_loc: bool = False,
    selectable: bool = False,
    key: str = "deca_tbl",
):
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
            show_deca_detail(active_df.iloc[rows[0]]["marquage"])
    else:
        st.dataframe(display_df, column_config=cfg, hide_index=True, use_container_width=True)


# ── Éditeur de décisions (2 lignes par DECA) ─────────────────────────────────

def render_deca_table_editor(
    active_df: pd.DataFrame,
    mode: str,
    key_prefix: str = "pc",
) -> list[dict]:
    """
    Affiche tous les DECAs d'un PN en 2 lignes par DECA :
      - Ligne 1 (info) : [🔍 Marquage] | Référence | Svc3 actuel | État
      - Ligne 2 (edit) : Bât (auto) | N.Service3 | N.Service4 | Pré-check | Décision | Commentaire
    Retourne une liste de dicts pour les fonctions de sauvegarde.
    """
    from components.deca_detail import show_deca_detail

    if active_df.empty:
        return []

    svc4_all = sorted({s for lst in svc1_to_svc4_all().values() for s in lst})

    # ── Ouvrir fiche : une seule fois par run pour éviter le duplicate ID ────
    detail_key = f"{key_prefix}_detail_open"
    if detail_key in st.session_state and st.session_state[detail_key]:
        mq_to_open = st.session_state[detail_key]
        st.session_state[detail_key] = None
        show_deca_detail(mq_to_open)

    # ── En-têtes ─────────────────────────────────────────────────────────────
    h1 = st.columns(_W_INFO)
    for col, lbl in zip(h1, ["Marquage", "Référence", "Svc3 actuel", "État"]):
        col.caption(f"**{lbl}**")
    h2 = st.columns(_W_EDIT)
    for col, lbl in zip(h2, ["Bât.", "N.Service3", "N.Service4", "Pré-check", "Décision", "Commentaire"]):
        col.caption(f"**{lbl}**")
    st.markdown('<hr style="margin:2px 0 6px 0; border-color:#ccc;">', unsafe_allow_html=True)

    forms: list[dict] = []

    for i, (_, row) in enumerate(active_df.iterrows()):
        marquage = row["marquage"]
        dec = queries.get_decision(marquage)
        dec = dict(dec) if dec else {}
        locked = dec.get("decision") in ("VALIDÉ", "EN ATTENTE")
        svc1_saved = dec.get("n_service1") or ""

        # ── Ligne 1 : infos ──────────────────────────────────────────────────
        r1 = st.columns(_W_INFO)
        if r1[0].button(
            f"🔍 {'🔒 ' if locked else ''}{marquage}",
            key=f"{key_prefix}_{marquage}_open",
            use_container_width=True,
        ):
            st.session_state[detail_key] = marquage
            st.rerun()
        r1[1].markdown(f"*{(row.get('ref_constructeur') or '—')[:30]}*")
        r1[2].caption(row.get("service3") or "—")
        r1[3].caption(row.get("etat") or "—")

        # ── Ligne 2 : saisie / affichage ─────────────────────────────────────
        r2 = st.columns(_W_EDIT)

        if locked:
            bldg = _SVC1_TO_BLDG.get(svc1_saved, "—")
            r2[0].markdown(f"**{bldg}**")
            r2[1].markdown(dec.get("n_service3") or "—")
            r2[2].markdown(dec.get("n_service4") or "—")
            r2[3].markdown(dec.get("pre_check") or "—")
            r2[4].success(dec.get("decision") or "—")
            r2[5].markdown(dec.get("commentaire") or "—")
            forms.append({
                "marquage":    marquage,
                "_locked":     True,
                "svc3":        dec.get("n_service3") or "",
                "svc1":        svc1_saved,
                "svc4":        dec.get("n_service4") or "",
                "pre_check":   dec.get("pre_check") or "",
                "decision":    dec.get("decision") or "",
                "commentaire": dec.get("commentaire") or "",
            })

        else:
            k_svc3 = f"{key_prefix}_{marquage}_svc3"
            k_svc4 = f"{key_prefix}_{marquage}_svc4"
            k_pre  = f"{key_prefix}_{marquage}_pre"
            k_dec  = f"{key_prefix}_{marquage}_dec"
            k_comm = f"{key_prefix}_{marquage}_comm"
            k_bldg = f"{key_prefix}_{marquage}_bldg"

            # Init session state depuis DB
            if k_svc3 not in st.session_state:
                st.session_state[k_svc3] = dec.get("n_service3") or ""
            if k_svc4 not in st.session_state:
                st.session_state[k_svc4] = dec.get("n_service4") or ""
            if k_pre not in st.session_state:
                st.session_state[k_pre] = dec.get("pre_check") or ""
            if k_comm not in st.session_state:
                st.session_state[k_comm] = dec.get("commentaire") or ""
            if k_dec not in st.session_state:
                opts = _STATUS_REUNION if mode == "reunion" else _STATUS_PRECHECK
                saved_dec = dec.get("decision")
                st.session_state[k_dec] = saved_dec if saved_dec in opts else opts[0]

            # N.Service3
            svc3 = r2[1].selectbox(
                "N.Service3", _SVC3_OPTS, key=k_svc3, label_visibility="collapsed"
            )

            # Bâtiment auto-dérivé
            svc1_candidates = svc1_for_svc3(svc3) if svc3 else []
            svc1 = ""

            if not svc3:
                r2[0].caption("—")
            elif len(svc1_candidates) == 1:
                svc1 = svc1_candidates[0]
                bldg = _SVC1_TO_BLDG.get(svc1, "?")
                r2[0].markdown(f"**{bldg}**")
            else:
                # Service3 ambigu (50 cas) : mini selectbox bâtiment
                bldg_opts = [_SVC1_TO_BLDG.get(s, s) for s in svc1_candidates]
                bldg_map  = {_SVC1_TO_BLDG.get(s, s): s for s in svc1_candidates}
                chosen = r2[0].selectbox(
                    "Bât.⚠", bldg_opts, key=k_bldg, label_visibility="collapsed",
                    help="Service3 présent dans les 2 bâtiments — choisir"
                )
                svc1 = bldg_map.get(chosen, "")

            # N.Service4 (filtré si bâtiment connu)
            svc4_opts = ([""] + svc4_options(svc1, svc3)) if svc1 else ([""] + svc4_all)
            cur_svc4 = st.session_state.get(k_svc4, "")
            if cur_svc4 and cur_svc4 not in svc4_opts:
                svc4_opts = svc4_opts + [cur_svc4]

            svc4 = r2[2].selectbox(
                "N.Service4", svc4_opts, key=k_svc4,
                label_visibility="collapsed",
                disabled=(bool(svc3) and not svc1),
            )

            # Pré-check / Décision / Commentaire
            if mode == "precheck":
                pre = r2[3].selectbox(
                    "Pré-check", _PRECHECK_OPTS, key=k_pre, label_visibility="collapsed"
                )
                final_dec = "PRÉ-CHECK" if svc3 else "EN COURS"
                r2[4].markdown(f"**{final_dec}**")
            else:
                r2[3].caption(dec.get("pre_check") or "—")
                final_dec = r2[4].selectbox(
                    "Décision", _STATUS_REUNION, key=k_dec, label_visibility="collapsed"
                )
                pre = dec.get("pre_check") or ""

            comm = r2[5].text_input(
                "Commentaire", key=k_comm, label_visibility="collapsed"
            )

            forms.append({
                "marquage":    marquage,
                "_locked":     False,
                "svc3":        svc3,
                "svc1":        svc1,
                "svc4":        svc4,
                "pre_check":   pre,
                "decision":    final_dec,
                "commentaire": comm,
            })

        # Séparateur léger entre DECAs
        if i < len(active_df) - 1:
            st.markdown(
                '<hr style="margin:4px 0; border:none; border-top:1px solid #e0e0e0;">',
                unsafe_allow_html=True,
            )

    return forms


# ── Alias rétro-compatibilité ─────────────────────────────────────────────────

def render_deca_form(row: dict, mode: str, key_prefix: str = "pc") -> dict:
    single_df = pd.DataFrame([row])
    forms = render_deca_table_editor(single_df, mode, key_prefix)
    return forms[0] if forms else {"marquage": row.get("marquage", ""), "_locked": False}
