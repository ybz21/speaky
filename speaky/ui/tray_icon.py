from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal, QObject
import os

from ..i18n import t


class TrayIcon(QObject):
    settings_clicked = Signal()
    quit_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon()
        self._setup_icon()
        self._setup_menu()
        # Single click opens settings
        self._tray.activated.connect(self._on_activated)

    def _setup_icon(self):
        icon_path = self._get_icon_path()
        if icon_path and os.path.exists(icon_path):
            self._tray.setIcon(QIcon(icon_path))
        else:
            style = QApplication.style()
            self._tray.setIcon(style.standardIcon(style.StandardPixmap.SP_ComputerIcon))
        self._tray.setToolTip(t("app_name"))

    def _get_icon_path(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        icon_path = os.path.join(base_dir, "..", "resources", "icon.png")
        if os.path.exists(icon_path):
            return icon_path
        icon_path = os.path.join(base_dir, "resources", "icon.png")
        if os.path.exists(icon_path):
            return icon_path
        return ""

    def _setup_menu(self):
        menu = QMenu()

        settings_action = QAction(t("settings"), menu)
        settings_action.triggered.connect(self.settings_clicked.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction(t("quit"), menu)
        quit_action.triggered.connect(self.quit_clicked.emit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def show_message(self, title: str, message: str):
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 2000)

    def _on_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:  # Single click
            self.settings_clicked.emit()
