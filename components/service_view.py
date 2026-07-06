"""
Vue "Par service" — 3ème vue disponible dans Pré-check et Réunion.

Arborescence :
  Service 3
    └─ Service 4
         └─ PN · nb DECAs · statut pre_check / décision  [actions]
  ⬜ Non assignés
    └─ PN · nb DECAs  [assigner → svc3]

En pré-check : on peut assigner un service3/4 depuis la section "Non assignés".
En réunion   : on peut valider en bloc tous les DECAs d'un service4.
"""
from __future__ import annotations
from collections import defaultdict

import streamlit as st
import pandas as pd

from db import queries, cached as db_cached
from services import svc3_options, svc1_for_svc3, svc2_for_svc3, svc4_options, svc3_labeled_options, svc4_labeled_options, svc3_from_label, svc4_from_label
from components.deca_detail import show_deca_detail


# ── Helpers ───────────────────────────────────────────────────────────────────

def _save(marquage: str, pn_short: str, module: str, mode: str,
          svc3: str, svc1: str, svc4: str,
          pre_check: str = "", decision: str = "", commentaire: str = ""):
    existing = queries.get_decision(marquage)
    if existing and existing["decision"] in ("VALIDÉ", "EN ATTENTE"):
        return
    svc2s = svc2_for_svc3(svc3) if svc3 and svc1 else []
    final_dec = ("PRÉ-CHECK" if svc3 else "EN COURS") if mode == "precheck" else (decision or "VALIDÉ")
    queries.upsert_decision(
        marquage=marquage, pn_short=pn_short, module_context=module,
        n_service1=svc1 or None, n_service2=svc2s[0] if svc2s else None,
        n_service3=svc3 or None, n_service4=svc4 or None,
        pre_check=pre_check or None, decision=final_dec,
        commentaire=commentaire or None, updated_by="user",
    )


def _pn_status_badges(deca_rows: list[dict], mode: str) -> str:
    """Retourne une ligne de badges de statut pour tous les DECAs d'un PN."""
    if mode == "precheck":
        badges = []
        for r in deca_rows:
            pc = r.get("pre_check") or ""
            if pc == "OK":
                badges.append("✅")
            elif pc == "NOK":
                badges.append("❌")
            elif pc == "OK?":
                badges.append("❓")
            else:
                badges.append("⚪")
        return " ".join(badges)
    else:
        badges = []
        for r in deca_rows:
            dec = r.get("decision") or ""
            if dec == "VALIDÉ":
                badges.append("✅")
            elif dec == "EN ATTENTE":
                badges.append("⏳")
            elif r.get("pre_check"):
                badges.append("🔵")
            else:
                badges.append("⚪")
        return " ".join(badges)


# ── Rendu d'un groupe PN sous un service4 ─────────────────────────────────────

def _render_pn_row(pn: str, deca_rows: list[dict], module: str, mode: str,
                   svc3: str, svc1: str, key_prefix: str):
    badges = _pn_status_badges(deca_rows, mode)
    n = len(deca_rows)
    locked = all(r.get("decision") in ("VALIDÉ", "EN ATTENTE") for r in deca_rows)

    col_pn, col_open, col_n, col_badges, col_actions = st.columns([2, 0.6, 0.5, 2, 3])
    lock_icon = "🔒 " if locked else ""
    col_pn.markdown(f"**{lock_icon}{pn}**")
    first_marquage = deca_rows[0]["marquage"]
    if col_open.button("🔍", key=f"{key_prefix}_open_{pn}_{first_marquage}",
                       help=f"Ouvrir fiche {first_marquage}", use_container_width=True):
        show_deca_detail(first_marquage)
    col_n.caption(f"{n} DECA{'s' if n > 1 else ''}")
    col_badges.markdown(badges)

    if mode == "reunion" and not locked:
        # Sélecteur service4 + bouton valider ce PN
        svc4_opts = [""] + svc4_options(svc1, svc3)
        current_svc4 = deca_rows[0].get("n_service4") or ""
        sel_key = f"{key_prefix}_svc4_{pn}"
        try:
            idx = svc4_opts.index(current_svc4) if current_svc4 in svc4_opts else 0
        except ValueError:
            idx = 0
        chosen_svc4 = col_actions.selectbox(
            "Svc4", svc4_opts, index=idx,
            key=sel_key, label_visibility="collapsed",
        )
        dec_key = f"{key_prefix}_dec_{pn}"
        chosen_dec = col_actions.radio(
            "Décision", ["VALIDÉ", "EN ATTENTE"], horizontal=True,
            key=dec_key, label_visibility="collapsed",
        )
        if col_actions.button("✓ Valider", key=f"{key_prefix}_val_{pn}", use_container_width=True):
            for r in deca_rows:
                _save(r["marquage"], pn, module, mode, svc3, svc1, chosen_svc4,
                      r.get("pre_check") or "", chosen_dec, r.get("dec_commentaire") or "")
            st.rerun()

    elif mode == "precheck" and not locked:
        # Pré-check flag rapide + svc4
        svc4_opts = [""] + svc4_options(svc1, svc3)
        current_svc4 = deca_rows[0].get("n_service4") or ""
        sel_key = f"{key_prefix}_svc4pc_{pn}"
        try:
            idx = svc4_opts.index(current_svc4) if current_svc4 in svc4_opts else 0
        except ValueError:
            idx = 0
        chosen_svc4 = col_actions.selectbox(
            "Svc4", svc4_opts, index=idx,
            key=sel_key, label_visibility="collapsed",
        )
        pc_opts = ["", "OK", "OK?", "NOK"]
        current_pc = deca_rows[0].get("pre_check") or ""
        pc_key = f"{key_prefix}_pc_{pn}"
        try:
            pc_idx = pc_opts.index(current_pc)
        except ValueError:
            pc_idx = 0
        chosen_pc = col_actions.selectbox(
            "Pré-check", pc_opts, index=pc_idx,
            key=pc_key, label_visibility="collapsed",
        )
        if col_actions.button("💾 Sauver", key=f"{key_prefix}_save_{pn}", use_container_width=True):
            for r in deca_rows:
                _save(r["marquage"], pn, module, mode, svc3, svc1, chosen_svc4,
                      chosen_pc, "EN COURS", r.get("dec_commentaire") or "")
            st.rerun()


# ── Section "Non assignés" ────────────────────────────────────────────────────

def _render_unassigned(unassigned_pns: dict[str, list[dict]], module: str, mode: str, key_prefix: str):
    if not unassigned_pns:
        return

    total_pn = len(unassigned_pns)
    total_deca = sum(len(v) for v in unassigned_pns.values())

    with st.expander(f"⬜ Non assignés — {total_pn} PN · {total_deca} DECAs", expanded=True):
        svc3_opts_labeled = svc3_labeled_options()  # ["", "LSO - ...", "MF - ..."]

        for pn, deca_rows in sorted(unassigned_pns.items()):
            n = len(deca_rows)
            col_pn, col_n, col_svc3, col_svc4, col_btn = st.columns([2, 0.5, 3, 2, 1.5])
            col_pn.markdown(f"**{pn}**")
            col_n.caption(f"{n} DECA{'s' if n > 1 else ''}")

            svc3_sel = col_svc3.selectbox(
                "N.Service3", svc3_opts_labeled,
                key=f"{key_prefix}_unass_svc3_{pn}",
                label_visibility="collapsed",
            )
            svc3_plain, svc1 = svc3_from_label(svc3_sel) if isinstance(svc3_sel, str) and svc3_sel else ("", "")

            # Service4 filtré selon svc3 choisi
            svc4_opts = [""] + (svc4_options(svc1, svc3_plain) if svc3_plain else [])
            svc4_sel = col_svc4.selectbox(
                "N.Service4", svc4_opts,
                key=f"{key_prefix}_unass_svc4_{pn}",
                label_visibility="collapsed",
                disabled=not svc3_plain,
            )

            if col_btn.button("→ Assigner", key=f"{key_prefix}_unass_assign_{pn}", use_container_width=True,
                              disabled=not svc3_plain):
                for r in deca_rows:
                    _save(r["marquage"], pn, module, mode, svc3_plain, svc1, svc4_sel or "",
                          r.get("pre_check") or "", "", r.get("dec_commentaire") or "")
                st.rerun()
            st.divider()


# ── Point d'entrée ────────────────────────────────────────────────────────────

def render_service_view(module: str, mode: str, key_prefix: str = "sv"):
    """Vue arborescente Service3 → Service4 → PNs/DECAs."""

    # ── Chargement données ────────────────────────────────────────────────────
    all_rows = db_cached.get_tools_for_module(module, include_excluded=False)
    if not all_rows:
        st.info(f"Aucun DECA actif pour {module}.")
        return

    rows = [dict(r) for r in all_rows]

    # Regroupe par (n_service3, n_service4) → PN → list[deca]
    assigned: dict[str, dict[str, dict[str, list[dict]]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    unassigned: dict[str, list[dict]] = defaultdict(list)

    for r in rows:
        svc3 = r.get("n_service3") or ""
        svc4 = r.get("n_service4") or ""
        pn   = r.get("pn_short") or "?"
        if svc3:
            assigned[svc3][svc4][pn].append(r)
        else:
            unassigned[pn].append(r)

    # ── Filtre service3 ───────────────────────────────────────────────────────
    all_svc3_in_use = sorted(assigned.keys())
    filter_opts = ["Tous"] + all_svc3_in_use
    chosen_filter = st.selectbox(
        "Filtrer par service 3", filter_opts,
        key=f"{key_prefix}_svc3_filter",
        label_visibility="collapsed",
    )
    svc3_to_show = all_svc3_in_use if chosen_filter == "Tous" else [chosen_filter]

    st.caption(
        f"{len(all_svc3_in_use)} service(s) 3 assignés · "
        f"{len(unassigned)} PN(s) non assignés"
    )
    st.divider()

    # ── Arborescence svc3 → svc4 → PNs ──────────────────────────────────────
    for svc3 in svc3_to_show:
        svc4_groups = assigned[svc3]
        total_deca = sum(len(drs) for s4g in svc4_groups.values() for drs in s4g.values())
        total_pn   = sum(len(s4g) for s4g in svc4_groups.values())

        # Détermine svc1 depuis le premier DECA assigné
        first_row = next((r for s4g in svc4_groups.values() for drs in s4g.values() for r in drs), {})
        svc1 = first_row.get("n_service1") or (svc1_for_svc3(svc3)[0] if svc1_for_svc3(svc3) else "")

        with st.expander(f"**{svc3}** — {total_pn} PN · {total_deca} DECAs", expanded=True):
            for svc4, pn_groups in sorted(svc4_groups.items()):
                svc4_label = svc4 if svc4 else "*(service 4 non défini)*"
                n_pn_s4  = len(pn_groups)
                n_dec_s4 = sum(len(v) for v in pn_groups.values())

                st.markdown(
                    f"<div style='padding:4px 0 2px 12px;border-left:3px solid #4a9eff;"
                    f"margin-bottom:4px;'><b>{svc4_label}</b> "
                    f"<span style='color:grey;font-size:0.85em'>— {n_pn_s4} PN · {n_dec_s4} DECAs</span></div>",
                    unsafe_allow_html=True,
                )

                for pn, deca_rows in sorted(pn_groups.items()):
                    _render_pn_row(pn, deca_rows, module, mode, svc3, svc1,
                                   key_prefix=f"{key_prefix}_{svc3[:8]}_{svc4[:8]}")

                # Bouton valider tout le service4 (réunion uniquement)
                if mode == "reunion":
                    all_unlocked = [r for drs in pn_groups.values() for r in drs
                                    if r.get("decision") not in ("VALIDÉ", "EN ATTENTE")]
                    if all_unlocked:
                        bulk_key = f"{key_prefix}_bulk_{svc3[:10]}_{svc4[:10]}"
                        if st.button(
                            f"✅ Valider tout '{svc4_label}' ({len(all_unlocked)} DECAs)",
                            key=bulk_key, type="secondary", use_container_width=False,
                        ):
                            for r in all_unlocked:
                                _save(r["marquage"], r["pn_short"], module, mode,
                                      svc3, svc1, svc4,
                                      r.get("pre_check") or "", "VALIDÉ",
                                      r.get("dec_commentaire") or "")
                            st.rerun()

                st.markdown("---")

    # ── Non assignés ─────────────────────────────────────────────────────────
    _render_unassigned(dict(unassigned), module, mode, key_prefix)
