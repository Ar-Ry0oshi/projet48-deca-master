"""
DECA Manager — attribution des services, mode utilisateur.
PyQt6 — tableau Excel-like par PN, fiche détail, photos, export XLSX.
Partage decisions.db avec le dashboard Streamlit (lecture seule côté Streamlit).
"""
import shutil
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
from PyQt6.QtCore import Qt, QThread, QObject, QEvent, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette, QPixmap, QAction, QShortcut, QKeySequence
from PyQt6.QtWidgets import QCompleter

import pandas as pd

from config import MODULES, PHOTOS_DIR, DATA_DIR
from db import queries
from services import (
    svc3_labeled_options, svc3_from_label, svc3_label,
    svc4_labeled_for_bld, svc4_from_label, svc4_label,
    svc2_for_svc3, is_valid_in_ref,
)

# ── Couleurs ──────────────────────────────────────────────────────────────────
C_VALIDE      = "#d4edda"   # vert clair — table DECA
C_PN_VALIDE   = "#6dbf7e"   # vert intense — liste PN (tout VALIDÉ)
C_PN_PCHECK   = "#fce8b2"   # jaune orangé — liste PN (EN ATTENTE / pré-checké)
C_EN_COURS    = "#ffffff"
C_LOCKED      = "#f0f0f0"
C_AUTO_FILL   = "#ede9fe"   # lavande — service source valide, à adopter
C_LENT        = "#dbeafe"   # bleu clair — outil en prêt (Loaned)

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
            lbl.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse |
                Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
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
            lbl_v.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse |
                Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
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


# ── Filtre clavier pour les cellules éditables ────────────────────────────────

class _CellKeyFilter(QObject):
    """Intercepte les raccourcis clavier dans les combos/lineedits de la table."""

    def __init__(self, table, row_idx: int, col: int):
        super().__init__(table)
        self._table = table
        self._row_idx = row_idx
        self._col = col

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.KeyPress:
            return False
        key  = event.key()
        mods = event.modifiers()
        ctrl  = Qt.KeyboardModifier.ControlModifier
        shift = Qt.KeyboardModifier.ShiftModifier
        alt   = Qt.KeyboardModifier.AltModifier

        # Alt+↓ / Alt+↑ → ligne DECA suivante / précédente
        if mods == alt:
            if key == Qt.Key.Key_Down:
                self._table._move_row(self._row_idx + 1)
                return True
            if key == Qt.Key.Key_Up:
                self._table._move_row(self._row_idx - 1)
                return True

        # Ctrl+Shift+D → appliquer à toutes les lignes
        if mods == (ctrl | shift) and key == Qt.Key.Key_D:
            if self._row_idx < len(self._table._rows):
                self._table.apply_svc3_to_all(self._table._rows[self._row_idx])
            return True

        # Ctrl+D → fill down (copier ligne au-dessus)
        if mods == ctrl and key == Qt.Key.Key_D:
            self._table._fill_down(self._row_idx)
            return True

        # Tab → ordre personnalisé svc3 → svc4 → comm → svc3 ligne suivante
        if key == Qt.Key.Key_Tab and not mods:
            self._table._tab_next(self._row_idx, self._col)
            return True
        if key == Qt.Key.Key_Backtab:
            self._table._tab_prev(self._row_idx, self._col)
            return True

        return False


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
        self.locked       = bool(dec and dec.get("decision") in ("VALIDÉ", "EN PRÊT"))
        self.statut       = (dec or {}).get("decision") or "EN COURS"
        self.n_svc3_plain = (dec or {}).get("n_service3") or ""
        self.n_svc4_plain = (dec or {}).get("n_service4") or ""
        self.n_svc1       = (dec or {}).get("n_service1") or ""
        self.commentaire  = (dec or {}).get("commentaire") or ""
        self.pre_check    = (dec or {}).get("pre_check") or ""
        # True si le service source (S1-4 de l'extract) est valide dans le référentiel
        # ET que la décision n'a pas encore de N.Service 3 → candidat "adopter source"
        s2_src = self.svcs[1]
        self.source_auto_fillable: bool = (
            not self.n_svc3_plain
            and is_valid_in_ref(self.svcs[0], s2_src, self.svc3_cur, self.svcs[3])
        )

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
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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

    def _drow_at(self, row: int) -> "DECARow | None":
        """Retourne le DECARow correspondant au rang visuel/modèle, robuste au tri."""
        item = self.item(row, COL_MARQ)
        if item is None:
            return None
        mq = item.data(Qt.ItemDataRole.UserRole)
        for d in self._rows:
            if d.marquage == mq:
                return d
        return None

    def _row_menu(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return
        drow = self._drow_at(index.row())
        if drow is None:
            return
        menu = QMenu(self)

        selected_rows = sorted({idx.row() for idx in self.selectedIndexes()})
        sel_drows = [d for r in selected_rows if (d := self._drow_at(r)) is not None]
        n_sel = sum(1 for d in sel_drows if not d.locked and d is not drow)

        n_auto = sum(1 for d in self._rows if not d.locked and d.source_auto_fillable)

        if not drow.locked:
            act_copy_sel = menu.addAction(
                f"↓  Appliquer N.Service 3/4 aux {n_sel} ligne(s) sélectionnée(s)"
                if n_sel else "↓  Appliquer N.Service 3/4 aux lignes sélectionnées"
            )
            act_copy_sel.setEnabled(n_sel > 0)
            act_copy_all = menu.addAction("↓  Appliquer N.Service 3/4 à toutes les lignes")
            menu.addSeparator()
            act_adopt_one = menu.addAction("✨  Adopter service source (cette ligne)")
            act_adopt_one.setEnabled(drow.source_auto_fillable)
            act_adopt_all = menu.addAction(
                f"✨  Adopter service source pour toutes les lignes ({n_auto} candidats)"
            )
            act_adopt_all.setEnabled(n_auto > 0)
        else:
            act_copy_sel = None
            act_copy_all = None
            act_adopt_one = None
            act_adopt_all = None

        act_unlock = menu.addAction("🔓  Déverrouiller cette ligne")
        if not drow.locked:
            act_unlock.setEnabled(False)

        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if not chosen:
            return

        if chosen is act_copy_sel:
            target_rows = [d for d in sel_drows if d is not drow and not d.locked]
            self.apply_svc3_to_rows(drow, target_rows)
            return

        if chosen is act_copy_all:
            self.apply_svc3_to_all(drow)
            return

        if chosen is act_adopt_one:
            self.adopt_source(drow)
            return

        if chosen is act_adopt_all:
            self.adopt_source_all()
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
        drow = self._drow_at(index.row())
        if drow:
            self._open_detail(drow.marquage)

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

        if drow.statut == "VALIDÉ":
            bg = C_VALIDE
        elif drow.statut == "EN PRÊT":
            bg = C_LENT
        elif drow.locked:
            bg = C_LOCKED
        elif drow.source_auto_fillable:
            bg = C_AUTO_FILL
        else:
            bg = C_EN_COURS

        marq_item = _ro_item(drow.marquage, bg)
        marq_item.setData(Qt.ItemDataRole.UserRole, drow.marquage)
        self.setItem(r, COL_MARQ,  marq_item)
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

        # Raccourcis clavier dans les cellules éditables
        row_idx = len(self._rows) - 1
        for widget, col in ((cb3, COL_NSVC3), (cb4, COL_NSVC4), (ed, COL_COMM)):
            filt = _CellKeyFilter(self, row_idx, col)
            target = widget.lineEdit() if isinstance(widget, QComboBox) else widget
            target.installEventFilter(filt)

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

    def apply_svc3_to_rows(self, source_drow: DECARow, targets: list):
        svc3_txt = source_drow.combo_svc3.currentText() if source_drow.combo_svc3 else ""
        svc4_txt = source_drow.combo_svc4.currentText() if source_drow.combo_svc4 else ""
        if not svc3_txt.strip():
            QMessageBox.information(self, "N.Service 3 vide",
                "La ligne source n'a pas de N.Service 3 sélectionné — rien à copier.")
            return
        for drow in targets:
            if not drow.combo_svc3:
                continue
            idx3 = drow.combo_svc3.findText(svc3_txt)
            if idx3 >= 0:
                drow.combo_svc3.setCurrentIndex(idx3)
            if drow.combo_svc4 and svc4_txt:
                idx4 = drow.combo_svc4.findText(svc4_txt)
                if idx4 >= 0:
                    drow.combo_svc4.setCurrentIndex(idx4)

    def apply_svc3_to_all(self, source_drow: DECARow):
        targets = [d for d in self._rows if d is not source_drow and not d.locked]
        self.apply_svc3_to_rows(source_drow, targets)

    def adopt_source(self, drow: DECARow):
        """Pré-remplit N.Service 3/4 depuis les colonnes service source de l'extract."""
        if drow.locked or not drow.source_auto_fillable:
            return
        s1, s3, s4 = drow.svcs[0], drow.svc3_cur, drow.svcs[3]
        lbl3 = svc3_label(s3, s1)
        if drow.combo_svc3:
            idx = drow.combo_svc3.findText(lbl3)
            if idx >= 0:
                drow.combo_svc3.setCurrentIndex(idx)
                # _on_svc3_change a mis à jour le svc4 combo, on peut maintenant set svc4
                lbl4 = svc4_label(s4, s1)
                if drow.combo_svc4:
                    idx4 = drow.combo_svc4.findText(lbl4)
                    if idx4 >= 0:
                        drow.combo_svc4.setCurrentIndex(idx4)

    def adopt_source_all(self):
        """Adopte le service source pour toutes les lignes auto-fillable du PN."""
        for drow in self._rows:
            if not drow.locked and drow.source_auto_fillable:
                self.adopt_source(drow)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_C and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            idx = self.currentIndex()
            if idx.isValid():
                w = self.cellWidget(idx.row(), idx.column())
                if isinstance(w, QComboBox):
                    text = w.currentText()
                elif isinstance(w, QLineEdit):
                    text = w.text()
                else:
                    item = self.item(idx.row(), idx.column())
                    text = item.text() if item else ""
                QApplication.clipboard().setText(text)
            return
        super().keyPressEvent(event)

    def _move_row(self, target: int):
        if 0 <= target < self.rowCount():
            self.selectRow(target)
            if target < len(self._rows):
                drow = self._rows[target]
                w = drow.combo_svc3 or drow.combo_svc4 or drow.edit_comm
                if w:
                    w.setFocus()

    def _fill_down(self, row_idx: int):
        """Copie N.Service 3/4 de la ligne au-dessus."""
        if row_idx <= 0 or row_idx >= len(self._rows):
            return
        src = self._rows[row_idx - 1]
        dst = self._rows[row_idx]
        if dst.locked or not dst.combo_svc3 or not src.combo_svc3:
            return
        for txt, cb_src, cb_dst in (
            (src.combo_svc3.currentText(), src.combo_svc3, dst.combo_svc3),
            (src.combo_svc4.currentText() if src.combo_svc4 else "", src.combo_svc4, dst.combo_svc4),
        ):
            if cb_dst and txt:
                idx = cb_dst.findText(txt)
                if idx >= 0:
                    cb_dst.setCurrentIndex(idx)

    def _tab_next(self, row_idx: int, col: int):
        if row_idx >= len(self._rows):
            return
        drow = self._rows[row_idx]
        if col == COL_NSVC3 and drow.combo_svc4:
            drow.combo_svc4.setFocus()
            drow.combo_svc4.lineEdit().selectAll()
        elif col == COL_NSVC4 and drow.edit_comm:
            drow.edit_comm.setFocus()
            drow.edit_comm.selectAll()
        elif col == COL_COMM:
            for nxt in range(row_idx + 1, len(self._rows)):
                nd = self._rows[nxt]
                if not nd.locked and nd.combo_svc3:
                    self.selectRow(nxt)
                    nd.combo_svc3.setFocus()
                    nd.combo_svc3.lineEdit().selectAll()
                    return

    def _tab_prev(self, row_idx: int, col: int):
        if row_idx >= len(self._rows):
            return
        drow = self._rows[row_idx]
        if col == COL_NSVC4 and drow.combo_svc3:
            drow.combo_svc3.setFocus()
            drow.combo_svc3.lineEdit().selectAll()
        elif col == COL_COMM and drow.combo_svc4:
            drow.combo_svc4.setFocus()
            drow.combo_svc4.lineEdit().selectAll()
        elif col == COL_NSVC3:
            for prv in range(row_idx - 1, -1, -1):
                pd = self._rows[prv]
                if not pd.locked and pd.edit_comm:
                    self.selectRow(prv)
                    pd.edit_comm.setFocus()
                    pd.edit_comm.selectAll()
                    return

    def open_detail_for_selected(self):
        rows = self.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row < len(self._rows):
            self._open_detail(self._rows[row].marquage)


# ── Vue rapide (sprint) ───────────────────────────────────────────────────────

class SprintViewDialog(QDialog):
    """Tableau plat de tous les DECAs des PNs simples — remplissage & validation rapide."""

    # Colonnes internes
    _C_PN    = 0
    _C_MARQ  = 1
    _C_REF   = 2
    _C_SVC3C = 3   # service3 actuel
    _C_SVC1C = 4
    _C_NSVC3 = 5   # combo N.Service3
    _C_NSVC4 = 6   # combo N.Service4
    _C_COMM  = 7
    _C_STAT  = 8
    _HEADERS = ["PN", "Marquage", "Réf", "Svc 3 actuel", "Svc 1 actuel",
                "N.Service 3", "N.Service 4", "Commentaire", "Statut"]
    _WIDTHS  = [130, 110, 130, 130, 110, 210, 210, 150, 80]

    def __init__(self, module: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Vue rapide — {module}")
        self.resize(1300, 700)
        self._module = module
        self._svc3_opts = svc3_labeled_options()
        self._drows: list[DECARow] = []
        self._setup_ui()
        self._load(max_deca=self._spin.value())

    def _setup_ui(self):
        from PyQt6.QtWidgets import QSpinBox
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # ── Barre de contrôle ─────────────────────────────────────────────
        bar = QHBoxLayout()
        bar.addWidget(QLabel("PNs avec au maximum"))
        self._spin = QSpinBox()
        self._spin.setRange(1, 20)
        self._spin.setValue(3)
        self._spin.setFixedWidth(55)
        bar.addWidget(self._spin)
        bar.addWidget(QLabel("DECAs"))
        btn_load = QPushButton("Charger")
        btn_load.setFixedHeight(28)
        btn_load.clicked.connect(lambda: self._load(self._spin.value()))
        bar.addWidget(btn_load)
        bar.addSpacing(20)
        self._lbl_info = QLabel("")
        self._lbl_info.setStyleSheet("color:#555;")
        bar.addWidget(self._lbl_info)
        bar.addStretch()

        # Filtres rapides
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filtrer PN / marquage…")
        self._search.setFixedWidth(180)
        self._search.setFixedHeight(28)
        self._search.textChanged.connect(self._filter_rows)
        bar.addWidget(self._search)

        btn_apply_all = QPushButton("↓  Appliquer svc3/4 à toutes les lignes visibles")
        btn_apply_all.setFixedHeight(28)
        btn_apply_all.setToolTip("Copie N.Service 3/4 de la ligne sélectionnée vers toutes les lignes visibles non verrouillées")
        btn_apply_all.clicked.connect(self._apply_selected_to_all)
        bar.addWidget(btn_apply_all)
        root.addLayout(bar)

        # ── Table ─────────────────────────────────────────────────────────
        self._table = QTableWidget()
        self._table.setColumnCount(len(self._HEADERS))
        self._table.setHorizontalHeaderLabels(self._HEADERS)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setAlternatingRowColors(False)
        for col, w in enumerate(self._WIDTHS):
            self._table.setColumnWidth(col, w)
        self._table.horizontalHeader().setStyleSheet(
            "QHeaderView::section { background:#dce6f1; font-weight:bold; padding:4px; border:1px solid #bbb; }"
        )
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._row_menu)
        self._table.doubleClicked.connect(self._on_double_click)
        root.addWidget(self._table, stretch=1)

        # ── Boutons bas ───────────────────────────────────────────────────
        bot = QHBoxLayout()
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color:#1a7f37; font-weight:bold;")
        bot.addWidget(self._lbl_status, stretch=1)

        btn_save = QPushButton("💾  Sauvegarder la progression")
        btn_save.setFixedHeight(34)
        btn_save.setToolTip("Enregistre les valeurs saisies sans exiger N.Service 3 — les lignes vides restent EN COURS")
        btn_save.setStyleSheet(
            "QPushButton { background:#6366f1; color:white; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#4f46e5; }"
        )
        btn_save.clicked.connect(self._save_progress)

        btn_valide = QPushButton("✓  Valider tout le visible")
        btn_valide.setFixedHeight(34)
        btn_valide.setStyleSheet(
            "QPushButton { background:#21c354; color:white; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#1aad47; }"
        )
        btn_valide.clicked.connect(lambda: self._validate_visible("VALIDÉ"))

        btn_attente = QPushButton("📋  Pré-checker tout le visible")
        btn_attente.setFixedHeight(34)
        btn_attente.setStyleSheet(
            "QPushButton { background:#1f497d; color:white; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#163a69; }"
        )
        btn_attente.clicked.connect(lambda: self._validate_visible("EN ATTENTE"))

        btn_close = QPushButton("Fermer")
        btn_close.setFixedHeight(34)
        btn_close.clicked.connect(self.accept)

        bot.addWidget(btn_save)
        bot.addWidget(btn_attente)
        bot.addWidget(btn_valide)
        bot.addWidget(btn_close)
        root.addLayout(bot)

    def _load(self, max_deca: int):
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        self._drows.clear()

        all_tools = queries.get_tools_for_module(self._module)
        decisions = queries.get_decisions_batch_for_module(self._module)

        # Groupe par PN, garde ceux avec ≤ max_deca DECAs
        pn_tools: dict[str, list] = {}
        for r in all_tools:
            pn = r["pn_short"]
            pn_tools.setdefault(pn, []).append(dict(r))

        eligible = {pn: rows for pn, rows in pn_tools.items() if len(rows) <= max_deca}
        n_pn  = len(eligible)
        n_deca_total = sum(len(v) for v in eligible.values())
        n_lent = 0

        prev_pn = None
        for pn in sorted(eligible):
            for rd in eligible[pn]:
                dec  = decisions.get(rd["marquage"])
                drow = DECARow(rd, dec)

                if drow.statut == "EN PRÊT":
                    n_lent += 1
                    continue  # outil en prêt — exclu de la vue rapide

                self._drows.append(drow)

                r = self._table.rowCount()
                self._table.insertRow(r)
                self._table.setRowHeight(r, 32)

                if drow.statut == "VALIDÉ":
                    bg = C_VALIDE
                elif drow.statut == "EN ATTENTE":
                    bg = C_PN_PCHECK
                elif drow.source_auto_fillable:
                    bg = C_AUTO_FILL
                else:
                    bg = C_EN_COURS

                # Fond alterné par PN
                if pn != prev_pn and prev_pn is not None:
                    pass  # on utilise bg standard
                prev_pn = pn

                def _ro(txt, b=bg):
                    return _ro_item(txt, b)

                pn_item = _ro(pn)
                font = QFont(); font.setBold(True)
                pn_item.setFont(font)
                self._table.setItem(r, self._C_PN,    pn_item)
                self._table.setItem(r, self._C_MARQ,  _ro(drow.marquage))
                self._table.setItem(r, self._C_REF,   _ro(drow.ref))
                self._table.setItem(r, self._C_SVC3C, _ro(drow.svc3_cur))
                self._table.setItem(r, self._C_SVC1C, _ro(drow.svcs[0]))
                self._table.setItem(r, self._C_STAT,  _ro(drow.statut))

                if drow.locked:
                    svc3_d = svc3_label(drow.n_svc3_plain, drow.n_svc1) if drow.n_svc3_plain and drow.n_svc1 else drow.n_svc3_plain
                    svc4_d = svc4_label(drow.n_svc4_plain, drow.n_svc1) if drow.n_svc4_plain and drow.n_svc1 else drow.n_svc4_plain
                    self._table.setItem(r, self._C_NSVC3, _ro(svc3_d))
                    self._table.setItem(r, self._C_NSVC4, _ro(svc4_d))
                    self._table.setItem(r, self._C_COMM,  _ro(drow.commentaire))
                else:
                    cb3 = DECATable._make_combo(self._svc3_opts)
                    if drow.n_svc3_plain and drow.n_svc1:
                        lbl = svc3_label(drow.n_svc3_plain, drow.n_svc1)
                        idx = cb3.findText(lbl)
                        if idx >= 0:
                            cb3.setCurrentIndex(idx)
                    cb4 = DECATable._make_combo([])
                    self._fill_svc4(cb4, drow.n_svc1, drow.n_svc3_plain, drow.n_svc4_plain)
                    ed = QLineEdit(drow.commentaire)
                    ed.setFrame(False)
                    ed.setStyleSheet("padding: 2px 4px;")
                    drow.combo_svc3 = cb3
                    drow.combo_svc4 = cb4
                    drow.edit_comm  = ed
                    cb3.currentTextChanged.connect(lambda txt, d=drow: self._on_svc3_change(txt, d))
                    self._table.setCellWidget(r, self._C_NSVC3, cb3)
                    self._table.setCellWidget(r, self._C_NSVC4, cb4)
                    self._table.setCellWidget(r, self._C_COMM,  ed)

        self._table.setSortingEnabled(False)
        lent_txt = f"  ·  {n_lent} en prêt (masqués)" if n_lent else ""
        self._lbl_info.setText(f"{n_pn} PNs  ·  {n_deca_total} DECAs chargés{lent_txt}")
        self._lbl_status.setText("")

    def _fill_svc4(self, cb4, svc1, svc3, current):
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

    def _on_svc3_change(self, label, drow):
        svc3_plain, svc1 = svc3_from_label(label)
        drow.n_svc3_plain = svc3_plain
        drow.n_svc1 = svc1
        self._fill_svc4(drow.combo_svc4, svc1, svc3_plain, "")

    def _filter_rows(self, text):
        text = text.upper()
        for r in range(self._table.rowCount()):
            pn_item   = self._table.item(r, self._C_PN)
            marq_item = self._table.item(r, self._C_MARQ)
            pn   = pn_item.text().upper()   if pn_item   else ""
            marq = marq_item.text().upper() if marq_item else ""
            self._table.setRowHidden(r, bool(text) and text not in pn and text not in marq)

    def _visible_unlocked_rows(self):
        result = []
        for r in range(self._table.rowCount()):
            if self._table.isRowHidden(r) or r >= len(self._drows):
                continue
            drow = self._drows[r]
            if not drow.locked:
                result.append((r, drow))
        return result

    def _apply_selected_to_all(self):
        sel = [idx.row() for idx in self._table.selectedIndexes()
               if idx.column() == 0 and idx.row() < len(self._drows)
               and not self._drows[idx.row()].locked]
        if not sel:
            QMessageBox.information(self, "Aucune source",
                "Sélectionne d'abord une ligne source (la ligne dont tu veux copier N.Service 3/4).")
            return
        src = self._drows[sel[0]]
        svc3_txt = src.combo_svc3.currentText() if src.combo_svc3 else ""
        svc4_txt = src.combo_svc4.currentText() if src.combo_svc4 else ""
        for _, drow in self._visible_unlocked_rows():
            if drow is src or not drow.combo_svc3:
                continue
            idx3 = drow.combo_svc3.findText(svc3_txt)
            if idx3 >= 0:
                drow.combo_svc3.setCurrentIndex(idx3)
            if drow.combo_svc4 and svc4_txt:
                idx4 = drow.combo_svc4.findText(svc4_txt)
                if idx4 >= 0:
                    drow.combo_svc4.setCurrentIndex(idx4)

    def _row_menu(self, pos):
        idx = self._table.indexAt(pos)
        if not idx.isValid() or idx.row() >= len(self._drows):
            return
        src = self._drows[idx.row()]
        if src.locked:
            return
        menu = QMenu(self)
        act_apply = menu.addAction("↓  Appliquer N.Service 3/4 à toutes les lignes visibles")
        menu.addSeparator()
        act_lent = menu.addAction("🔄  Marquer comme 'En prêt' (Loaned) — retire l'outil de la liste")

        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))

        if chosen is act_apply:
            svc3_txt = src.combo_svc3.currentText() if src.combo_svc3 else ""
            svc4_txt = src.combo_svc4.currentText() if src.combo_svc4 else ""
            for _, drow in self._visible_unlocked_rows():
                if drow is src or not drow.combo_svc3:
                    continue
                idx3 = drow.combo_svc3.findText(svc3_txt)
                if idx3 >= 0:
                    drow.combo_svc3.setCurrentIndex(idx3)
                if drow.combo_svc4 and svc4_txt:
                    idx4 = drow.combo_svc4.findText(svc4_txt)
                    if idx4 >= 0:
                        drow.combo_svc4.setCurrentIndex(idx4)

        elif chosen is act_lent:
            self._mark_lent(src)

    def _save_progress(self):
        """Sauvegarde les svc3/4/commentaire sans exiger N.Service 3 — statut reste EN COURS."""
        n = 0
        for _, drow in self._visible_unlocked_rows():
            svc3_lbl    = drow.combo_svc3.currentText() if drow.combo_svc3 else ""
            svc3_plain, svc1 = svc3_from_label(svc3_lbl)
            svc4_lbl    = drow.combo_svc4.currentText() if drow.combo_svc4 else ""
            svc4_plain  = svc4_from_label(svc4_lbl)
            svc2s       = svc2_for_svc3(svc3_plain) if svc3_plain else []
            commentaire = drow.edit_comm.text() if drow.edit_comm else ""
            # Ne rétrograde pas un EN ATTENTE existant
            keep_status = drow.statut if drow.statut == "EN ATTENTE" else "EN COURS"
            queries.upsert_decision(
                marquage       = drow.marquage,
                pn_short       = drow.pn_short,
                module_context = self._module,
                n_service1     = svc1 or None,
                n_service2     = svc2s[0] if svc2s else None,
                n_service3     = svc3_plain or None,
                n_service4     = svc4_plain or None,
                pre_check      = None,
                decision       = keep_status,
                commentaire    = commentaire or None,
                updated_by     = "manager_sprint_save",
            )
            n += 1
        self._lbl_status.setText(f"💾  {n} DECA(s) sauvegardés.")
        if isinstance(self.parent(), MainWindow):
            self.parent()._reload_pn_list()
            self.parent()._update_stats()

    def _mark_lent(self, drow: DECARow):
        """Marque l'outil comme 'En prêt' : aucun service requis, retiré de la vue."""
        queries.upsert_decision(
            marquage       = drow.marquage,
            pn_short       = drow.pn_short,
            module_context = self._module,
            n_service1     = None,
            n_service2     = None,
            n_service3     = None,
            n_service4     = None,
            pre_check      = None,
            decision       = "EN PRÊT",
            commentaire    = drow.commentaire or None,
            updated_by     = "manager_sprint",
        )
        self._load(self._spin.value())
        if isinstance(self.parent(), MainWindow):
            self.parent()._reload_pn_list()
            self.parent()._update_stats()

    def _on_double_click(self, index):
        row = index.row()
        if row < len(self._drows):
            drow = self._drows[row]
            all_mqs = [d.marquage for d in self._drows]
            dlg = DECADetailDialog(drow.marquage, all_mqs, self)
            dlg.exec()

    def _validate_visible(self, decision_val: str):
        rows = self._visible_unlocked_rows()
        missing = [self._drows[r].marquage for r, d in rows
                   if not (d.combo_svc3 and d.combo_svc3.currentText().strip())]
        if missing:
            QMessageBox.warning(self, "N.Service 3 manquant",
                "N.Service 3 obligatoire pour :\n" + "\n".join(missing[:10]) +
                (f"\n… et {len(missing) - 10} autres" if len(missing) > 10 else ""))
            return

        updated_by = "manager_sprint"
        n = 0
        for _, drow in rows:
            svc3_lbl   = drow.combo_svc3.currentText() if drow.combo_svc3 else ""
            svc3_plain, svc1 = svc3_from_label(svc3_lbl)
            svc4_lbl   = drow.combo_svc4.currentText() if drow.combo_svc4 else ""
            svc4_plain = svc4_from_label(svc4_lbl)
            svc2s      = svc2_for_svc3(svc3_plain) if svc3_plain else []
            commentaire = drow.edit_comm.text() if drow.edit_comm else ""

            existing = queries.get_decision(drow.marquage)
            if existing and existing["decision"] == "EN ATTENTE":
                queries.reset_decision(drow.marquage, reset_by=updated_by)

            queries.upsert_decision(
                marquage       = drow.marquage,
                pn_short       = drow.pn_short,
                module_context = self._module,
                n_service1     = svc1 or None,
                n_service2     = svc2s[0] if svc2s else None,
                n_service3     = svc3_plain or None,
                n_service4     = svc4_plain or None,
                pre_check      = None,
                decision       = decision_val,
                commentaire    = commentaire or None,
                updated_by     = updated_by,
            )
            n += 1

        verb = "validés" if decision_val == "VALIDÉ" else "mis en attente"
        self._lbl_status.setText(f"✓  {n} DECA(s) {verb}.")
        self._load(self._spin.value())
        if isinstance(self.parent(), MainWindow):
            self.parent()._reload_pn_list()
            self.parent()._update_stats()


# ── Application en masse ─────────────────────────────────────────────────────

class BatchApplyDialog(QDialog):
    """Applique N.Service 3/4 à une sélection de PNs du module en une opération."""

    def __init__(self, module: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Application en masse — {module}")
        self.resize(560, 680)
        self._module = module
        self._svc3_opts = svc3_labeled_options()
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── Service pickers ───────────────────────────────────────────────
        svc_box = QFrame()
        svc_box.setStyleSheet("background:#f0f4fa; border-radius:6px; padding:4px;")
        svc_lay = QGridLayout(svc_box)
        svc_lay.setSpacing(6)

        svc_lay.addWidget(QLabel("<b>N.Service 3</b>"), 0, 0)
        self.cb_svc3 = DECATable._make_combo(self._svc3_opts)
        self.cb_svc3.setMinimumWidth(300)
        svc_lay.addWidget(self.cb_svc3, 0, 1)

        svc_lay.addWidget(QLabel("<b>N.Service 4</b>"), 1, 0)
        self.cb_svc4 = DECATable._make_combo([])
        svc_lay.addWidget(self.cb_svc4, 1, 1)

        self.cb_svc3.currentTextChanged.connect(self._on_svc3_change)
        root.addWidget(svc_box)

        # ── Mode (pré-remplir vs valider) ─────────────────────────────────
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup
        mode_lay = QHBoxLayout()
        self._rb_encours = QRadioButton("Pré-remplir seulement (EN COURS)")
        self._rb_valide  = QRadioButton("Valider directement (VALIDÉ)")
        self._rb_encours.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self._rb_encours)
        grp.addButton(self._rb_valide)
        mode_lay.addWidget(self._rb_encours)
        mode_lay.addWidget(self._rb_valide)
        root.addLayout(mode_lay)

        # ── Filtre + sélection rapide ──────────────────────────────────────
        sel_lay = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Filtrer les PNs…")
        self._search.setFixedHeight(26)
        self._search.textChanged.connect(self._filter_pns)
        sel_lay.addWidget(self._search, stretch=1)
        btn_all   = QPushButton("Tout cocher")
        btn_none  = QPushButton("Tout décocher")
        btn_untreated = QPushButton("Non traités seulement")
        for b in (btn_all, btn_none, btn_untreated):
            b.setFixedHeight(26)
            b.setStyleSheet("font-size:11px;")
        btn_all.clicked.connect(lambda: self._check_all(True))
        btn_none.clicked.connect(lambda: self._check_all(False))
        btn_untreated.clicked.connect(self._check_untreated)
        sel_lay.addWidget(btn_all)
        sel_lay.addWidget(btn_none)
        sel_lay.addWidget(btn_untreated)
        root.addLayout(sel_lay)

        # ── Liste PNs avec cases à cocher ─────────────────────────────────
        self._pn_list = QListWidget()
        self._pn_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        root.addWidget(self._pn_list, stretch=1)

        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet("color:#666; font-size:11px;")
        root.addWidget(self._lbl_count)

        # ── Boutons ───────────────────────────────────────────────────────
        self._lbl_result = QLabel("")
        self._lbl_result.setWordWrap(True)
        root.addWidget(self._lbl_result)

        btn_row = QHBoxLayout()
        self._btn_apply = QPushButton("⚡  Appliquer")
        self._btn_apply.setFixedHeight(34)
        self._btn_apply.setStyleSheet(
            "QPushButton { background:#0078d4; color:white; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#005fa3; }"
        )
        self._btn_apply.clicked.connect(self._apply)
        btn_cancel = QPushButton("Fermer")
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(self.accept)
        btn_row.addWidget(self._btn_apply)
        btn_row.addWidget(btn_cancel)
        root.addLayout(btn_row)

        self._load_pns()

    def _load_pns(self):
        self._pn_list.clear()
        all_tools  = queries.get_tools_for_module(self._module)
        decisions  = queries.get_decisions_batch_for_module(self._module)

        pn_data: dict[str, dict] = {}
        for r in all_tools:
            pn = r["pn_short"]
            if pn not in pn_data:
                pn_data[pn] = {"marquages": [], "complexity": r["complexity_flag"] or "unique"}
            pn_data[pn]["marquages"].append(r["marquage"])

        self._pn_meta: dict[str, dict] = {}
        for pn, d in sorted(pn_data.items()):
            mqs = d["marquages"]
            statuses = [decisions[m]["decision"] for m in mqs if m in decisions]
            done = bool(statuses) and all(s in ("VALIDÉ", "EN ATTENTE") for s in statuses)
            self._pn_meta[pn] = {"marquages": mqs, "done": done, "complexity": d["complexity"]}

            item = QListWidgetItem()
            item.setCheckState(Qt.CheckState.Unchecked)
            n_deca = len(mqs)
            status_hint = "✓ traité" if done else "à traiter"
            item.setText(f"{pn}  ({n_deca} DECA{'s' if n_deca > 1 else ''})  — {status_hint}")
            item.setData(Qt.ItemDataRole.UserRole, pn)
            if done:
                item.setForeground(QColor("#888"))
            self._pn_list.addItem(item)

        self._update_count()

    def _on_svc3_change(self, label: str):
        svc3_plain, svc1 = svc3_from_label(label)
        opts = svc4_labeled_for_bld(svc1, svc3_plain) if svc1 else [""]
        self.cb_svc4.blockSignals(True)
        self.cb_svc4.clear()
        self.cb_svc4.addItems(opts)
        completer = QCompleter(opts)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.cb_svc4.setCompleter(completer)
        self.cb_svc4.blockSignals(False)

    def _filter_pns(self, text: str):
        text = text.upper()
        for i in range(self._pn_list.count()):
            item = self._pn_list.item(i)
            pn = item.data(Qt.ItemDataRole.UserRole) or ""
            item.setHidden(bool(text) and text not in pn.upper())

    def _check_all(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self._pn_list.count()):
            item = self._pn_list.item(i)
            if not item.isHidden():
                item.setCheckState(state)
        self._update_count()

    def _check_untreated(self):
        for i in range(self._pn_list.count()):
            item = self._pn_list.item(i)
            if item.isHidden():
                continue
            pn = item.data(Qt.ItemDataRole.UserRole)
            done = self._pn_meta.get(pn, {}).get("done", False)
            item.setCheckState(Qt.CheckState.Unchecked if done else Qt.CheckState.Checked)
        self._update_count()

    def _update_count(self):
        n = sum(1 for i in range(self._pn_list.count())
                if self._pn_list.item(i).checkState() == Qt.CheckState.Checked)
        self._lbl_count.setText(f"{n} PN(s) sélectionné(s)")

    def _apply(self):
        svc3_lbl = self.cb_svc3.currentText().strip()
        if not svc3_lbl:
            QMessageBox.warning(self, "Service manquant", "Sélectionne d'abord un N.Service 3.")
            return

        svc3_plain, svc1 = svc3_from_label(svc3_lbl)
        svc4_lbl   = self.cb_svc4.currentText().strip()
        svc4_plain = svc4_from_label(svc4_lbl) if svc4_lbl else ""
        svc2s      = svc2_for_svc3(svc3_plain) if svc3_plain else []
        svc2       = svc2s[0] if svc2s else ""
        decision   = "VALIDÉ" if self._rb_valide.isChecked() else "EN COURS"

        selected_pns = [
            self._pn_list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._pn_list.count())
            if self._pn_list.item(i).checkState() == Qt.CheckState.Checked
        ]

        if not selected_pns:
            QMessageBox.information(self, "Rien à faire", "Aucun PN sélectionné.")
            return

        n_deca = 0
        for pn in selected_pns:
            for marquage in self._pn_meta[pn]["marquages"]:
                queries.upsert_decision(
                    marquage       = marquage,
                    pn_short       = pn,
                    module_context = self._module,
                    n_service1     = svc1 or None,
                    n_service2     = svc2 or None,
                    n_service3     = svc3_plain or None,
                    n_service4     = svc4_plain or None,
                    pre_check      = None,
                    decision       = decision,
                    commentaire    = None,
                    updated_by     = "manager_batch",
                )
                n_deca += 1

        verb = "validés" if decision == "VALIDÉ" else "pré-remplis"
        self._lbl_result.setText(
            f"✓  {n_deca} DECA(s) sur {len(selected_pns)} PN(s) {verb} "
            f"avec N.Service 3 = {svc3_plain}."
        )
        self._lbl_result.setStyleSheet("color:#1a7f37; font-weight:bold;")
        self._load_pns()
        if isinstance(self.parent(), MainWindow):
            self.parent()._reload_pn_list()
            self.parent()._update_stats()


# ── Reload sources ───────────────────────────────────────────────────────────

class _ReloadThread(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def run(self):
        try:
            from scripts.reload_sources import reload
            stats = reload()
            self.finished.emit(stats)
        except Exception as e:
            self.error.emit(str(e))


class ReloadSourcesDialog(QDialog):
    """Permet de choisir de nouveaux fichiers sources, les copie dans data/ et relance le reload."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Recharger les sources DECA")
        self.setFixedWidth(600)
        self._paths: dict[str, Path | None] = {"deca": None, "panoply": None, "dmc": None, "icv": None}
        self._thread: _ReloadThread | None = None
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        intro = QLabel(
            "Sélectionne un ou plusieurs nouveaux fichiers sources.\n"
            "Seul le fichier DECA est obligatoire — les autres sont optionnels.\n"
            "Les fichiers seront copiés dans <b>data/</b> avant le rechargement."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet("color:#444; margin-bottom:6px;")
        root.addWidget(intro)

        grid = QGridLayout()
        grid.setSpacing(6)

        sources = [
            ("deca",    "Extract DECA *",  "CSV ou XLSX (*DECA* / *Extract*)"),
            ("panoply", "Panoply",          "XLSX (Panoply*.xlsx)"),
            ("dmc",     "DMC / ESM",        "XLSX (DMC*.xlsx / ESM*.xlsx)"),
            ("icv",     "ICV Translation",  "XLSX (ICV*.xlsx / *Translation*.xlsx)"),
        ]

        self._lbl_file: dict[str, QLabel] = {}
        for row_idx, (key, name, hint) in enumerate(sources):
            lbl_name = QLabel(f"<b>{name}</b>")
            lbl_hint = QLabel(hint)
            lbl_hint.setStyleSheet("color:#888; font-size:11px;")
            self._lbl_file[key] = QLabel("— aucun fichier sélectionné —")
            self._lbl_file[key].setStyleSheet("color:#999; font-style:italic; font-size:11px;")
            btn = QPushButton("Parcourir…")
            btn.setFixedWidth(100)
            btn.clicked.connect(lambda _, k=key: self._browse(k))

            grid.addWidget(lbl_name,              row_idx * 2,     0)
            grid.addWidget(btn,                   row_idx * 2,     1)
            grid.addWidget(lbl_hint,              row_idx * 2 + 1, 0)
            grid.addWidget(self._lbl_file[key],   row_idx * 2 + 1, 1)

        root.addLayout(grid)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color:#ddd;")
        root.addWidget(line)

        self._lbl_status = QLabel("")
        self._lbl_status.setWordWrap(True)
        root.addWidget(self._lbl_status)

        btn_row = QHBoxLayout()
        self._btn_reload = QPushButton("⟳  Recharger")
        self._btn_reload.setFixedHeight(34)
        self._btn_reload.setStyleSheet(
            "QPushButton { background:#0078d4; color:white; font-weight:bold; border-radius:4px; }"
            "QPushButton:hover { background:#005fa3; }"
            "QPushButton:disabled { background:#aaa; }"
        )
        self._btn_reload.clicked.connect(self._do_reload)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.setFixedHeight(34)
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self._btn_reload)
        btn_row.addWidget(btn_cancel)
        root.addLayout(btn_row)

    def _browse(self, key: str):
        path, _ = QFileDialog.getOpenFileName(
            self, f"Sélectionner le fichier {key.upper()}",
            "", "Fichiers source (*.csv *.xlsx *.xls)"
        )
        if path:
            self._paths[key] = Path(path)
            self._lbl_file[key].setText(Path(path).name)
            self._lbl_file[key].setStyleSheet("color:#222; font-style:normal; font-size:11px;")

    def _do_reload(self):
        if not self._paths["deca"]:
            QMessageBox.warning(self, "Fichier manquant", "Le fichier DECA est obligatoire.")
            return

        # Copie les fichiers sélectionnés dans data/
        DATA_DIR.mkdir(exist_ok=True)
        for key, src in self._paths.items():
            if src:
                dest = DATA_DIR / src.name
                shutil.copy2(src, dest)

        self._btn_reload.setEnabled(False)
        self._lbl_status.setText("⏳  Rechargement en cours…")
        self._lbl_status.setStyleSheet("color:#0078d4;")

        self._thread = _ReloadThread()
        self._thread.finished.connect(self._on_done)
        self._thread.error.connect(self._on_error)
        self._thread.start()

    def _on_done(self, stats: dict):
        self._lbl_status.setText(
            f"✓  Rechargement terminé — {stats.get('total', '?')} DECAs chargés "
            f"({stats.get('excluded', 0)} exclus)."
        )
        self._lbl_status.setStyleSheet("color:#1a7f37; font-weight:bold;")
        self._btn_reload.setEnabled(True)
        self._btn_reload.setText("Fermer")
        self._btn_reload.clicked.disconnect()
        self._btn_reload.clicked.connect(self.accept)

    def _on_error(self, msg: str):
        self._lbl_status.setText(f"✗  Erreur : {msg}")
        self._lbl_status.setStyleSheet("color:#c0392b; font-weight:bold;")
        self._btn_reload.setEnabled(True)


# ── Recherche globale ─────────────────────────────────────────────────────────

class GlobalSearchDialog(QDialog):
    def __init__(self, query: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Recherche : {query}")
        self.resize(900, 500)
        self._nav_args: tuple | None = None  # (module, pn)
        self._setup_ui(query)

    def _setup_ui(self, query: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        results = queries.global_search(query)
        lbl = QLabel(f"<b>{len(results)}</b> résultat(s) pour « {query} »"
                     + (" (limité à 100)" if len(results) == 100 else ""))
        root.addWidget(lbl)

        tbl = QTableWidget(len(results), 6)
        tbl.setHorizontalHeaderLabels(["PN", "Marquage", "Modules", "Complexité", "Statut", "Action"])
        tbl.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.setShowGrid(True)
        tbl.setColumnWidth(0, 130)
        tbl.setColumnWidth(1, 130)
        tbl.setColumnWidth(2, 200)
        tbl.setColumnWidth(3, 100)
        tbl.setColumnWidth(4, 90)
        tbl.setColumnWidth(5, 90)

        def _sel_item(text: str) -> QTableWidgetItem:
            it = QTableWidgetItem(text or "")
            it.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            return it

        for row_idx, r in enumerate(results):
            modules = r["modules_effective"] or ""
            first_module = modules.split(",")[0].strip()
            pn = r["pn_short"] or ""
            tbl.setItem(row_idx, 0, _sel_item(pn))
            tbl.setItem(row_idx, 1, _sel_item(r["marquage"] or ""))
            tbl.setItem(row_idx, 2, _sel_item(modules))
            tbl.setItem(row_idx, 3, _sel_item(r["complexity_flag"] or ""))
            statut = r["decision"] or "—"
            stat_item = _sel_item(statut)
            if statut == "VALIDÉ":
                stat_item.setBackground(QColor(C_VALIDE))
            elif statut == "EN ATTENTE":
                stat_item.setBackground(QColor("#faeeda"))
            tbl.setItem(row_idx, 4, stat_item)

            if first_module and pn:
                btn = QPushButton("→ Aller")
                btn.setFixedHeight(26)
                btn.clicked.connect(lambda _, m=first_module, p=pn: self._navigate(m, p))
                tbl.setCellWidget(row_idx, 5, btn)

        root.addWidget(tbl)

        btn_close = QPushButton("Fermer")
        btn_close.clicked.connect(self.close)
        root.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _navigate(self, module: str, pn: str):
        self._nav_args = (module, pn)
        self.accept()


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
        self._last_validated_pn: str | None = None
        self._setup_ui()
        self._load_module(self._module)
        self._update_source_tooltip()
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
        top.addSpacing(20)
        self.search_global = QLineEdit()
        self.search_global.setPlaceholderText("🔍 Recherche globale (PN / marquage)…")
        self.search_global.setFixedWidth(260)
        self.search_global.setFixedHeight(32)
        self.search_global.returnPressed.connect(self._open_global_search)
        top.addWidget(self.search_global)
        btn_search = QPushButton("Rechercher")
        btn_search.setFixedHeight(32)
        btn_search.clicked.connect(self._open_global_search)
        top.addWidget(btn_search)
        top.addStretch()

        # ── Menu "⋮" — regroupe les actions secondaires pour éviter l'overflow ──
        from PyQt6.QtWidgets import QToolButton, QMenu
        from PyQt6.QtGui import QAction
        self._btn_reload_src = None  # référence pour tooltip (mis à jour dans _update_source_tooltip)

        btn_more = QToolButton()
        btn_more.setText("⋮  Actions")
        btn_more.setFixedHeight(32)
        btn_more.setStyleSheet(
            "QToolButton { border:1px solid #bbb; border-radius:4px; padding:0 10px; font-size:13px; }"
            "QToolButton:hover { background:#e8e8e8; }"
            "QToolButton::menu-indicator { image: none; }"
        )
        btn_more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        menu_more = QMenu(btn_more)
        act_reload  = QAction("⟳  Recharger les sources…",     self)
        act_sprint  = QAction("⚡  Vue rapide…",                 self)
        act_batch   = QAction("⚡  Appliquer en masse…",         self)
        act_export  = QAction("📋  Export complet du module",    self)
        act_model   = QAction("📥  Export modèle d'import",      self)
        act_stats   = QAction("📊  Ouvrir les Statistiques",     self)
        act_reload.setToolTip("Remplace les fichiers sources et recharge la base")
        act_sprint.setToolTip("Vue plate de tous les PNs avec peu de DECAs")
        act_batch.setToolTip("Appliquer N.Service 3/4 à plusieurs PNs d'un coup")
        act_reload.triggered.connect(self._open_reload_sources)
        act_sprint.triggered.connect(self._open_sprint_view)
        act_batch.triggered.connect(self._open_batch_apply)
        act_export.triggered.connect(self._export_full)
        act_model.triggered.connect(self._export_model)
        act_stats.triggered.connect(self._open_stats)
        menu_more.addAction(act_reload)
        menu_more.addSeparator()
        menu_more.addAction(act_sprint)
        menu_more.addAction(act_batch)
        menu_more.addSeparator()
        menu_more.addAction(act_export)
        menu_more.addAction(act_model)
        menu_more.addSeparator()
        menu_more.addAction(act_stats)
        btn_more.setMenu(menu_more)
        self._act_reload_src = act_reload   # pour le tooltip source
        top.addWidget(btn_more)
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
        btn_batch = QPushButton("⚡  Appliquer en masse…")
        btn_batch.setFixedHeight(28)
        btn_batch.setStyleSheet("font-size:11px; color:#444;")
        btn_batch.setToolTip("Appliquer N.Service 3/4 à une sélection de PNs en une seule opération")
        btn_batch.clicked.connect(self._open_batch_apply)
        ll.addWidget(btn_batch)

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

        # ── Raccourcis clavier ────────────────────────────────────────────
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(self._valider)
        QShortcut(QKeySequence("Ctrl+Z"),      self).activated.connect(self._undo)
        QShortcut(QKeySequence("Ctrl+Down"),   self).activated.connect(self._next_pn)
        QShortcut(QKeySequence("Ctrl+Up"),     self).activated.connect(self._prev_pn)
        QShortcut(QKeySequence("F2"),          self).activated.connect(self.table.open_detail_for_selected)

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
                all_valide  = bool(statuses) and all(s == "VALIDÉ"    for s in statuses)
                all_done    = bool(statuses) and all(s in ("VALIDÉ", "EN ATTENTE") for s in statuses)
                any_pcheck  = bool(statuses) and any(s == "EN ATTENTE" for s in statuses) and not all_valide
                done = all_done
                count = len(mqs)
                icon = "✓" if all_valide else ("◑" if any_pcheck else " ")
                label_pn = f"{icon}  {pn}  ({count})"
                item = QListWidgetItem(label_pn)
                item.setData(Qt.ItemDataRole.UserRole, {"pn": pn, "done": done})
                if all_valide:
                    item.setBackground(QColor(C_PN_VALIDE))
                elif any_pcheck:
                    item.setBackground(QColor(C_PN_PCHECK))
                else:
                    item.setBackground(QColor(C_EN_COURS))
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

    def _update_source_tooltip(self):
        info = queries.get_source_info()
        if info and info.get("source_file"):
            loaded = (info.get("loaded_at") or "")[:16].replace("T", " ")
            tip = (
                f"Source actuelle : {info['source_file']}\n"
                f"Chargé le : {loaded} UTC\n"
                f"Total DECAs : {info.get('n_total', '?')}\n\n"
                "Cliquer pour recharger les sources…"
            )
        else:
            tip = "Aucune source chargée — cliquer pour charger…"
        if self._act_reload_src:
            self._act_reload_src.setToolTip(tip)

    def _open_sprint_view(self):
        dlg = SprintViewDialog(self._module, self)
        dlg.exec()
        self._reload_pn_list()
        self._update_stats()

    def _open_batch_apply(self):
        dlg = BatchApplyDialog(self._module, self)
        dlg.exec()

    def _open_reload_sources(self):
        dlg = ReloadSourcesDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._load_module(self._module)
            self._update_source_tooltip()
            self.statusBar().showMessage("Sources rechargées — module rafraîchi.", 5000)

    def _open_global_search(self):
        query = self.search_global.text().strip()
        if not query:
            return
        dlg = GlobalSearchDialog(query, self)
        dlg.exec()
        if dlg._nav_args:
            module, pn = dlg._nav_args
            if module in MODULES:
                self.cb_module.setCurrentText(module)
            # Select the PN in the list
            for i in range(self.pn_list.count()):
                it = self.pn_list.item(i)
                data = it.data(Qt.ItemDataRole.UserRole)
                if data and data["pn"] == pn:
                    self.pn_list.setCurrentItem(it)
                    break

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

    def _prev_pn(self):
        for i in range(self.pn_list.count() - 1, -1, -1):
            it = self.pn_list.item(i)
            if it.isHidden() or it.data(Qt.ItemDataRole.UserRole) is None:
                continue
            if it.data(Qt.ItemDataRole.UserRole)["pn"] == self._current_pn:
                for j in range(i - 1, -1, -1):
                    prv = self.pn_list.item(j)
                    if not prv.isHidden() and prv.data(Qt.ItemDataRole.UserRole) is not None:
                        self.pn_list.setCurrentItem(prv)
                        return
                break

    def _refresh_pn_item(self, pn: str, decision_val: str):
        """Met à jour uniquement l'item PN concerné — sans reconstruire toute la liste."""
        decs = queries.get_decisions_for_pn_in_module(pn, self._module)
        statuses = [r["decision"] for r in decs if r["decision"]]
        all_valide = bool(statuses) and all(s == "VALIDÉ" for s in statuses)
        any_pcheck = bool(statuses) and any(s == "EN ATTENTE" for s in statuses) and not all_valide
        done = bool(statuses) and all(s in ("VALIDÉ", "EN ATTENTE") for s in statuses)
        count = len(decs)

        for item in self._pn_items:
            data = item.data(Qt.ItemDataRole.UserRole)
            if not data or data["pn"] != pn:
                continue
            data["done"] = done
            item.setData(Qt.ItemDataRole.UserRole, data)
            icon = "✓" if all_valide else ("◑" if any_pcheck else " ")
            item.setText(f"{icon}  {pn}  ({count})")
            if all_valide:
                item.setBackground(QColor(C_PN_VALIDE))
            elif any_pcheck:
                item.setBackground(QColor(C_PN_PCHECK))
            else:
                item.setBackground(QColor(C_EN_COURS))
            break

        done_count = sum(1 for it in self._pn_items
                        if (d := it.data(Qt.ItemDataRole.UserRole)) and d.get("done"))
        self.lbl_stats.setText(f"{done_count} / {len(self._pn_items)} PNs traités")

    def _undo(self):
        """Ctrl+Z : délègue au widget focalisé si possible, sinon annule la dernière validation."""
        focused = QApplication.focusWidget()
        if isinstance(focused, QLineEdit) and focused.isUndoAvailable():
            focused.undo()
            return
        if not self._last_validated_pn:
            self.statusBar().showMessage("Rien à annuler.", 2000)
            return
        pn = self._last_validated_pn
        all_tools = queries.get_tools_for_module(self._module)
        for r in all_tools:
            if r["pn_short"] == pn:
                queries.reset_decision(r["marquage"], reset_by="manager_undo")
        self._last_validated_pn = None
        self._refresh_pn_item(pn, "EN COURS")
        self.statusBar().showMessage(f"↩  Annulé : {pn} remis en EN COURS.", 3000)

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
        saved_pn     = self._current_pn

        # Naviguer IMMÉDIATEMENT vers le PN suivant (affichage sans délai)
        self._next_pn()

        # Écriture en DB (SQLite rapide, quelques ms)
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

        # Mise à jour ciblée de l'item PN (pas de reconstruction complète)
        self._refresh_pn_item(saved_pn, decision_val)
        self._last_validated_pn = saved_pn

        label = "mis en attente" if self._expert_mode else "validé(s)"
        self.statusBar().showMessage(
            f"{'📋' if self._expert_mode else '✓'}  {len(forms)} DECA(s) {label} pour {saved_pn}.", 4000
        )

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
        """Export modèle d'import : Marquage + N.Services décidés (prêt à importer)."""
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
        df = pd.DataFrame([dict(r) for r in rows])[
            ["marquage", "n_service1", "n_service2", "n_service3", "n_service4"]
        ]
        df.columns = ["Marquage", "[Service] Service1", "[Service] Service2",
                      "[Service] Service3", "[Service] Service4"]
        df.fillna("", inplace=True)
        df.to_excel(path, index=False)
        self.statusBar().showMessage(f"Modèle d'import réussi → {path}", 5000)

    def _open_stats(self):
        from stats_window import StatsWindow
        if not hasattr(self, "_stats_win") or not self._stats_win.isVisible():
            self._stats_win = StatsWindow()
        self._stats_win.show()
        self._stats_win.raise_()


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
