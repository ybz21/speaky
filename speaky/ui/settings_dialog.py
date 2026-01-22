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
    """Core settings page - hotkey, language, autostart, streaming"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        # Voice input key settings (merged hotkey + language)
        self.add_group_label(t("voice_input_group"))

        self.hotkey_combo = EditableComboBox()
        self.hotkey_combo.addItems([
            "ctrl", "alt", "shift", "cmd",
            "ctrl_l", "ctrl_r", "alt_l", "alt_r", "shift_l", "shift_r",
            "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
            "space", "tab", "caps_lock",
        ])
        self.hotkey_combo.setMinimumWidth(150)
        self.add_card(t("hotkey_label"), self.hotkey_combo)

        self.hold_time_spin = DoubleSpinBox()
        self.hold_time_spin.setRange(0.0, 5.0)
        self.hold_time_spin.setSingleStep(0.1)
        self.hold_time_spin.setDecimals(1)
        self.hold_time_spin.setMinimumWidth(120)
        self.add_card(t("hold_time_label"), self.hold_time_spin)

        self.lang_combo = ComboBox()
        self.lang_combo.addItems(["zh", "en", "ja", "ko"])
        self.lang_combo.setMinimumWidth(150)
        self.add_card(t("recognition_lang"), self.lang_combo)

        # 音频设备选择
        self.audio_device_combo = ComboBox()
        self.audio_device_combo.setMinimumWidth(250)
        self._audio_devices = []  # [(index, name), ...]
        self._refresh_audio_devices()
        self.add_card(t("audio_device"), self.audio_device_combo)

        # 音频增益调节
        gain_widget = QWidget()
        gain_layout = QHBoxLayout(gain_widget)
        gain_layout.setContentsMargins(0, 0, 0, 0)
        self.gain_slider = Slider(Qt.Orientation.Horizontal)
        self.gain_slider.setRange(10, 50)  # 0.1x - 5.0x, stored as 10-500 (x10)
        self.gain_slider.setSingleStep(1)
        self.gain_slider.setMinimumWidth(150)
        self._gain_label = BodyLabel("1.0x")
        self._gain_label.setMinimumWidth(40)
        self.gain_slider.valueChanged.connect(
            lambda v: self._gain_label.setText(f"{v/10:.1f}x")
        )
        gain_layout.addWidget(self.gain_slider)
        gain_layout.addWidget(self._gain_label)
        self.add_card(t("audio_gain"), gain_widget)

        self.streaming_mode = SwitchButton()
        self.streaming_mode.setToolTip(t("streaming_tooltip"))
        self.add_card(t("streaming_mode"), self.streaming_mode)

        self.sound_notification = SwitchButton()
        self.add_card(t("sound_notification"), self.sound_notification)

        # Engine selection
        self.add_group_label(t("engine_group"))

        self.engine_combo = ComboBox()
        self._engine_items = [
            ("volc_bigmodel", t("volc_bigmodel_settings")),
            ("volcengine", t("volc_settings")),
            ("openai", t("openai_settings")),
            ("local", t("local_settings")),
        ]
        for engine_id, engine_name in self._engine_items:
            self.engine_combo.addItem(engine_name)
        self.engine_combo.setMinimumWidth(220)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_index_changed)
        self.add_card(t("engine_label"), self.engine_combo)

        # 1. Volcengine BigModel settings
        self._volc_bigmodel_label = SubtitleLabel(t("volc_bigmodel_settings"), self._container)
        self._volc_bigmodel_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._volc_bigmodel_label)

        self.volc_bigmodel_appkey = LineEdit()
        self.volc_bigmodel_appkey.setMinimumWidth(250)
        self._volc_bigmodel_appkey_card = self.add_card(t("app_key"), self.volc_bigmodel_appkey)

        self.volc_bigmodel_ak = PasswordLineEdit()
        self.volc_bigmodel_ak.setMinimumWidth(250)
        self._volc_bigmodel_ak_card = self.add_card(t("access_key"), self.volc_bigmodel_ak)

        # 2. Volcengine settings
        self._volc_label = SubtitleLabel(t("volc_settings"), self._container)
        self._volc_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._volc_label)

        self.volc_appid = LineEdit()
        self.volc_appid.setMinimumWidth(250)
        self._volc_appid_card = self.add_card(t("app_id"), self.volc_appid)

        self.volc_ak = PasswordLineEdit()
        self.volc_ak.setMinimumWidth(250)
        self._volc_ak_card = self.add_card(t("access_key"), self.volc_ak)

        self.volc_sk = PasswordLineEdit()
        self.volc_sk.setMinimumWidth(250)
        self._volc_sk_card = self.add_card(t("secret_key"), self.volc_sk)

        # 3. OpenAI settings
        self._openai_label = SubtitleLabel(t("openai_settings"), self._container)
        self._openai_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._openai_label)

        self.openai_key = PasswordLineEdit()
        self.openai_key.setMinimumWidth(250)
        self._openai_key_card = self.add_card(t("api_key"), self.openai_key)

        self.openai_model = ComboBox()
        self.openai_model.addItems([
            "gpt-4o-transcribe",
            "gpt-4o-mini-transcribe",
            "whisper-1",
        ])
        self.openai_model.setMinimumWidth(180)
        self._openai_model_card = self.add_card(t("model"), self.openai_model)

        self.openai_url = LineEdit()
        self.openai_url.setPlaceholderText("https://api.openai.com/v1")
        self.openai_url.setMinimumWidth(250)
        self._openai_url_card = self.add_card(t("base_url"), self.openai_url)

        # 4. Local settings
        self._local_label = SubtitleLabel(t("local_settings"), self._container)
        self._local_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._local_label)

        from speaky.ui.model_download_widget import create_whisper_download_widget
        self.local_widget = create_whisper_download_widget()
        self.local_widget.setContentsMargins(20, 10, 20, 10)
        self._layout.addWidget(self.local_widget)
        self._local_widget_card = self.local_widget

        # Store engine widgets for visibility control
        self._volc_bigmodel_widgets = [self._volc_bigmodel_label, self._volc_bigmodel_appkey_card,
                                        self._volc_bigmodel_ak_card]
        self._volc_widgets = [self._volc_label, self._volc_appid_card, self._volc_ak_card, self._volc_sk_card]
        self._openai_widgets = [self._openai_label, self._openai_key_card, self._openai_model_card, self._openai_url_card]
        self._local_widgets = [self._local_label, self._local_widget_card]

        # Initialize visibility
        self._on_engine_index_changed(0)

        # System settings
        self.add_group_label(t("system_group"))

        self.auto_start = SwitchButton()
        self.add_card(t("auto_start"), self.auto_start)

        self.add_save_button()

    def _on_engine_index_changed(self, index: int):
        """Show/hide engine-specific settings based on selection"""
        if 0 <= index < len(self._engine_items):
            engine = self._engine_items[index][0]
        else:
            engine = "volc_bigmodel"

        for w in self._volc_bigmodel_widgets:
            w.setVisible(engine == "volc_bigmodel")
        for w in self._volc_widgets:
            w.setVisible(engine == "volcengine")
        for w in self._openai_widgets:
            w.setVisible(engine == "openai")
        for w in self._local_widgets:
            w.setVisible(engine == "local")

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


class AIKeyPage(SettingsPage):
    """AI Key settings page - AI hotkey and URL configuration"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        self.add_group_label(t("ai_group"))

        self.ai_enabled = SwitchButton()
        self.add_card(t("ai_enabled"), self.ai_enabled)

        self.ai_hotkey_combo = EditableComboBox()
        self.ai_hotkey_combo.addItems([
            "shift", "ctrl", "alt", "cmd",
            "ctrl_l", "ctrl_r", "alt_l", "alt_r", "shift_l", "shift_r",
            "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10", "f11", "f12",
            "space", "tab", "caps_lock",
        ])
        self.ai_hotkey_combo.setMinimumWidth(150)
        self.add_card(t("ai_hotkey_label"), self.ai_hotkey_combo)

        self.ai_hold_time_spin = DoubleSpinBox()
        self.ai_hold_time_spin.setRange(0.0, 5.0)
        self.ai_hold_time_spin.setSingleStep(0.1)
        self.ai_hold_time_spin.setDecimals(1)
        self.ai_hold_time_spin.setMinimumWidth(120)
        self.add_card(t("ai_hold_time_label"), self.ai_hold_time_spin)

        self.ai_url_input = LineEdit()
        self.ai_url_input.setPlaceholderText("https://chatgpt.com")
        self.ai_url_input.setMinimumWidth(250)
        self.add_card(t("ai_url_label"), self.ai_url_input)

        self.ai_page_load_delay_spin = DoubleSpinBox()
        self.ai_page_load_delay_spin.setRange(1.0, 10.0)
        self.ai_page_load_delay_spin.setSingleStep(0.5)
        self.ai_page_load_delay_spin.setDecimals(1)
        self.ai_page_load_delay_spin.setMinimumWidth(120)
        self.add_card(t("ai_page_load_delay_label"), self.ai_page_load_delay_spin)

        self.ai_auto_enter = SwitchButton()
        self.add_card(t("ai_auto_enter"), self.ai_auto_enter)

        self.add_save_button()


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
    openai_models_fetched = Signal(list, str)  # (models, error)

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

        # LLM Provider settings (OpenAI compatible)
        self.add_group_label(t("llm_provider_group"))

        self.openai_api_key = PasswordLineEdit()
        self.openai_api_key.setMinimumWidth(250)
        self.add_card(t("api_key"), self.openai_api_key)

        self.openai_base_url = LineEdit()
        self.openai_base_url.setPlaceholderText("https://api.openai.com/v1")
        self.openai_base_url.setMinimumWidth(250)
        self.add_card(t("base_url"), self.openai_base_url)

        # Model selection with fetch button
        model_widget = QWidget()
        model_layout = QHBoxLayout(model_widget)
        model_layout.setContentsMargins(0, 0, 0, 0)
        self.openai_model = EditableComboBox()
        self.openai_model.setMinimumWidth(180)
        self.openai_model.setPlaceholderText("gpt-4o-mini")
        # Enable filtering/search in dropdown
        self._setup_model_completer(self.openai_model)
        self._openai_fetch_btn = PushButton(t("fetch_models"))
        self._openai_fetch_btn.clicked.connect(self._fetch_openai_models)
        model_layout.addWidget(self.openai_model)
        model_layout.addWidget(self._openai_fetch_btn)
        self.add_card(t("model"), model_widget)

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
        self.openai_models_fetched.connect(self._on_openai_models_fetched)

    def _setup_model_completer(self, combo: EditableComboBox):
        """Setup completer for model search/filtering."""
        from PySide6.QtWidgets import QCompleter
        from PySide6.QtCore import Qt

        # Create completer that will be updated when models are fetched
        completer = QCompleter([], combo)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)  # Match anywhere in string
        combo.setCompleter(completer)

    def _update_model_completer(self, combo: EditableComboBox, models: list):
        """Update completer with new model list."""
        from PySide6.QtCore import QStringListModel

        completer = combo.completer()
        if completer:
            completer.setModel(QStringListModel(models))

    def set_openai_model(self, model: str):
        """Set OpenAI model text, retaining value even if not in list."""
        if model:
            # First try to find and select if in list
            index = self.openai_model.findText(model)
            if index >= 0:
                self.openai_model.setCurrentIndex(index)
            else:
                # Not in list, just set the text directly
                self.openai_model.setCurrentText(model)

    def _on_openai_models_fetched(self, models: list, error: str):
        """Handle OpenAI models fetch result on main thread"""
        import logging
        logger = logging.getLogger(__name__)

        logger.info(f"[Settings] _on_openai_models_fetched: {len(models)} models, error={error}")
        self._openai_fetch_btn.setEnabled(True)
        self._openai_fetch_btn.setText(t("fetch_models"))

        if models:
            logger.info(f"[Settings] Updating ComboBox with {len(models)} models")
            current = self.openai_model.currentText()
            self._populate_models(models)
            # Restore previous value
            if current:
                self.set_openai_model(current)
            # Save to config for persistence
            self._config.set("llm.openai.cached_models", models)
            self._config.save()
            logger.info(f"[Settings] Saved {len(models)} models to cache")
        else:
            logger.warning(f"[Settings] No models fetched, error={error}")
            MessageBox(t("error"), t("fetch_models_failed"), self).exec()

    def _populate_models(self, models: list):
        """Populate model combo box with models list"""
        self.openai_model.clear()
        for model in models:
            self.openai_model.addItem(model)
        # Update completer for search
        self._update_model_completer(self.openai_model, models)

    def load_cached_models(self):
        """Load cached models from config"""
        import logging
        logger = logging.getLogger(__name__)

        cached_models = self._config.get("llm.openai.cached_models", [])
        if cached_models:
            logger.info(f"[Settings] Loading {len(cached_models)} cached models")
            self._populate_models(cached_models)

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

    def _fetch_openai_models(self):
        """Fetch models from OpenAI-compatible API"""
        import asyncio
        import logging
        import threading
        from speaky.llm.models import fetch_openai_models

        logger = logging.getLogger(__name__)

        base_url = self.openai_base_url.text() or "https://api.openai.com/v1"
        api_key = self.openai_api_key.text()

        if not api_key:
            MessageBox(t("error"), t("api_key_required"), self).exec()
            return

        logger.info(f"[Settings] Fetching OpenAI models from: {base_url}")
        self._openai_fetch_btn.setEnabled(False)
        self._openai_fetch_btn.setText(t("fetching"))

        def run_async():
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                models = loop.run_until_complete(fetch_openai_models(base_url, api_key))
                loop.close()
                logger.info(f"[Settings] Background thread got {len(models)} models, emitting signal")
                self.openai_models_fetched.emit(models, "")
            except Exception as e:
                logger.error(f"[Settings] Fetch OpenAI models error: {e}")
                self.openai_models_fetched.emit([], str(e))

        threading.Thread(target=run_async, daemon=True).start()


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
        self._ai_key_page = AIKeyPage(self._config, self)
        self._ai_key_page.setObjectName("aiKeyPage")
        self._llm_agent_page = LLMAgentPage(self._config, self)
        self._llm_agent_page.setObjectName("llmAgentPage")
        self._appearance_page = AppearancePage(self._config, self)
        self._appearance_page.setObjectName("appearancePage")
        self._log_page = LogPage(self)
        self._log_page.setObjectName("logPage")

        # Add pages to navigation
        self.addSubInterface(self._core_page, FluentIcon.SETTING, t("tab_core"))
        self.addSubInterface(self._ai_key_page, FluentIcon.SEND, t("tab_ai_key"))
        self.addSubInterface(self._llm_agent_page, FluentIcon.ROBOT, t("tab_llm_agent"))
        self.addSubInterface(self._appearance_page, FluentIcon.PALETTE, t("tab_appearance"))
        self.addSubInterface(self._log_page, FluentIcon.DOCUMENT, t("tab_log"))

        # Connect save signals
        self._core_page.save_clicked.connect(self._save_settings)
        self._ai_key_page.save_clicked.connect(self._save_settings)
        self._llm_agent_page.save_clicked.connect(self._save_settings)
        self._appearance_page.save_clicked.connect(self._save_settings)

    def _load_settings(self):
        # Core page - ASR settings
        self._core_page.hotkey_combo.setCurrentText(self._config.get("core.asr.hotkey", "ctrl"))
        self._core_page.hold_time_spin.setValue(self._config.get("core.asr.hotkey_hold_time", 1.0))
        self._core_page.lang_combo.setCurrentText(self._config.get("core.asr.language", "zh"))
        self._core_page.set_audio_device(self._config.get("core.asr.audio_device"))
        gain = self._config.get("core.asr.audio_gain", 1.0)
        self._core_page.gain_slider.setValue(int(gain * 10))
        self._core_page._gain_label.setText(f"{gain:.1f}x")
        self._core_page.auto_start.setChecked(is_autostart_enabled())
        self._core_page.streaming_mode.setChecked(self._config.get("core.asr.streaming_mode", True))
        self._core_page.sound_notification.setChecked(self._config.get("core.asr.sound_notification", True))

        # AI Key page
        self._ai_key_page.ai_enabled.setChecked(self._config.get("core.ai.enabled", True))
        self._ai_key_page.ai_hotkey_combo.setCurrentText(self._config.get("core.ai.hotkey", "alt"))
        self._ai_key_page.ai_hold_time_spin.setValue(self._config.get("core.ai.hotkey_hold_time", 0.5))
        self._ai_key_page.ai_url_input.setText(self._config.get("core.ai.url", "https://chatgpt.com"))
        self._ai_key_page.ai_page_load_delay_spin.setValue(self._config.get("core.ai.page_load_delay", 3.0))
        self._ai_key_page.ai_auto_enter.setChecked(self._config.get("core.ai.auto_enter", True))

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

        # Engine settings - 火山一句话
        self._core_page.volc_appid.setText(self._config.get("engine.volcengine.app_id", ""))
        self._core_page.volc_ak.setText(self._config.get("engine.volcengine.access_key", ""))
        self._core_page.volc_sk.setText(self._config.get("engine.volcengine.secret_key", ""))

        # Engine settings - OpenAI
        self._core_page.openai_key.setText(self._config.get("engine.openai.api_key", ""))
        self._core_page.openai_model.setCurrentText(self._config.get("engine.openai.model", "whisper-1"))
        self._core_page.openai_url.setText(self._config.get("engine.openai.base_url", ""))

        # Engine settings - 本地模式
        self._core_page.local_widget.set_model(self._config.get("engine.local.model", "base"))
        self._core_page.local_widget.set_option("device", self._config.get("engine.local.device", "auto"))

        # LLM Agent page
        self._llm_agent_page.agent_enabled.setChecked(self._config.get("llm_agent.enabled", False))
        self._llm_agent_page.agent_hotkey_combo.setCurrentText(self._config.get("llm_agent.hotkey", "tab"))
        self._llm_agent_page.agent_hold_time_spin.setValue(self._config.get("llm_agent.hotkey_hold_time", 0.5))

        # OpenAI LLM settings
        self._llm_agent_page.openai_api_key.setText(self._config.get("llm.openai.api_key", ""))
        self._llm_agent_page.openai_base_url.setText(self._config.get("llm.openai.base_url", ""))
        # Load cached models first, then set the selected model
        self._llm_agent_page.load_cached_models()
        self._llm_agent_page.set_openai_model(self._config.get("llm.openai.model", "gpt-4o-mini"))

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
        self._config.set("core.asr.language", self._core_page.lang_combo.currentText())
        # 音频设备：-1 表示默认设备，保存为 None
        audio_device = self._core_page.get_selected_audio_device()
        self._config.set("core.asr.audio_device", None if audio_device == -1 else audio_device)
        # 音频增益
        self._config.set("core.asr.audio_gain", self._core_page.gain_slider.value() / 10)
        self._config.set("core.asr.streaming_mode", self._core_page.streaming_mode.isChecked())
        self._config.set("core.asr.sound_notification", self._core_page.sound_notification.isChecked())

        # AI Key settings
        self._config.set("core.ai.enabled", self._ai_key_page.ai_enabled.isChecked())
        self._config.set("core.ai.hotkey", self._ai_key_page.ai_hotkey_combo.currentText())
        self._config.set("core.ai.hotkey_hold_time", self._ai_key_page.ai_hold_time_spin.value())
        self._config.set("core.ai.url", self._ai_key_page.ai_url_input.text() or "https://chatgpt.com")
        self._config.set("core.ai.page_load_delay", self._ai_key_page.ai_page_load_delay_spin.value())
        self._config.set("core.ai.auto_enter", self._ai_key_page.ai_auto_enter.isChecked())

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

        # 火山一句话
        self._config.set("engine.volcengine.app_id", self._core_page.volc_appid.text())
        self._config.set("engine.volcengine.access_key", self._core_page.volc_ak.text())
        self._config.set("engine.volcengine.secret_key", self._core_page.volc_sk.text())

        # OpenAI
        self._config.set("engine.openai.api_key", self._core_page.openai_key.text())
        self._config.set("engine.openai.model", self._core_page.openai_model.currentText())
        self._config.set("engine.openai.base_url", self._core_page.openai_url.text() or "https://api.openai.com/v1")

        # 本地模式
        self._config.set("engine.local.model", self._core_page.local_widget.get_model())
        self._config.set("engine.local.device", self._core_page.local_widget.get_option("device"))

        # LLM Agent settings
        self._config.set("llm_agent.enabled", self._llm_agent_page.agent_enabled.isChecked())
        self._config.set("llm_agent.hotkey", self._llm_agent_page.agent_hotkey_combo.currentText())
        self._config.set("llm_agent.hotkey_hold_time", self._llm_agent_page.agent_hold_time_spin.value())

        # OpenAI LLM settings
        self._config.set("llm.openai.api_key", self._llm_agent_page.openai_api_key.text())
        self._config.set("llm.openai.base_url", self._llm_agent_page.openai_base_url.text() or "https://api.openai.com/v1")
        self._config.set("llm.openai.model", self._llm_agent_page.openai_model.currentText() or "gpt-4o-mini")

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
