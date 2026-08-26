"""Lanceur standalone pour le Mode Plan (assignation Service 4)."""
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from plan_window import PlanWindow

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = PlanWindow()
    win.show()
    sys.exit(app.exec())
