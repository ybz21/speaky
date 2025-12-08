import logging
import sys
import threading
from typing import Optional

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from .config import config
from .audio import AudioRecorder
from .hotkey import HotkeyListener
from .input_method import input_method, check_macos_accessibility, open_macos_accessibility_settings
from .engines.base import BaseEngine
from .ui.floating_window import FloatingWindow
from .ui.tray_icon import TrayIcon
from .ui.settings_dialog import SettingsDialog
from .i18n import t, i18n

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SignalBridge(QObject):
    start_recording = pyqtSignal()
    stop_recording = pyqtSignal()
    audio_level = pyqtSignal(float)
    recognition_done = pyqtSignal(str)
    recognition_error = pyqtSignal(str)


class SpeakyApp:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # Initialize i18n language from config
        i18n.set_language(config.get("ui_language", "auto"))

        self._signals = SignalBridge()
        self._recorder = AudioRecorder()
        self._engine: Optional[BaseEngine] = None
        self._floating_window = FloatingWindow()
        self._tray = TrayIcon()
        self._settings_dialog: Optional[SettingsDialog] = None

        self._setup_engine()
        self._setup_hotkey()
        self._setup_signals()
        self._setup_tray()

    def _setup_engine(self):
        engine_name = config.engine
        logger.info(f"Setting up engine: {engine_name}")
        if engine_name == "whisper":
            from .engines.whisper_engine import WhisperEngine
            self._engine = WhisperEngine(
                model_name=config.get("whisper.model", "base"),
                device=config.get("whisper.device", "auto"),
            )
        elif engine_name == "openai":
            from .engines.openai_engine import OpenAIEngine
            self._engine = OpenAIEngine(
                api_key=config.get("openai.api_key", ""),
                model=config.get("openai.model", "whisper-1"),
                base_url=config.get("openai.base_url", "https://api.openai.com/v1"),
            )
        elif engine_name == "volcengine":
            from .engines.volcengine_engine import VolcEngineEngine
            self._engine = VolcEngineEngine(
                app_id=config.get("volcengine.app_id", ""),
                access_key=config.get("volcengine.access_key", ""),
                secret_key=config.get("volcengine.secret_key", ""),
            )
        elif engine_name == "volc_bigmodel":
            from .engines.volc_bigmodel_engine import VolcBigModelEngine
            self._engine = VolcBigModelEngine(
                app_key=config.get("volc_bigmodel.app_key", ""),
                access_key=config.get("volc_bigmodel.access_key", ""),
                model=config.get("volc_bigmodel.model", "bigmodel"),
            )
        elif engine_name == "aliyun":
            from .engines.aliyun_engine import AliyunEngine
            self._engine = AliyunEngine(
                app_key=config.get("aliyun.app_key", ""),
                access_token=config.get("aliyun.access_token", ""),
            )
        elif engine_name == "tencent":
            from .engines.tencent_engine import TencentEngine
            self._engine = TencentEngine(
                secret_id=config.get("tencent.secret_id", ""),
                secret_key=config.get("tencent.secret_key", ""),
            )

    def _setup_hotkey(self):
        self._hotkey_listener = HotkeyListener(
            hotkey=config.hotkey,
            on_press=self._on_hotkey_press,
            on_release=self._on_hotkey_release,
            hold_time=config.get("hotkey_hold_time", 1.0),
        )
        self._recorder.set_audio_level_callback(
            lambda level: self._signals.audio_level.emit(level)
        )

    def _setup_signals(self):
        self._signals.start_recording.connect(self._on_start_recording)
        self._signals.stop_recording.connect(self._on_stop_recording)
        self._signals.audio_level.connect(self._floating_window.update_audio_level)
        self._signals.recognition_done.connect(self._on_recognition_done)
        self._signals.recognition_error.connect(self._on_recognition_error)

    def _setup_tray(self):
        self._tray.settings_clicked.connect(self._show_settings)
        self._tray.quit_clicked.connect(self._quit)

    def _on_hotkey_press(self):
        logger.info("Hotkey pressed - starting recording")
        # Save current focus before showing floating window
        input_method.save_focus()
        self._signals.start_recording.emit()

    def _on_hotkey_release(self):
        logger.info("Hotkey released - stopping recording")
        self._signals.stop_recording.emit()

    def _on_start_recording(self):
        logger.info("Starting recording, showing floating window")
        self._floating_window.show_recording()
        self._recorder.start()

    def _on_stop_recording(self):
        logger.info("Stopping recording")
        audio_data = self._recorder.stop()
        if not audio_data:
            logger.warning("No audio data recorded")
            self._floating_window.hide()
            return

        logger.info(f"Recorded {len(audio_data)} bytes of audio data")
        self._floating_window.show_recognizing()

        def recognize():
            try:
                if self._engine is None:
                    logger.error("No recognition engine configured")
                    self._signals.recognition_error.emit(t("no_engine"))
                    return
                logger.info(f"Transcribing with engine: {self._engine.name}")
                text = self._engine.transcribe(audio_data, config.language)
                if text:
                    logger.info(f"Recognition result: {text}")
                    self._signals.recognition_done.emit(text)
                else:
                    logger.warning("Recognition result is empty")
                    self._signals.recognition_error.emit(t("empty_result"))
            except Exception as e:
                logger.error(f"Recognition error: {e}", exc_info=True)
                self._signals.recognition_error.emit(str(e))

        threading.Thread(target=recognize, daemon=True).start()

    def _on_recognition_done(self, text: str):
        self._floating_window.show_result(text)
        QTimer.singleShot(100, lambda: input_method.type_text(text))

    def _on_recognition_error(self, error: str):
        self._floating_window.show_error(error)

    def _show_settings(self):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(config)
            self._settings_dialog.settings_changed.connect(self._on_settings_changed)
        self._settings_dialog.show()
        self._settings_dialog.raise_()

    def _on_settings_changed(self):
        self._setup_engine()
        self._hotkey_listener.update_hotkey(config.hotkey)
        self._hotkey_listener.update_hold_time(config.get("hotkey_hold_time", 1.0))

    def _quit(self):
        self._hotkey_listener.stop()
        self._recorder.close()
        self._tray.hide()
        self._app.quit()

    def run(self):
        logger.info(f"Speaky starting with hotkey: {config.hotkey}")
        logger.info(f"Engine: {config.engine}, Language: {config.language}")
        self._tray.show()
        self._tray.show_message(
            t("app_name"),
            t("started_message", hotkey=config.hotkey.upper())
        )
        self._hotkey_listener.start()
        logger.info("Hotkey listener started")
        return self._app.exec_()


def main():
    import platform

    # Check macOS Accessibility permission before starting
    if platform.system() == "Darwin" and not check_macos_accessibility():
        print("\n⚠️  Speaky 需要辅助功能权限才能正常工作")
        print("   - 监听全局快捷键")
        print("   - 模拟键盘输入（粘贴）")
        print("\n正在打开系统设置...")
        open_macos_accessibility_settings()
        print("\n📋 请在系统设置中：")
        print("   1. 找到你的终端应用（Terminal/iTerm 等）")
        print("   2. 点击开关启用权限")
        print("   3. 授权后重新运行程序")
        print()
        input("按 Enter 继续运行（可能功能受限）...")

    app = SpeakyApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
