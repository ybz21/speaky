from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QScrollArea, QFrame, QPlainTextEdit, QFileDialog
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QIcon, QFont, QTextCursor

from qfluentwidgets import (
    ComboBox, EditableComboBox, LineEdit, PasswordLineEdit, PrimaryPushButton,
    SwitchButton, Slider, DoubleSpinBox, BodyLabel, SubtitleLabel,
    CardWidget, FluentIcon, MessageBox, PushButton,
    setTheme, Theme, setThemeColor
)
from qfluentwidgets import FluentWindow

from speaky.i18n import t, i18n
from speaky.autostart import is_autostart_enabled, set_autostart
from speaky.ui.tray_icon import get_app_icon


def apply_theme(theme: str):
    """Apply theme setting"""
    if theme == "light":
        setTheme(Theme.LIGHT)
    elif theme == "dark":
        setTheme(Theme.DARK)
    else:  # auto
        setTheme(Theme.AUTO)


class SettingCard(CardWidget):
    """Custom setting card with label and widget"""

    def __init__(self, title: str, widget: QWidget, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)

        self._label = BodyLabel(title, self)
        layout.addWidget(self._label)
        layout.addStretch()
        layout.addWidget(widget)


class SettingsPage(QScrollArea):
    """Base class for settings pages"""
    save_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("background: transparent;")

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(20, 20, 20, 20)
        self._layout.setSpacing(12)
        self.setWidget(self._container)

    def add_group_label(self, text: str):
        label = SubtitleLabel(text, self._container)
        label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(label)

    def add_card(self, title: str, widget: QWidget):
        card = SettingCard(title, widget, self._container)
        self._layout.addWidget(card)
        return card

    def add_stretch(self):
        self._layout.addStretch()

    def add_save_button(self):
        """Add save button at the bottom of page"""
        self._layout.addStretch()
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = PrimaryPushButton(t("save"))
        save_btn.setMinimumWidth(120)
        save_btn.clicked.connect(self.save_clicked.emit)
        btn_layout.addWidget(save_btn)
        self._layout.addLayout(btn_layout)


class CorePage(SettingsPage):
    """Core settings page"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        _hotkey_items = [
            "ctrl", "alt", "shift", "cmd",
            "ctrl_l", "ctrl_r", "alt_l", "alt_r", "shift_l", "shift_r",
            "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
            "space", "tab", "caps_lock",
        ]

        # ═══════════════ 热键配置 ═══════════════
        self.add_group_label(t("hotkey_group"))

        self.hotkey_combo = EditableComboBox()
        self.hotkey_combo.addItems(_hotkey_items)
        self.hotkey_combo.setMinimumWidth(150)
        self.add_card(t("hotkey_label"), self.hotkey_combo)

        self.ai_hotkey_combo = EditableComboBox()
        self.ai_hotkey_combo.addItems(_hotkey_items)
        self.ai_hotkey_combo.setMinimumWidth(150)
        self.add_card(t("ai_hotkey_label"), self.ai_hotkey_combo)

        self.hold_time_spin = DoubleSpinBox()
        self.hold_time_spin.setRange(0.0, 5.0)
        self.hold_time_spin.setSingleStep(0.1)
        self.hold_time_spin.setDecimals(1)
        self.hold_time_spin.setMinimumWidth(120)
        self.add_card(t("hold_time_label"), self.hold_time_spin)

        self.sound_notification = SwitchButton()
        self.add_card(t("sound_notification"), self.sound_notification)

        self.ai_auto_enter = SwitchButton()
        self.add_card(t("ai_auto_enter"), self.ai_auto_enter)

        # ═══════════════ 语音引擎 ═══════════════
        self.add_group_label(t("engine_group"))

        self.engine_combo = ComboBox()
        self._engine_items = [
            ("volc_bigmodel", t("volc_bigmodel_settings")),
            ("local", t("local_settings")),
        ]
        for engine_id, engine_name in self._engine_items:
            self.engine_combo.addItem(engine_name)
        self.engine_combo.setMinimumWidth(220)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_index_changed)
        self.add_card(t("engine_label"), self.engine_combo)

        # 火山大模型配置
        self.volc_bigmodel_appkey = LineEdit()
        self.volc_bigmodel_appkey.setMinimumWidth(250)
        self._volc_bigmodel_appkey_card = self.add_card(t("app_key"), self.volc_bigmodel_appkey)

        self.volc_bigmodel_ak = PasswordLineEdit()
        self.volc_bigmodel_ak.setMinimumWidth(250)
        self._volc_bigmodel_ak_card = self.add_card(t("access_key"), self.volc_bigmodel_ak)

        # 本地模型配置
        from speaky.ui.model_download_widget import create_whisper_download_widget
        self.local_widget = create_whisper_download_widget()
        self.local_widget.setContentsMargins(20, 10, 20, 10)
        self._layout.addWidget(self.local_widget)
        self._local_widget_card = self.local_widget

        self._volc_bigmodel_widgets = [self._volc_bigmodel_appkey_card, self._volc_bigmodel_ak_card]
        self._local_widgets = [self._local_widget_card]
        self._on_engine_index_changed(0)

        # AI 润色
        self.llm_polish = SwitchButton()
        self.llm_polish.setToolTip(t("llm_polish_tooltip"))
        self.add_card(t("llm_polish"), self.llm_polish)

        # ═══════════════ 大模型配置 ═══════════════
        self.add_group_label(t("llm_provider_group"))

        self.llm_base_url = LineEdit()
        self.llm_base_url.setPlaceholderText("https://api.openai.com/v1")
        self.llm_base_url.setMinimumWidth(250)
        self.add_card(t("base_url"), self.llm_base_url)

        self.llm_api_key = PasswordLineEdit()
        self.llm_api_key.setMinimumWidth(250)
        self.add_card(t("api_key"), self.llm_api_key)

        self.llm_model = LineEdit()
        self.llm_model.setPlaceholderText("gpt-4o-mini")
        self.llm_model.setMinimumWidth(200)
        self.add_card(t("model"), self.llm_model)

        # ═══════════════ 系统 ═══════════════
        self.add_group_label(t("system_group"))

        self.auto_start = SwitchButton()
        self.add_card(t("auto_start"), self.auto_start)

        # 高级配置（默认折叠）
        self._advanced_btn = PushButton(t("advanced_settings"))
        self._advanced_btn.clicked.connect(self._toggle_advanced)
        self._layout.addWidget(self._advanced_btn)

        self._advanced_visible = False

        self.audio_device_combo = ComboBox()
        self.audio_device_combo.setMinimumWidth(250)
        self._audio_devices = []
        self._refresh_audio_devices()
        self._audio_device_card = self.add_card(t("audio_device"), self.audio_device_combo)

        gain_widget = QWidget()
        gain_layout = QHBoxLayout(gain_widget)
        gain_layout.setContentsMargins(0, 0, 0, 0)
        self.gain_slider = Slider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(10, 50)
        self.gain_slider.setSingleStep(1)
        self.gain_slider.setMinimumWidth(150)
        self._gain_label = BodyLabel("1.0x")
        self._gain_label.setMinimumWidth(40)
        self.gain_slider.valueChanged.connect(
            lambda v: self._gain_label.setText(f"{v/10:.1f}x")
        )
        gain_layout.addWidget(self.gain_slider)
        gain_layout.addWidget(self._gain_label)
        self._audio_gain_card = self.add_card(t("audio_gain"), gain_widget)

        self._advanced_widgets = [self._audio_device_card, self._audio_gain_card]
        for w in self._advanced_widgets:
            w.setVisible(False)

        self.add_save_button()

    def _on_engine_index_changed(self, index: int):
        if 0 <= index < len(self._engine_items):
            engine = self._engine_items[index][0]
        else:
            engine = "volc_bigmodel"
        for w in self._volc_bigmodel_widgets:
            w.setVisible(engine == "volc_bigmodel")
        for w in self._local_widgets:
            w.setVisible(engine == "local")

    def _toggle_advanced(self):
        self._advanced_visible = not self._advanced_visible
        for w in self._advanced_widgets:
            w.setVisible(self._advanced_visible)
        self._advanced_btn.setText(
            t("hide_advanced") if self._advanced_visible else t("advanced_settings")
        )

    def _refresh_audio_devices(self):
        """刷新音频设备列表"""
        from speaky.audio import AudioRecorder
        try:
            recorder = AudioRecorder()
            devices = recorder.get_input_devices()
            recorder.close()

            self.audio_device_combo.clear()
            self._audio_devices = [(-1, t("audio_device_default"))] + devices

            for idx, name in self._audio_devices:
                self.audio_device_combo.addItem(name)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to get audio devices: {e}")
            self.audio_device_combo.addItem(t("audio_device_default"))
            self._audio_devices = [(-1, t("audio_device_default"))]

    def get_selected_audio_device(self) -> int:
        """获取选中的音频设备索引，-1 表示默认设备"""
        idx = self.audio_device_combo.currentIndex()
        if 0 <= idx < len(self._audio_devices):
            return self._audio_devices[idx][0]
        return -1

    def set_audio_device(self, device_index):
        """设置选中的音频设备"""
        if device_index is None:
            device_index = -1
        for i, (idx, _) in enumerate(self._audio_devices):
            if idx == device_index:
                self.audio_device_combo.setCurrentIndex(i)
                return
        # 如果没找到，选择默认设备
        self.audio_device_combo.setCurrentIndex(0)



class AppearancePage(SettingsPage):
    """Appearance settings page - theme, UI language, waveform, opacity"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        self.add_group_label(t("ui_group"))

        # Theme selection
        self.theme_combo = ComboBox()
        self._theme_values = ["light", "dark", "auto"]
        self.theme_combo.addItem(t("theme_light"))
        self.theme_combo.addItem(t("theme_dark"))
        self.theme_combo.addItem(t("theme_auto"))
        self.theme_combo.setMinimumWidth(150)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        self.add_card(t("theme"), self.theme_combo)

        # UI Language
        self.ui_lang_combo = ComboBox()
        self._ui_lang_codes = ["auto", "en", "zh", "zh_TW", "ja", "ko", "de", "fr", "es", "pt", "ru"]
        for lang_code in self._ui_lang_codes:
            display_name = i18n.get_language_name(lang_code)
            self.ui_lang_combo.addItem(display_name)
        self.ui_lang_combo.setMinimumWidth(150)
        self.add_card(t("ui_lang"), self.ui_lang_combo)

        self.show_waveform = SwitchButton()
        self.add_card(t("show_waveform"), self.show_waveform)

        # Opacity slider with value label
        opacity_widget = QWidget()
        opacity_layout = QHBoxLayout(opacity_widget)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        self.opacity_slider = Slider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(50, 100)
        self.opacity_slider.setMinimumWidth(200)
        self._opacity_label = BodyLabel("90%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self._opacity_label.setText(f"{v}%")
        )
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self._opacity_label)
        self.add_card(t("window_opacity"), opacity_widget)

        self.add_save_button()

    def _on_theme_changed(self, index: int):
        """Apply theme immediately when changed"""
        if 0 <= index < len(self._theme_values):
            theme = self._theme_values[index]
            apply_theme(theme)

    def get_ui_lang_code(self) -> str:
        """Get selected UI language code"""
        idx = self.ui_lang_combo.currentIndex()
        if 0 <= idx < len(self._ui_lang_codes):
            return self._ui_lang_codes[idx]
        return "auto"

    def set_ui_lang_code(self, code: str):
        """Set UI language by code"""
        if code in self._ui_lang_codes:
            self.ui_lang_combo.setCurrentIndex(self._ui_lang_codes.index(code))


class LLMAgentPage(SettingsPage):
    """LLM Agent settings page - LLM configuration and MCP servers"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # LLM Agent basic settings
        self.add_group_label(t("llm_agent_group"))

        self.agent_enabled = SwitchButton()
        self.add_card(t("llm_agent_enabled"), self.agent_enabled)

        self.agent_hotkey_combo = EditableComboBox()
        self.agent_hotkey_combo.addItems([
            "tab", "ctrl", "alt", "shift", "cmd",
            "ctrl_l", "ctrl_r", "alt_l", "alt_r", "shift_l", "shift_r",
            "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
            "space", "caps_lock",
        ])
        self.agent_hotkey_combo.setMinimumWidth(150)
        self.add_card(t("llm_agent_hotkey"), self.agent_hotkey_combo)

        self.agent_hold_time_spin = DoubleSpinBox()
        self.agent_hold_time_spin.setRange(0.0, 5.0)
        self.agent_hold_time_spin.setSingleStep(0.1)
        self.agent_hold_time_spin.setDecimals(1)
        self.agent_hold_time_spin.setMinimumWidth(120)
        self.add_card(t("llm_agent_hold_time"), self.agent_hold_time_spin)

        # AI 键网站配置
        self.add_group_label(t("ai_group"))

        self.ai_url_input = LineEdit()
        self.ai_url_input.setPlaceholderText("https://chatgpt.com")
        self.ai_url_input.setMinimumWidth(250)
        self.add_card(t("ai_url_label"), self.ai_url_input)

        # MCP Server settings
        self.add_group_label(t("mcp_servers_group"))

        self.mcp_playwright = SwitchButton()
        self.add_card("Playwright (Browser)", self.mcp_playwright)

        self.mcp_filesystem = SwitchButton()
        self.add_card("Filesystem", self.mcp_filesystem)

        self.mcp_fetch = SwitchButton()
        self.add_card("Fetch (HTTP)", self.mcp_fetch)

        # Browser extension setup
        self.add_group_label(t("browser_extension_group"))

        # Extension status
        self._ext_status_label = BodyLabel("")
        self.add_card(t("browser_extension"), self._ext_status_label)

        # Extension buttons
        ext_btn_widget = QWidget()
        ext_btn_layout = QHBoxLayout(ext_btn_widget)
        ext_btn_layout.setContentsMargins(0, 0, 0, 0)
        self._ext_install_btn = PushButton(t("install_extension"))
        self._ext_install_btn.clicked.connect(self._install_browser_extension)
        self._ext_open_chrome_btn = PushButton(t("open_extensions_page"))
        self._ext_open_chrome_btn.clicked.connect(self._open_chrome_extensions)
        ext_btn_layout.addWidget(self._ext_install_btn)
        ext_btn_layout.addWidget(self._ext_open_chrome_btn)
        ext_btn_layout.addStretch()
        self.add_card("", ext_btn_widget)

        # Check extension status on init
        self._check_extension_status()

        self.add_save_button()

    def _connect_signals(self):
        pass

    def _check_extension_status(self):
        """Check if browser extension is downloaded"""
        ext_path = Path.home() / ".speaky" / "mcp" / "extension" / "manifest.json"
        if ext_path.exists():
            self._ext_status_label.setText(t("extension_installed"))
            self._ext_status_label.setStyleSheet("color: green;")
            self._ext_install_btn.setText(t("reinstall_extension"))
        else:
            self._ext_status_label.setText(t("extension_not_installed"))
            self._ext_status_label.setStyleSheet("color: orange;")
            self._ext_install_btn.setText(t("install_extension"))

    def _install_browser_extension(self):
        """Download and install browser extension"""
        import subprocess
        import threading

        self._ext_install_btn.setEnabled(False)
        self._ext_install_btn.setText(t("installing"))

        def install_worker():
            try:
                ext_dir = Path.home() / ".speaky" / "mcp" / "extension"
                ext_dir.mkdir(parents=True, exist_ok=True)

                # Download latest extension
                import urllib.request
                import zipfile
                import io

                url = "https://github.com/microsoft/playwright-mcp/releases/download/v0.0.53/playwright-mcp-extension-0.0.53.zip"
                with urllib.request.urlopen(url, timeout=30) as response:
                    zip_data = response.read()

                # Extract zip
                with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                    zf.extractall(ext_dir)

                # Update UI on main thread
                QTimer.singleShot(0, self._on_extension_installed)

            except Exception as e:
                QTimer.singleShot(0, lambda: self._on_extension_install_error(str(e)))

        threading.Thread(target=install_worker, daemon=True).start()

    def _on_extension_installed(self):
        """Called when extension is installed successfully"""
        self._ext_install_btn.setEnabled(True)
        self._check_extension_status()
        MessageBox(
            t("success"),
            t("extension_install_success"),
            self
        ).exec()

    def _on_extension_install_error(self, error: str):
        """Called when extension installation fails"""
        self._ext_install_btn.setEnabled(True)
        self._ext_install_btn.setText(t("install_extension"))
        MessageBox(t("error"), f"{t('extension_install_failed')}: {error}", self).exec()

    def _open_chrome_extensions(self):
        """Open Chrome extensions page"""
        import subprocess
        import webbrowser
        try:
            webbrowser.open("chrome://extensions/")
        except Exception:
            # Fallback: try to open with xdg-open
            try:
                subprocess.Popen(["google-chrome", "chrome://extensions/"])
            except Exception:
                MessageBox(
                    t("tip"),
                    t("open_extensions_manually"),
                    self
                ).exec()



class LogPage(QWidget):
    """Log viewer page embedded in settings"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._log_file = Path.home() / ".speaky" / "speaky.log"
        self._auto_scroll = True
        self._last_size = 0
        self._setup_ui()
        self._setup_refresh_timer()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # Header with file path
        header_layout = QHBoxLayout()
        path_label = BodyLabel(f"{t('log_file_path')}: {self._log_file}")
        path_label.setStyleSheet("color: #888;")
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

        self._refresh_btn = PushButton(t("refresh"))
        self._refresh_btn.clicked.connect(self._load_log)
        button_layout.addWidget(self._refresh_btn)

        self._clear_btn = PushButton(t("clear_log"))
        self._clear_btn.clicked.connect(self._clear_log)
        button_layout.addWidget(self._clear_btn)

        self._export_btn = PushButton(t("export_log"))
        self._export_btn.clicked.connect(self._export_log)
        button_layout.addWidget(self._export_btn)

        button_layout.addStretch()

        self._auto_scroll_btn = PushButton(t("auto_scroll_on"))
        self._auto_scroll_btn.setCheckable(True)
        self._auto_scroll_btn.setChecked(True)
        self._auto_scroll_btn.clicked.connect(self._toggle_auto_scroll)
        button_layout.addWidget(self._auto_scroll_btn)

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
                MessageBox(t("error"), str(e), self).exec()

    def showEvent(self, event):
        """Load log when page becomes visible"""
        super().showEvent(event)
        self._load_log()

    def hideEvent(self, event):
        """Stop checking when page is hidden"""
        super().hideEvent(event)


class SettingsDialog(FluentWindow):
    """Fluent-style settings window"""
    settings_changed = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        # Delete on close so destroyed signal is emitted
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # Disable mica effect to fix theme switching issue on Windows
        self.setMicaEffectEnabled(False)
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        self.setWindowTitle(t("settings_title"))
        self.setWindowIcon(get_app_icon())
        self.resize(700, 550)

        # Create pages
        self._core_page = CorePage(self._config, self)
        self._core_page.setObjectName("corePage")
        self._llm_agent_page = LLMAgentPage(self._config, self)
        self._llm_agent_page.setObjectName("llmAgentPage")
        self._appearance_page = AppearancePage(self._config, self)
        self._appearance_page.setObjectName("appearancePage")
        self._log_page = LogPage(self)
        self._log_page.setObjectName("logPage")

        # Add pages to navigation
        self.addSubInterface(self._core_page, FluentIcon.SETTING, t("tab_core"))
        self.addSubInterface(self._llm_agent_page, FluentIcon.ROBOT, t("tab_llm_agent"))
        self.addSubInterface(self._appearance_page, FluentIcon.PALETTE, t("tab_appearance"))
        self.addSubInterface(self._log_page, FluentIcon.DOCUMENT, t("tab_log"))

        # Connect save signals
        self._core_page.save_clicked.connect(self._save_settings)
        self._llm_agent_page.save_clicked.connect(self._save_settings)
        self._appearance_page.save_clicked.connect(self._save_settings)

    def _load_settings(self):
        # Core page - ASR settings
        self._core_page.hotkey_combo.setCurrentText(self._config.get("core.asr.hotkey", "ctrl"))
        self._core_page.hold_time_spin.setValue(self._config.get("core.asr.hotkey_hold_time", 1.0))
        self._core_page.set_audio_device(self._config.get("core.asr.audio_device"))
        gain = self._config.get("core.asr.audio_gain", 1.0)
        self._core_page.gain_slider.setValue(int(gain * 10))
        self._core_page._gain_label.setText(f"{gain:.1f}x")
        self._core_page.auto_start.setChecked(is_autostart_enabled())
        self._core_page.sound_notification.setChecked(self._config.get("core.asr.sound_notification", True))
        self._core_page.llm_polish.setChecked(self._config.get("core.asr.llm_polish", False))

        # AI 键
        self._core_page.ai_hotkey_combo.setCurrentText(self._config.get("core.ai.hotkey", "alt"))
        self._core_page.ai_auto_enter.setChecked(self._config.get("core.ai.auto_enter", True))

        # 大模型配置（共用）
        self._core_page.llm_base_url.setText(self._config.get("llm.openai.base_url", ""))
        self._core_page.llm_api_key.setText(self._config.get("llm.openai.api_key", ""))
        self._core_page.llm_model.setText(self._config.get("llm.openai.model", "gpt-4o-mini"))

        # Engine page
        engine = self._config.get("engine.current", "volc_bigmodel")
        # 找到引擎对应的索引
        for i, (engine_id, _) in enumerate(self._core_page._engine_items):
            if engine_id == engine:
                self._core_page.engine_combo.setCurrentIndex(i)
                break
        self._core_page._on_engine_index_changed(self._core_page.engine_combo.currentIndex())

        # Engine settings - 火山大模型
        self._core_page.volc_bigmodel_appkey.setText(self._config.get("engine.volc_bigmodel.app_key", ""))
        self._core_page.volc_bigmodel_ak.setText(self._config.get("engine.volc_bigmodel.access_key", ""))

        # Engine settings - 本地模式
        self._core_page.local_widget.set_model(self._config.get("engine.local.model", "base"))
        self._core_page.local_widget.set_option("device", self._config.get("engine.local.device", "auto"))

        # LLM Agent page
        self._llm_agent_page.agent_enabled.setChecked(self._config.get("llm_agent.enabled", False))
        self._llm_agent_page.agent_hotkey_combo.setCurrentText(self._config.get("llm_agent.hotkey", "tab"))
        self._llm_agent_page.agent_hold_time_spin.setValue(self._config.get("llm_agent.hotkey_hold_time", 0.5))
        self._llm_agent_page.ai_url_input.setText(self._config.get("core.ai.url", "https://chatgpt.com"))

        # MCP servers
        self._llm_agent_page.mcp_playwright.setChecked(self._config.get("mcp.servers.playwright.enabled", True))
        self._llm_agent_page.mcp_filesystem.setChecked(self._config.get("mcp.servers.filesystem.enabled", True))
        self._llm_agent_page.mcp_fetch.setChecked(self._config.get("mcp.servers.fetch.enabled", True))

        # Appearance page
        theme = self._config.get("appearance.theme", "auto")
        if theme in self._appearance_page._theme_values:
            idx = self._appearance_page._theme_values.index(theme)
            self._appearance_page.theme_combo.setCurrentIndex(idx)
        ui_lang = self._config.get("appearance.ui_language", "auto")
        self._appearance_page.set_ui_lang_code(ui_lang)
        self._appearance_page.show_waveform.setChecked(self._config.get("appearance.show_waveform", True))
        opacity = int(self._config.get("appearance.window_opacity", 0.9) * 100)
        self._appearance_page.opacity_slider.setValue(opacity)
        self._appearance_page._opacity_label.setText(f"{opacity}%")

    def _save_settings(self):
        # Check if language changed (need to close dialog to refresh UI)
        old_lang = self._config.get("appearance.ui_language", "auto")
        new_lang = self._appearance_page.get_ui_lang_code()
        lang_changed = old_lang != new_lang

        # Core - ASR settings
        self._config.set("core.asr.hotkey", self._core_page.hotkey_combo.currentText())
        self._config.set("core.asr.hotkey_hold_time", self._core_page.hold_time_spin.value())
        # 音频设备：-1 表示默认设备，保存为 None
        audio_device = self._core_page.get_selected_audio_device()
        self._config.set("core.asr.audio_device", None if audio_device == -1 else audio_device)
        # 音频增益
        self._config.set("core.asr.audio_gain", self._core_page.gain_slider.value() / 10)
        self._config.set("core.asr.sound_notification", self._core_page.sound_notification.isChecked())
        self._config.set("core.asr.llm_polish", self._core_page.llm_polish.isChecked())

        # AI Key settings（共用 hold_time）
        self._config.set("core.ai.enabled", True)
        self._config.set("core.ai.hotkey", self._core_page.ai_hotkey_combo.currentText())
        self._config.set("core.ai.hotkey_hold_time", self._core_page.hold_time_spin.value())
        self._config.set("core.ai.auto_enter", self._core_page.ai_auto_enter.isChecked())

        # 大模型配置（共用，润色和 LLM Agent 都用这个）
        self._config.set("llm.openai.base_url", self._core_page.llm_base_url.text() or "https://api.openai.com/v1")
        self._config.set("llm.openai.api_key", self._core_page.llm_api_key.text())
        self._config.set("llm.openai.model", self._core_page.llm_model.text() or "gpt-4o-mini")

        # Set auto-start
        set_autostart(self._core_page.auto_start.isChecked())

        # Engine settings - 直接从 _engine_items 获取 engine_id
        idx = self._core_page.engine_combo.currentIndex()
        if 0 <= idx < len(self._core_page._engine_items):
            engine = self._core_page._engine_items[idx][0]
        else:
            engine = "volc_bigmodel"  # Default
        self._config.set("engine.current", engine)

        # 火山大模型
        self._config.set("engine.volc_bigmodel.app_key", self._core_page.volc_bigmodel_appkey.text())
        self._config.set("engine.volc_bigmodel.access_key", self._core_page.volc_bigmodel_ak.text())

        # 本地模式
        self._config.set("engine.local.model", self._core_page.local_widget.get_model())
        self._config.set("engine.local.device", self._core_page.local_widget.get_option("device"))

        # LLM Agent settings
        self._config.set("llm_agent.enabled", self._llm_agent_page.agent_enabled.isChecked())
        self._config.set("llm_agent.hotkey", self._llm_agent_page.agent_hotkey_combo.currentText())
        self._config.set("llm_agent.hotkey_hold_time", self._llm_agent_page.agent_hold_time_spin.value())
        self._config.set("core.ai.url", self._llm_agent_page.ai_url_input.text() or "https://chatgpt.com")

        # MCP servers
        self._config.set("mcp.servers.playwright.enabled", self._llm_agent_page.mcp_playwright.isChecked())
        self._config.set("mcp.servers.filesystem.enabled", self._llm_agent_page.mcp_filesystem.isChecked())
        self._config.set("mcp.servers.fetch.enabled", self._llm_agent_page.mcp_fetch.isChecked())

        # Appearance settings
        theme_idx = self._appearance_page.theme_combo.currentIndex()
        theme = self._appearance_page._theme_values[theme_idx] if 0 <= theme_idx < len(self._appearance_page._theme_values) else "auto"
        self._config.set("appearance.theme", theme)
        self._config.set("appearance.ui_language", self._appearance_page.get_ui_lang_code())
        self._config.set("appearance.show_waveform", self._appearance_page.show_waveform.isChecked())
        self._config.set("appearance.window_opacity", self._appearance_page.opacity_slider.value() / 100)

        self._config.save()

        # Update i18n language
        i18n.set_language(self._appearance_page.get_ui_lang_code())

        # Apply theme
        apply_theme(theme)

        # Show success message
        MessageBox(t("tip"), t("saved_message"), self).exec()

        # Emit signal to notify main app of settings change (before close to avoid crash)
        self.settings_changed.emit()

        # If language changed, close dialog so it recreates with new language
        if lang_changed:
            self.close()
