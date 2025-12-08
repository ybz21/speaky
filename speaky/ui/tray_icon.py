from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal, QObject
import os
import platform

from ..i18n import t


def get_app_icon() -> QIcon:
    """Get the application icon, returns QIcon object"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    resources_dir = os.path.join(base_dir, "resources")

    # Try different icon formats
    icon_files = ["icon.png", "icon_64.png", "icon.ico", "icon.svg"]
    for icon_file in icon_files:
        icon_path = os.path.join(resources_dir, icon_file)
        if os.path.exists(icon_path):
            return QIcon(icon_path)

    # Fallback to system icon
    style = QApplication.style()
    return style.standardIcon(style.StandardPixmap.SP_ComputerIcon)


def get_tray_icon() -> QIcon:
    """Get icon optimized for system tray (smaller size)"""
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    resources_dir = os.path.join(base_dir, "resources")

    # Prefer smaller sizes for tray
    if platform.system() == "Windows":
        # Windows tray prefers ICO
        icon_files = ["icon.ico", "icon_32.png", "icon_64.png", "icon.png"]
    else:
        # macOS/Linux prefer PNG
        icon_files = ["icon_32.png", "icon_64.png", "icon.png", "icon.ico"]

    for icon_file in icon_files:
        icon_path = os.path.join(resources_dir, icon_file)
        if os.path.exists(icon_path):
            return QIcon(icon_path)

    # Fallback to system icon
    style = QApplication.style()
    return style.standardIcon(style.StandardPixmap.SP_ComputerIcon)


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
        self._tray.setIcon(get_tray_icon())
        self._tray.setToolTip(t("app_name"))

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
