import faulthandler
import logging
import os
import platform
import sys
import threading
from typing import Optional

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal

from .config import config
from .audio import AudioRecorder
from .hotkey import HotkeyListener
from .input_method import check_macos_accessibility, open_macos_accessibility_settings
from .engines.base import BaseEngine
from .ui.floating_window import FloatingWindow
from .ui.tray_icon import TrayIcon
from .ui.settings_dialog import SettingsDialog, apply_theme
from .ui.log_viewer import LogViewerDialog
from .i18n import t, i18n
from .handlers import VoiceModeHandler, AIModeHandler
from .sound import set_sound_enabled

# Enable faulthandler to dump traceback on segfault
faulthandler.enable()

# Setup logging - both console and file
log_dir = os.path.expanduser("~/.speaky")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "speaky.log")

# Create handlers
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

# Create formatters
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Setup root logger
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[console_handler, file_handler]
)
logger = logging.getLogger(__name__)
logger.info(f"Log file: {log_file}")

# Global exception handler
def global_exception_handler(exctype, value, tb):
    import traceback
    logger.error("Uncaught exception:")
    logger.error(''.join(traceback.format_exception(exctype, value, tb)))
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = global_exception_handler


def set_macos_accessory_mode():
    """Set macOS app to Accessory mode - won't appear in Dock or steal focus"""
    if platform.system() != "Darwin":
        return
    try:
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    except ImportError:
        pass


class SignalBridge(QObject):
    """Qt 信号桥接器，用于跨线程通信"""
    # 语音模式信号
    start_recording = Signal()
    stop_recording = Signal()
    recognition_done = Signal(str)
    recognition_error = Signal(str)

    # AI 模式信号
    ai_start_recording = Signal()
    ai_stop_recording = Signal()
    ai_recognition_done = Signal(str)

    # 共享信号
    audio_level = Signal(float)
    partial_result = Signal(str)


class SpeakyApp:
    """Speaky 应用主类

    职责：
    1. 初始化核心组件（录音器、引擎、UI）
    2. 设置快捷键监听
    3. 将事件路由到对应的 handler
    4. 管理应用生命周期
    """

    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # Set macOS to accessory mode
        set_macos_accessory_mode()

        # Initialize i18n language from config
        i18n.set_language(config.get("appearance.ui_language", "auto"))

        # Apply theme from config
        apply_theme(config.get("appearance.theme", "auto"))

        # Initialize sound notification setting
        set_sound_enabled(config.get("core.asr.sound_notification", True))

        # 初始化核心组件
        self._signals = SignalBridge()
        self._recorder = AudioRecorder(
            device_index=config.get("core.asr.audio_device"),
            gain=config.get("core.asr.audio_gain", 1.0)
        )
        self._engine: Optional[BaseEngine] = None
        self._floating_window = FloatingWindow()
        self._tray = TrayIcon()
        self._settings_dialog: Optional[SettingsDialog] = None
        self._log_viewer: Optional[LogViewerDialog] = None

        # 初始化引擎
        self._setup_engine()

        # 初始化模式处理器
        self._voice_handler = VoiceModeHandler(
            signals=self._signals,
            recorder=self._recorder,
            engine_getter=lambda: self._engine,
            floating_window=self._floating_window,
            config=config,
        )
        self._ai_handler = AIModeHandler(
            signals=self._signals,
            recorder=self._recorder,
            engine_getter=lambda: self._engine,
            floating_window=self._floating_window,
            config=config,
        )

        # 设置快捷键和信号连接
        self._setup_hotkeys()
        self._setup_signals()
        self._setup_tray()

        # 预热录音器
        self._recorder.warmup()

    def _setup_engine(self):
        """初始化语音识别引擎"""
        engine_name = config.engine
        logger.info(f"Setting up engine: {engine_name}")

        if engine_name == "whisper":
            from .engines.whisper_engine import WhisperEngine
            self._engine = WhisperEngine(
                model_name=config.get("engine.whisper.model", "base"),
                device=config.get("engine.whisper.device", "auto"),
                compute_type=config.get("engine.whisper.compute_type", "auto"),
            )
        elif engine_name == "openai":
            from .engines.openai_engine import OpenAIEngine
            self._engine = OpenAIEngine(
                api_key=config.get("engine.openai.api_key", ""),
                model=config.get("engine.openai.model", "whisper-1"),
                base_url=config.get("engine.openai.base_url", "https://api.openai.com/v1"),
            )
        elif engine_name == "volcengine":
            from .engines.volcengine_engine import VolcEngineEngine
            self._engine = VolcEngineEngine(
                app_id=config.get("engine.volcengine.app_id", ""),
                access_key=config.get("engine.volcengine.access_key", ""),
                secret_key=config.get("engine.volcengine.secret_key", ""),
            )
        elif engine_name == "volc_bigmodel":
            from .engines.volc_bigmodel_engine import VolcBigModelEngine
            self._engine = VolcBigModelEngine(
                app_key=config.get("engine.volc_bigmodel.app_key", ""),
                access_key=config.get("engine.volc_bigmodel.access_key", ""),
                model=config.get("engine.volc_bigmodel.model", "bigmodel"),
            )
            # Pre-warm connection for faster first request
            if hasattr(self._engine, 'warmup'):
                threading.Thread(target=self._engine.warmup, daemon=True).start()
        elif engine_name == "whisper_remote":
            from .engines.whisper_remote_engine import WhisperRemoteEngine
            self._engine = WhisperRemoteEngine(
                server_url=config.get("engine.whisper_remote.server_url", "http://localhost:8000"),
                model=config.get("engine.whisper_remote.model", "whisper-1"),
                api_key=config.get("engine.whisper_remote.api_key", ""),
            )

    def _setup_hotkeys(self):
        """设置快捷键监听器"""
        # 语音模式快捷键
        self._hotkey_listener = HotkeyListener(
            hotkey=config.hotkey,
            on_press=self._voice_handler.on_hotkey_press,
            on_release=self._voice_handler.on_hotkey_release,
            hold_time=config.get("core.asr.hotkey_hold_time", 1.0),
        )

        # 音频电平回调
        self._recorder.set_audio_level_callback(
            lambda level: self._signals.audio_level.emit(level)
        )

        # AI 模式快捷键
        if config.get("core.ai.enabled", True):
            self._ai_hotkey_listener = HotkeyListener(
                hotkey=config.get("core.ai.hotkey", "shift"),
                on_press=self._ai_handler.on_hotkey_press,
                on_release=self._ai_handler.on_hotkey_release,
                hold_time=config.get("core.ai.hotkey_hold_time", 1.0),
            )
        else:
            self._ai_hotkey_listener = None

    def _setup_signals(self):
        """设置信号连接，将事件路由到对应的 handler"""
        # 共享信号 -> 浮窗
        self._signals.audio_level.connect(self._floating_window.update_audio_level)
        self._signals.partial_result.connect(self._floating_window.update_partial_result)

        # 语音模式信号 -> VoiceHandler
        self._signals.start_recording.connect(self._voice_handler.on_start_recording)
        self._signals.stop_recording.connect(self._voice_handler.on_stop_recording)
        self._signals.recognition_done.connect(self._on_voice_recognition_done)
        self._signals.recognition_error.connect(self._voice_handler.on_recognition_error)

        # AI 模式信号 -> AIHandler
        self._signals.ai_start_recording.connect(self._ai_handler.on_start_recording)
        self._signals.ai_stop_recording.connect(self._ai_handler.on_stop_recording)
        self._signals.ai_recognition_done.connect(self._ai_handler.on_recognition_done)

    def _on_voice_recognition_done(self, text: str):
        """语音识别完成的路由处理

        根据当前模式将结果路由到正确的 handler
        """
        # 检查是否是 AI 模式（通过检查 AI handler 的状态）
        if self._ai_handler._browser_open_time is not None:
            # AI 模式：转发到 AI handler
            self._ai_handler._browser_open_time = None  # Reset state
            self._signals.ai_recognition_done.emit(text)
        else:
            # 语音模式：直接处理
            self._voice_handler.on_recognition_done(text)

    def _setup_tray(self):
        """设置托盘图标"""
        self._tray.settings_clicked.connect(self._show_settings)
        self._tray.log_viewer_clicked.connect(self._show_log_viewer)
        self._tray.quit_clicked.connect(self._quit)

    def _show_settings(self):
        """显示设置对话框"""
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(config)
            self._settings_dialog.settings_changed.connect(self._on_settings_changed)
            self._settings_dialog.destroyed.connect(self._on_settings_dialog_closed)
        self._settings_dialog.show()
        self._settings_dialog.raise_()

    def _on_settings_dialog_closed(self):
        """设置对话框关闭时重置引用，以便下次用新语言重建"""
        self._settings_dialog = None

    def _show_log_viewer(self):
        """显示日志查看器"""
        if self._log_viewer is None:
            self._log_viewer = LogViewerDialog()
            self._log_viewer.destroyed.connect(self._on_log_viewer_closed)
        self._log_viewer.show()
        self._log_viewer.raise_()

    def _on_log_viewer_closed(self):
        """日志查看器关闭时重置引用"""
        self._log_viewer = None

    def _on_settings_changed(self):
        """设置变更处理"""
        try:
            # Reload config from file
            config.load()

            # Update engine
            self._setup_engine()

            # Update hotkey settings
            self._hotkey_listener.update_hotkey(config.hotkey)
            self._hotkey_listener.update_hold_time(config.get("core.asr.hotkey_hold_time", 1.0))

            # Update AI hotkey settings
            if self._ai_hotkey_listener:
                self._ai_hotkey_listener.update_hotkey(config.get("core.ai.hotkey", "shift"))
                self._ai_hotkey_listener.update_hold_time(config.get("core.ai.hotkey_hold_time", 1.0))

            # Update audio device and gain
            self._recorder.set_device(config.get("core.asr.audio_device"))
            self._recorder.set_gain(config.get("core.asr.audio_gain", 1.0))

            # Update sound notification setting
            set_sound_enabled(config.get("core.asr.sound_notification", True))

            logger.info("Settings updated successfully")
        except Exception as e:
            logger.error(f"Error updating settings: {e}", exc_info=True)

    def _quit(self):
        """退出应用"""
        self._hotkey_listener.stop()
        if self._ai_hotkey_listener:
            self._ai_hotkey_listener.stop()
        self._recorder.close()
        self._tray.hide()
        self._app.quit()

    def run(self):
        """运行应用"""
        logger.info(f"Speaky starting with hotkey: {config.hotkey}")
        if config.get("core.ai.enabled", True):
            logger.info(f"AI hotkey: {config.get('core.ai.hotkey', 'shift')}, URL: {config.get('core.ai.url', 'https://chatgpt.com')}")
        logger.info(f"Engine: {config.engine}, Language: {config.language}")

        self._tray.show()
        self._tray.show_message(
            t("app_name"),
            t("started_message", hotkey=config.hotkey.upper())
        )

        self._hotkey_listener.start()
        if self._ai_hotkey_listener:
            self._ai_hotkey_listener.start()
            logger.info("AI hotkey listener started")
        logger.info("Hotkey listener started")

        return self._app.exec()


def main():
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
