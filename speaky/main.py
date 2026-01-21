import faulthandler
import logging
import os
import platform
import signal
import sys
import threading
from typing import Optional

# 在导入任何 X11 相关库之前，初始化 X11 多线程支持
# 这是为了避免 pynput (Xlib) 和 Qt (X11) 多线程冲突导致的 Segmentation fault
if platform.system() == "Linux":
    try:
        import ctypes
        x11 = ctypes.CDLL("libX11.so.6")
        x11.XInitThreads()
    except Exception:
        pass  # 如果失败，继续运行

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QTimer

from .paths import get_log_path, get_user_data_path
from .config import config
from .audio import AudioRecorder
from .hotkey import HotkeyListener
from .input_method import check_macos_accessibility, open_macos_accessibility_settings
from .engines.base import BaseEngine
from .ui.floating_window import FloatingWindow
from .ui.tray_icon import TrayIcon
from .ui.settings_dialog import SettingsDialog, apply_theme
from .i18n import t, i18n
from .handlers import VoiceModeHandler, AIModeHandler
from .handlers.llm_agent import LLMAgentHandler
from .llm import AgentContent
from .sound import set_sound_enabled

# Setup logging - both console and file
log_dir = get_log_path()
log_file = log_dir / "speaky.log"

# Create handlers - 在 Windows GUI 模式下 sys.stderr 可能为 None
handlers = []
file_handler = logging.FileHandler(str(log_file), encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
handlers.append(file_handler)

# 只有在 stdout/stderr 可用时才添加 console handler
if sys.stderr is not None:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(formatter)
    handlers.append(console_handler)

# Create formatters
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Setup root logger
logging.basicConfig(
    level=logging.DEBUG,
    handlers=handlers
)
logger = logging.getLogger(__name__)
logger.info(f"Log file: {log_file}")

# Enable faulthandler to dump traceback on segfault (写入日志文件而非 stderr)
try:
    faulthandler.enable(file=open(str(log_dir / "crash.log"), "w"))
except Exception:
    pass  # 如果失败，继续运行

# Global exception handler
def global_exception_handler(exctype, value, tb):
    import traceback
    logger.error("Uncaught exception:")
    logger.error(''.join(traceback.format_exception(exctype, value, tb)))
    # 只有在 stderr 可用时才调用默认处理器
    if sys.stderr is not None:
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
    ai_do_input = Signal(str)

    # LLM Agent 信号
    agent_content = Signal(AgentContent)
    schedule_hide = Signal(int)  # delay_ms

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

        # 初始化 LLM Agent 处理器
        self._llm_agent_handler = LLMAgentHandler(
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

        # 预初始化 LLM Agent（后台线程，加载 MCP 工具）
        self._llm_agent_handler.initialize_async()

    def _setup_engine(self):
        """初始化语音识别引擎"""
        engine_name = config.engine
        logger.info(f"Setting up engine: {engine_name}")

        if engine_name == "local":
            from .engines.whisper_engine import WhisperEngine
            self._engine = WhisperEngine(
                model_name=config.get("engine.local.model", "base"),
                device=config.get("engine.local.device", "auto"),
                compute_type=config.get("engine.local.compute_type", "auto"),
            )
            # 预加载模型，避免第一次识别时卡顿
            if self._engine.is_model_downloaded():
                threading.Thread(target=self._engine.preload, daemon=True).start()
            else:
                logger.warning(f"[Local] 模型未下载，请先在设置中下载模型")
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
            )
            # Pre-warm connection for faster first request
            if hasattr(self._engine, 'warmup'):
                threading.Thread(target=self._engine.warmup, daemon=True).start()

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

        # LLM Agent 快捷键
        if config.get("llm_agent.enabled", False):
            self._llm_agent_hotkey_listener = HotkeyListener(
                hotkey=config.get("llm_agent.hotkey", "tab"),
                on_press=self._llm_agent_handler.on_hotkey_press,
                on_release=self._llm_agent_handler.on_hotkey_release,
                hold_time=config.get("llm_agent.hotkey_hold_time", 0.5),
            )
        else:
            self._llm_agent_hotkey_listener = None

    def _setup_signals(self):
        """设置信号连接，将事件路由到对应的 handler"""
        # 共享信号 -> 浮窗
        self._signals.audio_level.connect(self._floating_window.update_audio_level)
        self._signals.partial_result.connect(self._floating_window.update_partial_result)

        # LLM Agent 信号 -> 浮窗
        self._signals.agent_content.connect(self._floating_window.set_agent_content)
        self._signals.schedule_hide.connect(self._schedule_hide_window)

        # 语音模式信号 -> VoiceHandler
        self._signals.start_recording.connect(self._voice_handler.on_start_recording)
        self._signals.stop_recording.connect(self._voice_handler.on_stop_recording)
        self._signals.recognition_done.connect(self._on_voice_recognition_done)
        self._signals.recognition_error.connect(self._voice_handler.on_recognition_error)

        # AI 模式信号 -> AIHandler
        self._signals.ai_start_recording.connect(self._ai_handler.on_start_recording)
        self._signals.ai_stop_recording.connect(self._ai_handler.on_stop_recording)
        self._signals.ai_recognition_done.connect(self._ai_handler.on_recognition_done)
        self._signals.ai_do_input.connect(self._ai_handler._do_input)

    def _on_voice_recognition_done(self, text: str):
        """语音识别完成的路由处理

        根据当前模式将结果路由到正确的 handler
        """
        # 检查是否是 AI 模式（通过检查 AI handler 的状态）
        if self._ai_handler._browser_open_time is not None:
            # AI 模式：转发到 AI handler（不要在这里重置 _browser_open_time）
            self._signals.ai_recognition_done.emit(text)
        else:
            # 语音模式：直接处理
            self._voice_handler.on_recognition_done(text)

    def _schedule_hide_window(self, delay_ms: int):
        """Schedule window hide after delay (called on main thread via signal)"""
        QTimer.singleShot(delay_ms, self._floating_window.hide)

    def _setup_tray(self):
        """设置托盘图标"""
        self._tray.settings_clicked.connect(self._show_settings)
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

            # Update LLM Agent hotkey settings
            if config.get("llm_agent.enabled", False):
                if self._llm_agent_hotkey_listener:
                    self._llm_agent_hotkey_listener.update_hotkey(config.get("llm_agent.hotkey", "tab"))
                    self._llm_agent_hotkey_listener.update_hold_time(config.get("llm_agent.hotkey_hold_time", 0.5))
                else:
                    # Create new listener if it wasn't enabled before
                    self._llm_agent_hotkey_listener = HotkeyListener(
                        hotkey=config.get("llm_agent.hotkey", "tab"),
                        on_press=self._llm_agent_handler.on_hotkey_press,
                        on_release=self._llm_agent_handler.on_hotkey_release,
                        hold_time=config.get("llm_agent.hotkey_hold_time", 0.5),
                    )
                    self._llm_agent_hotkey_listener.start()
            else:
                # Stop listener if it was enabled before
                if self._llm_agent_hotkey_listener:
                    self._llm_agent_hotkey_listener.stop()
                    self._llm_agent_hotkey_listener = None

            # Reset LLM Agent handler when settings change
            self._llm_agent_handler.reset()

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
        if self._llm_agent_hotkey_listener:
            self._llm_agent_hotkey_listener.stop()
        self._recorder.close()
        self._tray.hide()
        self._app.quit()

    def run(self):
        """运行应用"""
        logger.info(f"Speaky starting with hotkey: {config.hotkey}")
        if config.get("core.ai.enabled", True):
            logger.info(f"AI hotkey: {config.get('core.ai.hotkey', 'shift')}, URL: {config.get('core.ai.url', 'https://chatgpt.com')}")
        logger.info(f"Engine: {config.engine}, Language: {config.language}")

        # Setup signal handler for graceful shutdown with Ctrl+C
        def signal_handler(signum, frame):
            logger.info("Received SIGINT, shutting down...")
            self._quit()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Qt event loop blocks Python signal handling, so we need a timer
        # to periodically give Python a chance to process signals
        signal_timer = QTimer()
        signal_timer.timeout.connect(lambda: None)  # No-op, just lets Python run
        signal_timer.start(500)  # Check every 500ms

        self._tray.show()
        self._tray.show_message(
            t("app_name"),
            t("started_message", hotkey=config.hotkey.upper())
        )

        self._hotkey_listener.start()
        if self._ai_hotkey_listener:
            self._ai_hotkey_listener.start()
            logger.info("AI hotkey listener started")
        if self._llm_agent_hotkey_listener:
            self._llm_agent_hotkey_listener.start()
            logger.info(f"LLM Agent hotkey listener started (hotkey: {config.get('llm_agent.hotkey', 'tab')})")
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
