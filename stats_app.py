"""Point d'entrée standalone pour l'application Statistiques DECA_Master."""
import sys
from pathlib import Path

# Assure que le dossier racine est dans le path (utile si lancé depuis un autre répertoire)
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor

from db.db import init_schema
from stats_window import StatsWindow


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,        QColor("#f5f5f5"))
    palette.setColor(QPalette.ColorRole.WindowText,    QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Base,          QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f0f0f0"))
    palette.setColor(QPalette.ColorRole.Text,          QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Button,        QColor("#e0e0e0"))
    palette.setColor(QPalette.ColorRole.ButtonText,    QColor("#000000"))
    palette.setColor(QPalette.ColorRole.Highlight,     QColor("#6366f1"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)

    init_schema()

    win = StatsWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
