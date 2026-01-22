"""LLM Agent Handler for voice-controlled AI assistant."""

import asyncio
import logging
import threading
import time
from typing import Optional

from speaky.llm import LLMClient, AgentStatus, AgentContent, ToolCall

logger = logging.getLogger(__name__)


class LLMAgentHandler:
    """Handler for LLM Agent mode.

    Processes voice input through:
    1. Speech recognition (ASR) - reuses streaming recognition from voice mode
    2. LLM understanding with MCP tools
    3. Display results in floating window
    """

    def __init__(self, signals, recorder, engine_getter, floating_window, config):
        """Initialize the handler.

        Args:
            signals: Qt signal bridge for cross-thread communication
            recorder: Audio recorder instance
            engine_getter: Callable that returns the ASR engine
            floating_window: Floating window for display
            config: Application configuration
        """
        self._signals = signals
        self._recorder = recorder
        self._engine_getter = engine_getter
        self._floating_window = floating_window
        self._config = config

        self._llm_client: Optional[LLMClient] = None
        self._is_recording = False
        self._initialized = False
        self._init_lock = threading.Lock()

        # Streaming recognition state
        self._realtime_session = None
        self._realtime_final_received = False
        self._recording_start_time = None

    async def _ensure_initialized(self):
        """Ensure LLM client is initialized (lazy initialization)."""
        if self._initialized:
            return

        with self._init_lock:
            if self._initialized:
                return

            llm_config = self._config.get("llm", {})
            mcp_config = self._config.get("mcp", {}).get("servers", {})

            self._llm_client = LLMClient(llm_config)
            await self._llm_client.initialize(mcp_config)
            self._initialized = True
            logger.info("LLM Agent Handler initialized")

    def initialize_async(self):
        """Initialize LLM agent in background thread (call at startup).

        This pre-initializes:
        1. LLM client (OpenAI compatible)
        2. MCP servers (playwright, filesystem, fetch)
        3. LangGraph agent with tools bound
        """
        if not self._config.get("llm_agent.enabled", False):
            logger.info("[LLM Agent] Disabled, skipping pre-initialization")
            return

        def init_worker():
            try:
                logger.info("[LLM Agent] ===== Starting pre-initialization =====")
                asyncio.run(self._ensure_initialized())

                # Log summary
                if self._llm_client and self._initialized:
                    tool_names = self._llm_client.get_tool_names()
                    logger.info(f"[LLM Agent] ===== Ready! {len(tool_names)} tools bound =====")
                else:
                    logger.warning("[LLM Agent] Pre-initialization incomplete")
            except Exception as e:
                logger.error(f"[LLM Agent] Pre-initialization failed: {e}", exc_info=True)

        threading.Thread(target=init_worker, daemon=True).start()
        logger.info("[LLM Agent] Pre-initialization started in background thread")

    def on_hotkey_press(self):
        """Handle hotkey press - start recording with streaming recognition."""
        if not self._config.get("llm_agent.enabled", False):
            return

        self._is_recording = True
        self._recording_start_time = time.time()

        # Update status via signal (will show window on main thread)
        content = AgentContent(status=AgentStatus.LISTENING)
        self._signals.agent_content.emit(content)

        # Play start sound
        from speaky.sound import play_start_sound
        play_start_sound()

        # Get engine and check streaming support
        engine = self._engine_getter()
        streaming_enabled = self._config.get("core.asr.streaming_mode", True)
        use_realtime = (
            streaming_enabled
            and engine is not None
            and engine.supports_realtime_streaming()
        )

        if use_realtime:
            logger.info("[LLM Agent] 使用实时流式 ASR")
            self._realtime_final_received = False

            def on_partial_callback(text):
                # Update partial result in floating window
                self._signals.partial_result.emit(text)

            def on_final_callback(text):
                self._realtime_final_received = True
                elapsed = time.time() - self._recording_start_time if self._recording_start_time else 0
                logger.info(f"[LLM Agent] 最终识别结果: {text[:50] if text else 'None'}... (耗时 {elapsed:.2f}s)")
                # Process with LLM
                self._on_recognition_done(text)

            def on_error_callback(error):
                logger.error(f"[LLM Agent] 识别错误: {error}")
                content = AgentContent(status=AgentStatus.ERROR, error=str(error))
                self._signals.agent_content.emit(content)
                self._schedule_hide_window(2000)

            # Create and start real-time session
            self._realtime_session = engine.create_realtime_session(
                language=self._config.get("core.asr.language", "zh"),
                on_partial=on_partial_callback,
                on_final=on_final_callback,
                on_error=on_error_callback,
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
        logger.info("[LLM Agent] 开始录音")

    def on_hotkey_release(self):
        """Handle hotkey release - stop recording and process."""
        if not self._is_recording:
            return

        self._is_recording = False
        audio_data = self._recorder.stop()
        logger.info("[LLM Agent] 停止录音")

        # Check if silent
        is_silent = self._recorder.is_silent()
        if is_silent:
            logger.warning("[LLM Agent] 未检测到声音")
            # Cancel realtime session if exists
            if self._realtime_session is not None:
                try:
                    self._realtime_session.cancel()
                except Exception as e:
                    logger.error(f"取消实时会话失败: {e}")
                self._realtime_session = None
            self._recorder.set_audio_data_callback(None)
            content = AgentContent(status=AgentStatus.ERROR, error="未检测到声音")
            self._signals.agent_content.emit(content)
            self._schedule_hide_window(2000)
            return

        # Clear audio data callback
        self._recorder.set_audio_data_callback(None)

        # Check if we were using real-time streaming
        if self._realtime_session is not None:
            logger.info("[LLM Agent] 结束流式会话")
            # Update status to recognizing
            content = AgentContent(status=AgentStatus.RECOGNIZING)
            self._signals.agent_content.emit(content)

            # Capture session reference before starting thread
            session = self._realtime_session
            self._realtime_session = None

            def finish_realtime(sess):
                try:
                    if sess is None:
                        if not self._realtime_final_received:
                            content = AgentContent(status=AgentStatus.ERROR, error="识别会话为空")
                            self._signals.agent_content.emit(content)
                            self._schedule_hide_window(2000)
                        return

                    # Add timeout wrapper for finish
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(sess.finish)
                        try:
                            result = future.result(timeout=5)
                        except concurrent.futures.TimeoutError:
                            logger.error("[LLM Agent] 等待结果超时")
                            sess.cancel()
                            if not self._realtime_final_received:
                                content = AgentContent(status=AgentStatus.ERROR, error="识别超时")
                                self._signals.agent_content.emit(content)
                                self._schedule_hide_window(2000)
                            return

                    # Only process if on_final callback wasn't called
                    if not self._realtime_final_received:
                        if result:
                            logger.info(f"[LLM Agent] finish() 返回结果: {result[:50]}...")
                            self._on_recognition_done(result)
                        else:
                            content = AgentContent(status=AgentStatus.ERROR, error="识别结果为空")
                            self._signals.agent_content.emit(content)
                            self._schedule_hide_window(2000)
                except Exception as e:
                    logger.error(f"[LLM Agent] finish error: {e}", exc_info=True)
                    if not self._realtime_final_received:
                        content = AgentContent(status=AgentStatus.ERROR, error=str(e))
                        self._signals.agent_content.emit(content)
                        self._schedule_hide_window(2000)

            threading.Thread(target=finish_realtime, args=(session,), daemon=True).start()
            return

        # Non-streaming mode fallback
        if not audio_data:
            content = AgentContent(status=AgentStatus.ERROR, error="无录音数据")
            self._signals.agent_content.emit(content)
            self._schedule_hide_window(2000)
            return

        # Process in background thread (non-streaming)
        threading.Thread(
            target=self._process_audio_nonstreaming,
            args=(audio_data,),
            daemon=True,
        ).start()

    def _process_audio_nonstreaming(self, audio_data):
        """Process audio with non-streaming ASR (fallback).

        Args:
            audio_data: Recorded audio data
        """
        try:
            # Update status to recognizing
            content = AgentContent(status=AgentStatus.RECOGNIZING)
            self._signals.agent_content.emit(content)

            # Speech recognition
            engine = self._engine_getter()
            if engine is None:
                raise RuntimeError("ASR engine not available")

            language = self._config.get("core.asr.language", "zh")
            text = engine.transcribe(audio_data, language)

            if not text or not text.strip():
                content = AgentContent(status=AgentStatus.ERROR, error="识别结果为空")
                self._signals.agent_content.emit(content)
                self._schedule_hide_window(2000)
                return

            logger.info(f"[LLM Agent] 识别结果: {text}")
            self._on_recognition_done(text)

        except Exception as e:
            logger.error(f"[LLM Agent] 识别错误: {e}", exc_info=True)
            content = AgentContent(status=AgentStatus.ERROR, error=str(e))
            self._signals.agent_content.emit(content)
            self._schedule_hide_window(2000)

    def _on_recognition_done(self, text: str):
        """Handle recognition result - send to LLM.

        Args:
            text: Recognized text
        """
        if not text or not text.strip():
            content = AgentContent(status=AgentStatus.ERROR, error="识别结果为空")
            self._signals.agent_content.emit(content)
            self._schedule_hide_window(2000)
            return

        # Play end sound
        from speaky.sound import play_end_sound
        play_end_sound()

        # Update status to thinking
        content = AgentContent(
            user_input=text,
            status=AgentStatus.THINKING,
            thinking="正在思考...",
        )
        self._signals.agent_content.emit(content)

        # Run LLM in background thread
        threading.Thread(
            target=self._run_llm,
            args=(text,),
            daemon=True,
        ).start()

    def _run_llm(self, text: str):
        """Run LLM agent in background thread.

        Args:
            text: User's voice input text
        """
        try:
            result = asyncio.run(self._run_agent(text))

            # Display result
            content = AgentContent(
                user_input=text,
                result=result,
                status=AgentStatus.DONE,
            )
            self._signals.agent_content.emit(content)

            # Schedule hide
            self._schedule_hide_window(5000)

        except Exception as e:
            logger.error(f"[LLM Agent] LLM error: {e}", exc_info=True)
            content = AgentContent(
                user_input=text,
                status=AgentStatus.ERROR,
                error=str(e),
            )
            self._signals.agent_content.emit(content)
            self._schedule_hide_window(3000)

    async def _run_agent(self, text: str) -> str:
        """Run the LLM agent with streaming updates.

        Args:
            text: User's voice input text

        Returns:
            Final response from the agent
        """
        import time as time_module
        start_time = time_module.time()

        await self._ensure_initialized()

        if self._llm_client is None:
            raise RuntimeError("LLM client not initialized")

        logger.info(f"[LLM Agent] Starting agent with input: {text}")
        logger.info(f"[LLM Agent] Available tools: {self._llm_client.get_tool_names()}")

        # Use streaming for real-time updates
        full_response = ""
        content = AgentContent(
            user_input=text,
            status=AgentStatus.THINKING,
        )

        event_count = 0
        async for event in self._llm_client.chat_stream(text):
            event_count += 1
            event_type = event.get("type")
            elapsed = time_module.time() - start_time

            if event_type == "token":
                # Accumulate response tokens
                token = event.get("content", "")
                full_response += token
                content.thinking = full_response
                self._signals.agent_content.emit(content)

            elif event_type == "tool_start":
                # Tool started
                tool_name = event.get("name", "unknown")
                tool_input = event.get("input", {})
                # Only log relevant input params, not runtime metadata
                clean_input = {k: v for k, v in tool_input.items() if k not in ("runtime", "config", "state")}
                logger.info(f"[LLM Agent] [{elapsed:.2f}s] Tool start: {tool_name}, input: {clean_input}")
                summary = self._summarize_tool_input(tool_input)
                content.tool_calls.append(ToolCall(tool_name, summary, "running"))
                content.status = AgentStatus.EXECUTING
                self._signals.agent_content.emit(content)

            elif event_type == "tool_end":
                # Tool completed
                tool_name = event.get("name", "")
                tool_output = event.get("output", "")
                logger.info(f"[LLM Agent] [{elapsed:.2f}s] Tool end: {tool_name}, output: {tool_output[:200] if tool_output else 'None'}...")
                for tool in content.tool_calls:
                    if tool.name == tool_name and tool.status == "running":
                        tool.status = "success"
                        break
                self._signals.agent_content.emit(content)

            elif event_type == "tool_error":
                # Tool failed
                tool_name = event.get("name", "")
                error = event.get("error", "")
                logger.error(f"[LLM Agent] [{elapsed:.2f}s] Tool error: {tool_name}, error: {error}")
                for tool in content.tool_calls:
                    if tool.name == tool_name and tool.status == "running":
                        tool.status = "error"
                        break
                self._signals.agent_content.emit(content)

        total_time = time_module.time() - start_time
        logger.info(f"[LLM Agent] Agent completed in {total_time:.2f}s, {event_count} events, response length: {len(full_response)}")
        logger.info(f"[LLM Agent] Final response: {full_response[:200]}...")

        return full_response or await self._llm_client.chat(text)

    def _summarize_tool_input(self, tool_input: dict) -> str:
        """Create a short summary of tool input for display.

        Args:
            tool_input: Tool input parameters

        Returns:
            Short summary string
        """
        if not tool_input:
            return ""

        # Extract key parameter
        for key in ["url", "path", "query", "command", "text"]:
            if key in tool_input:
                value = str(tool_input[key])
                return value[:30] + "..." if len(value) > 30 else value

        # Fallback to first value
        first_value = str(list(tool_input.values())[0])
        return first_value[:30] + "..." if len(first_value) > 30 else first_value

    def _schedule_hide_window(self, delay_ms: int):
        """Schedule window hide after delay.

        Args:
            delay_ms: Delay in milliseconds
        """
        # Use signal to schedule on main thread (QTimer from non-Qt thread doesn't work)
        self._signals.schedule_hide.emit(delay_ms)

    def reset(self):
        """Reset handler state (called when settings change)."""
        self._initialized = False
        self._llm_client = None
        self._realtime_session = None
        logger.info("LLM Agent Handler reset")
