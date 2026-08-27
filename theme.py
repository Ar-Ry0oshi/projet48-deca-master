"""Gestion du thème clair / sombre (Fusion palette) — partagé entre toutes les fenêtres."""
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt

_is_dark = False   # état courant (commence en clair)


def is_dark() -> bool:
    return _is_dark


def apply_light(app=None):
    global _is_dark
    _is_dark = False
    a = app or QApplication.instance()
    if not a:
        return
    a.setStyle("Fusion")
    a.setPalette(a.style().standardPalette())
    a.setStyleSheet("")


def apply_dark(app=None):
    global _is_dark
    _is_dark = True
    a = app or QApplication.instance()
    if not a:
        return
    a.setStyle("Fusion")
    pal = QPalette()
    D = QColor
    pal.setColor(QPalette.ColorRole.Window,          D(53, 53, 53))
    pal.setColor(QPalette.ColorRole.WindowText,      Qt.GlobalColor.white)
    pal.setColor(QPalette.ColorRole.Base,            D(35, 35, 35))
    pal.setColor(QPalette.ColorRole.AlternateBase,   D(45, 45, 45))
    pal.setColor(QPalette.ColorRole.ToolTipBase,     D(25, 25, 25))
    pal.setColor(QPalette.ColorRole.ToolTipText,     Qt.GlobalColor.white)
    pal.setColor(QPalette.ColorRole.Text,            Qt.GlobalColor.white)
    pal.setColor(QPalette.ColorRole.Button,          D(53, 53, 53))
    pal.setColor(QPalette.ColorRole.ButtonText,      Qt.GlobalColor.white)
    pal.setColor(QPalette.ColorRole.BrightText,      Qt.GlobalColor.red)
    pal.setColor(QPalette.ColorRole.Link,            D(42, 130, 218))
    pal.setColor(QPalette.ColorRole.Highlight,       D(42, 130, 218))
    pal.setColor(QPalette.ColorRole.HighlightedText, D(35, 35, 35))
    # zones désactivées
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, D(128, 128, 128))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       D(128, 128, 128))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, D(128, 128, 128))
    a.setPalette(pal)


def toggle(app=None):
    if _is_dark:
        apply_light(app)
    else:
        apply_dark(app)


def toggle_label() -> str:
    """Texte du bouton pour l'état SUIVANT (ce qui se passera au clic)."""
    return "☀️  Mode clair" if _is_dark else "🌙  Mode sombre"
