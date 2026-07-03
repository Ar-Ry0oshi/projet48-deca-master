"""
Modal de détail d'un DECA — infos complètes + photos réseau + changelog.

Usage:
    from components.deca_detail import show_deca_detail
    show_deca_detail(marquage)   # ouvre le dialog Streamlit
"""
from pathlib import Path, PureWindowsPath

import streamlit as st

from db import queries
from config import PHOTOS_DIR


# ── Index photos (scanné une fois, mis en cache) ──────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _build_photo_index(folder_str: str) -> list[str]:
    """Retourne la liste de tous les chemins .jpg du dossier (mis en cache 10 min)."""
    folder = Path(folder_str)
    paths = []
    for ext in ("*.jpg", "*.JPG", "*.jpeg", "*.JPEG"):
        paths.extend(str(f) for f in sorted(folder.glob(ext)))
    return paths


def _find_photos(marquage: str) -> list[Path]:
    """
    Cherche les .jpg dont le nom contient le marquage (5 chiffres).
    Utilise un index mis en cache pour éviter de rescanner le dossier.
    """
    if not PHOTOS_DIR or not PHOTOS_DIR.exists():
        return []

    all_paths = _build_photo_index(str(PHOTOS_DIR))

    results, seen = [], set()
    for p in all_paths:
        f = Path(p)
        stem_norm = f.stem.replace(" ", "").replace("-", "").replace("_", "")
        if (marquage in stem_norm or marquage in f.stem) and f not in seen:
            seen.add(f)
            results.append(f)
    return results


# ── Sections du modal ─────────────────────────────────────────────────────────

def _render_tool_info(tool: dict):
    st.markdown("#### Informations outil")

    col1, col2, col3 = st.columns(3)
    col1.metric("Marquage", tool.get("marquage") or "—")
    col2.metric("État", tool.get("etat") or "—")
    col3.metric("Disponible", tool.get("disponible") or "—")

    col4, col5, col6 = st.columns(3)
    col4.metric("Famille", tool.get("famille") or "—")
    col5.metric("Sous-famille", tool.get("sous_famille") or "—")
    col6.metric("Type", tool.get("type_outil") or "—")

    col7, col8, col9 = st.columns(3)
    col7.metric("Constructeur", tool.get("constructeur") or "—")
    col8.metric("N° série", tool.get("nserie") or "—")
    col9.metric("Ref. constructeur", tool.get("ref_constructeur") or "—")

    st.divider()

    # Services actuels
    st.markdown("**Services actuels**")
    svc_cols = st.columns(5)
    for i, col in enumerate(svc_cols, 1):
        col.caption(f"Svc {i}")
        col.markdown(tool.get(f"service{i}") or "—")

    # Localisations
    st.markdown("**Localisations**")
    loc_cols = st.columns(5)
    for i, col in enumerate(loc_cols, 1):
        col.caption(f"Loc {i}")
        col.markdown(tool.get(f"localisation{i}") or "—")

    st.divider()

    # Modules & ICV
    col_mod, col_assy, col_src = st.columns(3)
    col_mod.markdown(f"**Modules** : {tool.get('modules_effective') or '—'}")
    col_assy.markdown(f"**ASSY flag** : {tool.get('assy_flag') or '—'}")
    col_src.markdown(f"**Source** : {tool.get('module_source') or '—'}")

    if tool.get("module_conflict_detail"):
        st.warning(f"Conflit sources — {tool['module_conflict_detail']}")

    if tool.get("opcodes_translated"):
        st.markdown(f"**ICV** : {tool['opcodes_translated']}")

    if tool.get("commentaire"):
        st.info(f"Commentaire outil : {tool['commentaire']}")

    if tool.get("procop"):
        st.caption(f"PROCOP : {tool['procop']}")


def _render_decision_info(marquage: str):
    dec = queries.get_decision(marquage)
    if not dec:
        st.caption("Aucune décision enregistrée.")
        return

    st.markdown("#### Décision")
    col1, col2 = st.columns(2)
    col1.metric("Statut", dec["decision"] or "—")
    col2.metric("Pré-check", dec["pre_check"] or "—")

    col3, col4 = st.columns(2)
    col3.markdown(f"**N.Service3**")
    col3.info(dec["n_service3"] or "—")
    col4.markdown(f"**N.Service4**")
    col4.info(dec["n_service4"] or "—")

    if dec["commentaire"]:
        st.markdown(f"**Commentaire** : {dec['commentaire']}")

    if dec["updated_at"]:
        st.caption(f"Mis à jour le {dec['updated_at'][:16]} par {dec['updated_by'] or '?'}")

    # ── Reset décision ────────────────────────────────────────────────────────
    if dec["decision"] in ("VALIDÉ", "EN ATTENTE"):
        st.divider()
        st.warning("Cette décision est verrouillée. Le reset la repasse à **EN COURS**.", icon="⚠️")
        col_btn, col_confirm, _ = st.columns([1, 2, 3])
        confirm = col_confirm.checkbox("Je confirme le déverrouillage", key=f"reset_confirm_{marquage}")
        if col_btn.button("🔓 Déverrouiller", key=f"reset_btn_{marquage}",
                          type="primary", disabled=not confirm, use_container_width=True):
            queries.reset_decision(marquage, reset_by="user")
            st.success(f"Décision `{marquage}` repassée à EN COURS.")
            st.rerun()


def _render_photos(marquage: str):
    if not PHOTOS_DIR or not PHOTOS_DIR.exists():
        st.markdown("#### Photos")
        st.caption("Dossier photos non accessible (réseau non connecté).")
        return

    with st.spinner("Recherche des photos…"):
        photos = _find_photos(marquage)

    st.markdown("#### Photos")

    if not photos:
        st.info(f"Aucune photo disponible pour `{marquage}` dans le dossier réseau.", icon="📷")
        return

    st.caption(f"{len(photos)} photo(s) trouvée(s).")

    # Carousel minimal via session state
    key_idx = f"photo_idx_{marquage}"
    if key_idx not in st.session_state:
        st.session_state[key_idx] = 0

    idx = st.session_state[key_idx]
    idx = max(0, min(idx, len(photos) - 1))

    if len(photos) > 1:
        col_prev, col_info, col_next = st.columns([1, 3, 1])
        if col_prev.button("◄", key=f"photo_prev_{marquage}", use_container_width=True):
            st.session_state[key_idx] = max(0, idx - 1)
            idx = st.session_state[key_idx]
        col_info.caption(f"{idx + 1} / {len(photos)} — `{photos[idx].name}`")
        if col_next.button("►", key=f"photo_next_{marquage}", use_container_width=True):
            st.session_state[key_idx] = min(len(photos) - 1, idx + 1)
            idx = st.session_state[key_idx]
    else:
        st.caption(f"`{photos[0].name}`")

    try:
        st.image(str(photos[idx]), width=None)  # pleine largeur sans use_container_width déprécié
    except Exception as e:
        st.error(f"Impossible d'afficher la photo : {e}")


def _render_changelog(marquage: str):
    logs = queries.get_changelog(marquage)
    if not logs:
        return

    with st.expander(f"Historique des modifications ({len(logs)})", expanded=False):
        for entry in logs:
            st.markdown(
                f"`{entry['changed_at'][:16]}` — **{entry['field_changed']}** : "
                f"{entry['old_value'] or '∅'} → **{entry['new_value']}** "
                f"_(par {entry['changed_by'] or '?'})_"
            )


# ── Point d'entrée ────────────────────────────────────────────────────────────

_NAV_KEY = "detail_nav"  # session state : {"marquages": [...], "idx": n}


@st.dialog("Détail DECA", width="large")
def show_deca_detail(marquage: str, marquages: list[str] | None = None):
    # ── Navigation inter-DECAs ────────────────────────────────────────────────
    if marquages and len(marquages) > 1:
        # Initialise ou met à jour la nav si on arrive sur un nouveau marquage
        nav = st.session_state.get(_NAV_KEY, {})
        if nav.get("marquages") != marquages or marquage not in marquages:
            nav = {"marquages": marquages, "idx": marquages.index(marquage) if marquage in marquages else 0}
            st.session_state[_NAV_KEY] = nav

        idx_nav = nav["idx"]
        total   = len(marquages)

        # Barre de marquages cliquables (style pagination)
        MAX_VISIBLE = 8
        start = max(0, idx_nav - MAX_VISIBLE // 2)
        end   = min(total, start + MAX_VISIBLE)
        start = max(0, end - MAX_VISIBLE)

        cols = st.columns([1] + [3] * (end - start) + [1])
        if cols[0].button("◄", key="dnav_prev", disabled=idx_nav == 0, use_container_width=True):
            st.session_state[_NAV_KEY]["idx"] = idx_nav - 1
            st.rerun(scope="fragment")
        for ci, mi in enumerate(range(start, end)):
            mq_lbl = marquages[mi]
            is_cur = mi == idx_nav
            btn_type = "primary" if is_cur else "secondary"
            if cols[ci + 1].button(mq_lbl, key=f"dnav_{mi}", type=btn_type, use_container_width=True):
                st.session_state[_NAV_KEY]["idx"] = mi
                st.rerun(scope="fragment")
        if cols[-1].button("►", key="dnav_next", disabled=idx_nav == total - 1, use_container_width=True):
            st.session_state[_NAV_KEY]["idx"] = idx_nav + 1
            st.rerun(scope="fragment")

        marquage = marquages[st.session_state[_NAV_KEY]["idx"]]
        st.divider()

    # ── Contenu fiche ─────────────────────────────────────────────────────────
    tool = queries.get_tool(marquage)
    if not tool:
        st.error(f"DECA `{marquage}` introuvable en base.")
        return

    tool = dict(tool)
    pn = tool.get("ref_constructeur") or tool.get("pn_short") or ""
    st.markdown(f"### `{marquage}` — {pn}")
    st.divider()

    tab_info, tab_photos, tab_decision = st.tabs(["Outil", "Photos", "Décision & historique"])

    with tab_info:
        _render_tool_info(tool)

    with tab_photos:
        _render_photos(marquage)

    with tab_decision:
        _render_decision_info(marquage)
        st.divider()
        _render_changelog(marquage)
