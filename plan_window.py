"""
plan_window.py — Mode Plan interactif pour l'assignation de Service 4.

Utilisation :
  - Ouvrir un PDF de plan d'atelier
  - Définir des zones polygonales (cliquer les sommets, double-clic pour fermer)
  - Sélectionner des DECAs dans le panel, cliquer sur une zone → Service 4 assigné

Zones sauvegardées dans un fichier .zones.json à côté du PDF.
"""
from __future__ import annotations
import json
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QGraphicsView, QGraphicsScene,
    QGraphicsPolygonItem, QGraphicsTextItem,
    QPushButton, QLabel, QTreeWidget, QTreeWidgetItem, QLineEdit,
    QAbstractItemView, QSplitter, QMessageBox, QFileDialog,
    QWidget, QInputDialog, QSizePolicy, QHeaderView,
)
from PyQt6.QtCore import Qt, QPointF, QUrl, pyqtSignal
from PyQt6.QtGui import (
    QPolygonF, QColor, QPen, QBrush, QPixmap, QFont, QCursor, QPainter,
    QDesktopServices,
)

try:
    import fitz  # PyMuPDF
    FITZ_OK = True
except ImportError:
    FITZ_OK = False

from functools import lru_cache
from db import queries
from config import DOCS_DIR
from services import svc4_options as _svc4_options

_BLD_TO_SVC1 = {
    "MF":  "SAESB MF - B24 - MODULE MX / REP",
    "LSO": "SAESB LSO - B118 - ENGINE MX / REP",
}
_SVC1_PREFIX_OTHER = {
    "MF":  "SAESB LSO",
    "LSO": "SAESB MF",
}

@lru_cache(maxsize=1)
def _doc_index() -> list:
    if not DOCS_DIR or not DOCS_DIR.exists():
        return []
    return sorted(DOCS_DIR.glob("*.pdf")) + sorted(DOCS_DIR.glob("*.PDF"))

def _find_docs(pn: str) -> list:
    if not pn:
        return []
    pn_norm = pn.strip().upper()
    return [f for f in _doc_index() if pn_norm in f.stem.upper()]

# ── Palette de couleurs pour les zones ───────────────────────────────────────

_ZONE_COLORS = [
    "#3b82f6", "#10b981", "#f59e0b", "#8b5cf6",
    "#ef4444", "#06b6d4", "#f97316", "#84cc16",
    "#ec4899", "#14b8a6",
]


# ── Zone (polygone cliquable) ─────────────────────────────────────────────────

class PlanZone(QGraphicsPolygonItem):

    def __init__(self, points: list, name: str, service4: str,
                 color_idx: int, assign_mode_ref: list):
        poly = QPolygonF([QPointF(x, y) for x, y in points])
        super().__init__(poly)
        self.zone_name    = name
        self.service4     = service4
        self._cidx        = color_idx
        self._color       = QColor(_ZONE_COLORS[color_idx % len(_ZONE_COLORS)])
        self._assign_ref  = assign_mode_ref
        self.setAcceptHoverEvents(True)
        self._apply_style(False)
        # label centré sur la zone
        self._lbl = QGraphicsTextItem(name, self)
        font = QFont(); font.setBold(True); font.setPointSize(9)
        self._lbl.setFont(font)
        self._lbl.setDefaultTextColor(Qt.GlobalColor.white)
        self._center_label()

    def _apply_style(self, hovered: bool):
        c = self._color
        alpha = 150 if hovered else 85
        self.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), alpha)))
        self.setPen(QPen(c, 3 if hovered else 2))

    def _center_label(self):
        br  = self.polygon().boundingRect()
        lb  = self._lbl.boundingRect()
        self._lbl.setPos(
            br.center().x() - lb.width()  / 2,
            br.center().y() - lb.height() / 2,
        )

    def hoverEnterEvent(self, e):
        self._apply_style(True)
        if self._assign_ref[0]:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        super().hoverEnterEvent(e)

    def hoverLeaveEvent(self, e):
        self._apply_style(False)
        self.unsetCursor()
        super().hoverLeaveEvent(e)

    def to_dict(self) -> dict:
        return {
            "name":      self.zone_name,
            "service4":  self.service4,
            "color_idx": self._cidx,
            "points":    [[p.x(), p.y()] for p in self.polygon()],
        }


# ── Scène ─────────────────────────────────────────────────────────────────────

class PlanScene(QGraphicsScene):
    zone_clicked = pyqtSignal(object)

    def __init__(self, assign_mode_ref: list, parent=None):
        super().__init__(parent)
        self._assign_ref = assign_mode_ref

    def emit_zone_click(self, zone: PlanZone):
        if self._assign_ref[0]:
            self.zone_clicked.emit(zone)


# ── Vue (gère le dessin et le zoom) ──────────────────────────────────────────

class PlanView(QGraphicsView):
    polygon_finished = pyqtSignal(list)  # [[x,y], ...]

    def __init__(self, scene: PlanScene, assign_mode_ref: list):
        super().__init__(scene)
        self._assign_ref        = assign_mode_ref
        self._drawing           = False
        self._pts: list[QPointF] = []
        self._preview           = []        # temp items
        self._skip_next_press   = False
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    # ── Zoom molette ──────────────────────────────────────────────────────

    def wheelEvent(self, e):
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    # ── Clavier ───────────────────────────────────────────────────────────

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape and self._drawing:
            self._cancel()
        super().keyPressEvent(e)

    # ── Souris ────────────────────────────────────────────────────────────

    def mousePressEvent(self, e):
        if self._assign_ref[0]:
            item = self.itemAt(e.pos())
            while item is not None:
                if isinstance(item, PlanZone):
                    self.scene().emit_zone_click(item)
                    return
                item = item.parentItem()
            return

        if not self._drawing or e.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(e)
            return
        if self._skip_next_press:
            self._skip_next_press = False
            return
        pt = self.mapToScene(e.pos())
        self._pts.append(pt)
        self._redraw_preview()

    def mouseDoubleClickEvent(self, e):
        if not self._drawing or not self._assign_ref[0] == False:
            return
        self._skip_next_press = True
        if len(self._pts) >= 3:
            coords = [[p.x(), p.y()] for p in self._pts]
            self._cancel()
            self.polygon_finished.emit(coords)
        else:
            QMessageBox.information(self, "Zone", "Il faut au moins 3 points.")

    # ── Preview du polygone en cours ──────────────────────────────────────

    def _redraw_preview(self):
        self._clear_preview()
        pts = self._pts
        if len(pts) < 1:
            return
        yellow = QPen(QColor("#facc15"), 2, Qt.PenStyle.DashLine)
        ghost  = QPen(QColor(250, 204, 21, 90), 1, Qt.PenStyle.DotLine)
        for i in range(len(pts) - 1):
            ln = self.scene().addLine(
                pts[i].x(), pts[i].y(), pts[i+1].x(), pts[i+1].y(), yellow)
            self._preview.append(ln)
        if len(pts) >= 2:
            ln = self.scene().addLine(
                pts[-1].x(), pts[-1].y(), pts[0].x(), pts[0].y(), ghost)
            self._preview.append(ln)
        for pt in pts:
            dot = self.scene().addEllipse(pt.x()-4, pt.y()-4, 8, 8,
                                           QPen(Qt.GlobalColor.yellow),
                                           QBrush(QColor("#facc15")))
            self._preview.append(dot)

    def _clear_preview(self):
        for it in self._preview:
            self.scene().removeItem(it)
        self._preview = []

    def _cancel(self):
        self._clear_preview()
        self._pts = []

    # ── Activation / désactivation mode dessin ────────────────────────────

    def start_drawing(self):
        self._drawing = True
        self._pts     = []
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def stop_drawing(self):
        self._cancel()
        self._drawing = False
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.unsetCursor()


# ── Panel latéral (sélection DECAs) ──────────────────────────────────────────

# Colonnes : Marquage | Loc 1 | Loc 2 | Loc 3 | Svc 4 assigné
_COLS      = ["Marquage", "Loc 1", "Loc 2", "Loc 3", "Svc 4 assigné"]
_COL_W     = [130, 70, 70, 70, 100]


class DECAPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._module   = ""
        self._building = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        lbl = QLabel("Sélection DECAs")
        lbl.setStyleSheet("font-weight:bold; color:#1a5276;")
        lay.addWidget(lbl)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filtrer PN / marquage…")
        self._search.textChanged.connect(self._filter)
        lay.addWidget(self._search)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(_COLS)
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._tree.setAlternatingRowColors(True)
        self._tree.setUniformRowHeights(True)
        hdr = self._tree.header()
        hdr.setStretchLastSection(True)
        for i, w in enumerate(_COL_W):
            self._tree.setColumnWidth(i, w)
        self._tree.itemDoubleClicked.connect(self._on_double_click)
        lay.addWidget(self._tree, stretch=1)

        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet("color:#666; font-size:11px;")
        lay.addWidget(self._lbl_count)

    def load(self, module: str = "", building: str = ""):
        self._module   = module
        self._building = building
        self._tree.clear()
        all_rows = queries.get_all_tools_for_export(module)
        # filtrer: si bâtiment sélectionné, exclure les outils clairement de l'autre bâtiment
        other_prefix = _SVC1_PREFIX_OTHER.get(building, "")
        rows = [
            r for r in all_rows
            if not other_prefix or not (dict(r).get("service1") or "").startswith(other_prefix)
        ]
        pn_map: dict[str, list] = {}
        for r in rows:
            pn = r["pn_short"] or "—"
            pn_map.setdefault(pn, []).append(r)

        for pn, tools in sorted(pn_map.items()):
            # ── Ligne PN ──────────────────────────────────────────────────
            docs  = _find_docs(pn)
            tds   = f"  📄 ({len(docs)})" if docs else ""
            pn_item = QTreeWidgetItem([pn + tds, "", "", "", ""])
            pn_item.setData(0, Qt.ItemDataRole.UserRole,
                            {"type": "pn", "pn": pn, "docs": docs})
            f = QFont(); f.setBold(True)
            pn_item.setFont(0, f)
            if docs:
                pn_item.setToolTip(0, "\n".join(d.name for d in docs))
            self._tree.addTopLevelItem(pn_item)

            # ── Lignes DECA ───────────────────────────────────────────────
            marquages = [t["marquage"] for t in tools]
            for t in tools:
                marq  = t["marquage"]
                loc1  = t["localisation1"] or ""
                loc2  = t["localisation2"] or ""
                loc3  = t["localisation3"] or ""
                svc4  = t["n_service4"] or t["service4"] or ""
                child = QTreeWidgetItem([marq, loc1, loc2, loc3, svc4])
                child.setData(0, Qt.ItemDataRole.UserRole,
                              {"type": "deca", "marquage": marq, "pn": pn,
                               "all_marquages": marquages, "row": dict(t)})
                pn_item.addChild(child)

        self._lbl_count.setText(
            f"{len(rows)} DECAs  ·  double-clic = fiche  ·  clic PN 📄 = TDS")

    def _on_double_click(self, item: QTreeWidgetItem, col: int):
        d = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if d.get("type") == "deca":
            # ouvrir la fiche outil
            from deca_manager import DECADetailDialog
            marq = d["marquage"]
            dlg  = DECADetailDialog(marq, d.get("all_marquages", [marq]),
                                    parent=self)
            dlg.exec()
        elif d.get("type") == "pn":
            # ouvrir TDS
            docs = d.get("docs", [])
            if not docs:
                return
            if len(docs) == 1:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(docs[0])))
            else:
                from PyQt6.QtWidgets import QMenu
                menu = QMenu(self)
                for doc in docs:
                    act = menu.addAction(doc.name)
                    act.setData(str(doc))
                chosen = menu.exec(self._tree.viewport().mapToGlobal(
                    self._tree.visualItemRect(item).bottomLeft()))
                if chosen:
                    QDesktopServices.openUrl(QUrl.fromLocalFile(chosen.data()))

    def selected_marquages(self) -> list[str]:
        result = []
        for item in self._tree.selectedItems():
            d = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if d.get("type") == "deca":
                result.append(d["marquage"])
            elif d.get("type") == "pn":
                for i in range(item.childCount()):
                    cd = item.child(i).data(0, Qt.ItemDataRole.UserRole) or {}
                    if cd.get("marquage"):
                        result.append(cd["marquage"])
        return list(dict.fromkeys(result))

    def _filter(self, text: str):
        t = text.strip().lower()
        for i in range(self._tree.topLevelItemCount()):
            pn_item = self._tree.topLevelItem(i)
            pn_match = not t or t in pn_item.text(0).lower()
            any_child = False
            for j in range(pn_item.childCount()):
                c = pn_item.child(j)
                show = pn_match or t in c.text(0).lower()
                c.setHidden(not show)
                if show:
                    any_child = True
            pn_item.setHidden(not (pn_match or any_child))


# ── Fenêtre principale ────────────────────────────────────────────────────────

class PlanWindow(QDialog):

    def __init__(self, module: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mode Plan — Assignation Service 4")
        self.setWindowFlag(Qt.WindowType.Window)   # fenêtre indépendante redimensionnable
        self.resize(1400, 900)
        self._module      = module
        self._building    = ""   # "MF" ou "LSO"
        self._svc1        = ""   # service1 complet pour filtres
        self._zones: list[PlanZone] = []
        self._pdf_path: Path | None = None
        self._zone_file:  Path | None = None
        self._assign_mode = [False]   # ref mutable partagée avec view/zones/scene
        self._setup_ui()

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── Barre d'outils ────────────────────────────────────────────────
        bar = QHBoxLayout()

        self._btn_pdf = QPushButton("📂  Ouvrir plan PDF")
        self._btn_pdf.clicked.connect(self._open_pdf)
        bar.addWidget(self._btn_pdf)

        bar.addSpacing(12)

        self._btn_edit = QPushButton("✏️  Éditer zones")
        self._btn_edit.setCheckable(True)
        self._btn_edit.setEnabled(False)
        self._btn_edit.toggled.connect(self._toggle_edit)
        bar.addWidget(self._btn_edit)

        self._btn_assign = QPushButton("🎯  Assigner")
        self._btn_assign.setCheckable(True)
        self._btn_assign.setEnabled(False)
        self._btn_assign.toggled.connect(self._toggle_assign)
        bar.addWidget(self._btn_assign)

        bar.addSpacing(12)

        self._btn_del_zone = QPushButton("🗑  Supprimer zone")
        self._btn_del_zone.setEnabled(False)
        self._btn_del_zone.clicked.connect(self._delete_zone)
        bar.addWidget(self._btn_del_zone)

        bar.addSpacing(12)

        self._btn_save_zones = QPushButton("💾  Sauvegarder zones")
        self._btn_save_zones.setEnabled(False)
        self._btn_save_zones.setToolTip("Sauvegarde la définition des zones dans le fichier .zones.json\n(les assignations sont sauvegardées automatiquement dans la DB)")
        self._btn_save_zones.clicked.connect(self._save_zones_explicit)
        bar.addWidget(self._btn_save_zones)

        bar.addStretch()

        self._lbl_mode = QLabel("Ouvrez un PDF pour commencer")
        self._lbl_mode.setStyleSheet("color:#555; font-style:italic;")
        bar.addWidget(self._lbl_mode)

        root.addLayout(bar)

        # ── Corps ─────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._scene = PlanScene(self._assign_mode)
        self._view  = PlanView(self._scene, self._assign_mode)
        self._scene.zone_clicked.connect(self._on_zone_clicked)
        self._view.polygon_finished.connect(self._on_polygon_finished)
        splitter.addWidget(self._view)

        self._panel = DECAPanel()
        self._panel.setMinimumWidth(280)
        self._panel.setMaximumWidth(420)
        splitter.addWidget(self._panel)
        splitter.setSizes([1020, 380])

        root.addWidget(splitter, stretch=1)

        # ── Barre de statut ───────────────────────────────────────────────
        self._status = QLabel("")
        self._status.setStyleSheet("padding:2px 6px; font-size:11px; color:#1a5276;")
        root.addWidget(self._status)

        self._panel.load(self._module)

    # ── PDF ───────────────────────────────────────────────────────────────

    def _open_pdf(self):
        if not FITZ_OK:
            QMessageBox.critical(self, "Dépendance manquante",
                "PyMuPDF est requis pour afficher le PDF.\n\n"
                "Installez-le :\n  pip install pymupdf")
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir plan d'atelier", "", "PDF (*.pdf)")
        if not path:
            return

        # Choix du bâtiment pour filtrer les DECAs et les svc4 disponibles
        bld, ok = QInputDialog.getItem(
            self, "Bâtiment", "Ce plan correspond à quel bâtiment ?",
            ["MF", "LSO"], editable=False)
        if not ok:
            return
        self._building = bld
        self._svc1     = _BLD_TO_SVC1.get(bld, "")

        self._pdf_path  = Path(path)
        self._zone_file = self._pdf_path.with_suffix(f".{bld.lower()}.zones.json")
        self._render_pdf()
        self._load_zones()
        self._btn_edit.setEnabled(True)
        self._btn_assign.setEnabled(True)
        self._btn_save_zones.setEnabled(True)
        self._lbl_mode.setText(f"Plan {bld} : {self._pdf_path.name}")
        self._status.setText(f"{len(self._zones)} zones chargées.")
        self._panel.load(self._module, building=self._building)

    def _render_pdf(self):
        self._scene.clear()
        self._zones = []
        doc  = fitz.open(str(self._pdf_path))
        page = doc[0]
        pix  = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        qpix = QPixmap()
        qpix.loadFromData(pix.tobytes("png"))
        self._scene.addPixmap(qpix)
        self._scene.setSceneRect(0, 0, qpix.width(), qpix.height())
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        doc.close()

    # ── Persistence des zones ─────────────────────────────────────────────

    def _load_zones(self):
        if not self._zone_file or not self._zone_file.exists():
            return
        data = json.loads(self._zone_file.read_text(encoding="utf-8"))
        for z in data.get("zones", []):
            self._add_zone(z["points"], z["name"], z["service4"], z.get("color_idx", 0))

    def _save_zones(self):
        if not self._zone_file:
            return
        self._zone_file.write_text(
            json.dumps({"zones": [z.to_dict() for z in self._zones]},
                       indent=2, ensure_ascii=False),
            encoding="utf-8")

    def _save_zones_explicit(self):
        self._save_zones()
        self._status.setText(
            f"💾  Zones sauvegardées ({len(self._zones)}) dans {self._zone_file.name if self._zone_file else '?'}.")

    def _add_zone(self, points: list, name: str, service4: str, color_idx: int) -> PlanZone:
        zone = PlanZone(points, name, service4, color_idx, self._assign_mode)
        self._scene.addItem(zone)
        self._zones.append(zone)
        return zone

    # ── Mode édition ─────────────────────────────────────────────────────

    def _toggle_edit(self, checked: bool):
        if checked:
            self._btn_assign.setChecked(False)
            self._assign_mode[0] = False
            self._view.start_drawing()
            self._btn_del_zone.setEnabled(True)
            self._lbl_mode.setText(
                "✏️  Clic = ajouter un point   |   Double-clic = fermer la zone   |   Échap = annuler")
        else:
            self._view.stop_drawing()
            self._btn_del_zone.setEnabled(False)
            self._lbl_mode.setText(f"Plan : {self._pdf_path.name if self._pdf_path else ''}")

    def _on_polygon_finished(self, coords: list):
        svc4_list = _svc4_options(self._svc1) if self._svc1 else []
        if svc4_list:
            name, ok = QInputDialog.getItem(
                self, "Service 4 de la zone",
                f"Service 4 ({self._building}) :",
                svc4_list, editable=True)
        else:
            name, ok = QInputDialog.getText(
                self, "Nouvelle zone", "Service 4 (nom de la zone) :")
        if not ok or not name.strip():
            return
        name = name.strip()
        idx  = len(self._zones)
        self._add_zone(coords, name, name, idx)
        self._save_zones()
        self._status.setText(f"✅  Zone «{name}» créée et sauvegardée ({len(self._zones)} zones au total).")

    def _delete_zone(self):
        if not self._zones:
            return
        names = [z.zone_name for z in self._zones]
        name, ok = QInputDialog.getItem(
            self, "Supprimer une zone", "Zone à supprimer :", names, editable=False)
        if not ok:
            return
        zone = next((z for z in self._zones if z.zone_name == name), None)
        if zone:
            self._scene.removeItem(zone)
            self._zones.remove(zone)
            self._save_zones()
            self._status.setText(f"Zone «{name}» supprimée.")

    # ── Mode assignation ──────────────────────────────────────────────────

    def _toggle_assign(self, checked: bool):
        if checked:
            self._btn_edit.setChecked(False)
            self._view.stop_drawing()
            self._assign_mode[0] = True
            self._lbl_mode.setText(
                "🎯  Sélectionnez des DECAs dans le panel → cliquez sur une zone")
        else:
            self._assign_mode[0] = False
            self._lbl_mode.setText(f"Plan : {self._pdf_path.name if self._pdf_path else ''}")

    def _on_zone_clicked(self, zone: PlanZone):
        marquages = self._panel.selected_marquages()
        if not marquages:
            self._status.setText("⚠️  Aucun DECA sélectionné dans le panel de droite.")
            return
        n = len(marquages)
        rep = QMessageBox.question(
            self, "Assigner Service 4",
            f"Assigner Service 4 = «{zone.service4}»\nà {n} DECA(s) sélectionné(s) ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if rep != QMessageBox.StandardButton.Yes:
            return

        errors = []
        for marq in marquages:
            try:
                dec  = queries.get_decision(marq)
                tool = queries.get_tool(marq)
                dec_d  = dict(dec)  if dec  else {}
                tool_d = dict(tool) if tool else {}
                queries.upsert_decision(
                    marquage       = marq,
                    pn_short       = tool_d.get("pn_short", ""),
                    module_context = self._module,
                    n_service1     = dec_d.get("n_service1"),
                    n_service2     = dec_d.get("n_service2"),
                    n_service3     = dec_d.get("n_service3"),
                    n_service4     = zone.service4,
                    pre_check      = dec_d.get("pre_check"),
                    decision       = dec_d.get("decision", "EN COURS"),
                    commentaire    = dec_d.get("commentaire"),
                    updated_by     = "plan_mode",
                )
            except Exception as ex:
                errors.append(f"{marq}: {ex}")

        if errors:
            self._status.setText(f"⚠️  {len(errors)} erreur(s) — reste assigné normalement.")
        else:
            self._status.setText(
                f"✅  «{zone.service4}» assigné à {n} DECA(s).")
        self._panel.load(self._module)
