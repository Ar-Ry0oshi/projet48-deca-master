"""
Page Pré-check — traitement PN par PN, mode solo.
Deux vues :
  - Navigation PN  : pour les multi-DECA et multi-module (1 PN à la fois)
  - Liste plate    : pour les uniques (tous les PNs d'un module dans une table)
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timezone

from config import MODULES, SERVICE_CASCADE, PRECHECK_FLAGS, ROW_COLORS
from db import queries
from components.pn_search import pn_search_widget


# ── Constantes ────────────────────────────────────────────────────────────────

SERVICE3_OPTIONS = [""] + MODULES + ["LSO"]
SERVICE4_OPTIONS = ["", "ASSY", "DISASSY", "ASSY AND DISASSY"]

_STATUS_PRECHECK = ["EN COURS", "PRÉ-CHECK"]   # statuts disponibles en pré-check
_STATUS_REUNION  = ["VALIDÉ", "EN ATTENTE"]     # statuts disponibles en réunion

COL_CURRENT_SVC = ["service1", "service2", "service3", "service4", "service5"]
COL_CURRENT_LOC = ["localisation1", "localisation2", "localisation3", "localisation4", "localisation5"]


# ── Session state helpers ─────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "precheck_module":   MODULES[0],
        "precheck_pn_idx":   0,
        "precheck_pn":       None,
        "precheck_view":     "nav",        # "nav" | "flat"
        "precheck_show_svc": True,
        "precheck_show_loc": False,
        "precheck_mode":     "precheck",   # "precheck" | "reunion"
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _go_to_pn(pn_short: str, module: str):
    pns = queries.get_pn_list_for_module(module)
    st.session_state["precheck_module"] = module
    if pn_short in pns:
        st.session_state["precheck_pn_idx"] = pns.index(pn_short)
    st.session_state["precheck_pn"] = pn_short


# ── Cascade service ───────────────────────────────────────────────────────────

def _cascade(svc3: str) -> tuple[str, str]:
    """Returns (service1, service2) from service3."""
    key = svc3.strip().upper() if svc3 else ""
    svc1, svc2 = SERVICE_CASCADE.get(key, ("", ""))
    return svc1, svc2


# ── Chargement des DECAs pour un PN ──────────────────────────────────────────

def _load_deca_rows(pn_short: str, module: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (active_df, excluded_df) for the given PN."""
    all_rows = queries.get_tools_for_module(module, include_excluded=True)
    pn_rows  = [r for r in all_rows if r["pn_short"] == pn_short]

    active   = [dict(r) for r in pn_rows if not r["is_excluded"]]
    excluded = [dict(r) for r in pn_rows if r["is_excluded"]]

    # Also fetch excluded from other modules (same PN)
    other_excl = queries.get_excluded_for_pn(pn_short)
    excl_marquages = {r["marquage"] for r in excluded}
    for r in other_excl:
        if r["marquage"] not in excl_marquages:
            excluded.append(dict(r))

    return pd.DataFrame(active), pd.DataFrame(excluded)


# ── Sauvegarde d'une ligne ────────────────────────────────────────────────────

def _save_row(row: dict, pn_short: str, module: str, mode: str):
    svc3 = row.get("n_service3") or ""
    svc4 = row.get("n_service4") or ""
    svc1, svc2 = _cascade(svc3)
    pre  = row.get("pre_check") or None
    comm = row.get("commentaire") or None

    # Déterminer le statut
    existing = queries.get_decision(row["marquage"])
    if existing and existing["decision"] in ("VALIDÉ", "EN ATTENTE"):
        return  # jamais écraser un statut définitif

    if mode == "reunion":
        decision = row.get("decision") or "VALIDÉ"
    else:
        decision = "PRÉ-CHECK" if svc3 else "EN COURS"

    queries.upsert_decision(
        marquage       = row["marquage"],
        pn_short       = pn_short,
        module_context = module,
        n_service1     = svc1 or None,
        n_service2     = svc2 or None,
        n_service3     = svc3 or None,
        n_service4     = svc4 or None,
        pre_check      = pre,
        decision       = decision,
        commentaire    = comm,
        updated_by     = "user",
    )


# ── Vérification avant passage au suivant ─────────────────────────────────────

def _pn_is_complete(edited_df: pd.DataFrame, mode: str) -> tuple[bool, str]:
    """Returns (ok, message)."""
    if edited_df.empty:
        return True, ""
    missing_svc3 = edited_df[edited_df["n_service3"].isna() | (edited_df["n_service3"] == "")]
    if not missing_svc3.empty:
        marks = ", ".join(missing_svc3["marquage"].tolist())
        return False, f"N.Service3 manquant sur : {marks}"
    if mode == "reunion":
        missing_dec = edited_df[~edited_df["decision"].isin(["VALIDÉ", "EN ATTENTE"])]
        if not missing_dec.empty:
            marks = ", ".join(missing_dec["marquage"].tolist())
            return False, f"Décision manquante (doit être Validé ou En attente) sur : {marks}"
    return True, ""


# ── Bandeau infos PN ──────────────────────────────────────────────────────────

def _render_pn_info(pn_short: str, active_df: pd.DataFrame):
    if active_df.empty:
        return
    row = active_df.iloc[0]
    modules_eff = row.get("modules_effective") or ""
    modules     = [m.strip() for m in modules_eff.split(",") if m.strip()]
    assy        = row.get("assy_flag") or "—"
    mod_source  = row.get("module_source") or "none"
    conflict    = row.get("module_conflict_detail") or ""
    opcodes     = row.get("opcodes_translated") or ""
    n_active    = len(active_df)
    n_modules   = len(modules)

    chips = st.columns([1, 1, 1, 1, 3])
    chips[0].metric("Modules", ", ".join(modules) if modules else "—")
    chips[1].metric("ASSY flag", assy)
    chips[2].metric("DECAs actifs", n_active)
    if n_modules > 1 and n_active < n_modules:
        chips[3].warning(f"⚠ {n_modules} modules, {n_active} DECAs", icon=None)
    elif n_modules > 1:
        chips[3].info(f"ℹ {n_modules} modules", icon=None)
    else:
        chips[3].empty()

    if mod_source == "conflict":
        st.caption(f"⚠️ Conflit sources — {conflict}")
    elif mod_source == "panoply_only":
        st.caption("Source : Panoply uniquement (absent du DMC)")
    elif mod_source == "esm_only":
        st.caption("Source : DMC/ESM uniquement (absent de Panoply)")

    if opcodes:
        st.caption(f"ICV : {opcodes}")


# ── Table principale (st.data_editor) ────────────────────────────────────────

def _build_editor_df(active_df: pd.DataFrame) -> pd.DataFrame:
    """Merge tool data with existing decisions into an editable dataframe."""
    if active_df.empty:
        return pd.DataFrame()

    rows = []
    for _, r in active_df.iterrows():
        dec = queries.get_decision(r["marquage"])
        rows.append({
            "marquage":        r["marquage"],
            "ref_constructeur": r.get("ref_constructeur") or "",
            "service1":        r.get("service1") or "",
            "service2":        r.get("service2") or "",
            "service3":        r.get("service3") or "",
            "service4":        r.get("service4") or "",
            "service5":        r.get("service5") or "",
            "localisation1":   r.get("localisation1") or "",
            "localisation2":   r.get("localisation2") or "",
            "localisation3":   r.get("localisation3") or "",
            "n_service3":      (dec["n_service3"] if dec else "") or "",
            "n_service4":      (dec["n_service4"] if dec else "") or "",
            "pre_check":       (dec["pre_check"] if dec else "") or "",
            "decision":        (dec["decision"] if dec else "EN COURS"),
            "commentaire":     (dec["commentaire"] if dec else "") or "",
            "_locked":         bool(dec and dec["decision"] in ("VALIDÉ", "EN ATTENTE")),
        })
    return pd.DataFrame(rows)


def _render_deca_table(
    pn_short: str,
    active_df: pd.DataFrame,
    mode: str,
    show_svc: bool,
    show_loc: bool,
    table_key: str,
) -> pd.DataFrame | None:
    """Renders the data_editor and returns the edited dataframe or None."""
    if active_df.empty:
        st.info("Aucun DECA actif pour ce PN dans ce module.")
        return None

    editor_df = _build_editor_df(active_df)

    # Column config
    col_cfg = {
        "marquage":         st.column_config.TextColumn("Marquage", disabled=True, width="small"),
        "ref_constructeur": st.column_config.TextColumn("Ref. constructeur", disabled=True, width="medium"),
        "service1":         st.column_config.TextColumn("Svc 1", disabled=True, width="small"),
        "service2":         st.column_config.TextColumn("Svc 2", disabled=True, width="small"),
        "service3":         st.column_config.TextColumn("Svc 3", disabled=True, width="small"),
        "service4":         st.column_config.TextColumn("Svc 4", disabled=True, width="small"),
        "service5":         st.column_config.TextColumn("Svc 5", disabled=True, width="small"),
        "localisation1":    st.column_config.TextColumn("Loc 1", disabled=True, width="small"),
        "localisation2":    st.column_config.TextColumn("Loc 2", disabled=True, width="small"),
        "localisation3":    st.column_config.TextColumn("Loc 3", disabled=True, width="small"),
        "n_service3":       st.column_config.SelectboxColumn(
                                "N.Service3 ✏", options=SERVICE3_OPTIONS, required=False, width="small"
                            ),
        "n_service4":       st.column_config.SelectboxColumn(
                                "N.Service4 ✏", options=SERVICE4_OPTIONS, required=False, width="small"
                            ),
        "pre_check":        st.column_config.SelectboxColumn(
                                "Pré-check", options=[""] + PRECHECK_FLAGS[:3], required=False, width="small"
                            ),
        "decision":         st.column_config.SelectboxColumn(
                                "Décision",
                                options=(_STATUS_REUNION if mode == "reunion" else _STATUS_PRECHECK),
                                required=True,
                                width="small",
                            ),
        "commentaire":      st.column_config.TextColumn("Commentaire", width="large"),
        "_locked":          None,  # hidden
    }

    # Columns to hide
    hidden = ["_locked"]
    if not show_svc:
        hidden += ["service1", "service2", "service3", "service4", "service5"]
    if not show_loc:
        hidden += ["localisation1", "localisation2", "localisation3"]

    col_order = [c for c in [
        "marquage", "ref_constructeur",
        "service1", "service2", "service3", "service4", "service5",
        "localisation1", "localisation2", "localisation3",
        "n_service3", "n_service4", "pre_check", "decision", "commentaire",
    ] if c not in hidden]

    disabled_rows = editor_df["_locked"].tolist()
    disabled_cols = ["marquage", "ref_constructeur",
                     "service1","service2","service3","service4","service5",
                     "localisation1","localisation2","localisation3"]

    edited = st.data_editor(
        editor_df[col_order + ["_locked"]],
        column_config=col_cfg,
        column_order=col_order,
        disabled=disabled_cols,
        hide_index=True,
        use_container_width=True,
        key=table_key,
        num_rows="fixed",
    )
    return edited


# ── Copie service vers toutes les lignes ──────────────────────────────────────

def _render_copy_toolbar(edited: pd.DataFrame | None, pn_short: str, module: str, mode: str):
    """Bouton 'Copier ligne 1 → toutes' pour les multi-DECA."""
    if edited is None or len(edited) <= 1:
        return

    col1, col2, col3 = st.columns([2, 2, 4])
    if col1.button("⬇ Copier Svc3 & Svc4 vers toutes les lignes", use_container_width=True):
        first = edited.iloc[0]
        svc3 = first.get("n_service3") or ""
        svc4 = first.get("n_service4") or ""
        for _, row in edited.iterrows():
            _save_row({**dict(row), "n_service3": svc3, "n_service4": svc4},
                      pn_short, module, mode)
        st.success(f"Service3={svc3} / Service4={svc4} appliqué à {len(edited)} DECAs.")
        st.rerun()

    if col2.button("✓ Valider toutes les lignes", use_container_width=True):
        for _, row in edited.iterrows():
            _save_row(dict(row), pn_short, module, "reunion")
        st.success(f"{len(edited)} DECAs validés.")
        st.rerun()


# ── Vue hors-périmètre ────────────────────────────────────────────────────────

def _render_excluded(excluded_df: pd.DataFrame):
    if excluded_df.empty:
        return
    with st.expander(f"Hors périmètre — même PN ({len(excluded_df)} DECAs)", expanded=False):
        display_cols = [c for c in [
            "marquage", "ref_constructeur", "exclusion_reason",
            "service1", "service2", "service3", "etat",
        ] if c in excluded_df.columns]
        st.dataframe(
            excluded_df[display_cols],
            hide_index=True,
            use_container_width=True,
            column_config={
                "marquage":         st.column_config.TextColumn("Marquage"),
                "ref_constructeur": st.column_config.TextColumn("Ref."),
                "exclusion_reason": st.column_config.TextColumn("Raison exclusion"),
                "service1":         st.column_config.TextColumn("Svc 1"),
                "service2":         st.column_config.TextColumn("Svc 2"),
                "service3":         st.column_config.TextColumn("Svc 3"),
                "etat":             st.column_config.TextColumn("État"),
            },
        )


# ── Vue navigation PN ─────────────────────────────────────────────────────────

def _render_nav_view(module: str, mode: str):
    pns = queries.get_pn_list_for_module(module)
    if not pns:
        st.info(f"Aucun PN actif sur {module}.")
        return

    # Sync pn from search
    if st.session_state.get("precheck_pn") in pns:
        st.session_state["precheck_pn_idx"] = pns.index(st.session_state["precheck_pn"])
        st.session_state["precheck_pn"] = None

    idx = st.session_state["precheck_pn_idx"]
    idx = max(0, min(idx, len(pns) - 1))
    pn  = pns[idx]

    # ── Navigation bar ────────────────────────────────────────────────────────
    col_prev, col_pn, col_ctr, col_badge, col_next = st.columns([0.5, 2, 1, 1.5, 0.5])
    if col_prev.button("◄", key="nav_prev", use_container_width=True):
        st.session_state["precheck_pn_idx"] = max(0, idx - 1)
        st.rerun()
    col_pn.markdown(f"### `{pn}`")
    col_ctr.caption(f"{idx + 1} / {len(pns)}")

    dec_info = queries.get_stats_for_module(module)
    # Statut du PN courant
    decs = [queries.get_decision(d["marquage"])
            for d in queries.get_tools_for_module(module) if d["pn_short"] == pn]
    statuses = [d["decision"] for d in decs if d]
    if all(s in ("VALIDÉ", "EN ATTENTE") for s in statuses) and statuses:
        col_badge.success("Validé")
    elif any(s == "PRÉ-CHECK" for s in statuses):
        col_badge.warning("Pré-check")
    else:
        col_badge.info("En cours")

    if col_next.button("►", key="nav_next", use_container_width=True):
        st.session_state["precheck_pn_idx"] = min(len(pns) - 1, idx + 1)
        st.rerun()

    # ── Infos PN ──────────────────────────────────────────────────────────────
    active_df, excluded_df = _load_deca_rows(pn, module)
    _render_pn_info(pn, active_df)

    st.divider()

    # ── Options affichage ─────────────────────────────────────────────────────
    opt1, opt2, _, _ = st.columns([1, 1, 1, 3])
    st.session_state["precheck_show_svc"] = opt1.checkbox(
        "Afficher services actuels", value=st.session_state["precheck_show_svc"]
    )
    st.session_state["precheck_show_loc"] = opt2.checkbox(
        "Afficher localisations", value=st.session_state["precheck_show_loc"]
    )

    # ── Table DECAs ───────────────────────────────────────────────────────────
    st.markdown(f"**DECAs à traiter** — {len(active_df)} actif(s)")
    edited = _render_deca_table(
        pn_short   = pn,
        active_df  = active_df,
        mode       = mode,
        show_svc   = st.session_state["precheck_show_svc"],
        show_loc   = st.session_state["precheck_show_loc"],
        table_key  = f"editor_{module}_{pn}",
    )

    # Copie rapide pour multi-DECA
    _render_copy_toolbar(edited, pn, module, mode)

    # ── Hors périmètre ────────────────────────────────────────────────────────
    _render_excluded(excluded_df)

    st.divider()

    # ── Actions ───────────────────────────────────────────────────────────────
    col_val, col_ign, col_hint = st.columns([1, 1, 3])

    if col_val.button("✓ Valider & suivant", type="primary", use_container_width=True):
        if edited is not None:
            ok, msg = _pn_is_complete(edited, mode)
            if not ok:
                st.error(msg)
            else:
                for _, row in edited.iterrows():
                    _save_row(dict(row), pn, module, mode)
                st.session_state["precheck_pn_idx"] = min(len(pns) - 1, idx + 1)
                st.rerun()

    if col_ign.button("→ Ignorer", use_container_width=True):
        # Save current state as-is then move on
        if edited is not None:
            for _, row in edited.iterrows():
                _save_row(dict(row), pn, module, mode)
        st.session_state["precheck_pn_idx"] = min(len(pns) - 1, idx + 1)
        st.rerun()

    col_hint.caption("Raccourcis : ◄ ► pour naviguer entre PNs")


# ── Vue liste plate (uniques) ─────────────────────────────────────────────────

def _render_flat_view(module: str, mode: str):
    # Uniques only: 1 PN = 1 DECA = 1 module
    all_rows = queries.get_tools_for_module(module)
    unique_pns = [r for r in all_rows if r["complexity_flag"] == "unique"]

    if not unique_pns:
        st.info(f"Aucun PN unique sur {module}.")
        return

    st.caption(
        f"{len(unique_pns)} PNs uniques — un seul DECA par PN, "
        "décision directement dans la table."
    )

    flat_rows = []
    for r in unique_pns:
        dec = queries.get_decision(r["marquage"])
        flat_rows.append({
            "pn_short":        r["pn_short"],
            "marquage":        r["marquage"],
            "ref_constructeur": r.get("ref_constructeur") or "",
            "service3":        r.get("service3") or "",
            "assy_flag":       r.get("assy_flag") or "",
            "n_service3":      (dec["n_service3"] if dec else "") or "",
            "n_service4":      (dec["n_service4"] if dec else "") or "",
            "pre_check":       (dec["pre_check"] if dec else "") or "",
            "decision":        (dec["decision"] if dec else "EN COURS"),
            "commentaire":     (dec["commentaire"] if dec else "") or "",
            "_locked":         bool(dec and dec["decision"] in ("VALIDÉ", "EN ATTENTE")),
        })

    df = pd.DataFrame(flat_rows)

    edited = st.data_editor(
        df[[c for c in df.columns if c != "_locked"]],
        column_config={
            "pn_short":         st.column_config.TextColumn("PN", disabled=True, width="small"),
            "marquage":         st.column_config.TextColumn("Marquage", disabled=True, width="small"),
            "ref_constructeur": st.column_config.TextColumn("Ref.", disabled=True, width="medium"),
            "service3":         st.column_config.TextColumn("Svc 3 actuel", disabled=True, width="small"),
            "assy_flag":        st.column_config.TextColumn("ASSY", disabled=True, width="small"),
            "n_service3":       st.column_config.SelectboxColumn(
                                    "N.Service3 ✏", options=SERVICE3_OPTIONS, required=False, width="small"
                                ),
            "n_service4":       st.column_config.SelectboxColumn(
                                    "N.Service4 ✏", options=SERVICE4_OPTIONS, required=False, width="small"
                                ),
            "pre_check":        st.column_config.SelectboxColumn(
                                    "Pré-check", options=[""] + PRECHECK_FLAGS[:3], required=False, width="small"
                                ),
            "decision":         st.column_config.SelectboxColumn(
                                    "Décision",
                                    options=(_STATUS_REUNION if mode == "reunion" else _STATUS_PRECHECK),
                                    required=True, width="small",
                                ),
            "commentaire":      st.column_config.TextColumn("Commentaire", width="large"),
        },
        disabled=["pn_short", "marquage", "ref_constructeur", "service3", "assy_flag"],
        hide_index=True,
        use_container_width=True,
        key=f"flat_editor_{module}",
        num_rows="fixed",
    )

    col_save, _ = st.columns([1, 4])
    if col_save.button("💾 Sauvegarder tout", type="primary"):
        saved = 0
        for _, row in edited.iterrows():
            # Skip locked rows
            orig = df[df["marquage"] == row["marquage"]]["_locked"]
            if not orig.empty and orig.iloc[0]:
                continue
            _save_row(dict(row), row["pn_short"], module, mode)
            saved += 1
        st.success(f"{saved} décisions sauvegardées.")
        st.rerun()


# ── Point d'entrée ────────────────────────────────────────────────────────────

def render():
    _init_state()

    # ── Topbar ────────────────────────────────────────────────────────────────
    col_mod, col_view, col_mode, col_search, col_stats = st.columns([1, 1.2, 1, 1.5, 2])

    with col_mod:
        module = st.selectbox(
            "Module", MODULES,
            index=MODULES.index(st.session_state["precheck_module"]),
            key="sel_module",
        )
        st.session_state["precheck_module"] = module

    with col_view:
        view = st.radio(
            "Vue", ["Navigation PN", "Liste plate"],
            index=0 if st.session_state["precheck_view"] == "nav" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state["precheck_view"] = "nav" if view == "Navigation PN" else "flat"

    with col_mode:
        mode_label = st.radio(
            "Mode", ["Pré-check", "Réunion"],
            index=0 if st.session_state["precheck_mode"] == "precheck" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state["precheck_mode"] = "precheck" if mode_label == "Pré-check" else "reunion"
        mode = st.session_state["precheck_mode"]

    with col_search:
        result = pn_search_widget(key_prefix="precheck_top")
        if result:
            _go_to_pn(result["pn_short"], result["module"])
            st.session_state["precheck_view"] = "nav"
            st.rerun()

    with col_stats:
        s = queries.get_stats_for_module(module)
        if s and s.get("total"):
            pct = round(100 * s.get("valide", 0) / s["total"])
            st.caption(
                f"**{s.get('valide', 0)}** validé · "
                f"**{s.get('precheck', 0)}** pré-check · "
                f"**{s.get('en_cours', 0)}** en cours "
                f"— {pct}% complet"
            )
            st.progress(pct / 100)

    st.divider()

    # ── Vue sélectionnée ──────────────────────────────────────────────────────
    if st.session_state["precheck_view"] == "nav":
        _render_nav_view(module, mode)
    else:
        _render_flat_view(module, mode)
