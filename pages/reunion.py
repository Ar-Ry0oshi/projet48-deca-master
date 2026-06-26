"""
Page Réunion — validation collective en séance.

Différences vs Pré-check :
  - Colonne pre_check visible mais non éditable (lecture seule)
  - Statuts disponibles : VALIDÉ | EN ATTENTE uniquement
  - Services (n_service3, n_service4, commentaire) restent éditables
  - Vue plus épurée, optimisée pour projection
"""
import streamlit as st
import pandas as pd

from config import MODULES, SERVICE_CASCADE, PRECHECK_FLAGS
from db import queries
from components.pn_search import pn_search_widget


# ── Constantes ────────────────────────────────────────────────────────────────

SERVICE3_OPTIONS = [""] + MODULES + ["LSO"]
SERVICE4_OPTIONS = ["", "ASSY", "DISASSY", "ASSY AND DISASSY"]
STATUS_OPTIONS   = ["VALIDÉ", "EN ATTENTE"]


# ── Session state ─────────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "reunion_module":  MODULES[0],
        "reunion_pn_idx":  0,
        "reunion_pn":      None,
        "reunion_view":    "nav",   # "nav" | "flat"
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _go_to_pn(pn_short: str, module: str):
    pns = queries.get_pn_list_for_module(module)
    st.session_state["reunion_module"] = module
    if pn_short in pns:
        st.session_state["reunion_pn_idx"] = pns.index(pn_short)
    st.session_state["reunion_pn"] = pn_short


# ── Cascade service ───────────────────────────────────────────────────────────

def _cascade(svc3: str) -> tuple[str, str]:
    key = svc3.strip().upper() if svc3 else ""
    return SERVICE_CASCADE.get(key, ("", ""))


# ── Chargement des DECAs ──────────────────────────────────────────────────────

def _load_deca_rows(pn_short: str, module: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_rows = queries.get_tools_for_module(module, include_excluded=True)
    pn_rows  = [r for r in all_rows if r["pn_short"] == pn_short]

    active   = [dict(r) for r in pn_rows if not r["is_excluded"]]
    excluded = [dict(r) for r in pn_rows if r["is_excluded"]]

    other_excl = queries.get_excluded_for_pn(pn_short)
    excl_marquages = {r["marquage"] for r in excluded}
    for r in other_excl:
        if r["marquage"] not in excl_marquages:
            excluded.append(dict(r))

    return pd.DataFrame(active), pd.DataFrame(excluded)


# ── Sauvegarde ────────────────────────────────────────────────────────────────

def _save_row(row: dict, pn_short: str, module: str):
    svc3 = row.get("n_service3") or ""
    svc4 = row.get("n_service4") or ""
    svc1, svc2 = _cascade(svc3)
    decision = row.get("decision") or "VALIDÉ"
    comm = row.get("commentaire") or None

    existing = queries.get_decision(row["marquage"])
    pre = (existing["pre_check"] if existing else None)

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
        updated_by     = "reunion",
    )


# ── Vérification avant passage au suivant ─────────────────────────────────────

def _pn_is_complete(edited_df: pd.DataFrame) -> tuple[bool, str]:
    if edited_df.empty:
        return True, ""
    missing_svc3 = edited_df[edited_df["n_service3"].isna() | (edited_df["n_service3"] == "")]
    if not missing_svc3.empty:
        marks = ", ".join(missing_svc3["marquage"].tolist())
        return False, f"N.Service3 manquant sur : {marks}"
    missing_dec = edited_df[~edited_df["decision"].isin(STATUS_OPTIONS)]
    if not missing_dec.empty:
        marks = ", ".join(missing_dec["marquage"].tolist())
        return False, f"Décision manquante sur : {marks}"
    return True, ""


# ── Bandeau infos PN ──────────────────────────────────────────────────────────

def _render_pn_info(pn_short: str, active_df: pd.DataFrame):
    if active_df.empty:
        return
    row = active_df.iloc[0]
    modules_eff = row.get("modules_effective") or ""
    modules = [m.strip() for m in modules_eff.split(",") if m.strip()]
    assy = row.get("assy_flag") or "—"
    n_active = len(active_df)

    chips = st.columns([1, 1, 1, 3])
    chips[0].metric("Modules", ", ".join(modules) if modules else "—")
    chips[1].metric("ASSY flag", assy)
    chips[2].metric("DECAs actifs", n_active)

    opcodes = row.get("opcodes_translated") or ""
    if opcodes:
        st.caption(f"ICV : {opcodes}")


# ── Construction du dataframe éditeur ─────────────────────────────────────────

def _build_editor_df(active_df: pd.DataFrame) -> pd.DataFrame:
    if active_df.empty:
        return pd.DataFrame()

    rows = []
    for _, r in active_df.iterrows():
        dec = queries.get_decision(r["marquage"])
        # En réunion, le statut par défaut est VALIDÉ (pas EN COURS)
        current_decision = (dec["decision"] if dec else "EN COURS")
        if current_decision not in STATUS_OPTIONS:
            current_decision = "VALIDÉ"

        rows.append({
            "marquage":         r["marquage"],
            "ref_constructeur": r.get("ref_constructeur") or "",
            "service3":         r.get("service3") or "",
            "pre_check":        (dec["pre_check"] if dec else "") or "",
            "n_service3":       (dec["n_service3"] if dec else "") or "",
            "n_service4":       (dec["n_service4"] if dec else "") or "",
            "decision":         current_decision,
            "commentaire":      (dec["commentaire"] if dec else "") or "",
            "_locked":          bool(dec and dec["decision"] in ("VALIDÉ", "EN ATTENTE")),
        })
    return pd.DataFrame(rows)


# ── Table DECAs (data_editor) ─────────────────────────────────────────────────

def _render_deca_table(
    pn_short: str,
    active_df: pd.DataFrame,
    table_key: str,
) -> pd.DataFrame | None:
    if active_df.empty:
        st.info("Aucun DECA actif pour ce PN dans ce module.")
        return None

    editor_df = _build_editor_df(active_df)

    col_cfg = {
        "marquage":         st.column_config.TextColumn("Marquage", disabled=True, width="small"),
        "ref_constructeur": st.column_config.TextColumn("Ref. constructeur", disabled=True, width="medium"),
        "service3":         st.column_config.TextColumn("Svc 3 actuel", disabled=True, width="small"),
        "pre_check":        st.column_config.TextColumn("Pré-check", disabled=True, width="small"),
        "n_service3":       st.column_config.SelectboxColumn(
                                "N.Service3 ✏", options=SERVICE3_OPTIONS, required=False, width="small"
                            ),
        "n_service4":       st.column_config.SelectboxColumn(
                                "N.Service4 ✏", options=SERVICE4_OPTIONS, required=False, width="small"
                            ),
        "decision":         st.column_config.SelectboxColumn(
                                "Décision ✏", options=STATUS_OPTIONS, required=True, width="small"
                            ),
        "commentaire":      st.column_config.TextColumn("Commentaire", width="large"),
        "_locked":          None,
    }

    col_order = [
        "marquage", "ref_constructeur", "service3", "pre_check",
        "n_service3", "n_service4", "decision", "commentaire",
    ]

    edited = st.data_editor(
        editor_df[col_order + ["_locked"]],
        column_config=col_cfg,
        column_order=col_order,
        disabled=["marquage", "ref_constructeur", "service3", "pre_check"],
        hide_index=True,
        use_container_width=True,
        key=table_key,
        num_rows="fixed",
    )
    return edited


# ── Copie rapide ──────────────────────────────────────────────────────────────

def _render_copy_toolbar(edited: pd.DataFrame | None, pn_short: str, module: str):
    if edited is None or len(edited) <= 1:
        return

    col1, col2, col3 = st.columns([2, 2, 4])
    if col1.button("⬇ Copier Svc3 & Svc4 vers toutes les lignes", use_container_width=True):
        first = edited.iloc[0]
        svc3 = first.get("n_service3") or ""
        svc4 = first.get("n_service4") or ""
        for _, row in edited.iterrows():
            _save_row({**dict(row), "n_service3": svc3, "n_service4": svc4}, pn_short, module)
        st.success(f"Service3={svc3} / Service4={svc4} appliqué à {len(edited)} DECAs.")
        st.rerun()

    if col2.button("✓ Valider toutes les lignes", use_container_width=True):
        for _, row in edited.iterrows():
            _save_row({**dict(row), "decision": "VALIDÉ"}, pn_short, module)
        st.success(f"{len(edited)} DECAs validés.")
        st.rerun()


# ── Hors périmètre ────────────────────────────────────────────────────────────

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
        )


# ── Statut du PN (badge) ──────────────────────────────────────────────────────

def _pn_status_badge(pn: str, module: str, col):
    tools = queries.get_tools_for_module(module)
    decs = [queries.get_decision(d["marquage"]) for d in tools if d["pn_short"] == pn]
    statuses = [d["decision"] for d in decs if d]
    if all(s == "VALIDÉ" for s in statuses) and statuses:
        col.success("Validé")
    elif any(s == "EN ATTENTE" for s in statuses):
        col.warning("En attente")
    elif any(s == "PRÉ-CHECK" for s in statuses):
        col.info("Pré-check")
    else:
        col.info("En cours")


# ── Vue navigation PN ─────────────────────────────────────────────────────────

def _render_nav_view(module: str):
    pns = queries.get_pn_list_for_module(module)
    if not pns:
        st.info(f"Aucun PN actif sur {module}.")
        return

    if st.session_state.get("reunion_pn") in pns:
        st.session_state["reunion_pn_idx"] = pns.index(st.session_state["reunion_pn"])
        st.session_state["reunion_pn"] = None

    idx = st.session_state["reunion_pn_idx"]
    idx = max(0, min(idx, len(pns) - 1))
    pn  = pns[idx]

    col_prev, col_pn, col_ctr, col_badge, col_next = st.columns([0.5, 2, 1, 1.5, 0.5])
    if col_prev.button("◄", key="reu_prev", use_container_width=True):
        st.session_state["reunion_pn_idx"] = max(0, idx - 1)
        st.rerun()
    col_pn.markdown(f"### `{pn}`")
    col_ctr.caption(f"{idx + 1} / {len(pns)}")
    _pn_status_badge(pn, module, col_badge)
    if col_next.button("►", key="reu_next", use_container_width=True):
        st.session_state["reunion_pn_idx"] = min(len(pns) - 1, idx + 1)
        st.rerun()

    active_df, excluded_df = _load_deca_rows(pn, module)
    _render_pn_info(pn, active_df)
    st.divider()

    st.markdown(f"**DECAs à valider** — {len(active_df)} actif(s)")
    edited = _render_deca_table(
        pn_short  = pn,
        active_df = active_df,
        table_key = f"reu_editor_{module}_{pn}",
    )

    _render_copy_toolbar(edited, pn, module)
    _render_excluded(excluded_df)

    st.divider()

    col_val, col_ign, col_hint = st.columns([1, 1, 3])

    if col_val.button("✓ Valider & suivant", type="primary", use_container_width=True):
        if edited is not None:
            ok, msg = _pn_is_complete(edited)
            if not ok:
                st.error(msg)
            else:
                for _, row in edited.iterrows():
                    _save_row(dict(row), pn, module)
                st.session_state["reunion_pn_idx"] = min(len(pns) - 1, idx + 1)
                st.rerun()

    if col_ign.button("→ Ignorer", use_container_width=True):
        if edited is not None:
            for _, row in edited.iterrows():
                _save_row(dict(row), pn, module)
        st.session_state["reunion_pn_idx"] = min(len(pns) - 1, idx + 1)
        st.rerun()

    col_hint.caption("◄ ► pour naviguer entre PNs")


# ── Vue liste plate ───────────────────────────────────────────────────────────

def _render_flat_view(module: str):
    all_rows = queries.get_tools_for_module(module)
    unique_pns = [r for r in all_rows if r["complexity_flag"] == "unique"]

    if not unique_pns:
        st.info(f"Aucun PN unique sur {module}.")
        return

    st.caption(f"{len(unique_pns)} PNs uniques — décision directement dans la table.")

    flat_rows = []
    for r in unique_pns:
        dec = queries.get_decision(r["marquage"])
        current_decision = (dec["decision"] if dec else "EN COURS")
        if current_decision not in STATUS_OPTIONS:
            current_decision = "VALIDÉ"

        flat_rows.append({
            "pn_short":         r["pn_short"],
            "marquage":         r["marquage"],
            "ref_constructeur": r.get("ref_constructeur") or "",
            "service3":         r.get("service3") or "",
            "pre_check":        (dec["pre_check"] if dec else "") or "",
            "n_service3":       (dec["n_service3"] if dec else "") or "",
            "n_service4":       (dec["n_service4"] if dec else "") or "",
            "decision":         current_decision,
            "commentaire":      (dec["commentaire"] if dec else "") or "",
            "_locked":          bool(dec and dec["decision"] in ("VALIDÉ", "EN ATTENTE")),
        })

    df = pd.DataFrame(flat_rows)
    col_order = ["pn_short", "marquage", "ref_constructeur", "service3", "pre_check",
                 "n_service3", "n_service4", "decision", "commentaire"]

    edited = st.data_editor(
        df[col_order],
        column_config={
            "pn_short":         st.column_config.TextColumn("PN", disabled=True, width="small"),
            "marquage":         st.column_config.TextColumn("Marquage", disabled=True, width="small"),
            "ref_constructeur": st.column_config.TextColumn("Ref.", disabled=True, width="medium"),
            "service3":         st.column_config.TextColumn("Svc 3 actuel", disabled=True, width="small"),
            "pre_check":        st.column_config.TextColumn("Pré-check", disabled=True, width="small"),
            "n_service3":       st.column_config.SelectboxColumn(
                                    "N.Service3 ✏", options=SERVICE3_OPTIONS, required=False, width="small"
                                ),
            "n_service4":       st.column_config.SelectboxColumn(
                                    "N.Service4 ✏", options=SERVICE4_OPTIONS, required=False, width="small"
                                ),
            "decision":         st.column_config.SelectboxColumn(
                                    "Décision ✏", options=STATUS_OPTIONS, required=True, width="small"
                                ),
            "commentaire":      st.column_config.TextColumn("Commentaire", width="large"),
        },
        disabled=["pn_short", "marquage", "ref_constructeur", "service3", "pre_check"],
        hide_index=True,
        use_container_width=True,
        key=f"reu_flat_{module}",
        num_rows="fixed",
    )

    col_save, _ = st.columns([1, 4])
    if col_save.button("💾 Sauvegarder tout", type="primary"):
        saved = 0
        for _, row in edited.iterrows():
            orig_locked = df[df["marquage"] == row["marquage"]]["_locked"]
            if not orig_locked.empty and orig_locked.iloc[0]:
                continue
            _save_row(dict(row), row["pn_short"], module)
            saved += 1
        st.success(f"{saved} décisions sauvegardées.")
        st.rerun()


# ── Point d'entrée ────────────────────────────────────────────────────────────

def render():
    _init_state()

    st.title("Réunion")

    # ── Topbar ────────────────────────────────────────────────────────────────
    col_mod, col_view, col_search, col_stats = st.columns([1, 1.2, 1.5, 2])

    with col_mod:
        module = st.selectbox(
            "Module", MODULES,
            index=MODULES.index(st.session_state["reunion_module"]),
            key="reu_sel_module",
        )
        st.session_state["reunion_module"] = module

    with col_view:
        view = st.radio(
            "Vue", ["Navigation PN", "Liste plate"],
            index=0 if st.session_state["reunion_view"] == "nav" else 1,
            horizontal=True,
            label_visibility="collapsed",
        )
        st.session_state["reunion_view"] = "nav" if view == "Navigation PN" else "flat"

    with col_search:
        result = pn_search_widget(key_prefix="reunion_top")
        if result:
            _go_to_pn(result["pn_short"], result["module"])
            st.session_state["reunion_view"] = "nav"
            st.rerun()

    with col_stats:
        s = queries.get_stats_for_module(module)
        if s and s.get("total"):
            pct = round(100 * s.get("valide", 0) / s["total"])
            st.caption(
                f"**{s.get('valide', 0)}** validé · "
                f"**{s.get('en_attente', 0)}** en attente · "
                f"**{s.get('precheck', 0)}** pré-check "
                f"— {pct}% validé"
            )
            st.progress(pct / 100)

    st.divider()

    if st.session_state["reunion_view"] == "nav":
        _render_nav_view(module)
    else:
        _render_flat_view(module)
