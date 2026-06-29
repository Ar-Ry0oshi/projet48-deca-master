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
        for i in range(1, 6):
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


# ── Éditeur de décisions — tableau Excel-like ─────────────────────────────────

def render_deca_table_editor(
    active_df: pd.DataFrame,
    mode: str,
    key_prefix: str = "pc",
) -> list[dict]:
    """
    Affiche les DECAs d'un PN dans un data_editor avec :
      - Colonnes info (read-only) : Marquage | Svc3 act. | Svc4 act. | Svc5 act. | Loc 1-5
      - Colonnes saisie (edit)    : N.Service3 | Bât. | N.Service4 | Pré-check | Décision | Commentaire
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

    # ── Construire les lignes ─────────────────────────────────────────────────
    meta: list[dict] = []   # métadonnées non affichées
    display_rows: list[dict] = []

    for _, row in active_df.iterrows():
        marquage = row["marquage"]
        dec = queries.get_decision(marquage)
        dec = dict(dec) if dec else {}
        locked = dec.get("decision") in ("VALIDÉ", "EN ATTENTE")

        if mode == "precheck":
            dec_val = dec.get("decision") or "EN COURS"
            if dec_val not in _STATUS_PRECHECK:
                dec_val = "EN COURS"
        else:
            dec_val = dec.get("decision") or "VALIDÉ"
            if dec_val not in _STATUS_REUNION:
                dec_val = "VALIDÉ"

        # Bâtiment affiché depuis décision sauvegardée
        svc1_saved = dec.get("n_service1") or ""
        bldg_saved = _SVC1_TO_BLDG.get(svc1_saved, "")

        cur_svc3 = row.get("service3") or ""
        cur_svc4 = row.get("service4") or ""

        # Pré-remplir N.Service3/4 avec les services actuels si aucune décision prise
        n_svc3_init = dec.get("n_service3") or ""
        n_svc4_init = dec.get("n_service4") or ""
        if not dec:
            if cur_svc3:
                n_svc3_init = cur_svc3
                svc1_for_init = svc1_for_svc3(cur_svc3)
                if svc1_for_init:
                    svc1_saved = svc1_for_init[0]
                    bldg_saved = _SVC1_TO_BLDG.get(svc1_saved, "")
            if cur_svc4:
                n_svc4_init = cur_svc4

        # DECA sans nouveau service = à traiter (◈), avec service = déjà fait (en bas)
        has_new_svc = bool(n_svc3_init and dec)   # décision existante avec svc3
        needs_treatment = not has_new_svc and not locked

        if locked:
            mq_display = f"🔒 {marquage}"
        elif needs_treatment:
            mq_display = f"◈ {marquage}"   # à traiter en priorité
        else:
            mq_display = marquage           # déjà rempli → ira en bas

        meta.append({
            "marquage":        marquage,
            "locked":          locked,
            "needs_treatment": needs_treatment,
            "cur_svc3":        cur_svc3,
            "svc1_saved":      svc1_saved,
            "pre_saved":       dec.get("pre_check") or "",
        })

        display_rows.append({
            "_sort":       0 if needs_treatment else (2 if locked else 1),
            "Marquage":    mq_display,
            "Svc 3 act.":  cur_svc3,
            "Svc 4 act.":  cur_svc4,
            "Svc 5 act.":  row.get("service5") or "",
            "Loc 1":       row.get("localisation1") or "",
            "Loc 2":       row.get("localisation2") or "",
            "Loc 3":       row.get("localisation3") or "",
            "Loc 4":       row.get("localisation4") or "",
            "Loc 5":       row.get("localisation5") or "",
            "Bât.":        bldg_saved,
            "N.Service3":  n_svc3_init,
            "N.Service4":  n_svc4_init,
            "Pré-check":   dec.get("pre_check") or "",
            "Décision":    dec_val,
            "Commentaire": dec.get("commentaire") or "",
        })

    # ── Tri : à traiter (◈) en haut, déjà fait au milieu, verrouillés en bas ──
    combined = sorted(zip(display_rows, meta), key=lambda x: x[0]["_sort"])
    display_rows = [d for d, _ in combined]
    meta         = [m for _, m in combined]

    display_cols = [c for c in display_rows[0] if c != "_sort"]
    df = pd.DataFrame(display_rows)[display_cols]

    # Clé stable par PN (évite que les edits d'un PN contaminent le suivant)
    pn_key = active_df["pn_short"].iloc[0] if "pn_short" in active_df.columns else "x"
    editor_key = f"{key_prefix}_editor_{pn_key}"

    # ── Légende indicateurs ───────────────────────────────────────────────────
    n_todo = sum(1 for m in meta if m["needs_treatment"])
    n_done = sum(1 for m in meta if not m["needs_treatment"] and not m["locked"])
    parts = []
    if n_todo:
        parts.append(f"◈ {n_todo} à traiter")
    if n_done:
        parts.append(f"{n_done} déjà remplis (en bas, N.Svc3/4 pré-remplis depuis source)")
    if parts:
        st.caption(" · ".join(parts))

    # ── Colonnes figées (read-only) ───────────────────────────────────────────
    fixed_cols = ["Marquage", "Svc 3 act.", "Svc 4 act.", "Svc 5 act.",
                  "Loc 1", "Loc 2", "Loc 3", "Loc 4", "Loc 5", "Bât."]

    # En mode precheck : Décision est calculée auto ; en réunion : Pré-check est figé
    if mode == "precheck":
        fixed_cols.append("Décision")
    else:
        fixed_cols.append("Pré-check")

    # ── Config colonnes ───────────────────────────────────────────────────────
    cfg = {
        "Marquage":    st.column_config.TextColumn("Marquage",    disabled=True, width="small"),
        "Svc 3 act.":  st.column_config.TextColumn("Svc 3 act.", disabled=True, width="small"),
        "Svc 4 act.":  st.column_config.TextColumn("Svc 4 act.", disabled=True, width="small"),
        "Svc 5 act.":  st.column_config.TextColumn("Svc 5 act.", disabled=True, width="small"),
        "Loc 1":       st.column_config.TextColumn("Loc 1",      disabled=True, width="small"),
        "Loc 2":       st.column_config.TextColumn("Loc 2",      disabled=True, width="small"),
        "Loc 3":       st.column_config.TextColumn("Loc 3",      disabled=True, width="small"),
        "Loc 4":       st.column_config.TextColumn("Loc 4",      disabled=True, width="small"),
        "Loc 5":       st.column_config.TextColumn("Loc 5",      disabled=True, width="small"),
        "Bât.":        st.column_config.TextColumn("Bât.",       disabled=True, width="small"),
        "N.Service3":  st.column_config.SelectboxColumn(
                           "N.Service3 ✏", options=_SVC3_OPTS, required=False, width="medium"
                       ),
        "N.Service4":  st.column_config.SelectboxColumn(
                           "N.Service4 ✏", options=[""] + svc4_all, required=False, width="medium"
                       ),
        "Pré-check":   st.column_config.SelectboxColumn(
                           "Pré-check ✏", options=_PRECHECK_OPTS, required=False, width="small"
                       ) if mode == "precheck" else st.column_config.TextColumn(
                           "Pré-check", disabled=True, width="small"
                       ),
        "Décision":    st.column_config.TextColumn(
                           "Décision", disabled=True, width="small"
                       ) if mode == "precheck" else st.column_config.SelectboxColumn(
                           "Décision ✏", options=_STATUS_REUNION, required=True, width="small"
                       ),
        "Commentaire": st.column_config.TextColumn("Commentaire ✏", width="large"),
    }

    edited = st.data_editor(
        df,
        column_config=cfg,
        disabled=fixed_cols,
        hide_index=True,
        use_container_width=True,
        key=editor_key,
        num_rows="fixed",
    )

    # ── Bouton "Voir détail" sous le tableau ──────────────────────────────────
    real_marquages = [m["marquage"] for m in meta]
    col_sel, col_btn, _ = st.columns([2, 1, 5])
    selected_mq = col_sel.selectbox(
        "Voir détail", real_marquages,
        key=f"{key_prefix}_detail_sel_{pn_key}",
        label_visibility="collapsed",
    )
    if col_btn.button("🔍 Ouvrir", key=f"{key_prefix}_detail_btn_{pn_key}", use_container_width=True):
        st.session_state[detail_key] = selected_mq
        st.rerun()

    # ── Construire la liste forms depuis edited ───────────────────────────────
    forms: list[dict] = []
    for i, (_, erow) in enumerate(edited.iterrows()):
        m = meta[i]
        locked = m["locked"]

        if locked:
            # Ignorer les édits sur les lignes verrouillées
            forms.append({
                "marquage":    m["marquage"],
                "_locked":     True,
                "svc3":        "",
                "svc1":        m["svc1_saved"],
                "svc4":        "",
                "pre_check":   m["pre_saved"],
                "decision":    erow["Décision"],
                "commentaire": erow["Commentaire"] or "",
            })
        else:
            svc3 = erow["N.Service3"] or ""
            svc1_candidates = svc1_for_svc3(svc3) if svc3 else []
            # En cas d'ambiguïté, prendre le premier (LSO avant MF)
            svc1 = svc1_candidates[0] if svc1_candidates else ""

            if mode == "precheck":
                final_dec = "PRÉ-CHECK" if svc3 else "EN COURS"
                pre = erow["Pré-check"] or ""
            else:
                final_dec = erow["Décision"] or "VALIDÉ"
                pre = m["pre_saved"]

            forms.append({
                "marquage":    m["marquage"],
                "_locked":     False,
                "svc3":        svc3,
                "svc1":        svc1,
                "svc4":        erow["N.Service4"] or "",
                "pre_check":   pre,
                "decision":    final_dec,
                "commentaire": erow["Commentaire"] or "",
            })

    return forms


# ── Alias rétro-compatibilité ─────────────────────────────────────────────────

def render_deca_form(row: dict, mode: str, key_prefix: str = "pc") -> dict:
    single_df = pd.DataFrame([row])
    forms = render_deca_table_editor(single_df, mode, key_prefix)
    return forms[0] if forms else {"marquage": row.get("marquage", ""), "_locked": False}
