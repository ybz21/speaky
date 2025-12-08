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


class GeneralPage(SettingsPage):
    """General settings page"""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        # Hotkey settings
        self.add_group_label(t("hotkey_group"))

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

        # Language settings
        self.add_group_label(t("language_group"))

        self.lang_combo = ComboBox()
        self.lang_combo.addItems(["zh", "en", "ja", "ko"])
        self.lang_combo.setMinimumWidth(150)
        self.add_card(t("recognition_lang"), self.lang_combo)

        self.ui_lang_combo = ComboBox()
        for lang_code in ["auto", "en", "zh", "zh_TW", "ja", "ko", "de", "fr", "es", "pt", "ru"]:
            display_name = i18n.get_language_name(lang_code)
            self.ui_lang_combo.addItem(display_name, lang_code)
        self.ui_lang_combo.setMinimumWidth(150)
        self.add_card(t("ui_lang"), self.ui_lang_combo)

        self.add_save_button()


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
        self.engine_combo.addItems([
            "whisper", "openai", "volcengine", "volc_bigmodel", "aliyun"
        ])
        self.engine_combo.setMinimumWidth(180)
        self.engine_combo.currentTextChanged.connect(self._on_engine_changed)
        self.add_card(t("engine_label"), self.engine_combo)

        # Whisper settings
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

        # OpenAI settings
        self._openai_label = SubtitleLabel(t("openai_settings"), self._container)
        self._openai_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._openai_label)

        self.openai_key = PasswordLineEdit()
        self.openai_key.setMinimumWidth(250)
        self._openai_key_card = self.add_card(t("api_key"), self.openai_key)

        self.openai_url = LineEdit()
        self.openai_url.setPlaceholderText("https://api.openai.com/v1")
        self.openai_url.setMinimumWidth(250)
        self._openai_url_card = self.add_card(t("base_url"), self.openai_url)

        # Volcengine settings
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

        # Volcengine BigModel settings
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

        # Aliyun settings
        self._aliyun_label = SubtitleLabel(t("aliyun_settings"), self._container)
        self._aliyun_label.setContentsMargins(0, 10, 0, 5)
        self._layout.addWidget(self._aliyun_label)

        self.aliyun_appkey = LineEdit()
        self.aliyun_appkey.setMinimumWidth(250)
        self._aliyun_appkey_card = self.add_card(t("app_key"), self.aliyun_appkey)

        self.aliyun_token = PasswordLineEdit()
        self.aliyun_token.setMinimumWidth(250)
        self._aliyun_token_card = self.add_card(t("access_token"), self.aliyun_token)

        self.add_save_button()

        # Store all engine widgets for visibility control
        self._whisper_widgets = [self._whisper_label, self._whisper_model_card, self._whisper_device_card]
        self._openai_widgets = [self._openai_label, self._openai_key_card, self._openai_url_card]
        self._volc_widgets = [self._volc_label, self._volc_appid_card, self._volc_ak_card, self._volc_sk_card]
        self._volc_bigmodel_widgets = [self._volc_bigmodel_label, self._volc_bigmodel_appkey_card,
                                        self._volc_bigmodel_ak_card, self._volc_bigmodel_model_card]
        self._aliyun_widgets = [self._aliyun_label, self._aliyun_appkey_card, self._aliyun_token_card]

    def _on_engine_changed(self, engine: str):
        for w in self._whisper_widgets:
            w.setVisible(engine == "whisper")
        for w in self._openai_widgets:
            w.setVisible(engine == "openai")
        for w in self._volc_widgets:
            w.setVisible(engine == "volcengine")
        for w in self._volc_bigmodel_widgets:
            w.setVisible(engine == "volc_bigmodel")
        for w in self._aliyun_widgets:
            w.setVisible(engine == "aliyun")


class UIPage(SettingsPage):
    """UI settings page"""

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
        self.add_card(t("theme"), self.theme_combo)

        self.show_waveform = SwitchButton()
        self.add_card(t("show_waveform"), self.show_waveform)

        self.streaming_mode = SwitchButton()
        self.add_card(t("streaming_mode"), self.streaming_mode)

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


class SettingsDialog(FluentWindow):
    """Fluent-style settings window"""
    settings_changed = Signal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        self.setWindowTitle(t("settings_title"))
        self.resize(700, 550)

        # Create pages
        self._general_page = GeneralPage(self._config, self)
        self._general_page.setObjectName("generalPage")
        self._engine_page = EnginePage(self._config, self)
        self._engine_page.setObjectName("enginePage")
        self._ui_page = UIPage(self._config, self)
        self._ui_page.setObjectName("uiPage")

        # Add pages to navigation
        self.addSubInterface(self._general_page, FluentIcon.SETTING, t("tab_general"))
        self.addSubInterface(self._engine_page, FluentIcon.IOT, t("tab_engine"))
        self.addSubInterface(self._ui_page, FluentIcon.PALETTE, t("tab_ui"))

        # Connect save signals
        self._general_page.save_clicked.connect(self._save_settings)
        self._engine_page.save_clicked.connect(self._save_settings)
        self._ui_page.save_clicked.connect(self._save_settings)

    def _load_settings(self):
        # General page
        self._general_page.hotkey_combo.setCurrentText(self._config.get("hotkey", "ctrl"))
        self._general_page.hold_time_spin.setValue(self._config.get("hotkey_hold_time", 1.0))
        self._general_page.lang_combo.setCurrentText(self._config.get("language", "zh"))

        ui_lang = self._config.get("ui_language", "auto")
        for i in range(self._general_page.ui_lang_combo.count()):
            if self._general_page.ui_lang_combo.itemData(i) == ui_lang:
                self._general_page.ui_lang_combo.setCurrentIndex(i)
                break

        # Engine page
        engine = self._config.get("engine", "whisper")
        self._engine_page.engine_combo.setCurrentText(engine)
        self._engine_page._on_engine_changed(engine)

        self._engine_page.whisper_model.setCurrentText(self._config.get("whisper.model", "base"))
        self._engine_page.whisper_device.setCurrentText(self._config.get("whisper.device", "auto"))

        self._engine_page.openai_key.setText(self._config.get("openai.api_key", ""))
        self._engine_page.openai_url.setText(self._config.get("openai.base_url", ""))

        self._engine_page.volc_appid.setText(self._config.get("volcengine.app_id", ""))
        self._engine_page.volc_ak.setText(self._config.get("volcengine.access_key", ""))
        self._engine_page.volc_sk.setText(self._config.get("volcengine.secret_key", ""))

        self._engine_page.volc_bigmodel_appkey.setText(self._config.get("volc_bigmodel.app_key", ""))
        self._engine_page.volc_bigmodel_ak.setText(self._config.get("volc_bigmodel.access_key", ""))
        self._engine_page.volc_bigmodel_model.setCurrentText(self._config.get("volc_bigmodel.model", "bigmodel"))

        self._engine_page.aliyun_appkey.setText(self._config.get("aliyun.app_key", ""))
        self._engine_page.aliyun_token.setText(self._config.get("aliyun.access_token", ""))

        # UI page
        theme = self._config.get("ui.theme", "auto")
        for i in range(self._ui_page.theme_combo.count()):
            if self._ui_page.theme_combo.itemData(i) == theme:
                self._ui_page.theme_combo.setCurrentIndex(i)
                break
        self._ui_page.show_waveform.setChecked(self._config.get("ui.show_waveform", True))
        self._ui_page.streaming_mode.setChecked(self._config.get("ui.streaming_mode", True))
        opacity = int(self._config.get("ui.window_opacity", 0.9) * 100)
        self._ui_page.opacity_slider.setValue(opacity)
        self._ui_page._opacity_label.setText(f"{opacity}%")

    def _save_settings(self):
        # General settings
        self._config.set("hotkey", self._general_page.hotkey_combo.currentText())
        self._config.set("hotkey_hold_time", self._general_page.hold_time_spin.value())
        self._config.set("language", self._general_page.lang_combo.currentText())
        self._config.set("ui_language", self._general_page.ui_lang_combo.currentData())

        # Engine settings
        self._config.set("engine", self._engine_page.engine_combo.currentText())

        self._config.set("whisper.model", self._engine_page.whisper_model.currentText())
        self._config.set("whisper.device", self._engine_page.whisper_device.currentText())

        self._config.set("openai.api_key", self._engine_page.openai_key.text())
        self._config.set("openai.base_url", self._engine_page.openai_url.text() or "https://api.openai.com/v1")

        self._config.set("volcengine.app_id", self._engine_page.volc_appid.text())
        self._config.set("volcengine.access_key", self._engine_page.volc_ak.text())
        self._config.set("volcengine.secret_key", self._engine_page.volc_sk.text())

        self._config.set("volc_bigmodel.app_key", self._engine_page.volc_bigmodel_appkey.text())
        self._config.set("volc_bigmodel.access_key", self._engine_page.volc_bigmodel_ak.text())
        self._config.set("volc_bigmodel.model", self._engine_page.volc_bigmodel_model.currentText())

        self._config.set("aliyun.app_key", self._engine_page.aliyun_appkey.text())
        self._config.set("aliyun.access_token", self._engine_page.aliyun_token.text())

        # UI settings
        theme = self._ui_page.theme_combo.currentData()
        self._config.set("ui.theme", theme)
        self._config.set("ui.show_waveform", self._ui_page.show_waveform.isChecked())
        self._config.set("ui.streaming_mode", self._ui_page.streaming_mode.isChecked())
        self._config.set("ui.window_opacity", self._ui_page.opacity_slider.value() / 100)

        self._config.save()

        # Update i18n language
        i18n.set_language(self._general_page.ui_lang_combo.currentData())

        # Apply theme
        apply_theme(theme)

        self.settings_changed.emit()

        # Show success message
        MessageBox(t("tip"), t("saved_message"), self).exec()
        self.close()
