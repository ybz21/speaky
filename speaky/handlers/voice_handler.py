"""Voice input mode handler"""

import logging
import time
import threading
from typing import Optional, Callable, TYPE_CHECKING

from .base import BaseModeHandler

if TYPE_CHECKING:
    from ..audio import AudioRecorder
    from ..engines.base import BaseEngine
    from ..ui.floating_window import FloatingWindow
    from PySide6.QtCore import QObject

logger = logging.getLogger(__name__)


class VoiceModeHandler(BaseModeHandler):
    """语音输入模式处理器

    处理普通语音输入：
    1. 按下快捷键 -> 保存焦点 -> 开始录音
    2. 松开快捷键 -> 停止录音 -> 识别
    3. 识别完成 -> 显示结果 -> 输入文本到原窗口
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

    def on_hotkey_press(self):
        """快捷键按下：保存焦点并开始录音"""
        logger.info("Voice hotkey pressed - starting recording")
        # Save current focus before showing floating window
        self._input_method.save_focus()
        self._signals.start_recording.emit()

    def on_hotkey_release(self):
        """快捷键松开：停止录音"""
        logger.info("Voice hotkey released - stopping recording")
        self._signals.stop_recording.emit()

    def on_start_recording(self):
        """开始录音（信号槽回调）"""
        self._start_recording()

    def on_stop_recording(self):
        """停止录音（信号槽回调）"""
        self._stop_recording()

    def on_recognition_done(self, text: str):
        """识别完成：显示结果并输入文本"""
        elapsed = time.time() - self._recording_start_time if self._recording_start_time else 0
        text_preview = text[:50] if text else 'None'
        text_len = len(text) if text else 0
        logger.info(f"[Voice] 识别完成，总耗时 {elapsed:.2f}s，文本长度={text_len}: {text_preview}...")

        # Save to history
        from ..history import add_to_history
        engine_name = self._engine.name if self._engine else ""
        add_to_history(text, engine_name)

        self._floating_window.show_result(text)

        # 在后台线程执行输入，避免阻塞主线程导致定时器延迟
        def do_type():
            time.sleep(0.1)  # 等待 100ms
            self._input_method.type_text(text)

        logger.info("[Voice] 100ms后输入文本")
        threading.Thread(target=do_type, daemon=True).start()

    def on_recognition_error(self, error: str):
        """识别错误：显示错误"""
        logger.info(f"[Voice] 识别错误: {error}")
        self._floating_window.show_error(error)
