"""
Page Réunion — validation collective en séance.

Différences vs Pré-check :
  - Colonne pre_check visible mais non éditable (lecture seule)
  - Statuts disponibles : VALIDÉ | EN ATTENTE uniquement
  - Services (n_service3, n_service4, commentaire) restent éditables avec cascade réelle
"""
import streamlit as st
import pandas as pd

from config import MODULES
from db import queries
from components.pn_search import pn_search_widget
from components.deca_detail import show_deca_detail
from components.pn_info import render_pn_info
from components.deca_hors_perimetre import render_excluded
from components.deca_table import render_readonly_table, render_deca_table_editor
from services import svc3_options, svc1_for_svc3, svc4_options, svc2_for_svc3, svc1_to_svc4_all


# ── Constantes ────────────────────────────────────────────────────────────────

_STATUS_OPTIONS = ["VALIDÉ", "EN ATTENTE"]


# ── Session state ─────────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "reunion_module":  MODULES[0],
        "reunion_pn_idx":  0,
        "reunion_pn":      None,
        "reunion_view":    "nav",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _go_to_pn(pn_short: str, module: str):
    pns = queries.get_pn_list_for_module(module)
    st.session_state["reunion_module"] = module
    st.session_state["reu_sel_module"] = module  # force le selectbox widget
    if pn_short in pns:
        st.session_state["reunion_pn_idx"] = pns.index(pn_short)
    st.session_state["reunion_pn"] = pn_short


# ── Chargement des DECAs ──────────────────────────────────────────────────────

def _load_deca_rows(pn_short: str, module: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_rows = queries.get_tools_for_module(module, include_excluded=True)
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

def _save_deca(marquage: str, pn_short: str, module: str,
               svc3: str, svc1: str, svc4: str,
               pre_check: str, decision: str, commentaire: str):
    existing = queries.get_decision(marquage)
    if existing and existing["decision"] in ("VALIDÉ", "EN ATTENTE"):
        return

    svc2s = svc2_for_svc3(svc3) if svc3 and svc1 else []

    queries.upsert_decision(
        marquage       = marquage,
        pn_short       = pn_short,
        module_context = module,
        n_service1     = svc1 or None,
        n_service2     = svc2s[0] if svc2s else None,
        n_service3     = svc3 or None,
        n_service4     = svc4 or None,
        pre_check      = pre_check or None,
        decision       = decision or "VALIDÉ",
        commentaire    = commentaire or None,
        updated_by     = "reunion",
    )


# ── Vérification ──────────────────────────────────────────────────────────────

def _forms_complete(forms: list[dict]) -> tuple[bool, str]:
    for f in forms:
        if f.get("_locked"):
            continue
        # EN ATTENTE autorisé sans N.Service3 (à traiter plus tard)
        if f.get("decision") == "EN ATTENTE":
            continue
        if not f.get("svc3"):
            return False, f"N.Service3 manquant sur `{f['marquage']}` (mettre EN ATTENTE si non décidé)"
        if not f.get("svc1"):
            return False, f"Bâtiment non résolu pour `{f['marquage']}`"
        if f.get("decision") not in _STATUS_OPTIONS:
            return False, f"Décision invalide sur `{f['marquage']}`"
    return True, ""


# ── Statut badge ──────────────────────────────────────────────────────────────

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

    idx = max(0, min(st.session_state["reunion_pn_idx"], len(pns) - 1))
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
    render_pn_info(pn, active_df)
    st.divider()

    if active_df.empty:
        st.info("Aucun DECA actif pour ce PN dans ce module.")
        return

    st.markdown(f"**Décisions** — {len(active_df)} DECA(s)")

    forms = render_deca_table_editor(active_df, mode="reunion", key_prefix="reu")

    # Copie rapide multi-DECA
    if len(active_df) > 1:
        c1, c2, _ = st.columns([2, 2, 4])
        if c1.button("⬇ Copier Svc3 & Svc4 du 1er vers tous", use_container_width=True):
            first = forms[0]
            for row in active_df.itertuples():
                _save_deca(
                    row.marquage, pn, module,
                    first["svc3"], first["svc1"], first["svc4"],
                    first["pre_check"], first["decision"], first["commentaire"],
                )
            st.success(f"Service3={first['svc3']} / Service4={first['svc4']} copié sur {len(forms)} DECAs.")
            st.rerun()
        if c2.button("✓ Valider toutes (VALIDÉ)", use_container_width=True):
            for f in forms:
                if not f.get("_locked"):
                    _save_deca(
                        f["marquage"], pn, module,
                        f["svc3"], f["svc1"], f["svc4"],
                        f["pre_check"], "VALIDÉ", f["commentaire"],
                    )
            st.success(f"{len(forms)} DECAs validés.")
            st.rerun()

    render_excluded(excluded_df)
    st.divider()

    col_val, col_ign, col_hint = st.columns([1, 1, 3])

    if col_val.button("✓ Valider & suivant", type="primary", use_container_width=True):
        ok, msg = _forms_complete(forms)
        if not ok:
            st.error(msg)
        else:
            for f in forms:
                if not f.get("_locked"):
                    _save_deca(
                        f["marquage"], pn, module,
                        f["svc3"], f["svc1"], f["svc4"],
                        f["pre_check"], f["decision"], f["commentaire"],
                    )
            st.session_state["reunion_pn_idx"] = min(len(pns) - 1, idx + 1)
            st.rerun()

    if col_ign.button("→ Ignorer", use_container_width=True):
        for f in forms:
            if not f.get("_locked"):
                _save_deca(
                    f["marquage"], pn, module,
                    f["svc3"], f["svc1"], f["svc4"],
                    f["pre_check"], f["decision"], f["commentaire"],
                )
        st.session_state["reunion_pn_idx"] = min(len(pns) - 1, idx + 1)
        st.rerun()

    col_hint.caption("◄ ► pour naviguer entre PNs")

    # Voir détail
    marquages = active_df["marquage"].tolist()
    st.divider()
    col_sel, col_btn, _ = st.columns([2, 1, 3])
    selected = col_sel.selectbox(
        "Voir détail", options=marquages,
        key=f"reu_detail_sel_{module}_{pn}",
        label_visibility="collapsed",
    )
    if col_btn.button("🔍 Ouvrir", key=f"reu_detail_btn_{module}_{pn}", use_container_width=True):
        show_deca_detail(selected)


# ── Vue liste plate ───────────────────────────────────────────────────────────

def _render_flat_view(module: str):
    all_rows = queries.get_tools_for_module(module)
    unique_pns = [r for r in all_rows if r["complexity_flag"] == "unique"]

    if not unique_pns:
        st.info(f"Aucun PN unique sur {module}.")
        return

    st.caption(f"{len(unique_pns)} PNs uniques — décision directement dans la table.")

    svc4_all = sorted({s for lst in svc1_to_svc4_all().values() for s in lst})

    flat_rows = []
    for r in unique_pns:
        dec = queries.get_decision(r["marquage"])
        current_decision = (dec["decision"] if dec else "VALIDÉ")
        if current_decision not in _STATUS_OPTIONS:
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
            "_locked":          bool(dec and dec["decision"] in _STATUS_OPTIONS),
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
                                    "N.Service3 ✏", options=_SVC3_OPTS, required=False, width="medium"
                                ),
            "n_service4":       st.column_config.SelectboxColumn(
                                    "N.Service4 ✏", options=[""] + svc4_all, required=False, width="medium"
                                ),
            "decision":         st.column_config.SelectboxColumn(
                                    "Décision ✏", options=_STATUS_OPTIONS, required=True, width="small"
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
            svc3 = row.get("n_service3") or ""
            svc1s = svc1_for_svc3(svc3) if svc3 else []
            svc1 = svc1s[0] if svc1s else ""
            _save_deca(
                row["marquage"], row["pn_short"], module,
                svc3, svc1, row.get("n_service4") or "",
                row.get("pre_check") or "", row.get("decision") or "VALIDÉ",
                row.get("commentaire") or "",
            )
            saved += 1
        st.success(f"{saved} décisions sauvegardées.")
        st.rerun()

    # Voir détail
    all_marquages = [r["marquage"] for r in unique_pns]
    if all_marquages:
        st.divider()
        col_sel, col_btn, _ = st.columns([2, 1, 3])
        selected_flat = col_sel.selectbox(
            "Voir détail", options=all_marquages,
            key=f"reu_detail_flat_sel_{module}",
            label_visibility="collapsed",
        )
        if col_btn.button("🔍 Ouvrir", key=f"reu_detail_flat_btn_{module}", use_container_width=True):
            show_deca_detail(selected_flat)


# ── Point d'entrée ────────────────────────────────────────────────────────────

def render():
    _init_state()

    st.title("Réunion")

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
