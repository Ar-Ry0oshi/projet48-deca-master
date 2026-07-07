"""
Page Pré-check — traitement PN par PN, mode solo.
Deux vues :
  - Navigation PN  : pour les multi-DECA et multi-module (1 PN à la fois)
  - Liste plate    : pour les uniques (tous les PNs d'un module dans une table)
"""
import streamlit as st
import pandas as pd

from config import MODULES, PRECHECK_FLAGS
from db import queries, cached as db_cached
from components.pn_search import pn_search_widget
from components.deca_detail import show_deca_detail
from components.pn_info import render_pn_info
from components.deca_hors_perimetre import render_excluded
from components.deca_table import render_readonly_table, render_deca_table_editor
from services import svc3_options, svc1_for_svc3, svc4_options


# ── Constantes ────────────────────────────────────────────────────────────────

_SVC3_OPTS   = [""] + svc3_options()
_PRECHECK_OPTS   = [""] + PRECHECK_FLAGS[:3]
_STATUS_PRECHECK = ["EN COURS", "PRÉ-CHECK"]
_STATUS_REUNION  = ["VALIDÉ", "EN ATTENTE"]


# ── Session state ─────────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "precheck_module":   MODULES[0],
        "precheck_pn_idx":   0,
        "precheck_pn":       None,
        "precheck_view":     "nav",
        "precheck_show_svc": True,
        "precheck_show_loc": False,
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


# ── Chargement DECAs ──────────────────────────────────────────────────────────

def _load_deca_rows(pn_short: str, module: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_rows = db_cached.get_tools_for_module(module, include_excluded=True)
    pn_rows  = [r for r in all_rows if r["pn_short"] == pn_short]
    active   = [dict(r) for r in pn_rows if not r["is_excluded"]]
    excluded = [dict(r) for r in pn_rows if r["is_excluded"]]
    other_excl = queries.get_excluded_for_pn(pn_short)
    seen = {r["marquage"] for r in excluded}
    for r in other_excl:
        if r["marquage"] not in seen:
            excluded.append(dict(r))
    return pd.DataFrame(active), pd.DataFrame(excluded)


# ── Sauvegarde ────────────────────────────────────────────────────────────────

def _save_deca(marquage: str, pn_short: str, module: str, mode: str,
               svc3: str, svc1: str, svc4: str,
               pre_check: str, decision: str, commentaire: str):
    existing = queries.get_decision(marquage)
    if existing and existing["decision"] in ("VALIDÉ", "EN ATTENTE"):
        return

    svc2s = []
    from services import svc2_for_svc3
    if svc3 and svc1:
        svc2s = svc2_for_svc3(svc3)

    if mode == "reunion":
        final_decision = decision or "VALIDÉ"
    else:
        final_decision = "PRÉ-CHECK" if svc3 else "EN COURS"

    queries.upsert_decision(
        marquage       = marquage,
        pn_short       = pn_short,
        module_context = module,
        n_service1     = svc1 or None,
        n_service2     = svc2s[0] if svc2s else None,
        n_service3     = svc3 or None,
        n_service4     = svc4 or None,
        pre_check      = pre_check or None,
        decision       = final_decision,
        commentaire    = commentaire or None,
        updated_by     = "user",
    )


# ── Vérification avant passage ────────────────────────────────────────────────

def _forms_complete(forms: list[dict], mode: str) -> tuple[bool, str]:
    for f in forms:
        if f.get("_locked"):
            continue
        if mode == "reunion":
            if not f.get("svc3") and f.get("decision") != "EN ATTENTE":
                return False, f"N.Service3 manquant sur `{f['marquage']}` (mettre EN ATTENTE si non décidé)"
            if f.get("decision") not in ("VALIDÉ", "EN ATTENTE"):
                return False, f"Décision manquante sur `{f['marquage']}`"
        # En precheck : pas de validation bloquante, on peut passer sans svc3
    return True, ""


# ── Vue navigation PN ─────────────────────────────────────────────────────────

def _render_nav_view(module: str, mode: str):
    pns = queries.get_pn_list_for_module(module)
    if not pns:
        st.info(f"Aucun PN actif sur {module}.")
        return

    if st.session_state.get("precheck_pn") in pns:
        st.session_state["precheck_pn_idx"] = pns.index(st.session_state["precheck_pn"])
        st.session_state["precheck_pn"] = None

    idx = max(0, min(st.session_state["precheck_pn_idx"], len(pns) - 1))
    pn  = pns[idx]

    # ── Barre de navigation ───────────────────────────────────────────────────
    col_prev, col_pn, col_ctr, col_badge, col_next = st.columns([0.5, 2, 1, 1.5, 0.5])
    if col_prev.button("◄", key="nav_prev", use_container_width=True):
        st.session_state["precheck_pn_idx"] = max(0, idx - 1)
        st.rerun()
    col_pn.markdown(f"### `{pn}`")
    col_ctr.caption(f"{idx + 1} / {len(pns)}")

    # Badge statut
    tools = db_cached.get_tools_for_module(module)
    decs = [queries.get_decision(d["marquage"]) for d in tools if d["pn_short"] == pn]
    decs = [dict(d) for d in decs if d]
    statuses = [d["decision"] for d in decs]
    if all(s in ("VALIDÉ", "EN ATTENTE") for s in statuses) and statuses:
        col_badge.success("Validé")
    elif any(d.get("pre_check") for d in decs):
        col_badge.warning("Pré-check")
    else:
        col_badge.info("En cours")

    if col_next.button("►", key="nav_next", use_container_width=True):
        st.session_state["precheck_pn_idx"] = min(len(pns) - 1, idx + 1)
        st.rerun()

    # ── Infos PN ──────────────────────────────────────────────────────────────
    active_df, excluded_df = _load_deca_rows(pn, module)
    render_pn_info(pn, active_df)

    # Préchauffage de l'index photos en arrière-plan (cache 10 min)
    from config import PHOTOS_DIR
    from components.deca_detail import _build_photo_index
    if PHOTOS_DIR and PHOTOS_DIR.exists():
        _build_photo_index(str(PHOTOS_DIR))

    st.divider()

    if active_df.empty:
        st.info("Aucun DECA actif pour ce PN dans ce module.")
        return

    st.markdown(f"**Décisions** — {len(active_df)} DECA(s) à traiter")

    # ── Table de décisions ────────────────────────────────────────────────────
    forms = render_deca_table_editor(active_df, mode, key_prefix="pc")

    # ── Copie rapide multi-DECA ───────────────────────────────────────────────
    if len(active_df) > 1:
        c1, c2, _ = st.columns([2, 2, 4])
        if c1.button("⬇ Copier Svc3 & Svc4 du 1er vers tous", use_container_width=True):
            first = forms[0]
            if not first.get("svc3"):
                st.error("Le premier DECA n'a pas de N.Service3 défini — remplissez-le d'abord.")
            elif not first.get("svc1"):
                st.error("Bâtiment non résolu pour le premier DECA.")
            else:
                for row in active_df.itertuples():
                    _save_deca(
                        row.marquage, pn, module, mode,
                        first["svc3"], first["svc1"], first["svc4"],
                        first["pre_check"], first["decision"], first["commentaire"],
                    )
                st.success(f"Service3={first['svc3']} / Service4={first['svc4']} appliqué à {len(forms)} DECAs.")
                st.rerun()

        if c2.button("✓ Valider toutes les lignes", use_container_width=True):
            for f in forms:
                if not f.get("_locked"):
                    _save_deca(
                        f["marquage"], pn, module, "reunion",
                        f["svc3"], f["svc1"], f["svc4"],
                        f["pre_check"], "VALIDÉ", f["commentaire"],
                    )
            st.success(f"{len(forms)} DECAs validés.")
            st.rerun()

    render_excluded(excluded_df)
    st.divider()

    # ── Actions ───────────────────────────────────────────────────────────────
    col_val, col_ign, col_hint = st.columns([1, 1, 3])

    if col_val.button("✓ Valider & suivant", type="primary", use_container_width=True):
        ok, msg = _forms_complete(forms, mode)
        if not ok:
            st.error(msg)
        else:
            for f in forms:
                if not f.get("_locked"):
                    _save_deca(
                        f["marquage"], pn, module, mode,
                        f["svc3"], f["svc1"], f["svc4"],
                        f["pre_check"], f["decision"], f["commentaire"],
                    )
            st.session_state["precheck_pn_idx"] = min(len(pns) - 1, idx + 1)
            st.rerun()

    if col_ign.button("→ Ignorer", use_container_width=True):
        for f in forms:
            if not f.get("_locked"):
                _save_deca(
                    f["marquage"], pn, module, mode,
                    f["svc3"], f["svc1"], f["svc4"],
                    f["pre_check"], f["decision"], f["commentaire"],
                )
        st.session_state["precheck_pn_idx"] = min(len(pns) - 1, idx + 1)
        st.rerun()

    col_hint.caption("◄ ► pour naviguer entre PNs · cliquer sur la table pour ouvrir la fiche")


# ── Vue liste plate (uniques) ─────────────────────────────────────────────────

def _render_flat_view(module: str, mode: str):
    all_rows = db_cached.get_tools_for_module(module)
    unique_pns = [dict(r) for r in all_rows if r["complexity_flag"] == "unique"]

    if not unique_pns:
        st.info(f"Aucun PN unique sur {module}.")
        return

    st.caption(
        f"{len(unique_pns)} PNs uniques — N.Service3 / N.Service4 / décision directement dans la table."
    )

    # On utilise un data_editor avec les vraies options de svc3
    # (service4 non filtré ici — trop de lignes pour des formulaires individuels)
    from services import svc3_labeled_options, svc4_labeled_options, svc3_label, svc4_label, svc3_from_label, svc4_from_label, svc1_for_svc3
    _svc3_opts = svc3_labeled_options()
    _svc4_opts = svc4_labeled_options()

    flat_rows = []
    for r in unique_pns:
        r = dict(r)
        dec = queries.get_decision(r["marquage"])
        dec = dict(dec) if dec else {}
        svc1_sv  = dec.get("n_service1") or ""
        n3_plain = dec.get("n_service3") or ""
        n4_plain = dec.get("n_service4") or ""
        n3_disp  = svc3_label(n3_plain, svc1_sv) if n3_plain and svc1_sv else n3_plain
        n4_disp  = svc4_label(n4_plain, svc1_sv) if n4_plain and svc1_sv else n4_plain
        flat_rows.append({
            "pn_short":         r["pn_short"],
            "marquage":         r["marquage"],
            "ref_constructeur": r.get("ref_constructeur") or "",
            "service3":         r.get("service3") or "",
            "localisation3":    r.get("localisation3") or "",
            "assy_flag":        r.get("assy_flag") or "",
            "n_service3":       n3_disp,
            "n_service4":       n4_disp,
            "pre_check":        dec.get("pre_check") or "",
            "commentaire":      dec.get("commentaire") or "",
            "_locked":          bool(dec and dec.get("decision") in ("VALIDÉ", "EN ATTENTE")),
        })

    df = pd.DataFrame(flat_rows)

    edited = st.data_editor(
        df[[c for c in df.columns if c != "_locked"]],
        column_config={
            "pn_short":         st.column_config.TextColumn("PN", disabled=True, width="small"),
            "marquage":         st.column_config.TextColumn("Marquage", disabled=True, width="small"),
            "ref_constructeur": st.column_config.TextColumn("Ref.", disabled=True, width="medium"),
            "service3":         st.column_config.TextColumn("Svc 3 act.", disabled=True, width="small"),
            "localisation3":    st.column_config.TextColumn("Loc 3", disabled=True, width="small"),
            "assy_flag":        st.column_config.TextColumn("ASSY", disabled=True, width="small"),
            "n_service3":       st.column_config.SelectboxColumn(
                                    "N.Service3 ✏", options=_svc3_opts, required=False, width="large"
                                ),
            "n_service4":       st.column_config.SelectboxColumn(
                                    "N.Service4 ✏", options=_svc4_opts, required=False, width="large"
                                ),
            "pre_check":        st.column_config.SelectboxColumn(
                                    "Pré-check ✏", options=_PRECHECK_OPTS, required=False, width="small"
                                ),
            "commentaire":      st.column_config.TextColumn("Commentaire ✏", width="large"),
        },
        disabled=["pn_short", "marquage", "ref_constructeur", "service3", "localisation3", "assy_flag"],
        hide_index=True,
        use_container_width=True,
        key=f"flat_editor_{module}",
        num_rows="fixed",
    )

    col_save, _ = st.columns([1, 4])
    if col_save.button("💾 Sauvegarder tout", type="primary"):
        saved = 0
        for _, row in edited.iterrows():
            orig = df[df["marquage"] == row["marquage"]]["_locked"]
            if not orig.empty and orig.iloc[0]:
                continue
            svc3, svc1 = svc3_from_label(row.get("n_service3") or "")
            svc4 = svc4_from_label(row.get("n_service4") or "")
            _save_deca(
                row["marquage"], row["pn_short"], module, mode,
                svc3, svc1, svc4,
                row.get("pre_check") or "", "EN COURS",
                row.get("commentaire") or "",
            )
            saved += 1
        st.success(f"{saved} décisions sauvegardées.")
        st.rerun()

    # ── Voir détail ───────────────────────────────────────────────────────────
    all_marquages = [r["marquage"] for r in unique_pns]
    if all_marquages:
        st.divider()
        col_sel, col_btn, _ = st.columns([2, 1, 3])
        selected_flat = col_sel.selectbox(
            "Voir détail", options=all_marquages,
            key=f"detail_flat_sel_{module}",
            label_visibility="collapsed",
        )
        if col_btn.button("🔍 Ouvrir", key=f"detail_flat_btn_{module}", use_container_width=True):
            show_deca_detail(selected_flat, marquages=all_marquages)


# ── Point d'entrée ────────────────────────────────────────────────────────────

def render():
    _init_state()

    col_mod, col_view, col_search, col_stats = st.columns([1, 1.2, 1.5, 2])
    mode = "precheck"

    with col_mod:
        module = st.selectbox(
            "Module", MODULES,
            index=MODULES.index(st.session_state["precheck_module"]),
        )
        st.session_state["precheck_module"] = module

    with col_view:
        _view_opts = ["Navigation PN", "Liste plate", "Par service"]
        _view_keys = ["nav", "flat", "service"]
        _cur_view  = st.session_state["precheck_view"]
        _cur_idx   = _view_keys.index(_cur_view) if _cur_view in _view_keys else 0
        view = st.radio(
            "Vue", _view_opts, index=_cur_idx,
            horizontal=True, label_visibility="collapsed",
        )
        st.session_state["precheck_view"] = _view_keys[_view_opts.index(view)]

    with col_search:
        result = pn_search_widget(key_prefix="precheck_top")
        if result:
            _go_to_pn(result["pn_short"], result["module"])
            st.session_state["precheck_view"] = "nav"
            st.rerun()

    with col_stats:
        s = queries.get_stats_for_module(module)
        if s and s.get("total"):
            from components.progress_bar import render_progress_bar
            render_progress_bar(s)

    st.divider()

    if st.session_state["precheck_view"] == "nav":
        _render_nav_view(module, mode)
    elif st.session_state["precheck_view"] == "service":
        from components.service_view import render_service_view
        render_service_view(module, mode, key_prefix="pc_sv")
    else:
        _render_flat_view(module, mode)
