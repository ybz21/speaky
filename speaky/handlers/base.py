"""Base mode handler with shared recording logic"""

import logging
import time
import threading
from typing import Optional, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from ..audio import AudioRecorder
    from ..engines.base import BaseEngine
    from ..ui.floating_window import FloatingWindow
    from PySide6.QtCore import QObject

logger = logging.getLogger(__name__)


class BaseModeHandler:
    """模式处理器基类

    提供共享的录音逻辑和抽象接口。
    子类需要实现具体的事件处理方法。
    """

    def __init__(
        self,
        signals: "QObject",
        recorder: "AudioRecorder",
        engine_getter: Callable[[], Optional["BaseEngine"]],
        floating_window: "FloatingWindow",
        config,
    ):
        """初始化处理器

        Args:
            signals: Qt 信号桥接器
            recorder: 音频录音器
            engine_getter: 获取当前引擎的函数（支持动态切换）
            floating_window: 浮动窗口
            config: 配置对象
        """
        self._signals = signals
        self._recorder = recorder
        self._get_engine = engine_getter
        self._floating_window = floating_window
        self._config = config

        self._realtime_session = None
        self._recording_start_time: Optional[float] = None
        self._realtime_final_received = False
        self._first_partial_received = False

    @property
    def _engine(self) -> Optional["BaseEngine"]:
        """获取当前引擎"""
        return self._get_engine()

    def on_hotkey_press(self):
        """快捷键按下 - 子类实现"""
        raise NotImplementedError

    def on_hotkey_release(self):
        """快捷键释放 - 子类实现"""
        raise NotImplementedError

    def on_recognition_done(self, text: str):
        """识别完成 - 子类实现"""
        raise NotImplementedError

    def on_recognition_error(self, error: str):
        """识别错误 - 子类实现"""
        raise NotImplementedError

    def _start_recording(self):
        """开始录音（共享逻辑）"""
        self._recording_start_time = time.time()
        logger.info(f"[按键按下] 开始录音，显示浮窗")
        self._floating_window.show_recording()

        # Check if we should use real-time streaming
        streaming_enabled = self._config.get("ui.streaming_mode", True)
        use_realtime = (
            streaming_enabled
            and self._engine is not None
            and self._engine.supports_realtime_streaming()
        )

        if use_realtime:
            logger.info(f"[流式识别] 使用实时流式 ASR")
            self._realtime_final_received = False
            self._first_partial_received = False

            def on_partial_callback(text):
                if not self._first_partial_received:
                    self._first_partial_received = True
                    elapsed = time.time() - self._recording_start_time
                    logger.info(f"[首次识别结果] 耗时 {elapsed:.2f}s: {text[:30] if text else 'None'}...")
                self._signals.partial_result.emit(text)

            def on_final_callback(text):
                self._realtime_final_received = True
                elapsed = time.time() - self._recording_start_time
                logger.info(f"[最终识别结果] 耗时 {elapsed:.2f}s: {repr(text[:50]) if text else 'None'}")
                self._emit_recognition_done(text)

            # Create and start real-time session
            t0 = time.time()
            logger.info(f"[创建会话] 开始创建实时会话...")
            self._realtime_session = self._engine.create_realtime_session(
                language=self._config.language,
                on_partial=on_partial_callback,
                on_final=on_final_callback,
                on_error=lambda err: self._emit_recognition_error(err),
            )
            logger.info(f"[创建会话] 会话创建完成，耗时 {time.time()-t0:.3f}s")

            t0 = time.time()
            logger.info(f"[启动会话] 开始启动会话...")
            self._realtime_session.start()
            logger.info(f"[启动会话] 会话启动完成，耗时 {time.time()-t0:.3f}s")

            # Set up audio data callback to feed real-time session
            def on_audio_data(data: bytes):
                if self._realtime_session:
                    self._realtime_session.send_audio(data)

            self._recorder.set_audio_data_callback(on_audio_data)
        else:
            # Non-streaming mode - no audio callback needed
            self._recorder.set_audio_data_callback(None)

        self._recorder.start()
        logger.info(f"[录音开始] 录音器已启动，总初始化耗时 {time.time()-self._recording_start_time:.3f}s")

    def _stop_recording(self):
        """停止录音（共享逻辑）"""
        stop_time = time.time()
        elapsed = stop_time - self._recording_start_time if self._recording_start_time else 0
        logger.info(f"[按键松开] 停止录音，录音时长 {elapsed:.2f}s")
        audio_data = self._recorder.stop()

        # Clear audio data callback
        self._recorder.set_audio_data_callback(None)

        # Check if we were using real-time streaming
        if self._realtime_session is not None:
            logger.info("[流式识别] 结束流式会话")
            self._floating_window.show_recognizing()

            # Capture session reference before starting thread
            session = self._realtime_session
            self._realtime_session = None

            def finish_realtime(sess):
                try:
                    if sess is None:
                        logger.warning("[流式识别] 会话为空")
                        if not self._realtime_final_received:
                            self._emit_recognition_error(self._t("empty_result"))
                        return

                    # Add timeout wrapper for finish
                    import concurrent.futures
                    t0 = time.time()
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(sess.finish)
                        try:
                            result = future.result(timeout=5)  # 5 second timeout
                        except concurrent.futures.TimeoutError:
                            logger.error(f"[流式识别] 等待结果超时 (5s)")
                            sess.cancel()
                            if not self._realtime_final_received:
                                self._emit_recognition_error("识别超时")
                            return

                    # Only emit if on_final callback wasn't called
                    if not self._realtime_final_received:
                        if result:
                            logger.info(f"[流式识别] finish() 返回结果: {result[:50]}...")
                            self._emit_recognition_done(result)
                        else:
                            logger.warning("[流式识别] finish() 返回空结果")
                            self._emit_recognition_error(self._t("empty_result"))
                    else:
                        logger.info(f"[流式识别] 已通过回调收到结果，finish() 耗时 {time.time()-t0:.2f}s")
                except Exception as e:
                    logger.error(f"Real-time finish error: {e}", exc_info=True)
                    if not self._realtime_final_received:
                        self._emit_recognition_error(str(e))

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
                    self._emit_recognition_error(self._t("no_engine"))
                    return

                streaming_enabled = self._config.get("ui.streaming_mode", True)
                logger.info(f"Transcribing with engine: {self._engine.name}, streaming={streaming_enabled}")

                # Use streaming API if engine supports it and streaming is enabled
                if streaming_enabled and self._engine.supports_streaming():
                    def on_partial(partial_text: str):
                        self._signals.partial_result.emit(partial_text)

                    text = self._engine.transcribe_streaming(
                        audio_data, self._config.language, on_partial=on_partial
                    )
                else:
                    text = self._engine.transcribe(audio_data, self._config.language)

                if text:
                    logger.info(f"Recognition result: {text}")
                    self._emit_recognition_done(text)
                else:
                    logger.warning("Recognition result is empty")
                    self._emit_recognition_error(self._t("empty_result"))
            except Exception as e:
                logger.error(f"Recognition error: {e}", exc_info=True)
                self._emit_recognition_error(str(e))

        threading.Thread(target=recognize, daemon=True).start()

    def _emit_recognition_done(self, text: str):
        """发送识别完成信号 - 子类可重写以使用不同信号"""
        self._signals.recognition_done.emit(text)

    def _emit_recognition_error(self, error: str):
        """发送识别错误信号 - 子类可重写以使用不同信号"""
        self._signals.recognition_error.emit(error)

    def _t(self, key: str) -> str:
        """获取翻译文本"""
        from ..i18n import t
        return t(key)
