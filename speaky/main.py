import logging
import platform
import sys
import threading
import time
from typing import Optional

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QObject, Signal, QTimer

from .config import config
from .audio import AudioRecorder
from .hotkey import HotkeyListener
from .input_method import input_method, check_macos_accessibility, open_macos_accessibility_settings
from .engines.base import BaseEngine
from .ui.floating_window import FloatingWindow
from .ui.tray_icon import TrayIcon
from .ui.settings_dialog import SettingsDialog, apply_theme
from .i18n import t, i18n

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


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
    start_recording = Signal()
    stop_recording = Signal()
    audio_level = Signal(float)
    recognition_done = Signal(str)
    recognition_error = Signal(str)
    partial_result = Signal(str)  # For streaming ASR
    # AI key signals
    ai_start_recording = Signal()
    ai_stop_recording = Signal()
    ai_recognition_done = Signal(str)


class SpeakyApp:
    def __init__(self):
        self._app = QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # Set macOS to accessory mode - won't appear in Dock or steal focus
        set_macos_accessory_mode()

        # Initialize i18n language from config
        i18n.set_language(config.get("ui_language", "auto"))

        # Apply theme from config
        apply_theme(config.get("ui.theme", "auto"))

        self._signals = SignalBridge()
        self._recorder = AudioRecorder()
        self._engine: Optional[BaseEngine] = None
        self._floating_window = FloatingWindow()
        self._tray = TrayIcon()
        self._settings_dialog: Optional[SettingsDialog] = None
        self._realtime_session = None  # For real-time streaming ASR

        self._ai_mode = False  # Track if we're in AI mode
        self._ai_raise_timer = None  # Timer to keep floating window on top
        self._setup_engine()
        self._setup_hotkey()
        self._setup_ai_hotkey()
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
            # Pre-warm connection for faster first request
            if hasattr(self._engine, 'warmup'):
                threading.Thread(target=self._engine.warmup, daemon=True).start()
        elif engine_name == "aliyun":
            from .engines.aliyun_engine import AliyunEngine
            self._engine = AliyunEngine(
                app_key=config.get("aliyun.app_key", ""),
                access_token=config.get("aliyun.access_token", ""),
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

    def _setup_ai_hotkey(self):
        """Setup AI hotkey listener"""
        if not config.get("ai_enabled", True):
            self._ai_hotkey_listener = None
            return
        self._ai_hotkey_listener = HotkeyListener(
            hotkey=config.get("ai_hotkey", "shift"),
            on_press=self._on_ai_hotkey_press,
            on_release=self._on_ai_hotkey_release,
            hold_time=config.get("ai_hotkey_hold_time", 1.0),
        )

    def _setup_signals(self):
        self._signals.start_recording.connect(self._on_start_recording)
        self._signals.stop_recording.connect(self._on_stop_recording)
        self._signals.audio_level.connect(self._floating_window.update_audio_level)
        self._signals.recognition_done.connect(self._on_recognition_done)
        self._signals.recognition_error.connect(self._on_recognition_error)
        self._signals.partial_result.connect(self._floating_window.update_partial_result)
        # AI key signals
        self._signals.ai_start_recording.connect(self._on_ai_start_recording)
        self._signals.ai_stop_recording.connect(self._on_ai_stop_recording)
        self._signals.ai_recognition_done.connect(self._on_ai_recognition_done)

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

        # Check if we should use real-time streaming
        streaming_enabled = config.get("ui.streaming_mode", True)
        use_realtime = (
            streaming_enabled
            and self._engine is not None
            and self._engine.supports_realtime_streaming()
        )

        if use_realtime:
            logger.info("Using real-time streaming ASR")
            # Track if final result was received via callback
            self._realtime_final_received = False

            def on_final_callback(text):
                self._realtime_final_received = True
                logger.info(f"on_final callback: {text}")
                self._signals.recognition_done.emit(text)

            # Create and start real-time session
            self._realtime_session = self._engine.create_realtime_session(
                language=config.language,
                on_partial=lambda text: self._signals.partial_result.emit(text),
                on_final=on_final_callback,
                on_error=lambda err: self._signals.recognition_error.emit(err),
            )
            self._realtime_session.start()

            # Set up audio data callback to feed real-time session
            def on_audio_data(data: bytes):
                if self._realtime_session:
                    self._realtime_session.send_audio(data)

            self._recorder.set_audio_data_callback(on_audio_data)
        else:
            # Non-streaming mode - no audio callback needed
            self._recorder.set_audio_data_callback(None)

        self._recorder.start()

    def _on_stop_recording(self):
        logger.info("Stopping recording")
        audio_data = self._recorder.stop()

        # Clear audio data callback
        self._recorder.set_audio_data_callback(None)

        # Check if we were using real-time streaming
        if self._realtime_session is not None:
            logger.info("Finishing real-time streaming session")
            self._floating_window.show_recognizing()

            # Capture session reference before starting thread
            session = self._realtime_session
            self._realtime_session = None

            def finish_realtime(sess):
                try:
                    if sess is None:
                        logger.warning("Real-time session is None")
                        if not self._realtime_final_received:
                            self._signals.recognition_error.emit(t("empty_result"))
                        return

                    # Add timeout wrapper for finish
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(sess.finish)
                        try:
                            result = future.result(timeout=5)  # 5 second timeout
                        except concurrent.futures.TimeoutError:
                            logger.error("Real-time finish timed out")
                            sess.cancel()
                            if not self._realtime_final_received:
                                self._signals.recognition_error.emit("识别超时")
                            return

                    # Only emit if on_final callback wasn't called
                    if not self._realtime_final_received:
                        if result:
                            logger.info(f"Real-time result from finish: {result}")
                            self._signals.recognition_done.emit(result)
                        else:
                            logger.warning("Real-time result is empty")
                            self._signals.recognition_error.emit(t("empty_result"))
                    else:
                        logger.info("Final result already received via callback")
                except Exception as e:
                    logger.error(f"Real-time finish error: {e}", exc_info=True)
                    if not self._realtime_final_received:
                        self._signals.recognition_error.emit(str(e))

            threading.Thread(target=finish_realtime, args=(session,), daemon=True).start()
            return

        # Non-streaming mode
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

                streaming_enabled = config.get("ui.streaming_mode", True)
                logger.info(f"Transcribing with engine: {self._engine.name}, streaming={streaming_enabled}")

                # Use streaming API if engine supports it and streaming is enabled
                if streaming_enabled and self._engine.supports_streaming():
                    def on_partial(partial_text: str):
                        self._signals.partial_result.emit(partial_text)

                    text = self._engine.transcribe_streaming(
                        audio_data, config.language, on_partial=on_partial
                    )
                else:
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
        logger.info(f"_on_recognition_done called, ai_mode={self._ai_mode}, text={text[:50] if text else 'None'}...")
        self._floating_window.show_result(text)
        # Check if we're in AI mode
        if self._ai_mode:
            logger.info("AI mode: Emitting ai_recognition_done signal")
            self._ai_mode = False
            self._signals.ai_recognition_done.emit(text)
        else:
            logger.info("Normal mode: Scheduling type_text")
            QTimer.singleShot(100, lambda: input_method.type_text(text))

    def _on_recognition_error(self, error: str):
        self._floating_window.show_error(error)
        self._ai_mode = False  # Reset AI mode on error

    # AI key handlers
    def _on_ai_hotkey_press(self):
        """AI 键按下：发送信号到主线程处理"""
        logger.info("AI hotkey pressed - emitting signal")
        self._signals.ai_start_recording.emit()

    def _on_ai_start_recording(self):
        """AI 键按下处理（在 Qt 主线程中执行）

        设计要点：
        1. 先显示浮窗并开始录音（确保用户看到反馈）
        2. 延迟 300ms 后打开浏览器（让浮窗先稳定显示）
        3. 启动定时 raise，确保浮窗始终在浏览器之上
        """
        try:
            logger.info("AI mode: Starting recording in main thread")

            self._ai_mode = True
            self._ai_browser_open_time = time.time()

            # 1. 先开始录音（会显示浮窗和设置流式回调）
            self._on_start_recording()

            # 2. 启动定时 raise，确保浮窗始终在最前面
            self._start_ai_raise_timer()

            # 3. 延迟打开浏览器（让浮窗先稳定显示）
            QTimer.singleShot(300, self._ai_open_browser)
        except Exception as e:
            logger.exception(f"AI mode: Exception in _on_ai_start_recording: {e}")

    def _ai_open_browser(self):
        """延迟打开浏览器"""
        try:
            import webbrowser
            ai_url = config.get("ai_url", "https://chatgpt.com")
            logger.info(f"AI mode: Opening {ai_url}")
            webbrowser.open(ai_url)
            # 打开浏览器后立即强制置顶浮窗
            QTimer.singleShot(200, self._floating_window.force_to_top)
            QTimer.singleShot(500, self._floating_window.force_to_top)
            QTimer.singleShot(1000, self._floating_window.force_to_top)
        except Exception as e:
            logger.exception(f"AI mode: Exception in _ai_open_browser: {e}")

    def _start_ai_raise_timer(self):
        """启动定时器，每 300ms raise 浮窗一次"""
        if self._ai_raise_timer is None:
            self._ai_raise_timer = QTimer()
            self._ai_raise_timer.timeout.connect(self._ai_raise_window)
            self._ai_raise_timer.start(300)  # 更频繁地 raise
            logger.info("AI mode: Started raise timer")

    def _ai_raise_window(self):
        """raise 浮窗确保在最前面"""
        try:
            if self._floating_window.isVisible():
                logger.debug("AI mode: Raising floating window")
                self._floating_window.force_to_top()
        except Exception as e:
            logger.exception(f"AI mode: Exception in _ai_raise_window: {e}")

    def _stop_ai_raise_timer(self):
        """停止 raise 定时器"""
        if self._ai_raise_timer:
            self._ai_raise_timer.stop()
            self._ai_raise_timer = None

    def _on_ai_hotkey_release(self):
        """AI 键松开：停止录音"""
        logger.info("AI hotkey released - stopping recording")
        self._stop_ai_raise_timer()  # 停止 raise 定时器
        self._signals.ai_stop_recording.emit()

    def _on_ai_stop_recording(self):
        """AI 模式停止录音"""
        try:
            logger.info("AI mode: _on_ai_stop_recording called")
            self._on_stop_recording()
            logger.info("AI mode: _on_stop_recording completed")
        except Exception as e:
            logger.exception(f"AI mode: Exception in _on_ai_stop_recording: {e}")

    def _on_ai_recognition_done(self, text: str):
        """识别完成：智能等待页面加载后输入

        等待策略：
        - 计算从打开浏览器到现在经过的时间
        - 确保至少等待 ai_page_load_delay 秒（默认3秒）
        - 如果识别耗时已经超过等待时间，则立即输入
        """
        try:
            logger.info(f"AI mode: _on_ai_recognition_done called with text: {text[:50] if text else 'None'}...")

            if not text or not text.strip():
                logger.warning("AI mode: Empty recognition result, skipping input")
                return

            page_load_delay = config.get("ai_page_load_delay", 3.0)
            elapsed = time.time() - getattr(self, '_ai_browser_open_time', time.time())
            remaining = max(0, page_load_delay - elapsed)

            logger.info(f"AI mode: Recognition done. Elapsed: {elapsed:.1f}s, waiting {remaining:.1f}s more before input")
            logger.info(f"AI mode: Text to input: {text}")

            # 等待剩余时间后输入
            QTimer.singleShot(int(remaining * 1000), lambda: self._ai_do_input(text))
        except Exception as e:
            logger.exception(f"AI mode: Exception in _on_ai_recognition_done: {e}")

    def _ai_do_input(self, text: str):
        """执行文字输入和回车"""
        try:
            logger.info(f"AI mode: _ai_do_input called with text: {text}")

            # 隐藏浮窗（输入前隐藏，避免遮挡）
            logger.info("AI mode: Hiding floating window")
            self._floating_window.hide()

            # 输入文字
            logger.info("AI mode: Calling input_method.type_text()")
            input_method.type_text(text)
            logger.info("AI mode: type_text completed")

            # 如果配置了自动回车，则发送
            if config.get("ai_auto_enter", True):
                logger.info("AI mode: Scheduling Enter key press")
                QTimer.singleShot(300, self._press_enter)
            else:
                logger.info("AI mode: Auto enter disabled, skipping Enter press")
        except Exception as e:
            logger.exception(f"AI mode: Exception in _ai_do_input: {e}")

    def _press_enter(self):
        """按回车键发送消息"""
        try:
            logger.info("AI mode: _press_enter called")
            from pynput.keyboard import Controller, Key
            keyboard = Controller()
            keyboard.press(Key.enter)
            keyboard.release(Key.enter)
            logger.info("AI mode: Enter pressed, message sent")
        except Exception as e:
            logger.exception(f"AI mode: Exception in _press_enter: {e}")

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
        # Update AI hotkey settings
        if self._ai_hotkey_listener:
            self._ai_hotkey_listener.update_hotkey(config.get("ai_hotkey", "shift"))
            self._ai_hotkey_listener.update_hold_time(config.get("ai_hotkey_hold_time", 1.0))
        # Reset settings dialog so it recreates with new language
        self._settings_dialog = None

    def _quit(self):
        self._hotkey_listener.stop()
        if self._ai_hotkey_listener:
            self._ai_hotkey_listener.stop()
        self._recorder.close()
        self._tray.hide()
        self._app.quit()

    def run(self):
        logger.info(f"Speaky starting with hotkey: {config.hotkey}")
        if config.get("ai_enabled", True):
            logger.info(f"AI hotkey: {config.get('ai_hotkey', 'shift')}, URL: {config.get('ai_url', 'https://chatgpt.com')}")
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
