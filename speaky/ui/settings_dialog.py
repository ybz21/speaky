from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QIcon

from qfluentwidgets import (
    ComboBox, EditableComboBox, LineEdit, PasswordLineEdit, PrimaryPushButton,
    SwitchButton, Slider, DoubleSpinBox, BodyLabel, SubtitleLabel,
    CardWidget, FluentIcon, MessageBox,
    setTheme, Theme, setThemeColor
)
from qfluentwidgets import FluentWindow

from ..i18n import t, i18n
from ..autostart import is_autostart_enabled, set_autostart
from .tray_icon import get_app_icon


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
        self.add_card(t("streaming_mode"), self.streaming_mode)

        self.sound_notification = SwitchButton()
        self.add_card(t("sound_notification"), self.sound_notification)

        # AI key settings
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

        # System settings
        self.add_group_label(t("system_group"))

        self.auto_start = SwitchButton()
        self.add_card(t("auto_start"), self.auto_start)

        self.add_save_button()

    def _refresh_audio_devices(self):
        """刷新音频设备列表"""
        from ..audio import AudioRecorder
        try:
            recorder = AudioRecorder()
            devices = recorder.get_input_devices()
            recorder.close()

            self.audio_device_combo.clear()
            self._audio_devices = [(-1, t("audio_device_default"))] + devices

            for idx, name in self._audio_devices:
                self.audio_device_combo.addItem(name, idx)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to get audio devices: {e}")
            self.audio_device_combo.addItem(t("audio_device_default"), -1)
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


class EnginePage(SettingsPage):
    """Engine settings page"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        # Engine selection
        self.add_group_label(t("engine_group"))

        self.engine_combo = ComboBox()
        # 5个引擎按顺序排列
        self._engine_items = [
            ("volc_bigmodel", t("volc_bigmodel_settings")),
            ("volcengine", t("volc_settings")),
            ("openai", t("openai_settings")),
            ("whisper_remote", t("whisper_remote_settings")),
            ("whisper", t("whisper_settings")),
        ]
        for engine_id, engine_name in self._engine_items:
            self.engine_combo.addItem(engine_name, engine_id)
        self.engine_combo.setMinimumWidth(220)
        self.engine_combo.currentIndexChanged.connect(self._on_engine_index_changed)
        self.add_card(t("engine_label"), self.engine_combo)

        # 1. Volcengine BigModel settings (火山引擎-语音识别大模型)
        self._volc_bigmodel_label = SubtitleLabel(t("volc_bigmodel_settings"), self._container)
        self._volc_bigmodel_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._volc_bigmodel_label)

        self.volc_bigmodel_appkey = LineEdit()
        self.volc_bigmodel_appkey.setMinimumWidth(250)
        self._volc_bigmodel_appkey_card = self.add_card(t("app_key"), self.volc_bigmodel_appkey)

        self.volc_bigmodel_ak = PasswordLineEdit()
        self.volc_bigmodel_ak.setMinimumWidth(250)
        self._volc_bigmodel_ak_card = self.add_card(t("access_key"), self.volc_bigmodel_ak)

        self.volc_bigmodel_model = ComboBox()
        self.volc_bigmodel_model.addItems(["bigmodel", "bigmodel_async", "bigmodel_nostream"])
        self.volc_bigmodel_model.setMinimumWidth(180)
        self._volc_bigmodel_model_card = self.add_card(t("model"), self.volc_bigmodel_model)

        # 2. Volcengine settings (火山引擎-一句话识别)
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

        self.openai_model = LineEdit()
        self.openai_model.setPlaceholderText("whisper-1")
        self.openai_model.setMinimumWidth(150)
        self._openai_model_card = self.add_card(t("model"), self.openai_model)

        self.openai_url = LineEdit()
        self.openai_url.setPlaceholderText("https://api.openai.com/v1")
        self.openai_url.setMinimumWidth(250)
        self._openai_url_card = self.add_card(t("base_url"), self.openai_url)

        # 4. Whisper Remote settings (Whisper 兼容接口)
        self._whisper_remote_label = SubtitleLabel(t("whisper_remote_settings"), self._container)
        self._whisper_remote_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._whisper_remote_label)

        self.whisper_remote_url = LineEdit()
        self.whisper_remote_url.setPlaceholderText("http://localhost:8000")
        self.whisper_remote_url.setMinimumWidth(250)
        self._whisper_remote_url_card = self.add_card(t("server_url"), self.whisper_remote_url)

        self.whisper_remote_model = LineEdit()
        self.whisper_remote_model.setPlaceholderText("whisper-1")
        self.whisper_remote_model.setMinimumWidth(150)
        self._whisper_remote_model_card = self.add_card(t("model"), self.whisper_remote_model)

        self.whisper_remote_key = PasswordLineEdit()
        self.whisper_remote_key.setMinimumWidth(250)
        self._whisper_remote_key_card = self.add_card(t("api_key"), self.whisper_remote_key)

        # 5. Whisper settings (本地 Whisper)
        self._whisper_label = SubtitleLabel(t("whisper_settings"), self._container)
        self._whisper_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._whisper_label)

        self.whisper_model = ComboBox()
        self.whisper_model.addItems(["tiny", "base", "small", "medium", "large"])
        self.whisper_model.setMinimumWidth(150)
        self._whisper_model_card = self.add_card(t("model"), self.whisper_model)

        self.whisper_device = ComboBox()
        self.whisper_device.addItems(["auto", "cpu", "cuda"])
        self.whisper_device.setMinimumWidth(150)
        self._whisper_device_card = self.add_card(t("device"), self.whisper_device)

        self.add_save_button()

        # Store all engine widgets for visibility control
        self._volc_bigmodel_widgets = [self._volc_bigmodel_label, self._volc_bigmodel_appkey_card,
                                        self._volc_bigmodel_ak_card, self._volc_bigmodel_model_card]
        self._volc_widgets = [self._volc_label, self._volc_appid_card, self._volc_ak_card, self._volc_sk_card]
        self._openai_widgets = [self._openai_label, self._openai_key_card, self._openai_model_card, self._openai_url_card]
        self._whisper_remote_widgets = [self._whisper_remote_label, self._whisper_remote_url_card,
                                         self._whisper_remote_model_card, self._whisper_remote_key_card]
        self._whisper_widgets = [self._whisper_label, self._whisper_model_card, self._whisper_device_card]

        # Initialize visibility (show first engine by default)
        self._on_engine_index_changed(0)

    def _on_engine_index_changed(self, index: int):
        # 直接从 _engine_items 获取 engine_id，避免 itemData 兼容性问题
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
        for w in self._whisper_remote_widgets:
            w.setVisible(engine == "whisper_remote")
        for w in self._whisper_widgets:
            w.setVisible(engine == "whisper")


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
        self.theme_combo.addItem(t("theme_light"), "light")
        self.theme_combo.addItem(t("theme_dark"), "dark")
        self.theme_combo.addItem(t("theme_auto"), "auto")
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
        theme = self.theme_combo.itemData(index)
        if theme:
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
        self._engine_page = EnginePage(self._config, self)
        self._engine_page.setObjectName("enginePage")
        self._appearance_page = AppearancePage(self._config, self)
        self._appearance_page.setObjectName("appearancePage")

        # Add pages to navigation
        self.addSubInterface(self._core_page, FluentIcon.SETTING, t("tab_core"))
        self.addSubInterface(self._engine_page, FluentIcon.IOT, t("tab_engine"))
        self.addSubInterface(self._appearance_page, FluentIcon.PALETTE, t("tab_appearance"))

        # Connect save signals
        self._core_page.save_clicked.connect(self._save_settings)
        self._engine_page.save_clicked.connect(self._save_settings)
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

        # Core page - AI settings
        self._core_page.ai_enabled.setChecked(self._config.get("core.ai.enabled", True))
        self._core_page.ai_hotkey_combo.setCurrentText(self._config.get("core.ai.hotkey", "alt"))
        self._core_page.ai_hold_time_spin.setValue(self._config.get("core.ai.hotkey_hold_time", 0.5))
        self._core_page.ai_url_input.setText(self._config.get("core.ai.url", "https://chatgpt.com"))
        self._core_page.ai_page_load_delay_spin.setValue(self._config.get("core.ai.page_load_delay", 3.0))
        self._core_page.ai_auto_enter.setChecked(self._config.get("core.ai.auto_enter", True))

        # Engine page
        engine = self._config.get("engine.current", "volc_bigmodel")
        # 找到引擎对应的索引
        for i, (engine_id, _) in enumerate(self._engine_page._engine_items):
            if engine_id == engine:
                self._engine_page.engine_combo.setCurrentIndex(i)
                break
        self._engine_page._on_engine_index_changed(self._engine_page.engine_combo.currentIndex())

        # Engine settings - 火山大模型
        self._engine_page.volc_bigmodel_appkey.setText(self._config.get("engine.volc_bigmodel.app_key", ""))
        self._engine_page.volc_bigmodel_ak.setText(self._config.get("engine.volc_bigmodel.access_key", ""))
        self._engine_page.volc_bigmodel_model.setCurrentText(self._config.get("engine.volc_bigmodel.model", "bigmodel"))

        # Engine settings - 火山一句话
        self._engine_page.volc_appid.setText(self._config.get("engine.volcengine.app_id", ""))
        self._engine_page.volc_ak.setText(self._config.get("engine.volcengine.access_key", ""))
        self._engine_page.volc_sk.setText(self._config.get("engine.volcengine.secret_key", ""))

        # Engine settings - OpenAI
        self._engine_page.openai_key.setText(self._config.get("engine.openai.api_key", ""))
        self._engine_page.openai_model.setText(self._config.get("engine.openai.model", "whisper-1"))
        self._engine_page.openai_url.setText(self._config.get("engine.openai.base_url", ""))

        # Engine settings - Whisper Remote
        self._engine_page.whisper_remote_url.setText(self._config.get("engine.whisper_remote.server_url", ""))
        self._engine_page.whisper_remote_model.setText(self._config.get("engine.whisper_remote.model", ""))
        self._engine_page.whisper_remote_key.setText(self._config.get("engine.whisper_remote.api_key", ""))

        # Engine settings - 本地 Whisper
        self._engine_page.whisper_model.setCurrentText(self._config.get("engine.whisper.model", "base"))
        self._engine_page.whisper_device.setCurrentText(self._config.get("engine.whisper.device", "auto"))

        # Appearance page
        theme = self._config.get("appearance.theme", "auto")
        for i in range(self._appearance_page.theme_combo.count()):
            if self._appearance_page.theme_combo.itemData(i) == theme:
                self._appearance_page.theme_combo.setCurrentIndex(i)
                break
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

        # Core - AI settings
        self._config.set("core.ai.enabled", self._core_page.ai_enabled.isChecked())
        self._config.set("core.ai.hotkey", self._core_page.ai_hotkey_combo.currentText())
        self._config.set("core.ai.hotkey_hold_time", self._core_page.ai_hold_time_spin.value())
        self._config.set("core.ai.url", self._core_page.ai_url_input.text() or "https://chatgpt.com")
        self._config.set("core.ai.page_load_delay", self._core_page.ai_page_load_delay_spin.value())
        self._config.set("core.ai.auto_enter", self._core_page.ai_auto_enter.isChecked())

        # Set auto-start
        set_autostart(self._core_page.auto_start.isChecked())

        # Engine settings - 直接从 _engine_items 获取 engine_id
        idx = self._engine_page.engine_combo.currentIndex()
        if 0 <= idx < len(self._engine_page._engine_items):
            engine = self._engine_page._engine_items[idx][0]
        else:
            engine = "volc_bigmodel"  # Default
        self._config.set("engine.current", engine)

        # 火山大模型
        self._config.set("engine.volc_bigmodel.app_key", self._engine_page.volc_bigmodel_appkey.text())
        self._config.set("engine.volc_bigmodel.access_key", self._engine_page.volc_bigmodel_ak.text())
        self._config.set("engine.volc_bigmodel.model", self._engine_page.volc_bigmodel_model.currentText())

        # 火山一句话
        self._config.set("engine.volcengine.app_id", self._engine_page.volc_appid.text())
        self._config.set("engine.volcengine.access_key", self._engine_page.volc_ak.text())
        self._config.set("engine.volcengine.secret_key", self._engine_page.volc_sk.text())

        # OpenAI
        self._config.set("engine.openai.api_key", self._engine_page.openai_key.text())
        self._config.set("engine.openai.model", self._engine_page.openai_model.text() or "whisper-1")
        self._config.set("engine.openai.base_url", self._engine_page.openai_url.text() or "https://api.openai.com/v1")

        # Whisper Remote
        self._config.set("engine.whisper_remote.server_url", self._engine_page.whisper_remote_url.text() or "http://localhost:8000")
        self._config.set("engine.whisper_remote.model", self._engine_page.whisper_remote_model.text() or "whisper-1")
        self._config.set("engine.whisper_remote.api_key", self._engine_page.whisper_remote_key.text())

        # 本地 Whisper
        self._config.set("engine.whisper.model", self._engine_page.whisper_model.currentText())
        self._config.set("engine.whisper.device", self._engine_page.whisper_device.currentText())

        # Appearance settings
        theme = self._appearance_page.theme_combo.currentData()
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
