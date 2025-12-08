from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction, QApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import pyqtSignal, QObject
import os


class TrayIcon(QObject):
    settings_clicked = pyqtSignal()
    quit_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tray = QSystemTrayIcon()
        self._setup_icon()
        self._setup_menu()

    def _setup_icon(self):
        icon_path = self._get_icon_path()
        if icon_path and os.path.exists(icon_path):
            self._tray.setIcon(QIcon(icon_path))
        else:
            self._tray.setIcon(QApplication.style().standardIcon(
                QApplication.style().SP_ComputerIcon
            ))
        self._tray.setToolTip("SpeekInput - 语音输入")

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

        settings_action = QAction("设置", menu)
        settings_action.triggered.connect(self.settings_clicked.emit)
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self.quit_clicked.emit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def show_message(self, title: str, message: str):
        self._tray.showMessage(title, message, QSystemTrayIcon.Information, 2000)
