from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QTabWidget, QWidget, QGroupBox, QCheckBox,
    QSlider, QMessageBox, QDoubleSpinBox
)
from PyQt5.QtCore import Qt, pyqtSignal

from ..i18n import t, i18n


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal()

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._setup_ui()
        self._load_settings()

    def _setup_ui(self):
        self.setWindowTitle(t("settings_title"))
        self.setMinimumSize(450, 400)

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._create_general_tab(), t("tab_general"))
        tabs.addTab(self._create_engine_tab(), t("tab_engine"))
        tabs.addTab(self._create_ui_tab(), t("tab_ui"))
        layout.addWidget(tabs)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        save_btn = QPushButton(t("save"))
        save_btn.clicked.connect(self._save_settings)
        button_layout.addWidget(save_btn)

        cancel_btn = QPushButton(t("cancel"))
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        hotkey_group = QGroupBox(t("hotkey_group"))
        hotkey_layout = QFormLayout(hotkey_group)

        self._hotkey_combo = QComboBox()
        self._hotkey_combo.addItems(["ctrl", "alt", "shift", "ctrl_l", "ctrl_r"])
        self._hotkey_combo.setEditable(True)
        hotkey_layout.addRow(t("hotkey_label"), self._hotkey_combo)

        self._hold_time_spin = QDoubleSpinBox()
        self._hold_time_spin.setRange(0.0, 5.0)
        self._hold_time_spin.setSingleStep(0.1)
        self._hold_time_spin.setDecimals(1)
        self._hold_time_spin.setSuffix(t("seconds"))
        self._hold_time_spin.setToolTip(t("hold_time_tooltip"))
        hotkey_layout.addRow(t("hold_time_label"), self._hold_time_spin)

        layout.addWidget(hotkey_group)

        lang_group = QGroupBox(t("language_group"))
        lang_layout = QFormLayout(lang_group)

        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["zh", "en", "ja", "ko"])
        lang_layout.addRow(t("recognition_lang"), self._lang_combo)

        self._ui_lang_combo = QComboBox()
        for lang_code in ["auto", "en", "zh", "zh_TW", "ja", "ko", "de", "fr", "es", "pt", "ru"]:
            display_name = i18n.get_language_name(lang_code)
            self._ui_lang_combo.addItem(display_name, lang_code)
        lang_layout.addRow(t("ui_lang"), self._ui_lang_combo)

        layout.addWidget(lang_group)
        layout.addStretch()

        return widget

    def _create_engine_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        engine_group = QGroupBox(t("engine_group"))
        engine_layout = QFormLayout(engine_group)

        self._engine_combo = QComboBox()
        self._engine_combo.addItems([
            "whisper", "openai", "volcengine", "aliyun", "tencent"
        ])
        self._engine_combo.currentTextChanged.connect(self._on_engine_changed)
        engine_layout.addRow(t("engine_label"), self._engine_combo)

        layout.addWidget(engine_group)

        # Whisper settings
        self._whisper_group = QGroupBox(t("whisper_settings"))
        whisper_layout = QFormLayout(self._whisper_group)

        self._whisper_model = QComboBox()
        self._whisper_model.addItems(["tiny", "base", "small", "medium", "large"])
        whisper_layout.addRow(t("model"), self._whisper_model)

        self._whisper_device = QComboBox()
        self._whisper_device.addItems(["auto", "cpu", "cuda"])
        whisper_layout.addRow(t("device"), self._whisper_device)

        layout.addWidget(self._whisper_group)

        # OpenAI settings
        self._openai_group = QGroupBox(t("openai_settings"))
        openai_layout = QFormLayout(self._openai_group)

        self._openai_key = QLineEdit()
        self._openai_key.setEchoMode(QLineEdit.Password)
        openai_layout.addRow(t("api_key"), self._openai_key)

        self._openai_url = QLineEdit()
        self._openai_url.setPlaceholderText("https://api.openai.com/v1")
        openai_layout.addRow(t("base_url"), self._openai_url)

        layout.addWidget(self._openai_group)

        # Volcengine settings
        self._volc_group = QGroupBox(t("volc_settings"))
        volc_layout = QFormLayout(self._volc_group)

        self._volc_appid = QLineEdit()
        volc_layout.addRow(t("app_id"), self._volc_appid)

        self._volc_ak = QLineEdit()
        self._volc_ak.setEchoMode(QLineEdit.Password)
        volc_layout.addRow(t("access_key"), self._volc_ak)

        self._volc_sk = QLineEdit()
        self._volc_sk.setEchoMode(QLineEdit.Password)
        volc_layout.addRow(t("secret_key"), self._volc_sk)

        layout.addWidget(self._volc_group)

        # Aliyun settings
        self._aliyun_group = QGroupBox(t("aliyun_settings"))
        aliyun_layout = QFormLayout(self._aliyun_group)

        self._aliyun_appkey = QLineEdit()
        aliyun_layout.addRow(t("app_key"), self._aliyun_appkey)

        self._aliyun_token = QLineEdit()
        self._aliyun_token.setEchoMode(QLineEdit.Password)
        aliyun_layout.addRow(t("access_token"), self._aliyun_token)

        layout.addWidget(self._aliyun_group)

        # Tencent settings
        self._tencent_group = QGroupBox(t("tencent_settings"))
        tencent_layout = QFormLayout(self._tencent_group)

        self._tencent_id = QLineEdit()
        tencent_layout.addRow(t("secret_id"), self._tencent_id)

        self._tencent_key = QLineEdit()
        self._tencent_key.setEchoMode(QLineEdit.Password)
        tencent_layout.addRow(t("secret_key"), self._tencent_key)

        layout.addWidget(self._tencent_group)

        layout.addStretch()
        return widget

    def _create_ui_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        ui_group = QGroupBox(t("ui_group"))
        ui_layout = QFormLayout(ui_group)

        self._show_waveform = QCheckBox(t("show_waveform"))
        ui_layout.addRow(self._show_waveform)

        self._opacity_slider = QSlider(Qt.Horizontal)
        self._opacity_slider.setRange(50, 100)
        self._opacity_slider.setValue(90)
        ui_layout.addRow(t("window_opacity"), self._opacity_slider)

        layout.addWidget(ui_group)
        layout.addStretch()

        return widget

    def _on_engine_changed(self, engine: str):
        self._whisper_group.setVisible(engine == "whisper")
        self._openai_group.setVisible(engine == "openai")
        self._volc_group.setVisible(engine == "volcengine")
        self._aliyun_group.setVisible(engine == "aliyun")
        self._tencent_group.setVisible(engine == "tencent")

    def _load_settings(self):
        self._hotkey_combo.setCurrentText(self._config.get("hotkey", "ctrl"))
        self._hold_time_spin.setValue(self._config.get("hotkey_hold_time", 1.0))
        self._lang_combo.setCurrentText(self._config.get("language", "zh"))

        # UI language
        ui_lang = self._config.get("ui_language", "auto")
        for i in range(self._ui_lang_combo.count()):
            if self._ui_lang_combo.itemData(i) == ui_lang:
                self._ui_lang_combo.setCurrentIndex(i)
                break

        self._engine_combo.setCurrentText(self._config.get("engine", "whisper"))

        self._whisper_model.setCurrentText(self._config.get("whisper.model", "base"))
        self._whisper_device.setCurrentText(self._config.get("whisper.device", "auto"))

        self._openai_key.setText(self._config.get("openai.api_key", ""))
        self._openai_url.setText(self._config.get("openai.base_url", ""))

        self._volc_appid.setText(self._config.get("volcengine.app_id", ""))
        self._volc_ak.setText(self._config.get("volcengine.access_key", ""))
        self._volc_sk.setText(self._config.get("volcengine.secret_key", ""))

        self._aliyun_appkey.setText(self._config.get("aliyun.app_key", ""))
        self._aliyun_token.setText(self._config.get("aliyun.access_token", ""))

        self._tencent_id.setText(self._config.get("tencent.secret_id", ""))
        self._tencent_key.setText(self._config.get("tencent.secret_key", ""))

        self._show_waveform.setChecked(self._config.get("ui.show_waveform", True))
        self._opacity_slider.setValue(int(self._config.get("ui.window_opacity", 0.9) * 100))

        self._on_engine_changed(self._engine_combo.currentText())

    def _save_settings(self):
        self._config.set("hotkey", self._hotkey_combo.currentText())
        self._config.set("hotkey_hold_time", self._hold_time_spin.value())
        self._config.set("language", self._lang_combo.currentText())
        self._config.set("ui_language", self._ui_lang_combo.currentData())
        self._config.set("engine", self._engine_combo.currentText())

        self._config.set("whisper.model", self._whisper_model.currentText())
        self._config.set("whisper.device", self._whisper_device.currentText())

        self._config.set("openai.api_key", self._openai_key.text())
        self._config.set("openai.base_url", self._openai_url.text() or "https://api.openai.com/v1")

        self._config.set("volcengine.app_id", self._volc_appid.text())
        self._config.set("volcengine.access_key", self._volc_ak.text())
        self._config.set("volcengine.secret_key", self._volc_sk.text())

        self._config.set("aliyun.app_key", self._aliyun_appkey.text())
        self._config.set("aliyun.access_token", self._aliyun_token.text())

        self._config.set("tencent.secret_id", self._tencent_id.text())
        self._config.set("tencent.secret_key", self._tencent_key.text())

        self._config.set("ui.show_waveform", self._show_waveform.isChecked())
        self._config.set("ui.window_opacity", self._opacity_slider.value() / 100)

        self._config.save()

        # Update i18n language
        i18n.set_language(self._ui_lang_combo.currentData())

        self.settings_changed.emit()
        self.accept()
        QMessageBox.information(self, t("tip"), t("saved_message"))
