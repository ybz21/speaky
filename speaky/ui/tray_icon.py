from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction, QClipboard
from PySide6.QtCore import Signal, QObject
import os
import platform

from ..i18n import t
from ..history import get_history, clear_history


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
        self._menu = QMenu()

        settings_action = QAction(t("settings"), self._menu)
        settings_action.triggered.connect(self.settings_clicked.emit)
        self._menu.addAction(settings_action)

        # History submenu
        self._history_menu = QMenu(t("history"), self._menu)
        self._menu.addMenu(self._history_menu)
        self._update_history_menu()

        self._menu.addSeparator()

        quit_action = QAction(t("quit"), self._menu)
        quit_action.triggered.connect(self.quit_clicked.emit)
        self._menu.addAction(quit_action)

        # Update history menu before showing
        self._menu.aboutToShow.connect(self._update_history_menu)

        self._tray.setContextMenu(self._menu)

    def _update_history_menu(self):
        """Update history submenu with recent items"""
        self._history_menu.clear()

        history_items = get_history(10)

        if not history_items:
            empty_action = QAction(t("history_empty"), self._history_menu)
            empty_action.setEnabled(False)
            self._history_menu.addAction(empty_action)
        else:
            for item in history_items:
                # Truncate long text for menu display
                display_text = item.text[:40] + "..." if len(item.text) > 40 else item.text
                # Replace newlines for display
                display_text = display_text.replace("\n", " ")
                action = QAction(display_text, self._history_menu)
                # Store full text in action data
                action.setData(item.text)
                action.triggered.connect(self._on_history_item_clicked)
                self._history_menu.addAction(action)

            self._history_menu.addSeparator()

            clear_action = QAction(t("clear_history"), self._history_menu)
            clear_action.triggered.connect(self._on_clear_history)
            self._history_menu.addAction(clear_action)

    def _on_history_item_clicked(self):
        """Copy history item to clipboard"""
        action = self.sender()
        if action:
            text = action.data()
            if text:
                clipboard = QApplication.clipboard()
                clipboard.setText(text)
                self._tray.showMessage(
                    t("app_name"),
                    t("history_copied"),
                    QSystemTrayIcon.MessageIcon.Information,
                    1500
                )

    def _on_clear_history(self):
        """Clear all history"""
        clear_history()
        self._update_history_menu()

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
