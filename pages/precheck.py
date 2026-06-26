"""
Page Pré-check — traitement PN par PN, mode solo.
Deux vues :
  - Navigation PN  : pour les multi-DECA et multi-module (1 PN à la fois)
  - Liste plate    : pour les uniques (tous les PNs d'un module dans une table)
"""
import streamlit as st
import pandas as pd

from config import MODULES, PRECHECK_FLAGS
from db import queries
from components.pn_search import pn_search_widget
from components.deca_detail import show_deca_detail
from services import svc3_options, svc1_for_svc3, svc4_options


# ── Constantes ────────────────────────────────────────────────────────────────

_SVC3_OPTS   = [""] + svc3_options()
_SVC1_LABELS = {
    "SAESB LSO - B118 - ENGINE MX / REP": "B118 — LSO",
    "SAESB MF - B24 - MODULE MX / REP":   "B24 — MF",
}
_STATUS_PRECHECK = ["EN COURS", "PRÉ-CHECK"]
_STATUS_REUNION  = ["VALIDÉ", "EN ATTENTE"]
_PRECHECK_OPTS   = [""] + PRECHECK_FLAGS[:3]


# ── Session state ─────────────────────────────────────────────────────────────

def _init_state():
    defaults = {
        "precheck_module":   MODULES[0],
        "precheck_pn_idx":   0,
        "precheck_pn":       None,
        "precheck_view":     "nav",
        "precheck_show_svc": True,
        "precheck_show_loc": False,
        "precheck_mode":     "precheck",
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


# ── Bandeau infos PN ──────────────────────────────────────────────────────────

def _render_pn_info(pn_short: str, active_df: pd.DataFrame):
    if active_df.empty:
        return
    row = active_df.iloc[0]
    modules = [m.strip() for m in (row.get("modules_effective") or "").split(",") if m.strip()]
    assy = row.get("assy_flag") or "—"
    mod_source = row.get("module_source") or "none"
    conflict = row.get("module_conflict_detail") or ""
    opcodes = row.get("opcodes_translated") or ""
    n_active = len(active_df)
    n_modules = len(modules)

    chips = st.columns([1, 1, 1, 1, 3])
    chips[0].metric("Modules", ", ".join(modules) if modules else "—")
    chips[1].metric("ASSY flag", assy)
    chips[2].metric("DECAs actifs", n_active)
    if n_modules > 1 and n_active < n_modules:
        chips[3].warning(f"⚠ {n_modules} modules, {n_active} DECAs")
    elif n_modules > 1:
        chips[3].info(f"ℹ {n_modules} modules")
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


# ── Table read-only (infos outil) ─────────────────────────────────────────────

def _render_readonly_table(active_df: pd.DataFrame, show_svc: bool, show_loc: bool):
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


# ── Formulaire de décision par DECA (avec cascade) ───────────────────────────

def _form_key(marquage: str, field: str) -> str:
    return f"pc_{marquage}_{field}"


def _init_form_state(marquage: str, dec: dict | None):
    """Initialise les valeurs du formulaire depuis la DB si pas encore en session."""
    for field, default in [
        ("svc3", (dec["n_service3"] if dec else "") or ""),
        ("bldg", ""),   # override bâtiment si service3 ambigu
        ("svc4", (dec["n_service4"] if dec else "") or ""),
        ("pre",  (dec["pre_check"]  if dec else "") or ""),
        ("dec",  (dec["decision"]   if dec else "EN COURS")),
        ("comm", (dec["commentaire"] if dec else "") or ""),
    ]:
        k = _form_key(marquage, field)
        if k not in st.session_state:
            st.session_state[k] = default


def _render_deca_form(row: dict, mode: str) -> dict:
    """
    Affiche le formulaire de décision pour un DECA.
    Retourne un dict avec les valeurs actuelles.
    """
    marquage = row["marquage"]
    dec = queries.get_decision(marquage)
    locked = bool(dec and dec["decision"] in ("VALIDÉ", "EN ATTENTE"))

    _init_form_state(marquage, dec)

    with st.container(border=True):
        header_col, badge_col = st.columns([3, 1])
        header_col.markdown(f"**`{marquage}`** — {row.get('ref_constructeur','')}")
        if locked:
            badge_col.success(dec["decision"])
        elif dec and dec.get("decision") == "PRÉ-CHECK":
            badge_col.warning("Pré-check")
        else:
            badge_col.info("En cours")

        if locked:
            # Affichage read-only
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"**N.Service3** : {dec.get('n_service3') or '—'}")
            c2.markdown(f"**Bâtiment** : {_SVC1_LABELS.get(dec.get('n_service1',''), dec.get('n_service1','') or '—')}")
            c3.markdown(f"**N.Service4** : {dec.get('n_service4') or '—'}")
            c4.markdown(f"**Commentaire** : {dec.get('commentaire') or '—'}")
            return {"marquage": marquage, "_locked": True}

        # ── Service 3 ─────────────────────────────────────────────────────────
        k_svc3 = _form_key(marquage, "svc3")
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
            k_bldg = _form_key(marquage, "bldg")
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
        k_svc4 = _form_key(marquage, "svc4")
        svc4_opts = [""] + svc4_options(svc1, svc3) if svc1 else [""]
        # Préserver la valeur si elle existe dans les nouvelles options
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
                key=_form_key(marquage, "pre"),
                disabled=locked,
            )
            # Décision auto en precheck
            auto_dec = "PRÉ-CHECK" if svc3 else "EN COURS"
            c2.caption("Décision (auto)")
            c2.markdown(f"**{auto_dec}**")
            final_dec = auto_dec
        else:
            pre = c1.selectbox(
                "Pré-check",
                options=_PRECHECK_OPTS,
                key=_form_key(marquage, "pre"),
                disabled=True,
                help="Lecture seule en mode réunion",
            )
            final_dec = c2.selectbox(
                "Décision",
                options=_STATUS_REUNION,
                key=_form_key(marquage, "dec"),
                disabled=locked,
            )

        comm = c3.text_input(
            "Commentaire",
            key=_form_key(marquage, "comm"),
            disabled=locked,
        )

    return {
        "marquage": marquage,
        "svc3": svc3,
        "svc1": svc1,
        "svc4": svc4,
        "pre_check": pre if mode == "precheck" else (dec["pre_check"] if dec else ""),
        "decision": final_dec,
        "commentaire": comm,
        "_locked": locked,
    }


# ── Vérification avant passage ────────────────────────────────────────────────

def _forms_complete(forms: list[dict], mode: str) -> tuple[bool, str]:
    for f in forms:
        if f.get("_locked"):
            continue
        if not f.get("svc3"):
            return False, f"N.Service3 manquant sur `{f['marquage']}`"
        if not f.get("svc1"):
            return False, f"Bâtiment non résolu pour `{f['marquage']}`"
        if mode == "reunion" and f.get("decision") not in ("VALIDÉ", "EN ATTENTE"):
            return False, f"Décision manquante sur `{f['marquage']}`"
    return True, ""


# ── Hors périmètre ────────────────────────────────────────────────────────────

def _render_excluded(excluded_df: pd.DataFrame):
    if excluded_df.empty:
        return
    with st.expander(f"Hors périmètre — même PN ({len(excluded_df)} DECAs)", expanded=False):
        display_cols = [c for c in [
            "marquage", "ref_constructeur", "exclusion_reason",
            "service1", "service2", "service3", "etat",
        ] if c in excluded_df.columns]
        st.dataframe(excluded_df[display_cols], hide_index=True, use_container_width=True)


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
    tools = queries.get_tools_for_module(module)
    decs = [queries.get_decision(d["marquage"]) for d in tools if d["pn_short"] == pn]
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

    if active_df.empty:
        st.info("Aucun DECA actif pour ce PN dans ce module.")
        return

    # ── Options affichage ─────────────────────────────────────────────────────
    opt1, opt2, _, _ = st.columns([1, 1, 1, 3])
    st.session_state["precheck_show_svc"] = opt1.checkbox(
        "Services actuels", value=st.session_state["precheck_show_svc"]
    )
    st.session_state["precheck_show_loc"] = opt2.checkbox(
        "Localisations", value=st.session_state["precheck_show_loc"]
    )

    # ── Table read-only ───────────────────────────────────────────────────────
    _render_readonly_table(
        active_df,
        show_svc=st.session_state["precheck_show_svc"],
        show_loc=st.session_state["precheck_show_loc"],
    )

    st.divider()
    st.markdown(f"**Décisions** — {len(active_df)} DECA(s) à traiter")

    # ── Formulaires cascade ───────────────────────────────────────────────────
    forms = []
    for _, row in active_df.iterrows():
        form_data = _render_deca_form(dict(row), mode)
        forms.append(form_data)

    # ── Copie rapide multi-DECA ───────────────────────────────────────────────
    if len(active_df) > 1:
        c1, c2, _ = st.columns([2, 2, 4])
        if c1.button("⬇ Copier Svc3 & Svc4 du 1er vers tous", use_container_width=True):
            first = forms[0]
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

    _render_excluded(excluded_df)
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

    col_hint.caption("◄ ► pour naviguer entre PNs")

    # ── Voir détail ───────────────────────────────────────────────────────────
    marquages = active_df["marquage"].tolist()
    st.divider()
    col_sel, col_btn, _ = st.columns([2, 1, 3])
    selected = col_sel.selectbox(
        "Voir détail", options=marquages,
        key=f"detail_sel_{module}_{pn}",
        label_visibility="collapsed",
    )
    if col_btn.button("🔍 Ouvrir", key=f"detail_btn_{module}_{pn}", use_container_width=True):
        show_deca_detail(selected)


# ── Vue liste plate (uniques) ─────────────────────────────────────────────────

def _render_flat_view(module: str, mode: str):
    all_rows = queries.get_tools_for_module(module)
    unique_pns = [r for r in all_rows if r["complexity_flag"] == "unique"]

    if not unique_pns:
        st.info(f"Aucun PN unique sur {module}.")
        return

    st.caption(
        f"{len(unique_pns)} PNs uniques — N.Service3 / N.Service4 / décision directement dans la table."
    )

    # On utilise un data_editor avec les vraies options de svc3
    # (service4 non filtré ici — trop de lignes pour des formulaires individuels)
    from services import svc3_options as _s3, svc1_to_svc4_all
    svc4_all = sorted({s for lst in svc1_to_svc4_all().values() for s in lst})

    flat_rows = []
    for r in unique_pns:
        dec = queries.get_decision(r["marquage"])
        flat_rows.append({
            "pn_short":         r["pn_short"],
            "marquage":         r["marquage"],
            "ref_constructeur": r.get("ref_constructeur") or "",
            "service3":         r.get("service3") or "",
            "assy_flag":        r.get("assy_flag") or "",
            "n_service3":       (dec["n_service3"] if dec else "") or "",
            "n_service4":       (dec["n_service4"] if dec else "") or "",
            "pre_check":        (dec["pre_check"]  if dec else "") or "",
            "decision":         (dec["decision"]   if dec else "EN COURS"),
            "commentaire":      (dec["commentaire"] if dec else "") or "",
            "_locked":          bool(dec and dec["decision"] in ("VALIDÉ", "EN ATTENTE")),
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
                                    "N.Service3 ✏", options=[""] + _s3(), required=False, width="medium"
                                ),
            "n_service4":       st.column_config.SelectboxColumn(
                                    "N.Service4 ✏", options=[""] + svc4_all, required=False, width="medium"
                                ),
            "pre_check":        st.column_config.SelectboxColumn(
                                    "Pré-check", options=_PRECHECK_OPTS, required=False, width="small"
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
            orig = df[df["marquage"] == row["marquage"]]["_locked"]
            if not orig.empty and orig.iloc[0]:
                continue
            svc3 = row.get("n_service3") or ""
            svc1s = svc1_for_svc3(svc3) if svc3 else []
            svc1 = svc1s[0] if svc1s else ""
            _save_deca(
                row["marquage"], row["pn_short"], module, mode,
                svc3, svc1, row.get("n_service4") or "",
                row.get("pre_check") or "", row.get("decision") or "EN COURS",
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
            show_deca_detail(selected_flat)


# ── Point d'entrée ────────────────────────────────────────────────────────────

def render():
    _init_state()

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

    if st.session_state["precheck_view"] == "nav":
        _render_nav_view(module, mode)
    else:
        _render_flat_view(module, mode)
