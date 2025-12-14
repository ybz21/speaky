"""Log viewer dialog"""

import os
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QFileDialog
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCursor

from ..i18n import t


class LogViewerDialog(QDialog):
    """Dialog for viewing application logs"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_file = Path.home() / ".speaky" / "speaky.log"
        self._auto_scroll = True
        self._last_size = 0
        self._setup_ui()
        self._setup_refresh_timer()
        self._load_log()

    def _setup_ui(self):
        self.setWindowTitle(t("log_viewer_title"))
        self.resize(800, 600)
        self.setMinimumSize(600, 400)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Header with file path
        header_layout = QHBoxLayout()
        path_label = QLabel(f"{t('log_file_path')}: {self._log_file}")
        path_label.setStyleSheet("color: #888; font-size: 11px;")
        header_layout.addWidget(path_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Log text area
        self._text_edit = QPlainTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = QFont("Consolas, Monaco, monospace")
        font.setPointSize(10)
        self._text_edit.setFont(font)
        self._text_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                border: 1px solid #333;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self._text_edit, 1)

        # Button bar
        button_layout = QHBoxLayout()

        self._refresh_btn = QPushButton(t("refresh"))
        self._refresh_btn.clicked.connect(self._load_log)
        button_layout.addWidget(self._refresh_btn)

        self._clear_btn = QPushButton(t("clear_log"))
        self._clear_btn.clicked.connect(self._clear_log)
        button_layout.addWidget(self._clear_btn)

        self._export_btn = QPushButton(t("export_log"))
        self._export_btn.clicked.connect(self._export_log)
        button_layout.addWidget(self._export_btn)

        button_layout.addStretch()

        self._auto_scroll_btn = QPushButton(t("auto_scroll_on"))
        self._auto_scroll_btn.setCheckable(True)
        self._auto_scroll_btn.setChecked(True)
        self._auto_scroll_btn.clicked.connect(self._toggle_auto_scroll)
        button_layout.addWidget(self._auto_scroll_btn)

        self._close_btn = QPushButton(t("close"))
        self._close_btn.clicked.connect(self.close)
        button_layout.addWidget(self._close_btn)

        layout.addLayout(button_layout)

    def _setup_refresh_timer(self):
        """Set up timer to auto-refresh log content"""
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._check_log_update)
        self._refresh_timer.start(1000)  # Check every second

    def _load_log(self):
        """Load log file content"""
        try:
            if self._log_file.exists():
                with open(self._log_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
                self._text_edit.setPlainText(content)
                self._last_size = self._log_file.stat().st_size
                if self._auto_scroll:
                    self._scroll_to_bottom()
            else:
                self._text_edit.setPlainText(t("log_file_not_found"))
        except Exception as e:
            self._text_edit.setPlainText(f"Error loading log: {e}")

    def _check_log_update(self):
        """Check if log file has been updated"""
        if not self.isVisible():
            return
        try:
            if self._log_file.exists():
                current_size = self._log_file.stat().st_size
                if current_size != self._last_size:
                    self._load_log()
        except Exception:
            pass

    def _scroll_to_bottom(self):
        """Scroll to the bottom of the log"""
        cursor = self._text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self._text_edit.setTextCursor(cursor)
        self._text_edit.ensureCursorVisible()

    def _toggle_auto_scroll(self, checked: bool):
        """Toggle auto-scroll mode"""
        self._auto_scroll = checked
        if checked:
            self._auto_scroll_btn.setText(t("auto_scroll_on"))
            self._scroll_to_bottom()
        else:
            self._auto_scroll_btn.setText(t("auto_scroll_off"))

    def _clear_log(self):
        """Clear the log file"""
        try:
            if self._log_file.exists():
                with open(self._log_file, "w", encoding="utf-8") as f:
                    f.write("")
                self._text_edit.clear()
                self._last_size = 0
        except Exception as e:
            self._text_edit.setPlainText(f"Error clearing log: {e}")

    def _export_log(self):
        """Export log to a file"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            t("export_log"),
            str(Path.home() / "speaky_log.txt"),
            "Text Files (*.txt);;All Files (*)"
        )
        if file_path:
            try:
                content = self._text_edit.toPlainText()
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
            except Exception as e:
                from qfluentwidgets import MessageBox
                MessageBox(t("error"), str(e), self).exec()

    def closeEvent(self, event):
        """Stop timer when closing"""
        self._refresh_timer.stop()
        super().closeEvent(event)
