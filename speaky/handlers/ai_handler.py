"""AI chat mode handler"""

import logging
import platform
import subprocess
import time
from typing import Optional, Callable, TYPE_CHECKING

from PySide6.QtCore import QTimer

from .base import BaseModeHandler

if TYPE_CHECKING:
    from ..audio import AudioRecorder
    from ..engines.base import BaseEngine
    from ..ui.floating_window import FloatingWindow
    from PySide6.QtCore import QObject

logger = logging.getLogger(__name__)


class AIModeHandler(BaseModeHandler):
    """AI 对话模式处理器

    处理 AI 模式语音输入：
    1. 按下快捷键 -> 开始录音 -> 打开浏览器 -> 保持浮窗置顶
    2. 松开快捷键 -> 停止录音 -> 识别
    3. 识别完成 -> 等待页面加载 -> 输入文本 -> 发送回车
    """

    def __init__(
        self,
        signals: "QObject",
        recorder: "AudioRecorder",
        engine_getter: Callable[[], Optional["BaseEngine"]],
        floating_window: "FloatingWindow",
        config,
    ):
        super().__init__(signals, recorder, engine_getter, floating_window, config)

        # Import here to avoid circular imports
        from ..input_method import input_method
        self._input_method = input_method

        # AI mode specific state
        self._raise_timer: Optional[QTimer] = None
        self._browser_open_time: Optional[float] = None

    def on_hotkey_press(self):
        """AI 快捷键按下：发送信号到主线程处理"""
        logger.info("AI hotkey pressed - emitting signal")
        self._signals.ai_start_recording.emit()

    def on_hotkey_release(self):
        """AI 快捷键松开：停止录音"""
        logger.info("AI hotkey released - stopping recording")
        # 通过信号在主线程停止，避免跨线程操作 Qt 对象
        self._signals.ai_stop_recording.emit()

    def on_start_recording(self):
        """AI 模式开始录音（在 Qt 主线程中执行）

        设计要点：
        1. 先显示浮窗并开始录音（确保用户看到反馈）
        2. 延迟 300ms 后打开浏览器（让浮窗先稳定显示）
        3. 启动定时 raise，确保浮窗始终在浏览器之上
        """
        try:
            logger.info("AI mode: Starting recording in main thread")

            self._browser_open_time = time.time()

            # 1. 先开始录音（会显示浮窗和设置流式回调）
            self._start_recording()

            # 2. 启动定时 raise，确保浮窗始终在最前面
            self._start_raise_timer()

            # 3. 延迟打开浏览器（让浮窗先稳定显示）
            QTimer.singleShot(300, self._open_browser)
        except Exception as e:
            logger.exception(f"AI mode: Exception in on_start_recording: {e}")

    def on_stop_recording(self):
        """AI 模式停止录音（在 Qt 主线程中执行）"""
        try:
            logger.info("AI mode: on_stop_recording called")
            # 先停止 raise timer（必须在主线程）
            self._stop_raise_timer()
            self._stop_recording()
            logger.info("AI mode: _stop_recording completed")
        except Exception as e:
            logger.exception(f"AI mode: Exception in on_stop_recording: {e}")

    def on_recognition_done(self, text: str):
        """识别完成：智能等待页面加载后输入

        等待策略：
        - 计算从打开浏览器到现在经过的时间
        - 确保至少等待 ai_page_load_delay 秒（默认3秒）
        - 如果识别耗时已经超过等待时间，则立即输入
        """
        try:
            elapsed = time.time() - self._recording_start_time if self._recording_start_time else 0
            text_preview = text[:50] if text else 'None'
            text_len = len(text) if text else 0
            logger.info(f"[AI] 识别完成，总耗时 {elapsed:.2f}s，文本长度={text_len}: {text_preview}...")

            # Save to history
            from ..history import add_to_history
            engine_name = self._engine.name if self._engine else ""
            add_to_history(text, engine_name)

            # 暂停 pynput 监听器，避免与 Qt X11 操作冲突
            from ..hotkey import pause_listener, resume_listener
            pause_listener()

            # AI 模式：显示结果（会自动在 500ms 后隐藏）
            self._floating_window.show_result(text)

            if not text or not text.strip():
                logger.warning("AI mode: Empty recognition result, skipping input")
                resume_listener()
                return

            page_load_delay = self._config.get("core.ai.page_load_delay", 3.0)
            browser_elapsed = time.time() - (self._browser_open_time or time.time())
            remaining = max(0, page_load_delay - browser_elapsed)

            logger.info(f"AI mode: Recognition done. Browser elapsed: {browser_elapsed:.1f}s, waiting {remaining:.1f}s more before input")
            logger.info(f"AI mode: Text to input: {text}")

            # 完全在后台线程执行，避免任何 Qt/X11 交互
            import threading
            import shutil
            def delayed_input():
                try:
                    time.sleep(remaining + 0.3)  # 等待页面加载 + 焦点转移

                    logger.info(f"AI mode: Executing input: {text[:50]}...")

                    # 先清空输入框（Ctrl+A 选中全部，然后粘贴会覆盖）
                    xdotool = shutil.which("xdotool")
                    if platform.system() == "Linux" and xdotool:
                        subprocess.run([xdotool, "key", "ctrl+a"], check=False, capture_output=True)
                        time.sleep(0.1)

                    self._input_method.type_text(text, restore_focus=False)
                    logger.info("AI mode: type_text completed")

                    if self._config.get("core.ai.auto_enter", True):
                        time.sleep(0.3)
                        self._press_enter()
                except Exception as e:
                    logger.exception(f"AI mode: Exception in delayed_input: {e}")
                finally:
                    # 重置状态并恢复 pynput 监听器
                    self._browser_open_time = None
                    resume_listener()

            threading.Thread(target=delayed_input, daemon=True).start()
        except Exception as e:
            logger.exception(f"AI mode: Exception in on_recognition_done: {e}")

    def on_recognition_error(self, error: str):
        """识别错误：显示错误"""
        logger.info(f"[AI] 识别错误: {error}")
        self._floating_window.show_error(error)

    def _open_browser(self):
        """延迟打开浏览器（使用 subprocess 避免 X11 冲突）"""
        try:
            ai_url = self._config.get("core.ai.url", "https://chatgpt.com")
            logger.info(f"AI mode: Opening {ai_url}")

            # 使用 subprocess 在后台打开浏览器，避免与 pynput 的 Xlib 冲突
            system = platform.system()
            if system == "Linux":
                subprocess.Popen(
                    ["xdg-open", ai_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif system == "Darwin":
                subprocess.Popen(
                    ["open", ai_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            elif system == "Windows":
                subprocess.Popen(
                    ["start", "", ai_url],
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            # 打开浏览器后立即强制置顶浮窗
            QTimer.singleShot(200, self._floating_window.force_to_top)
            QTimer.singleShot(500, self._floating_window.force_to_top)
            QTimer.singleShot(1000, self._floating_window.force_to_top)
        except Exception as e:
            logger.exception(f"AI mode: Exception in _open_browser: {e}")

    def _start_raise_timer(self):
        """启动定时器，每 300ms raise 浮窗一次"""
        if self._raise_timer is None:
            self._raise_timer = QTimer()
            self._raise_timer.timeout.connect(self._raise_window)
            self._raise_timer.start(300)
            logger.info("AI mode: Started raise timer")

    def _raise_window(self):
        """raise 浮窗确保在最前面"""
        try:
            if self._floating_window.isVisible():
                logger.debug("AI mode: Raising floating window")
                self._floating_window.force_to_top()
        except Exception as e:
            logger.exception(f"AI mode: Exception in _raise_window: {e}")

    def _stop_raise_timer(self):
        """停止 raise 定时器"""
        if self._raise_timer:
            self._raise_timer.stop()
            self._raise_timer = None

    def _do_input(self, text: str):
        """执行文字输入和回车（通过信号从主线程安全调用）"""
        try:
            logger.info(f"AI mode: _do_input called with text: {text}")

            # 在后台线程执行输入操作，避免阻塞主线程
            import threading
            def do_input_thread():
                try:
                    # 等待焦点转移到浏览器
                    time.sleep(0.5)

                    logger.info(f"AI mode: Executing input with text: {text[:50]}...")

                    # 输入文字（AI 模式不恢复焦点，保持在浏览器）
                    self._input_method.type_text(text, restore_focus=False)
                    logger.info("AI mode: type_text completed")

                    # 如果配置了自动回车，等待后按回车
                    if self._config.get("core.ai.auto_enter", True):
                        time.sleep(0.3)
                        self._press_enter()
                except Exception as e:
                    logger.exception(f"AI mode: Exception in do_input_thread: {e}")

            threading.Thread(target=do_input_thread, daemon=True).start()
        except Exception as e:
            logger.exception(f"AI mode: Exception in _do_input: {e}")

    def _press_enter(self):
        """按回车键发送消息"""
        try:
            logger.info("AI mode: _press_enter called")
            import shutil

            system = platform.system()
            if system == "Linux":
                # Linux: 使用 xdotool 避免 pynput X11 冲突
                xdotool = shutil.which("xdotool")
                if xdotool:
                    subprocess.run(
                        [xdotool, "key", "Return"],
                        check=False,
                        capture_output=True
                    )
                    logger.info("AI mode: Enter pressed via xdotool")
                else:
                    logger.warning("AI mode: xdotool not found, cannot press Enter")
            else:
                # macOS/Windows: 使用 pynput
                from pynput.keyboard import Controller, Key
                keyboard = Controller()
                keyboard.press(Key.enter)
                keyboard.release(Key.enter)
                logger.info("AI mode: Enter pressed via pynput")
        except Exception as e:
            logger.exception(f"AI mode: Exception in _press_enter: {e}")

    def _emit_recognition_done(self, text: str):
        """AI 模式使用 ai_recognition_done 信号"""
        # 注意：这里仍然发送通用信号，由 main.py 路由到正确的处理方法
        # 这样可以保持信号的一致性
        self._signals.recognition_done.emit(text)
