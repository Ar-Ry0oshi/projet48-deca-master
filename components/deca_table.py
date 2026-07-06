"""
Composant partagé — table read-only et éditeur de décisions par PN.
Utilisé par precheck.py et reunion.py.
"""
import pandas as pd
import streamlit as st

from db import queries
from services import (
    svc1_for_svc3, svc3_labeled_options, svc3_label, svc3_from_label,
    svc4_labeled_options, svc4_label, svc4_from_label,
)
from config import PRECHECK_FLAGS


# ── Constantes ────────────────────────────────────────────────────────────────

_SVC3_OPTS  = svc3_labeled_options()   # ['', 'LSO — ...', 'MF — ...']
_SVC4_OPTS  = svc4_labeled_options()   # ['', 'LSO — ...', 'MF — ...']

_SVC1_TO_BLDG = {
    "SAESB LSO - B118 - ENGINE MX / REP": "LSO",
    "SAESB MF - B24 - MODULE MX / REP":   "MF",
}

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
            width='stretch',
            on_select="rerun",
            selection_mode="single-row",
            key=key,
        )
        rows = event.selection.rows if hasattr(event, "selection") else []
        if rows:
            show_deca_detail(active_df.iloc[rows[0]]["marquage"])
    else:
        st.dataframe(display_df, column_config=cfg, hide_index=True, width='stretch')


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

    # ── Ouvrir fiche : une seule fois par run pour éviter le duplicate ID ────
    detail_key = f"{key_prefix}_detail_open"
    if detail_key in st.session_state and st.session_state[detail_key]:
        mq_to_open = st.session_state[detail_key]
        st.session_state[detail_key] = None
        all_mqs = active_df["marquage"].tolist()
        show_deca_detail(mq_to_open, marquages=all_mqs)

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
            dec_val = dec.get("decision") or ""
            if dec_val not in _STATUS_REUNION:
                # EN COURS ou vide = déverrouillé/non traité → EN ATTENTE par défaut
                dec_val = "EN ATTENTE"

        svc1_saved = dec.get("n_service1") or ""
        cur_svc3 = row.get("service3") or ""
        cur_svc4 = row.get("service4") or ""

        # Valeur DB → label affiché (préfixé bâtiment)
        n_svc3_plain = dec.get("n_service3") or ""
        n_svc4_plain = dec.get("n_service4") or ""

        if n_svc3_plain and svc1_saved:
            n_svc3_display = svc3_label(n_svc3_plain, svc1_saved)
        elif n_svc3_plain:
            # Fallback : chercher le bâtiment depuis les mappings
            s1l = svc1_for_svc3(n_svc3_plain)
            n_svc3_display = svc3_label(n_svc3_plain, s1l[0]) if s1l else n_svc3_plain
        else:
            n_svc3_display = ""

        if n_svc4_plain and svc1_saved:
            n_svc4_display = svc4_label(n_svc4_plain, svc1_saved)
        else:
            n_svc4_display = n_svc4_plain

        # Pré-remplir depuis la source si aucune décision en DB
        if not dec:
            if cur_svc3:
                s1l = svc1_for_svc3(cur_svc3)
                svc1_saved = s1l[0] if s1l else ""
                n_svc3_display = svc3_label(cur_svc3, svc1_saved) if svc1_saved else cur_svc3
            if cur_svc4 and svc1_saved:
                n_svc4_display = svc4_label(cur_svc4, svc1_saved)
            elif cur_svc4:
                n_svc4_display = cur_svc4

        # ◈ = aucun service connu → à traiter ; sinon → déjà rempli (en bas)
        needs_treatment = not cur_svc3 and not n_svc3_plain and not locked

        if locked:
            mq_display = f"🔒 {marquage}"
        elif needs_treatment:
            mq_display = f"◈ {marquage}"
        else:
            mq_display = marquage

        meta.append({
            "marquage":        marquage,
            "locked":          locked,
            "needs_treatment": needs_treatment,
            "cur_svc3":        cur_svc3,
            "svc1_saved":      svc1_saved,
            "pre_saved":       dec.get("pre_check") or "",
        })

        row_dict = {
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
            "N.Service3":  n_svc3_display,
            "N.Service4":  n_svc4_display,
            "Pré-check":   dec.get("pre_check") or "",
            "Commentaire": dec.get("commentaire") or "",
        }
        if mode != "precheck":
            row_dict["Décision"] = dec_val
        display_rows.append(row_dict)

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
                  "Loc 1", "Loc 2", "Loc 3", "Loc 4", "Loc 5"]

    if mode != "precheck":
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
        "N.Service3":  st.column_config.SelectboxColumn(
                           "N.Service3 ✏", options=_SVC3_OPTS, required=False, width="large"
                       ),
        "N.Service4":  st.column_config.SelectboxColumn(
                           "N.Service4 ✏", options=_SVC4_OPTS, required=False, width="large"
                       ),
        "Pré-check":   st.column_config.SelectboxColumn(
                           "Pré-check ✏", options=_PRECHECK_OPTS, required=False, width="small"
                       ) if mode == "precheck" else st.column_config.TextColumn(
                           "Pré-check", disabled=True, width="small"
                       ),
        "Décision":    st.column_config.SelectboxColumn(
                           "Décision ✏", options=_STATUS_REUNION, required=True, width="small"
                       ),
        "Commentaire": st.column_config.TextColumn("Commentaire ✏", width="large"),
    }

    edited = st.data_editor(
        df,
        column_config=cfg,
        disabled=fixed_cols,
        hide_index=True,
        width='stretch',
        key=editor_key,
        num_rows="fixed",
    )

    # ── Bouton "Voir détail" — chips cliquables + dropdown recherche ──────────
    real_marquages = sorted([m["marquage"] for m in meta])

    # Chips cliquables (st.pills) — clic direct ouvre la fiche
    # On passe par une clé "pending" pour ne jamais écrire dans la clé widget après instantiation
    pills_pending_key = f"{key_prefix}_pills_pending_{pn_key}"
    if st.session_state.get(pills_pending_key):
        st.session_state[detail_key] = st.session_state[pills_pending_key]
        st.session_state[pills_pending_key] = None
        st.rerun()

    clicked = st.pills(
        "Ouvrir fiche",
        real_marquages,
        selection_mode="single",
        key=f"{key_prefix}_pills_{pn_key}",
        label_visibility="collapsed",
    )
    if clicked:
        st.session_state[pills_pending_key] = clicked
        st.rerun()

    # Dropdown de recherche + bouton ouvrir (pour chercher rapidement par frappe)
    col_sel, col_btn, _ = st.columns([2, 1, 5])
    selected_mq = col_sel.selectbox(
        "Rechercher", real_marquages,
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
            forms.append({
                "marquage":    m["marquage"],
                "_locked":     True,
                "svc3":        "",
                "svc1":        m["svc1_saved"],
                "svc4":        "",
                "pre_check":   m["pre_saved"],
                "decision":    erow["Décision"] if mode != "precheck" else "EN COURS",
                "commentaire": erow["Commentaire"] or "",
            })
        else:
            # Extraire svc3 plain + svc1 depuis le label "MF — SM53 ASSY..."
            svc3_lbl = erow["N.Service3"] or ""
            svc3, svc1 = svc3_from_label(svc3_lbl)
            svc4 = svc4_from_label(erow["N.Service4"] or "")

            if mode == "precheck":
                final_dec = "EN COURS"   # precheck ne touche jamais la colonne décision
                pre = erow["Pré-check"] or ""
            else:
                final_dec = erow["Décision"] or "VALIDÉ"
                pre = m["pre_saved"]

            forms.append({
                "marquage":    m["marquage"],
                "_locked":     False,
                "svc3":        svc3,
                "svc1":        svc1,
                "svc4":        svc4,
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
