"""
Page Données — gestion des sources, rechargement DB et export DECA.
"""
import shutil
from pathlib import Path
from datetime import datetime
import io

import streamlit as st

from config import DATA_DIR, MODULES, SRC_DECA_PATTERNS, SRC_PANOPLY_PATTERNS, SRC_DMC_PATTERNS, SRC_ICV_PATTERNS
from scripts.reload_sources import reload, _find_file
from scripts.export_deca import build_export_df, export


def _current_files() -> dict:
    return {
        "DECA":    _find_file(DATA_DIR, SRC_DECA_PATTERNS),
        "Panoply": _find_file(DATA_DIR, SRC_PANOPLY_PATTERNS),
        "DMC/ESM": _find_file(DATA_DIR, SRC_DMC_PATTERNS),
        "ICV":     _find_file(DATA_DIR, SRC_ICV_PATTERNS),
    }


def _file_info(path: Path | None) -> str:
    if not path:
        return "— absent"
    mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
    size_kb = path.stat().st_size // 1024
    return f"`{path.name}` — {size_kb} Ko — modifié {mtime}"


def render():
    st.title("Gestion des données")

    # ── Fichiers actuels ──────────────────────────────────────────────────────
    st.subheader("Sources actuelles")
    files = _current_files()
    for label, path in files.items():
        col_label, col_info = st.columns([1, 4])
        col_label.markdown(f"**{label}**")
        col_info.markdown(_file_info(path))

    st.divider()

    # ── Remplacement de l'extract DECA ───────────────────────────────────────
    st.subheader("Remplacer l'extract DECA")
    st.caption(
        "Glisse ici le nouvel export CSV depuis DECA. "
        "Les formats février (21 col, virgule) et mai (208 col, point-virgule) sont tous les deux supportés."
    )

    uploaded = st.file_uploader(
        "Extract DECA (.csv)",
        type=["csv"],
        key="deca_upload",
        label_visibility="collapsed",
    )

    if uploaded:
        dest = DATA_DIR / uploaded.name
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Warn if replacing an existing file
        if files["DECA"] and files["DECA"].name != uploaded.name:
            st.warning(
                f"Ça va remplacer **{files['DECA'].name}** par **{uploaded.name}**. "
                "L'ancien fichier sera supprimé."
            )

        col_ok, col_cancel = st.columns([1, 5])
        if col_ok.button("Confirmer le remplacement", type="primary"):
            # Remove old DECA file(s)
            for pat in SRC_DECA_PATTERNS:
                for old in DATA_DIR.glob(pat):
                    old.unlink()

            dest.write_bytes(uploaded.getvalue())
            st.success(f"Fichier `{uploaded.name}` enregistré dans `data/`.")
            st.rerun()

    st.divider()

    # ── Remplacement des autres sources ──────────────────────────────────────
    with st.expander("Remplacer Panoply / DMC / ICV"):
        for label, patterns, key in [
            ("Panoply", SRC_PANOPLY_PATTERNS, "panoply_upload"),
            ("DMC / ESM", SRC_DMC_PATTERNS, "dmc_upload"),
            ("ICV Translation", SRC_ICV_PATTERNS, "icv_upload"),
        ]:
            up = st.file_uploader(f"{label} (.xlsx)", type=["xlsx"], key=key)
            if up:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                (DATA_DIR / up.name).write_bytes(up.getvalue())
                st.success(f"`{up.name}` enregistré.")

    st.divider()

    # ── Rechargement DB ───────────────────────────────────────────────────────
    st.subheader("Recharger la base de données")
    st.caption(
        "Relit toutes les sources et repeuple la table `tools`. "
        "Les décisions existantes ne sont **jamais** effacées."
    )

    missing = [lbl for lbl, p in files.items() if not p and lbl != "ICV"]
    if missing:
        st.error(f"Sources manquantes avant de pouvoir recharger : {', '.join(missing)}")
    else:
        if st.button("Recharger maintenant", type="primary"):
            with st.spinner("Chargement des sources…"):
                try:
                    stats = reload(DATA_DIR)
                    st.success("Rechargement terminé.")
                    col1, col2, col3, col4, col5 = st.columns(5)
                    col1.metric("Total DECAs", stats["total"])
                    col2.metric("Exclus", stats["excluded"])
                    col3.metric("Uniques", stats["unique"])
                    col4.metric("Multi-DECA", stats["multi_deca"])
                    col5.metric("Multi-module", stats["multi_module"])

                    with st.expander("Détails"):
                        st.json({
                            "no_match": stats["no_match"],
                            "conflits Panoply≠ESM": stats["conflict"],
                            "Panoply seulement": stats["panoply_only"],
                            "ESM seulement": stats["esm_only"],
                        })
                except Exception as e:
                    st.error(f"Erreur lors du rechargement : {e}")
                    raise

    st.divider()

    # ── Export DECA ───────────────────────────────────────────────────────────
    st.subheader("Export DECA")
    st.caption(
        "Génère le fichier `.xlsx` à pousser dans DECA. "
        "Seules les décisions **VALIDÉ** sont incluses."
    )

    col_mod, col_prev = st.columns([1, 4])
    with col_mod:
        export_module = st.selectbox(
            "Filtrer par module",
            options=["Tous"] + MODULES,
            key="export_module_sel",
        )
        module_filter = None if export_module == "Tous" else export_module

    # Preview
    try:
        preview_df = build_export_df(module_filter)
    except Exception as e:
        preview_df = None
        st.error(f"Erreur lors de la prévisualisation : {e}")

    if preview_df is not None and not preview_df.empty:
        with col_prev:
            st.caption(f"{len(preview_df)} décision(s) VALIDÉ à exporter.")

        with st.expander("Aperçu de l'export", expanded=False):
            st.dataframe(preview_df, hide_index=True, use_container_width=True)

        # Générer le xlsx en mémoire pour le download
        buf = io.BytesIO()
        import pandas as pd
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            preview_df.to_excel(writer, index=False, sheet_name="Décisions VALIDÉ")
        buf.seek(0)

        from datetime import timezone
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
        suffix = f"_{module_filter}" if module_filter else "_ALL"
        filename = f"export_DECA{suffix}_{ts}.xlsx"

        st.download_button(
            label=f"Télécharger l'export ({len(preview_df)} lignes)",
            data=buf,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            type="primary",
        )
    elif preview_df is not None and preview_df.empty:
        with col_prev:
            st.warning("Aucune décision VALIDÉ" + (f" sur {module_filter}" if module_filter else "") + ".")
