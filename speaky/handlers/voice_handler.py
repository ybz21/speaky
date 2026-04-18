"""Voice input mode handler"""

import logging
import time
import threading
from typing import Optional, Callable, TYPE_CHECKING

from speaky.handlers.base import BaseModeHandler

if TYPE_CHECKING:
    from speaky.audio import AudioRecorder
    from speaky.engines.base import BaseEngine
    from speaky.ui.floating_window import FloatingWindow
    from PySide6.QtCore import QObject

logger = logging.getLogger(__name__)

LLM_POLISH_PROMPT = """请润色以下语音识别的文本，使其更通顺、准确。要求：
1. 修正明显的语音识别错误
2. 添加适当的标点符号
3. 保持原意不变，不要添加或删除内容
4. 直接输出润色后的文本，不要有任何解释或前缀

原文：
{text}"""


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
        from speaky.input_method import input_method
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
        from speaky.history import add_to_history
        engine_name = self._engine.name if self._engine else ""
        add_to_history(text, engine_name)

        # 检查是否启用 LLM 润色
        if self._config.get("core.asr.llm_polish", False):
            self._polish_and_input(text)
        else:
            self._finish_input(text)

    def _finish_input(self, text: str):
        """显示结果并输入文本"""
        self._floating_window.show_result(text)

        def do_type():
            time.sleep(0.1)
            self._input_method.type_text(text)

        logger.info("[Voice] 100ms后输入文本")
        threading.Thread(target=do_type, daemon=True).start()

    def _polish_and_input(self, text: str):
        """通过 LLM 润色文本后再输入"""
        from speaky.i18n import t
        self._floating_window.show_recognizing()
        self._floating_window.update_partial_result(t("polishing"))

        def do_polish():
            try:
                from openai import OpenAI
                api_key = self._config.get("llm.openai.api_key", "")
                base_url = (self._config.get("llm.openai.base_url", "") or "https://api.openai.com/v1").strip()
                model = self._config.get("llm.openai.model", "") or "gpt-4o-mini"

                if not api_key:
                    logger.warning("[Voice] LLM polish enabled but no API key, skipping")
                    self._do_finish_input(text)
                    return

                client = OpenAI(api_key=api_key, base_url=base_url)
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": LLM_POLISH_PROMPT.format(text=text)}],
                    temperature=0.3,
                    max_tokens=len(text) * 3 + 100,
                )
                polished = response.choices[0].message.content.strip()
                logger.info(f"[Voice] LLM 润色完成: {polished[:50]}...")

                # 用润色后的文本完成输入（通过信号回到主线程）
                from speaky.history import add_to_history
                engine_name = self._engine.name if self._engine else ""
                add_to_history(polished, engine_name + "+llm")
                self._do_finish_input(polished)
            except Exception as e:
                logger.error(f"[Voice] LLM 润色失败: {e}", exc_info=True)
                # 润色失败，使用原始文本
                self._do_finish_input(text)

        threading.Thread(target=do_polish, daemon=True).start()

    def _do_finish_input(self, text: str):
        """在后台线程中完成输入（线程安全）"""
        # 使用 partial_result 信号更新 UI（回到主线程）
        self._signals.partial_result.emit(text)
        self._floating_window.show_result(text)

        def do_type():
            time.sleep(0.1)
            self._input_method.type_text(text)

        threading.Thread(target=do_type, daemon=True).start()

    def on_recognition_error(self, error: str):
        """识别错误：显示错误"""
        logger.info(f"[Voice] 识别错误: {error}")
        self._floating_window.show_error(error)
