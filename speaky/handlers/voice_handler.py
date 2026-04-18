"""Voice input mode handler"""

import json
import logging
import re
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

LLM_POLISH_PROMPT = """你是语音转文字润色助手。请润色以下语音识别文本：
1. 修正错别字和同音字错误
2. 合并语音识别产生的错误断句（如"去。替换。现在。"应合并为"去替换现在"），重新合理分句
3. 去除口语冗余词（嗯、那个、就是说、这个等重复出现的）
4. 如果内容包含多个要点或任务，用分点列出使其更有条理
5. 保持原意，代码和英文专有名词不改
6. 直接输出润色后的文本，不要解释

原文：{text}"""


def clean_llm_output(raw: str) -> str:
    """清理 LLM 输出：去除 think 标签、引号包裹等"""
    # 去除 <think>...</think>（闭合的）
    text = re.sub(r'<think>[\s\S]*?</think>', '', raw).strip()
    # 去除未闭合的 <think>...（被截断时）
    text = re.sub(r'<think>[\s\S]*$', '', text).strip()
    # 去除可能的引号包裹
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    # 尝试从 JSON 提取（兼容某些模型）
    if text.startswith('{'):
        try:
            return json.loads(text).get("text", text)
        except (json.JSONDecodeError, AttributeError):
            pass
    return text


class VoiceModeHandler(BaseModeHandler):
    def __init__(self, signals, recorder, engine_getter, floating_window, config):
        super().__init__(signals, recorder, engine_getter, floating_window, config)
        from speaky.input_method import input_method
        self._input_method = input_method

    def on_hotkey_press(self):
        logger.info("Voice hotkey pressed")
        self._input_method.save_focus()
        self._signals.start_recording.emit()

    def on_hotkey_release(self):
        logger.info("Voice hotkey released")
        self._signals.stop_recording.emit()

    def _show_processing_state(self):
        from speaky.i18n import t
        if self._config.get("core.asr.llm_polish", False):
            self._floating_window.show_polishing(t("polishing"))
        else:
            self._floating_window.show_recognizing()

    def on_start_recording(self):
        self._start_recording()

    def on_stop_recording(self):
        self._stop_recording()

    def on_recognition_done(self, text: str):
        elapsed = time.time() - self._recording_start_time if self._recording_start_time else 0
        logger.info(f"[Voice] 识别完成 {elapsed:.2f}s len={len(text)}: {text[:50]}...")

        from speaky.history import add_to_history
        add_to_history(text, self._engine.name if self._engine else "")

        if self._config.get("core.asr.llm_polish", False):
            self._polish_and_type(text)
        else:
            self._show_and_type(text)

    def on_recognition_error(self, error: str):
        logger.info(f"[Voice] 识别错误: {error}")
        self._floating_window.show_error(error)

    def _show_and_type(self, text: str, polish_done: bool = False):
        """显示结果并输入文本（必须在主线程调用）"""
        if polish_done:
            from speaky.i18n import t
            self._floating_window.show_result(text, status_text=t("polish_done"))
        else:
            self._floating_window.show_result(text)

        def do_type():
            time.sleep(0.1)
            self._input_method.type_text(text)
        threading.Thread(target=do_type, daemon=True).start()

    def _polish_and_type(self, text: str):
        """后台润色，完成后通过信号回主线程"""
        def do_polish():
            try:
                from openai import OpenAI
                api_key = self._config.get("llm.openai.api_key", "")
                base_url = (self._config.get("llm.openai.base_url", "") or "https://api.openai.com/v1").strip()
                model = self._config.get("llm.openai.model", "") or "gpt-4o-mini"

                if not api_key:
                    logger.warning("[Voice] No API key, skip polish")
                    self._type_and_finish(text)
                    return

                client = OpenAI(api_key=api_key, base_url=base_url)
                stream = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": LLM_POLISH_PROMPT.format(text=text)}],
                    temperature=0.3,
                    max_tokens=len(text) * 5 + 500,
                    stream=True,
                )

                full = ""
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    full += delta
                    # 实时显示（过滤 think 标签）
                    if '<think>' in full and '</think>' not in full:
                        continue  # 还在思考中，不显示
                    cleaned = clean_llm_output(full)
                    if cleaned:
                        self._signals.partial_result.emit(cleaned)

                polished = clean_llm_output(full) or text
                logger.info(f"[Voice] 润色完成: {polished[:50]}...")

                from speaky.history import add_to_history
                add_to_history(polished, (self._engine.name if self._engine else "") + "+llm")

                self._type_and_finish(polished)
            except Exception as e:
                logger.error(f"[Voice] 润色失败: {e}", exc_info=True)
                self._type_and_finish(text)

        threading.Thread(target=do_polish, daemon=True).start()

    def _type_and_finish(self, text: str):
        """输入文本并通过信号让浮窗显示结果+自动隐藏（线程安全）"""
        # 用信号更新浮窗状态（跨线程安全）
        from speaky.i18n import t
        self._signals.partial_result.emit(t("polish_done") + "  " + text)
        # 输入文本
        time.sleep(0.1)
        self._input_method.type_text(text)
        # 通过信号让主线程隐藏窗口
        self._signals.schedule_hide.emit(1500)
