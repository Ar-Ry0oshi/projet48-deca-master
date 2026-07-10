"""
DECA Manager — attribution des services, mode utilisateur.
PyQt6 — tableau Excel-like par PN, fiche détail, photos, export XLSX.
Partage decisions.db avec le dashboard Streamlit (lecture seule côté Streamlit).
"""
import sys
from pathlib import Path
from functools import lru_cache

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QListWidget, QListWidgetItem, QTableWidget, QTableWidgetItem,
    QComboBox, QLabel, QPushButton, QLineEdit, QHeaderView,
    QMessageBox, QFileDialog, QAbstractItemView, QStatusBar,
    QDialog, QGridLayout, QScrollArea, QMenu, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread
from PyQt6.QtGui import QColor, QFont, QPalette, QPixmap, QAction
from PyQt6.QtWidgets import QCompleter

import pandas as pd

from config import MODULES, PHOTOS_DIR
from db import queries
from services import (
    svc3_labeled_options, svc3_from_label, svc3_label,
    svc4_labeled_for_bld, svc4_from_label, svc4_label,
    svc2_for_svc3,
)

# ── Couleurs ──────────────────────────────────────────────────────────────────
C_VALIDE   = "#d4edda"
C_EN_COURS = "#ffffff"
C_LOCKED   = "#f0f0f0"

# ── Index colonnes ────────────────────────────────────────────────────────────
COL_MARQ     = 0
COL_REF      = 1
COL_SVC3     = 2
COL_SVC1     = 3
COL_SVC2     = 4
COL_SVC4     = 5
COL_SVC5     = 6
COL_LOC1     = 7
COL_LOC2     = 8
COL_LOC3     = 9
COL_LOC4     = 10
COL_LOC5     = 11
COL_ASSY     = 12
COL_CPXTY    = 13
COL_NSVC3    = 14
COL_NSVC4    = 15
COL_COMM     = 16
COL_PRECHECK = 17   # visible en mode Expert seulement
COL_STAT     = 18

PRECHECK_OPTIONS = ["", "OK", "OK?", "NOK", "New Service already defined"]

HEADERS = [
    "Marquage", "Réf constructeur", "Svc 3 actuel",
    "Svc 1", "Svc 2", "Svc 4", "Svc 5",
    "Loc 1", "Loc 2", "Loc 3", "Loc 4", "Loc 5",
    "Assemblage", "Complexité",
    "N.Service 3", "N.Service 4", "Commentaire", "Pré-check", "Statut",
]
COL_WIDTHS = [110, 140, 140, 110, 110, 110, 80, 90, 90, 90, 90, 80, 70, 100, 210, 210, 150, 100, 80]


def _ro_item(text: str, bg: str) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text) if text else "")
    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
    item.setBackground(QColor(bg))
    return item


# ── Recherche photos ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _photo_index() -> list[Path]:
    if not PHOTOS_DIR or not PHOTOS_DIR.exists():
        return []
    paths = []
    for ext in ("*.jpg", "*.JPG", "*.jpeg", "*.JPEG"):
        paths.extend(sorted(PHOTOS_DIR.glob(ext)))
    return paths


def _find_photos(marquage: str) -> list[Path]:
    results, seen = [], set()
    for f in _photo_index():
        stem = f.stem.replace(" ", "").replace("-", "").replace("_", "")
        if (marquage in stem or marquage in f.stem) and f not in seen:
            seen.add(f)
            results.append(f)
    return results


# ── Fiche outil ───────────────────────────────────────────────────────────────

class DECADetailDialog(QDialog):
    def __init__(self, marquage: str, pn_marquages: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fiche outil")
        self.resize(1000, 680)
        self._marquages = pn_marquages
        self._idx = pn_marquages.index(marquage) if marquage in pn_marquages else 0
        self._photos: list[Path] = []
        self._photo_idx = 0
        self._setup_ui()
        self._load(self._marquages[self._idx])

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # ── Barre navigation DECA ─────────────────────────────────────────
        nav = QHBoxLayout()
        self.btn_prev_deca = QPushButton("◄  DECA précédent")
        self.btn_prev_deca.clicked.connect(self._prev_deca)
        nav.addWidget(self.btn_prev_deca)
        self.lbl_deca_ctr = QLabel("")
        self.lbl_deca_ctr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font_b = QFont(); font_b.setBold(True); font_b.setPointSize(11)
        self.lbl_deca_ctr.setFont(font_b)
        nav.addWidget(self.lbl_deca_ctr, stretch=1)
        self.btn_next_deca = QPushButton("DECA suivant  ►")
        self.btn_next_deca.clicked.connect(self._next_deca)
        nav.addWidget(self.btn_next_deca)
        root.addLayout(nav)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(line)

        # ── Corps : infos gauche + photos droite ──────────────────────────
        body = QHBoxLayout()

        # Infos (scrollable)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        info_widget = QWidget()
        self.info_layout = QVBoxLayout(info_widget)
        self.info_layout.setContentsMargins(0, 0, 8, 0)
        scroll.setWidget(info_widget)
        body.addWidget(scroll, stretch=3)

        # Photos
        photo_panel = QVBoxLayout()
        self.lbl_photo = QLabel("Pas de photo")
        self.lbl_photo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_photo.setMinimumSize(320, 320)
        self.lbl_photo.setStyleSheet("border:1px solid #ccc; background:#f8f8f8;")
        photo_panel.addWidget(self.lbl_photo)

        photo_nav = QHBoxLayout()
        self.btn_prev_photo = QPushButton("◄")
        self.btn_prev_photo.setFixedWidth(40)
        self.btn_prev_photo.clicked.connect(self._prev_photo)
        self.lbl_photo_ctr = QLabel("")
        self.lbl_photo_ctr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.btn_next_photo = QPushButton("►")
        self.btn_next_photo.setFixedWidth(40)
        self.btn_next_photo.clicked.connect(self._next_photo)
        photo_nav.addWidget(self.btn_prev_photo)
        photo_nav.addWidget(self.lbl_photo_ctr, stretch=1)
        photo_nav.addWidget(self.btn_next_photo)
        photo_panel.addLayout(photo_nav)

        body.addLayout(photo_panel, stretch=2)
        root.addLayout(body)

        # ── Bouton fermer ─────────────────────────────────────────────────
        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.close)
        root.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _load(self, marquage: str):
        self.setWindowTitle(f"Fiche outil — {marquage}")
        idx = self._marquages.index(marquage) if marquage in self._marquages else 0
        self._idx = idx

        # Compteur navigation
        n = len(self._marquages)
        self.lbl_deca_ctr.setText(f"{marquage}  ({idx + 1} / {n})")
        self.btn_prev_deca.setEnabled(idx > 0)
        self.btn_next_deca.setEnabled(idx < n - 1)

        # Effacer infos précédentes
        while self.info_layout.count():
            item = self.info_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Charger données
        tool = queries.get_tool(marquage)
        dec  = queries.get_decision(marquage)
        tool_d = dict(tool) if tool else {}
        dec_d  = dict(dec)  if dec  else {}

        self._add_section("Identification")
        self._add_grid([
            ("Marquage",        tool_d.get("marquage")),
            ("Réf constructeur",tool_d.get("ref_constructeur")),
            ("PN",              tool_d.get("pn_short")),
            ("État",            tool_d.get("etat")),
            ("Disponible",      tool_d.get("disponible")),
            ("Famille",         tool_d.get("famille")),
            ("Sous-famille",    tool_d.get("sous_famille")),
            ("Type",            tool_d.get("type_outil")),
            ("Constructeur",    tool_d.get("constructeur")),
            ("N° série",        tool_d.get("nserie")),
        ])

        self._add_section("Services actuels")
        self._add_grid([
            ("Service 1", tool_d.get("service1")),
            ("Service 2", tool_d.get("service2")),
            ("Service 3", tool_d.get("service3")),
            ("Service 4", tool_d.get("service4")),
            ("Localisation 1", tool_d.get("localisation1")),
            ("Localisation 2", tool_d.get("localisation2")),
            ("Localisation 3", tool_d.get("localisation3")),
            ("Localisation 4", tool_d.get("localisation4")),
        ])

        self._add_section("Modules & flags")
        self._add_grid([
            ("Modules",      tool_d.get("modules_effective")),
            ("Source",       tool_d.get("module_source")),
            ("Assemblage",   tool_d.get("assy_flag")),
            ("Complexité",   tool_d.get("complexity_flag")),
            ("ICV",          tool_d.get("opcodes_translated")),
            ("PROCOP",       tool_d.get("procop")),
        ])

        if tool_d.get("commentaire"):
            self._add_section("Commentaire outil")
            lbl = QLabel(tool_d["commentaire"])
            lbl.setWordWrap(True)
            lbl.setStyleSheet("background:#fff8e1; padding:6px; border-radius:4px;")
            self.info_layout.addWidget(lbl)

        self._add_section("Décision")
        if dec_d:
            self._add_grid([
                ("Statut",      dec_d.get("decision")),
                ("Pré-check",   dec_d.get("pre_check")),
                ("N.Service 1", dec_d.get("n_service1")),
                ("N.Service 2", dec_d.get("n_service2")),
                ("N.Service 3", dec_d.get("n_service3")),
                ("N.Service 4", dec_d.get("n_service4")),
                ("Commentaire", dec_d.get("commentaire")),
                ("Mis à jour",  dec_d.get("updated_at")),
                ("Par",         dec_d.get("updated_by")),
            ])
        else:
            self.info_layout.addWidget(QLabel("Aucune décision enregistrée."))

        self.info_layout.addStretch()

        # Photos
        self._photos = _find_photos(marquage)
        self._photo_idx = 0
        self._show_photo()

    def _add_section(self, title: str):
        lbl = QLabel(f"<b>{title}</b>")
        lbl.setStyleSheet("margin-top:8px; color:#1a5276;")
        self.info_layout.addWidget(lbl)
        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#aaa;")
        self.info_layout.addWidget(line)

    def _add_grid(self, pairs: list[tuple]):
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(4, 2, 4, 2)
        grid.setSpacing(4)
        row = 0
        for label, value in pairs:
            if value is None or value == "":
                continue
            lbl_k = QLabel(f"<span style='color:#555;'>{label}</span>")
            lbl_v = QLabel(f"<b>{value}</b>")
            lbl_v.setWordWrap(True)
            grid.addWidget(lbl_k, row, 0)
            grid.addWidget(lbl_v, row, 1)
            row += 1
        if row == 0:
            return
        self.info_layout.addWidget(grid_w)

    def _show_photo(self):
        if not self._photos:
            self.lbl_photo.setText("Pas de photo disponible\n(dossier réseau non accessible\nou aucune photo trouvée)")
            self.lbl_photo_ctr.setText("")
            self.btn_prev_photo.setEnabled(False)
            self.btn_next_photo.setEnabled(False)
            return

        n = len(self._photos)
        self.lbl_photo_ctr.setText(f"{self._photo_idx + 1} / {n}")
        self.btn_prev_photo.setEnabled(self._photo_idx > 0)
        self.btn_next_photo.setEnabled(self._photo_idx < n - 1)

        path = self._photos[self._photo_idx]
        px = QPixmap(str(path))
        if px.isNull():
            self.lbl_photo.setText("Impossible de charger la photo.")
        else:
            self.lbl_photo.setPixmap(
                px.scaled(self.lbl_photo.size(), Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )

    def _prev_photo(self):
        self._photo_idx = max(0, self._photo_idx - 1)
        self._show_photo()

    def _next_photo(self):
        self._photo_idx = min(len(self._photos) - 1, self._photo_idx + 1)
        self._show_photo()

    def _prev_deca(self):
        if self._idx > 0:
            self._idx -= 1
            self._load(self._marquages[self._idx])

    def _next_deca(self):
        if self._idx < len(self._marquages) - 1:
            self._idx += 1
            self._load(self._marquages[self._idx])


# ── Pré-chargement photos en arrière-plan ────────────────────────────────────

class _PhotoPreloader(QThread):
    def run(self):
        _photo_index()  # chauffe le lru_cache sans bloquer l'UI


# ── Barre de filtres par colonne ─────────────────────────────────────────────

class ColumnFilterBar(QWidget):
    """Une QLineEdit par colonne, alignée sous les en-têtes de la table."""

    def __init__(self, table: QTableWidget, parent=None):
        super().__init__(parent)
        self._table = table
        self._filters: list[QLineEdit] = []

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for header in HEADERS:
            le = QLineEdit()
            le.setPlaceholderText(header[:10])
            le.setFixedHeight(22)
            le.setStyleSheet("border:1px solid #bbb; padding:1px 3px; font-size:11px;")
            le.textChanged.connect(self._apply)
            layout.addWidget(le)
            self._filters.append(le)

        layout.addStretch(0)

        table.horizontalHeader().sectionResized.connect(self._sync)

    def _sync(self, *_):
        for col, le in enumerate(self._filters):
            if self._table.isColumnHidden(col):
                le.hide()
            else:
                le.show()
                le.setFixedWidth(self._table.columnWidth(col))

    def sync_now(self):
        self._sync()

    def clear_all(self):
        for le in self._filters:
            le.blockSignals(True)
            le.clear()
            le.blockSignals(False)
        self._apply()

    def _apply(self):
        texts = [le.text().lower() for le in self._filters]
        for row in range(self._table.rowCount()):
            visible = True
            for col, text in enumerate(texts):
                if not text:
                    continue
                cell_text = ""
                item = self._table.item(row, col)
                if item:
                    cell_text = item.text().lower()
                widget = self._table.cellWidget(row, col)
                if isinstance(widget, QComboBox):
                    cell_text = widget.currentText().lower()
                elif isinstance(widget, QLineEdit):
                    cell_text = widget.text().lower()
                if text not in cell_text:
                    visible = False
                    break
            self._table.setRowHidden(row, not visible)


# ── Ligne DECA ────────────────────────────────────────────────────────────────

class DECARow:
    def __init__(self, row_data: dict, dec: dict | None):
        self.marquage   = row_data["marquage"]
        self.pn_short   = row_data["pn_short"]
        self.ref        = row_data.get("ref_constructeur") or ""
        self.svc3_cur   = row_data.get("service3") or ""
        self.svcs       = [row_data.get(f"service{i}") or "" for i in range(1, 6)]
        self.locs       = [row_data.get(f"localisation{i}") or "" for i in range(1, 6)]
        self.assy       = row_data.get("assy_flag") or ""
        self.complexity = row_data.get("complexity_flag") or ""
        self.locked       = bool(dec and dec.get("decision") == "VALIDÉ")
        self.statut       = (dec or {}).get("decision") or "EN COURS"
        self.n_svc3_plain = (dec or {}).get("n_service3") or ""
        self.n_svc4_plain = (dec or {}).get("n_service4") or ""
        self.n_svc1       = (dec or {}).get("n_service1") or ""
        self.commentaire  = (dec or {}).get("commentaire") or ""
        self.pre_check    = (dec or {}).get("pre_check") or ""
        self.combo_svc3:    QComboBox | None = None
        self.combo_svc4:    QComboBox | None = None
        self.edit_comm:     QLineEdit | None = None
        self.combo_precheck: QComboBox | None = None


# ── Table DECA ────────────────────────────────────────────────────────────────

class DECATable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._svc3_opts = svc3_labeled_options()
        self._rows: list[DECARow] = []

        self.setColumnCount(len(HEADERS))
        self.setHorizontalHeaderLabels(HEADERS)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.setShowGrid(True)
        self.setSortingEnabled(True)

        for col, w in enumerate(COL_WIDTHS):
            self.setColumnWidth(col, w)

        self.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background:#dce6f1; font-weight:bold; "
            "padding:4px; border:1px solid #bbb; }"
        )

        # Menu cacher/afficher colonnes
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._column_menu)

        # Double-clic → fiche
        self.doubleClicked.connect(self._on_double_click)

        # Clic droit sur une ligne → menu contextuel
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._row_menu)

    def _row_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid() or index.row() >= len(self._rows):
            return
        drow = self._rows[index.row()]
        menu = QMenu(self)

        if not drow.locked:
            act_copy = menu.addAction("↓  Appliquer N.Service 3/4 à toutes les lignes")
        else:
            act_copy = None

        act_unlock = menu.addAction("🔓  Déverrouiller cette ligne")
        if not drow.locked:
            act_unlock.setEnabled(False)

        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if not chosen:
            return

        if chosen is act_copy:
            self.apply_svc3_to_all(drow)
            return

        if chosen is act_unlock:
            confirm = QMessageBox.question(
                self, "Déverrouiller",
                f"Déverrouiller  {drow.marquage}  ?\n\nLa décision VALIDÉ sera remise en EN COURS.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if confirm != QMessageBox.StandardButton.Yes:
                return
            queries.reset_decision(drow.marquage, reset_by="manager_user")
            parent = self.parent()
            while parent and not isinstance(parent, MainWindow):
                parent = parent.parent()
            if parent:
                parent._on_pn_selected(parent.pn_list.currentItem(), None)

    def _column_menu(self, pos):
        menu = QMenu(self)
        for col, header in enumerate(HEADERS):
            action = menu.addAction(header)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(col))
            action.setData(col)
        chosen = menu.exec(self.horizontalHeader().mapToGlobal(pos))
        if chosen:
            col = chosen.data()
            self.setColumnHidden(col, not self.isColumnHidden(col))

    def _on_double_click(self, index):
        row = index.row()
        if row < len(self._rows):
            self._open_detail(self._rows[row].marquage)

    def _open_detail(self, marquage: str):
        all_mqs = [r.marquage for r in self._rows]
        dlg = DECADetailDialog(marquage, all_mqs, self)
        dlg.exec()

    def load_pn(self, pn: str, module: str):
        self.setSortingEnabled(False)
        self._rows.clear()
        self.setRowCount(0)

        all_tools = queries.get_tools_for_module(module)
        active = [dict(r) for r in all_tools if r["pn_short"] == pn and not r["is_excluded"]]
        decisions = queries.get_decisions_batch_for_module(module)

        for rd in active:
            dec = decisions.get(rd["marquage"])
            drow = DECARow(rd, dec)
            self._rows.append(drow)
            self._insert_row(drow)

        self.setSortingEnabled(True)

    def _insert_row(self, drow: DECARow):
        r = self.rowCount()
        self.insertRow(r)
        self.setRowHeight(r, 34)

        bg = C_VALIDE if drow.statut == "VALIDÉ" else (C_LOCKED if drow.locked else C_EN_COURS)

        self.setItem(r, COL_MARQ,  _ro_item(drow.marquage, bg))
        self.setItem(r, COL_REF,   _ro_item(drow.ref, bg))
        self.setItem(r, COL_SVC3,  _ro_item(drow.svc3_cur, bg))
        self.setItem(r, COL_SVC1,  _ro_item(drow.svcs[0], bg))
        self.setItem(r, COL_SVC2,  _ro_item(drow.svcs[1], bg))
        self.setItem(r, COL_SVC4,  _ro_item(drow.svcs[3], bg))
        self.setItem(r, COL_SVC5,  _ro_item(drow.svcs[4], bg))
        self.setItem(r, COL_LOC1,  _ro_item(drow.locs[0], bg))
        self.setItem(r, COL_LOC2,  _ro_item(drow.locs[1], bg))
        self.setItem(r, COL_LOC3,  _ro_item(drow.locs[2], bg))
        self.setItem(r, COL_LOC4,  _ro_item(drow.locs[3], bg))
        self.setItem(r, COL_LOC5,  _ro_item(drow.locs[4], bg))
        self.setItem(r, COL_ASSY,  _ro_item(drow.assy, bg))
        self.setItem(r, COL_CPXTY, _ro_item(drow.complexity, bg))
        self.setItem(r, COL_STAT, _ro_item(drow.statut, bg))

        if drow.locked:
            svc3_d = svc3_label(drow.n_svc3_plain, drow.n_svc1) if drow.n_svc3_plain and drow.n_svc1 else drow.n_svc3_plain
            svc4_d = svc4_label(drow.n_svc4_plain, drow.n_svc1) if drow.n_svc4_plain and drow.n_svc1 else drow.n_svc4_plain
            self.setItem(r, COL_NSVC3,    _ro_item(svc3_d, bg))
            self.setItem(r, COL_NSVC4,    _ro_item(svc4_d, bg))
            self.setItem(r, COL_COMM,     _ro_item(drow.commentaire, bg))
            self.setItem(r, COL_PRECHECK, _ro_item(drow.pre_check, bg))
            return

        cb3 = self._make_combo(self._svc3_opts)
        if drow.n_svc3_plain and drow.n_svc1:
            lbl = svc3_label(drow.n_svc3_plain, drow.n_svc1)
            idx = cb3.findText(lbl)
            if idx >= 0:
                cb3.setCurrentIndex(idx)

        cb4 = self._make_combo([])
        self._fill_svc4(cb4, drow.n_svc1, drow.n_svc3_plain, drow.n_svc4_plain)

        ed = QLineEdit(drow.commentaire)
        ed.setFrame(False)
        ed.setStyleSheet("padding: 2px 4px;")

        cb_pc = QComboBox()
        cb_pc.addItems(PRECHECK_OPTIONS)
        if drow.pre_check in PRECHECK_OPTIONS:
            cb_pc.setCurrentText(drow.pre_check)

        drow.combo_svc3     = cb3
        drow.combo_svc4     = cb4
        drow.edit_comm      = ed
        drow.combo_precheck = cb_pc

        cb3.currentTextChanged.connect(lambda txt, d=drow: self._on_svc3_change(txt, d))

        self.setCellWidget(r, COL_NSVC3,    cb3)
        self.setCellWidget(r, COL_NSVC4,    cb4)
        self.setCellWidget(r, COL_COMM,     ed)
        self.setCellWidget(r, COL_PRECHECK, cb_pc)

    @staticmethod
    def _make_combo(items: list[str]) -> QComboBox:
        cb = QComboBox()
        cb.setEditable(True)
        cb.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        cb.addItems(items)
        completer = QCompleter(items)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        cb.setCompleter(completer)

        def _autofill():
            typed = cb.lineEdit().text().strip().lower()
            if not typed:
                return
            for i in range(cb.count()):
                if typed in cb.itemText(i).lower():
                    cb.setCurrentIndex(i)
                    return
            # Aucun match : remet le texte de l'item actuel
            cb.lineEdit().setText(cb.currentText())

        cb.lineEdit().returnPressed.connect(_autofill)
        cb.lineEdit().editingFinished.connect(_autofill)
        return cb

    def _on_svc3_change(self, label: str, drow: DECARow):
        svc3_plain, svc1 = svc3_from_label(label)
        drow.n_svc3_plain = svc3_plain
        drow.n_svc1 = svc1
        self._fill_svc4(drow.combo_svc4, svc1, svc3_plain, "")

    def _fill_svc4(self, cb4: QComboBox | None, svc1: str, svc3: str, current: str):
        if cb4 is None:
            return
        cb4.blockSignals(True)
        cb4.clear()
        opts = svc4_labeled_for_bld(svc1, svc3) if svc1 else [""]
        cb4.addItems(opts)
        completer = QCompleter(opts)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        cb4.setCompleter(completer)
        if current and svc1:
            lbl = svc4_label(current, svc1)
            idx = cb4.findText(lbl)
            if idx >= 0:
                cb4.setCurrentIndex(idx)
        cb4.blockSignals(False)

    def get_form_data(self) -> list[dict]:
        result = []
        for drow in self._rows:
            if drow.locked:
                continue
            svc3_lbl = drow.combo_svc3.currentText() if drow.combo_svc3 else ""
            svc3_plain, svc1 = svc3_from_label(svc3_lbl)
            svc4_lbl = drow.combo_svc4.currentText() if drow.combo_svc4 else ""
            svc4_plain = svc4_from_label(svc4_lbl)
            svc2s = svc2_for_svc3(svc3_plain) if svc3_plain else []
            result.append({
                "marquage":    drow.marquage,
                "pn_short":    drow.pn_short,
                "svc3":        svc3_plain,
                "svc1":        svc1,
                "svc2":        svc2s[0] if svc2s else "",
                "svc4":        svc4_plain,
                "commentaire": drow.edit_comm.text() if drow.edit_comm else "",
                "pre_check":   drow.combo_precheck.currentText() if drow.combo_precheck else "",
            })
        return result

    def apply_svc3_to_all(self, source_drow: DECARow):
        """Copie N.Service 3 et 4 de source_drow vers toutes les lignes non verrouillées."""
        svc3_txt = source_drow.combo_svc3.currentText() if source_drow.combo_svc3 else ""
        svc4_txt = source_drow.combo_svc4.currentText() if source_drow.combo_svc4 else ""
        for drow in self._rows:
            if drow is source_drow or drow.locked or not drow.combo_svc3:
                continue
            idx3 = drow.combo_svc3.findText(svc3_txt)
            if idx3 >= 0:
                drow.combo_svc3.setCurrentIndex(idx3)
            if drow.combo_svc4 and svc4_txt:
                idx4 = drow.combo_svc4.findText(svc4_txt)
                if idx4 >= 0:
                    drow.combo_svc4.setCurrentIndex(idx4)

    def open_detail_for_selected(self):
        rows = self.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row < len(self._rows):
            self._open_detail(self._rows[row].marquage)


# ── Fenêtre principale ────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DECA Manager — Attribution des services")
        self.resize(1400, 760)
        self._module = MODULES[0]
        self._current_pn: str | None = None
        self._pn_items: list[QListWidgetItem] = []
        self._expert_mode = False
        self._setup_ui()
        self._load_module(self._module)
        # Pré-charger l'index photos en arrière-plan
        self._preloader = _PhotoPreloader()
        self._preloader.start()

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Barre supérieure ──────────────────────────────────────────────
        top = QHBoxLayout()
        top.addWidget(QLabel("Module :"))
        self.cb_module = QComboBox()
        self.cb_module.addItems(MODULES)
        self.cb_module.currentTextChanged.connect(self._load_module)
        top.addWidget(self.cb_module)
        top.addSpacing(20)
        self.lbl_stats = QLabel("")
        font_b = QFont(); font_b.setBold(True)
        self.lbl_stats.setFont(font_b)
        top.addWidget(self.lbl_stats)
        top.addSpacing(20)
        self.btn_mode = QPushButton("Mode : Suggestion")
        self.btn_mode.setFixedHeight(32)
        self.btn_mode.setFixedWidth(190)
        self.btn_mode.setCheckable(True)
        self.btn_mode.setStyleSheet(
            "QPushButton { border:2px solid #888; border-radius:4px; padding:0 10px; }"
            "QPushButton:checked { background:#1f497d; color:white; border-color:#1f497d; font-weight:bold; }"
        )
        self.btn_mode.clicked.connect(self._toggle_mode)
        top.addWidget(self.btn_mode)
        top.addStretch()
        btn_export_full = QPushButton("📋  Export complet du module")
        btn_export_full.setFixedHeight(32)
        btn_export_full.setToolTip("Exporte TOUS les DECAs (validés, en attente, sans décision) avec statut, horodatage et commentaire")
        btn_export_full.clicked.connect(self._export_full)
        top.addWidget(btn_export_full)

        btn_export_model = QPushButton("📥  Export modèle d'import")
        btn_export_model.setFixedHeight(32)
        btn_export_model.setStyleSheet(
            "QPushButton { background:#0078d4; color:white; font-weight:bold; border-radius:4px; padding:0 10px; }"
            "QPushButton:hover { background:#005fa3; }"
        )
        btn_export_model.setToolTip("Exporte la liste des marquages au format import : Marquage + colonnes [Service]")
        btn_export_model.clicked.connect(self._export_model)
        top.addWidget(btn_export_model)
        root.addLayout(top)

        # ── Splitter ──────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Panneau gauche — largeur fixe pour que les PNs soient toujours visibles
        left = QWidget()
        left.setFixedWidth(300)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 6, 0)
        ll.addWidget(QLabel("<b>PNs du module</b>"))
        self.search_pn = QLineEdit()
        self.search_pn.setPlaceholderText("🔍 Rechercher un PN…")
        self.search_pn.textChanged.connect(self._filter_list)
        ll.addWidget(self.search_pn)
        self.cb_filter = QComboBox()
        self.cb_filter.addItems(["Tous", "À traiter", "Traités"])
        self.cb_filter.currentTextChanged.connect(self._filter_list)
        ll.addWidget(self.cb_filter)
        self.pn_list = QListWidget()
        self.pn_list.currentItemChanged.connect(self._on_pn_selected)
        ll.addWidget(self.pn_list)

        # Panneau droit
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)

        # En-tête PN
        hdr = QHBoxLayout()
        self.lbl_pn = QLabel("← Sélectionne un PN")
        font_h = QFont(); font_h.setBold(True); font_h.setPointSize(11)
        self.lbl_pn.setFont(font_h)
        hdr.addWidget(self.lbl_pn, stretch=1)
        rl.addLayout(hdr)

        # Table + barre de filtres
        self.table = DECATable()
        self.table.setMinimumWidth(100)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setColumnHidden(COL_PRECHECK, True)  # caché par défaut (mode utilisateur)
        self.col_filters = ColumnFilterBar(self.table)
        rl.addWidget(self.col_filters)
        rl.addWidget(self.table)

        hint = QLabel("💡 Clic droit sur l'en-tête → cacher/afficher colonnes  ·  Double-clic → fiche outil")
        hint.setStyleSheet("color:#888; font-size:11px;")
        rl.addWidget(hint)

        # Boutons action
        btn_row = QHBoxLayout()
        self.btn_fiche = QPushButton("📋  Fiche outil")
        self.btn_fiche.setFixedHeight(36)
        self.btn_fiche.clicked.connect(self.table.open_detail_for_selected)
        btn_row.addWidget(self.btn_fiche)

        self.btn_valider = QPushButton("✓  Valider & suivant")
        self.btn_valider.setFixedHeight(36)
        self.btn_valider.setStyleSheet(
            "QPushButton { background:#21c354; color:white; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#1aad47; }"
        )
        self.btn_valider.clicked.connect(self._valider)
        btn_row.addWidget(self.btn_valider)

        self.btn_next = QPushButton("PN suivant  →")
        self.btn_next.setFixedHeight(36)
        self.btn_next.clicked.connect(self._next_pn)
        btn_row.addWidget(self.btn_next)
        btn_row.addStretch()
        rl.addLayout(btn_row)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 1100])
        root.addWidget(splitter)
        self.setStatusBar(QStatusBar())

    # ── Mode Expert/Utilisateur ───────────────────────────────────────────────

    def _toggle_mode(self):
        self._expert_mode = self.btn_mode.isChecked()
        if self._expert_mode:
            self.btn_mode.setText("Mode : Confirmation  🔬")
            self.btn_valider.setText("📋  Pré-checker & suivant")
            self.btn_valider.setStyleSheet(
                "QPushButton { background:#1f497d; color:white; font-weight:bold; border-radius:4px; }"
                "QPushButton:hover { background:#163a69; }"
            )
        else:
            self.btn_mode.setText("Mode : Suggestion")
            self.btn_valider.setText("✓  Valider & suivant")
            self.btn_valider.setStyleSheet(
                "QPushButton { background:#21c354; color:white; font-weight:bold; border-radius:4px; }"
                "QPushButton:hover { background:#1aad47; }"
            )
        # Affiche/cache la colonne Pré-check
        self.table.setColumnHidden(COL_PRECHECK, not self._expert_mode)

    # ── Chargement module ─────────────────────────────────────────────────────

    def _load_module(self, module: str):
        self._module = module
        self._current_pn = None
        self.lbl_pn.setText("← Sélectionne un PN")
        self.table.setRowCount(0)
        self._reload_pn_list()
        self._update_stats()

    def _reload_pn_list(self):
        self.pn_list.clear()
        self._pn_items.clear()

        all_tools = queries.get_tools_for_module(self._module)
        decisions = queries.get_decisions_batch_for_module(self._module)

        # Agrège par PN : marquages, complexité, nb DECAs
        pn_data: dict[str, dict] = {}
        for r in all_tools:
            pn = r["pn_short"]
            if pn not in pn_data:
                pn_data[pn] = {
                    "marquages": [],
                    "complexity": r["complexity_flag"] or "unique",
                }
            pn_data[pn]["marquages"].append(r["marquage"])

        # Tri par groupe puis par nb de DECAs décroissant
        GROUPS = [
            ("multi_deca",   "── Multi-DECAs ──────────────"),
            ("multi_module", "── Multi-modules ────────────"),
            ("unique",       "── DECA unique ──────────────"),
            ("no_match",     "── Sans module ──────────────"),
        ]

        def _add_separator(label: str):
            sep = QListWidgetItem(label)
            sep.setFlags(Qt.ItemFlag.NoItemFlags)
            sep.setForeground(QColor("#666666"))
            font = QFont(); font.setBold(True); font.setPointSize(8)
            sep.setFont(font)
            sep.setBackground(QColor("#e8e8e8"))
            self.pn_list.addItem(sep)

        for complexity, label in GROUPS:
            pns_in_group = sorted(
                [pn for pn, d in pn_data.items() if d["complexity"] == complexity],
                key=lambda pn: -len(pn_data[pn]["marquages"])
            )
            if not pns_in_group:
                continue
            # Progression du groupe
            g_done  = sum(1 for pn in pns_in_group
                          if all(decisions.get(m, {}).get("decision") in ("VALIDÉ", "EN ATTENTE")
                                 for m in pn_data[pn]["marquages"]))
            g_total = len(pns_in_group)
            _add_separator(f"{label}  {g_done}/{g_total}")
            for pn in pns_in_group:
                mqs = pn_data[pn]["marquages"]
                statuses = [decisions[m]["decision"] for m in mqs if m in decisions]
                done = bool(statuses) and all(s in ("VALIDÉ", "EN ATTENTE") for s in statuses)
                count = len(mqs)
                label_pn = f"{'✓' if done else ' '}  {pn}  ({count})"
                item = QListWidgetItem(label_pn)
                item.setData(Qt.ItemDataRole.UserRole, {"pn": pn, "done": done})
                item.setBackground(QColor(C_VALIDE if done else C_EN_COURS))
                self.pn_list.addItem(item)
                self._pn_items.append(item)

        self._filter_list()

    def _filter_list(self):
        search = self.search_pn.text().upper()
        status = self.cb_filter.currentText()
        for item in self._pn_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            done = data["done"]
            match = (not search) or (search in data["pn"].upper())
            if status == "À traiter" and done:
                match = False
            if status == "Traités" and not done:
                match = False
            item.setHidden(not match)
        # Cacher les séparateurs dont tous les enfants sont cachés
        for i in range(self.pn_list.count()):
            it = self.pn_list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) is not None:
                continue  # c'est un PN, pas un séparateur
            # Cherche si au moins un PN visible suit ce séparateur
            visible = False
            for j in range(i + 1, self.pn_list.count()):
                nxt = self.pn_list.item(j)
                if nxt.data(Qt.ItemDataRole.UserRole) is None:
                    break  # prochain séparateur
                if not nxt.isHidden():
                    visible = True
                    break
            it.setHidden(not visible)

    def _update_stats(self):
        total = len(self._pn_items)
        done  = sum(1 for it in self._pn_items if it.data(Qt.ItemDataRole.UserRole)["done"])
        self.lbl_stats.setText(f"{done} / {total} PNs traités")

    # ── Navigation PN ─────────────────────────────────────────────────────────

    def _on_pn_selected(self, item: QListWidgetItem, _):
        if not item:
            return
        pn = item.data(Qt.ItemDataRole.UserRole)["pn"]
        self._current_pn = pn
        self.lbl_pn.setText(f"PN :  {pn}")
        self.col_filters.clear_all()
        self.table.load_pn(pn, self._module)
        self.col_filters.sync_now()

    def _next_pn(self):
        for i in range(self.pn_list.count()):
            it = self.pn_list.item(i)
            if it.isHidden() or it.data(Qt.ItemDataRole.UserRole) is None:
                continue
            if it.data(Qt.ItemDataRole.UserRole)["pn"] == self._current_pn:
                for j in range(i + 1, self.pn_list.count()):
                    nxt = self.pn_list.item(j)
                    if not nxt.isHidden() and nxt.data(Qt.ItemDataRole.UserRole) is not None:
                        self.pn_list.setCurrentItem(nxt)
                        return
                break

    # ── Validation ────────────────────────────────────────────────────────────

    def _valider(self):
        if not self._current_pn:
            QMessageBox.warning(self, "Aucun PN", "Sélectionne d'abord un PN.")
            return

        forms = self.table.get_form_data()
        if not forms:
            QMessageBox.information(self, "Déjà validé", "Toutes les lignes sont déjà validées.")
            self._next_pn()
            return

        missing = [f["marquage"] for f in forms if not f["svc3"]]
        if missing:
            QMessageBox.warning(
                self, "N.Service 3 manquant",
                "N.Service 3 obligatoire pour :\n" + "\n".join(missing)
            )
            return

        decision_val = "EN ATTENTE" if self._expert_mode else "VALIDÉ"
        updated_by   = "manager_expert" if self._expert_mode else "manager_user"

        for f in forms:
            existing = queries.get_decision(f["marquage"])
            if existing and existing["decision"] == "EN ATTENTE":
                queries.reset_decision(f["marquage"], reset_by=updated_by)
            queries.upsert_decision(
                marquage       = f["marquage"],
                pn_short       = f["pn_short"],
                module_context = self._module,
                n_service1     = f["svc1"] or None,
                n_service2     = f["svc2"] or None,
                n_service3     = f["svc3"] or None,
                n_service4     = f["svc4"] or None,
                pre_check      = f["pre_check"] or None,
                decision       = decision_val,
                commentaire    = f["commentaire"] or None,
                updated_by     = updated_by,
            )

        label = "mis en attente" if self._expert_mode else "validé(s)"
        self.statusBar().showMessage(
            f"{'📋' if self._expert_mode else '✓'}  {len(forms)} DECA(s) {label} pour {self._current_pn}.", 4000
        )
        self._reload_pn_list()
        self._update_stats()
        self._next_pn()

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_full(self):
        """Export complet : tous les DECAs du module, peu importe le statut."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export complet du module",
            f"export_complet_{self._module}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        rows = queries.get_all_tools_for_export(self._module)
        if not rows:
            QMessageBox.information(self, "Export vide", "Aucun outil trouvé pour ce module.")
            return
        df = pd.DataFrame([dict(r) for r in rows])
        df.rename(columns={
            "marquage": "Marquage", "pn_short": "PN", "ref_constructeur": "Réf constructeur",
            "service1": "Svc 1", "service2": "Svc 2", "service3": "Svc 3 actuel",
            "service4": "Svc 4", "service5": "Svc 5",
            "localisation1": "Loc 1", "localisation2": "Loc 2", "localisation3": "Loc 3",
            "localisation4": "Loc 4", "assy_flag": "Assemblage",
            "complexity_flag": "Complexité", "modules_effective": "Modules",
            "decision": "Statut", "n_service1": "N.Service 1", "n_service2": "N.Service 2",
            "n_service3": "N.Service 3", "n_service4": "N.Service 4",
            "pre_check": "Pré-check", "dec_commentaire": "Commentaire décision",
            "updated_at": "Horodatage", "updated_by": "Mis à jour par",
        }, inplace=True)
        df.to_excel(path, index=False)
        self.statusBar().showMessage(f"Export complet réussi → {path}", 5000)

    def _export_model(self):
        """Export modèle d'import : Marquage + colonnes [Service] vides."""
        path, _ = QFileDialog.getSaveFileName(
            self, "Export modèle d'import",
            f"modele_import_{self._module}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        rows = queries.get_all_tools_for_export(self._module)
        if not rows:
            QMessageBox.information(self, "Export vide", "Aucun outil trouvé pour ce module.")
            return
        df = pd.DataFrame([dict(r) for r in rows])[["marquage"]]
        df.columns = ["Marquage"]
        df["[Service] Service1"] = ""
        df["[Service] Service2"] = ""
        df["[Service] Service3"] = ""
        df["[Service] Service4"] = ""
        df.to_excel(path, index=False)
        self.statusBar().showMessage(f"Modèle d'import réussi → {path}", 5000)


# ── Entrée ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor("#f5f5f5"))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Base,            QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor("#f0f0f0"))
    palette.setColor(QPalette.ColorRole.Text,            QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Button,          QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor("#0078d4"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor("#000000"))
    app.setPalette(palette)

    win = MainWindow()
    win.showMaximized()
    sys.exit(app.exec())
