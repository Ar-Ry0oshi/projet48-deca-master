"""Lanceur standalone pour le Mode Plan (assignation Service 4)."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QAbstractItemView,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from config import MODULES


class _ModulePickerDialog(QDialog):
    """Sélection du module avant d'ouvrir le Mode Plan."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mode Plan — Choisir le module")
        self.setMinimumWidth(340)
        self.selected_module: str = ""

        lay = QVBoxLayout(self)
        lay.setSpacing(10)

        lbl = QLabel("Sélectionnez le module / sous-module à traiter :")
        lbl.setWordWrap(True)
        font = QFont(); font.setBold(True)
        lbl.setFont(font)
        lay.addWidget(lbl)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for m in MODULES:
            item = QListWidgetItem(m)
            item.setData(Qt.ItemDataRole.UserRole, m)
            self._list.addItem(item)
        self._list.itemDoubleClicked.connect(self._accept)
        lay.addWidget(self._list)

        btn_row = QHBoxLayout()
        btn_ok = QPushButton("Ouvrir le plan")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._accept)
        btn_cancel = QPushButton("Annuler")
        btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        lay.addLayout(btn_row)

    def _accept(self):
        sel = self._list.selectedItems()
        if not sel:
            return
        self.selected_module = sel[0].data(Qt.ItemDataRole.UserRole)
        self.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    picker = _ModulePickerDialog()
    if picker.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)

    from plan_window import PlanWindow
    win = PlanWindow(module=picker.selected_module)
    win.show()
    sys.exit(app.exec())
