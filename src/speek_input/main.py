import sys
import threading
from typing import Optional

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from .config import config
from .audio import AudioRecorder
from .hotkey import HotkeyListener
from .input_method import input_method
from .engines.base import BaseEngine
from .ui.floating_window import FloatingWindow
from .ui.tray_icon import TrayIcon
from .ui.settings_dialog import SettingsDialog


class SignalBridge(QObject):
    start_recording = pyqtSignal()
    stop_recording = pyqtSignal()
    audio_level = pyqtSignal(float)
    recognition_done = pyqtSignal(str)
    recognition_error = pyqtSignal(str)


class SpeekInputApp:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

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
                access_token=config.get("volcengine.access_token", ""),
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
        self._signals.start_recording.emit()

    def _on_hotkey_release(self):
        self._signals.stop_recording.emit()

    def _on_start_recording(self):
        self._floating_window.show_recording()
        self._recorder.start()

    def _on_stop_recording(self):
        audio_data = self._recorder.stop()
        if not audio_data:
            self._floating_window.hide()
            return

        self._floating_window.show_recognizing()

        def recognize():
            try:
                if self._engine is None:
                    self._signals.recognition_error.emit("未配置识别引擎")
                    return
                text = self._engine.transcribe(audio_data, config.language)
                if text:
                    self._signals.recognition_done.emit(text)
                else:
                    self._signals.recognition_error.emit("识别结果为空")
            except Exception as e:
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

    def _quit(self):
        self._hotkey_listener.stop()
        self._recorder.close()
        self._tray.hide()
        self._app.quit()

    def run(self):
        self._tray.show()
        self._tray.show_message("SpeekInput", f"已启动，长按 {config.hotkey.upper()} 开始语音输入")
        self._hotkey_listener.start()
        return self._app.exec_()


def main():
    app = SpeekInputApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
