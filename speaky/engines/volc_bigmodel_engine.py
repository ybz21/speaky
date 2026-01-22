import asyncio
import gzip
import json
import logging
import struct
import threading
import uuid
from typing import Optional, Tuple, Callable
from queue import Queue, Empty

import aiohttp
from speaky.engines.base import BaseEngine, RealtimeSession

logger = logging.getLogger(__name__)

# Protocol constants
class ProtocolVersion:
    V1 = 0b0001

class MessageType:
    CLIENT_FULL_REQUEST = 0b0001
    CLIENT_AUDIO_ONLY_REQUEST = 0b0010
    SERVER_FULL_RESPONSE = 0b1001
    SERVER_ERROR_RESPONSE = 0b1111

class MessageTypeSpecificFlags:
    NO_SEQUENCE = 0b0000
    POS_SEQUENCE = 0b0001
    NEG_SEQUENCE = 0b0010
    NEG_WITH_SEQUENCE = 0b0011

class SerializationType:
    NO_SERIALIZATION = 0b0000
    JSON = 0b0001

class CompressionType:
    NO_COMPRESSION = 0b0000
    GZIP = 0b0001


def build_header(
    message_type: int = MessageType.CLIENT_FULL_REQUEST,
    flags: int = MessageTypeSpecificFlags.POS_SEQUENCE,
    serialization: int = SerializationType.JSON,
    compression: int = CompressionType.GZIP,
) -> bytes:
    """Build protocol header"""
    header = bytearray()
    header.append((ProtocolVersion.V1 << 4) | 1)  # version + header size
    header.append((message_type << 4) | flags)
    header.append((serialization << 4) | compression)
    header.append(0x00)  # reserved
    return bytes(header)


def build_audio_request(seq: int, audio_data: bytes, is_last: bool = False) -> bytes:
    """Build audio-only request for WebSocket.

    Args:
        seq: Sequence number (will be negated if is_last)
        audio_data: Raw audio bytes to send
        is_last: Whether this is the last audio packet
    """
    if is_last:
        flags = MessageTypeSpecificFlags.NEG_WITH_SEQUENCE
        seq = -seq
    else:
        flags = MessageTypeSpecificFlags.POS_SEQUENCE

    header = build_header(
        message_type=MessageType.CLIENT_AUDIO_ONLY_REQUEST,
        flags=flags,
    )

    compressed = gzip.compress(audio_data) if audio_data else gzip.compress(b"")

    request = bytearray()
    request.extend(header)
    request.extend(struct.pack('>i', seq))
    request.extend(struct.pack('>I', len(compressed)))
    request.extend(compressed)

    return bytes(request), compressed


def build_full_request(
    seq: int,
    audio_format: str,
    rate: int,
    bits: int,
    channels: int,
    log_payload: bool = False,
) -> bytes:
    """Build full client request for WebSocket connection.

    Args:
        seq: Sequence number
        audio_format: Audio format ("wav" or "pcm")
        rate: Sample rate (e.g., 16000)
        bits: Bits per sample (e.g., 16)
        channels: Number of channels (e.g., 1)
        log_payload: Whether to log the payload
    """
    header = build_header(
        message_type=MessageType.CLIENT_FULL_REQUEST,
        flags=MessageTypeSpecificFlags.POS_SEQUENCE,
    )

    payload = {
        "user": {"uid": "speaky"},
        "audio": {
            "format": audio_format,
            "codec": "raw",
            "rate": rate,
            "bits": bits,
            "channel": channels,
        },
        "request": {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_ddc": True,
            "show_utterances": True,
        },
    }

    if log_payload:
        logger.info(f"[初始请求] payload: {payload}")

    payload_bytes = gzip.compress(json.dumps(payload).encode('utf-8'))

    request = bytearray()
    request.extend(header)
    request.extend(struct.pack('>i', seq))
    request.extend(struct.pack('>I', len(payload_bytes)))
    request.extend(payload_bytes)

    return bytes(request)


def parse_response(msg: bytes) -> dict:
    """Parse server response"""
    result = {
        "code": 0,
        "is_last": False,
        "sequence": 0,
        "payload": None,
    }

    if len(msg) < 4:
        return result

    header_size = msg[0] & 0x0f
    message_type = msg[1] >> 4
    flags = msg[1] & 0x0f
    compression = msg[2] & 0x0f

    payload = msg[header_size * 4:]

    # Parse flags
    if flags & 0x01:  # has sequence
        result["sequence"] = struct.unpack('>i', payload[:4])[0]
        payload = payload[4:]
    if flags & 0x02:  # is last
        result["is_last"] = True

    # Parse message type
    if message_type == MessageType.SERVER_FULL_RESPONSE:
        payload_size = struct.unpack('>I', payload[:4])[0]
        payload = payload[4:]
    elif message_type == MessageType.SERVER_ERROR_RESPONSE:
        result["code"] = struct.unpack('>i', payload[:4])[0]
        payload_size = struct.unpack('>I', payload[4:8])[0]
        payload = payload[8:]

    if not payload:
        return result

    # Decompress
    if compression == CompressionType.GZIP:
        try:
            payload = gzip.decompress(payload)
        except Exception as e:
            logger.error(f"Failed to decompress: {e}")
            return result

    # Parse JSON
    try:
        result["payload"] = json.loads(payload.decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to parse JSON: {e}")

    return result


class VolcBigModelEngine(BaseEngine):
    """火山引擎语音大模型 (Bigmodel ASR)

    使用语音大模型 WebSocket API v3
    文档: https://www.volcengine.com/docs/6561/1354868
    """

    def __init__(
        self,
        app_key: str,
        access_key: str,
        segment_duration: int = 200,
    ):
        self._app_key = app_key
        self._access_key = access_key
        self._segment_duration = segment_duration
        # 固定使用 bigmodel_async 端点（双向流式优化版，结果变化时返回，性能更优）
        self._ws_url_async = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"

        # Persistent connection manager for faster session startup
        self._connection_manager: Optional["VolcConnectionManager"] = None

        logger.info(f"VolcBigModel initialized: app_key={app_key[:4] if app_key else 'None'}..., access_key={access_key[:4] if access_key else 'None'}...")

    def _get_connection_manager(self) -> "VolcConnectionManager":
        """Get or create connection manager for persistent connections."""
        if self._connection_manager is None:
            # 使用 bigmodel_async 端点实现真正的流式输出
            self._connection_manager = VolcConnectionManager(
                app_key=self._app_key,
                access_key=self._access_key,
                ws_url=self._ws_url_async,
            )
        return self._connection_manager

    def warmup(self):
        """Pre-initialize connection for faster first request."""
        import time as _time
        t0 = _time.time()
        logger.info("[引擎预热] 开始预热连接...")
        manager = self._get_connection_manager()
        manager.ensure_ready()
        logger.info(f"[引擎预热] ConnectionManager 就绪，耗时 {_time.time()-t0:.2f}s")
        # Pre-warm WebSocket connection
        manager.warmup_websocket()
        logger.info(f"[引擎预热] 已启动 WebSocket 预热任务")

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._transcribe_async(audio_data, language, streaming=False)
            )
        finally:
            loop.close()

    def supports_streaming(self) -> bool:
        return True

    def transcribe_streaming(
        self,
        audio_data: bytes,
        language: str = "zh",
        on_partial: Optional[Callable[[str], None]] = None,
    ) -> str:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._transcribe_async(audio_data, language, streaming=True, on_partial=on_partial)
            )
        finally:
            loop.close()

    async def _transcribe_async(
        self,
        audio_data: bytes,
        language: str,
        streaming: bool = False,
        on_partial: Optional[Callable[[str], None]] = None,
    ) -> str:
        request_id = str(uuid.uuid4())
        logger.info(f"Starting BigModel transcription, request_id={request_id}")

        # Validate WAV format
        if not self._is_valid_wav(audio_data):
            logger.error("Invalid WAV format")
            return ""

        # Parse WAV info for logging and segment size calculation
        try:
            nchannels, sampwidth, framerate, nframes, _ = self._read_wav_info(audio_data)
        except Exception as e:
            logger.error(f"Failed to parse WAV: {e}")
            return ""

        logger.info(f"Audio info: channels={nchannels}, bits={sampwidth*8}, rate={framerate}, frames={nframes}")

        # Calculate segment size based on audio properties
        size_per_sec = nchannels * sampwidth * framerate
        segment_size = size_per_sec * self._segment_duration // 1000

        # Build headers - exactly matching demo format
        # 使用豆包流式语音识别模型2.0小时版
        headers = {
            "X-Api-Resource-Id": "volc.seedasr.sauc.duration",
            "X-Api-Request-Id": request_id,
            "X-Api-Access-Key": self._access_key,
            "X-Api-App-Key": self._app_key,
        }

        # 固定使用 bigmodel_async 端点
        ws_url = self._ws_url_async
        logger.info(f"Connecting to {ws_url} (streaming={streaming})")

        result_text = ""
        seq = 1

        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, headers=headers) as ws:
                    logger.info(f"Connected to {ws_url}")

                    # Send full client request
                    full_request = self._build_full_request(seq, framerate, sampwidth, nchannels)
                    await ws.send_bytes(full_request)
                    seq += 1

                    # Wait for initial response
                    msg = await ws.receive()
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        resp = parse_response(msg.data)
                        logger.debug(f"Initial response: {resp}")
                        if resp["code"] != 0:
                            logger.error(f"Initial request failed: {resp}")
                            return ""

                    # Send audio segments - send the ENTIRE WAV file content (including header)
                    # This matches the demo behavior
                    segments = self._split_audio(audio_data, segment_size)
                    total = len(segments)

                    async def send_audio():
                        nonlocal seq
                        for i, segment in enumerate(segments):
                            is_last = (i == total - 1)
                            audio_request = self._build_audio_request(seq, segment, is_last)
                            await ws.send_bytes(audio_request)
                            logger.debug(f"Sent segment {i+1}/{total}, seq={seq}, last={is_last}")
                            if not is_last:
                                seq += 1
                            await asyncio.sleep(self._segment_duration / 1000)

                    # Start sending in background
                    send_task = asyncio.create_task(send_audio())

                    # Receive responses
                    try:
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.BINARY:
                                resp = parse_response(msg.data)
                                logger.debug(f"Response: seq={resp['sequence']}, last={resp['is_last']}")

                                if resp["code"] != 0:
                                    logger.error(f"Error response: {resp}")
                                    break

                                if resp["payload"]:
                                    payload = resp["payload"]
                                    # Extract text from result
                                    if "result" in payload:
                                        res = payload["result"]
                                        if isinstance(res, list) and res:
                                            result_text = res[0].get("text", "")
                                        elif isinstance(res, dict):
                                            result_text = res.get("text", "")
                                        logger.debug(f"Current text: {result_text}")

                                        # Call streaming callback for partial results
                                        if streaming and on_partial and result_text:
                                            on_partial(result_text)

                                if resp["is_last"]:
                                    logger.info("Received last package")
                                    break

                            elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                                logger.warning(f"WebSocket closed: {msg.type}")
                                break
                    finally:
                        send_task.cancel()
                        try:
                            await send_task
                        except asyncio.CancelledError:
                            pass

        except Exception as e:
            logger.error(f"BigModel ASR error: {e}", exc_info=True)
            return ""

        logger.info(f"Transcription complete: {result_text}")
        return result_text.strip()

    @staticmethod
    def _is_valid_wav(data: bytes) -> bool:
        """Check if data is a valid WAV file"""
        if len(data) < 44:
            return False
        return data[:4] == b'RIFF' and data[8:12] == b'WAVE'

    @staticmethod
    def _read_wav_info(data: bytes) -> Tuple[int, int, int, int, bytes]:
        """Parse WAV header and return (num_channels, samp_width, sample_rate, nframes, wave_data)"""
        if len(data) < 44:
            raise ValueError("Invalid WAV file: too short")

        # Parse WAV header
        chunk_id = data[:4]
        if chunk_id != b'RIFF':
            raise ValueError("Invalid WAV file: not RIFF format")

        format_ = data[8:12]
        if format_ != b'WAVE':
            raise ValueError("Invalid WAV file: not WAVE format")

        # Parse fmt subchunk
        num_channels = struct.unpack('<H', data[22:24])[0]
        sample_rate = struct.unpack('<I', data[24:28])[0]
        bits_per_sample = struct.unpack('<H', data[34:36])[0]

        # Find data subchunk
        pos = 36
        while pos < len(data) - 8:
            subchunk_id = data[pos:pos+4]
            subchunk_size = struct.unpack('<I', data[pos+4:pos+8])[0]
            if subchunk_id == b'data':
                wave_data = data[pos+8:pos+8+subchunk_size]
                samp_width = bits_per_sample // 8
                nframes = subchunk_size // (num_channels * samp_width)
                return (num_channels, samp_width, sample_rate, nframes, wave_data)
            pos += 8 + subchunk_size

        raise ValueError("Invalid WAV file: no data subchunk found")

    def _build_full_request(self, seq: int, rate: int, bits: int, channels: int) -> bytes:
        """Build full client request"""
        return build_full_request(
            seq=seq,
            audio_format="wav",
            rate=rate,
            bits=bits * 8,
            channels=channels,
        )

    def _build_audio_request(self, seq: int, segment: bytes, is_last: bool = False) -> bytes:
        """Build audio-only request"""
        request, _ = build_audio_request(seq, segment, is_last)
        return request

    @staticmethod
    def _split_audio(data: bytes, segment_size: int) -> list:
        """Split audio into segments"""
        segments = []
        for i in range(0, len(data), segment_size):
            segments.append(data[i:i + segment_size])
        return segments

    def is_available(self) -> bool:
        return bool(self._app_key and self._access_key)

    @property
    def name(self) -> str:
        return "火山语音大模型"

    def supports_realtime_streaming(self) -> bool:
        return True

    def create_realtime_session(
        self,
        language: str = "zh",
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> "VolcRealtimeSession":
        # Use connection manager for faster startup
        manager = self._get_connection_manager()
        return VolcRealtimeSession(
            connection_manager=manager,
            on_partial=on_partial,
            on_final=on_final,
            on_error=on_error,
        )


class VolcConnectionManager:
    """Manages persistent WebSocket connections for faster session startup.

    Key optimizations:
    1. Pre-establishes connection in background thread
    2. Keeps event loop running between sessions
    3. Reuses aiohttp ClientSession
    4. Pre-warms WebSocket connection for instant response
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16-bit

    def __init__(self, app_key: str, access_key: str, ws_url: str):
        self._app_key = app_key
        self._access_key = access_key
        self._ws_url = ws_url

        # Persistent event loop thread
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._is_ready = threading.Event()
        self._lock = threading.Lock()

        # Pre-warmed WebSocket connection
        self._warm_ws = None
        self._warm_ws_ready = threading.Event()
        self._warming_up = False
        self._warm_ws_created_at = 0  # 预热连接创建时间
        self._warm_ws_max_age = 30  # 预热连接最大存活时间（秒）

        # Start background loop
        self._start_loop()

    def _start_loop(self):
        """Start the persistent event loop in a background thread."""
        if self._loop_thread is not None and self._loop_thread.is_alive():
            return

        def run_loop():
            import time as _time
            t0 = _time.time()
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            # Create persistent session
            async def setup():
                self._session = aiohttp.ClientSession()
                logger.info(f"[ConnectionManager] aiohttp session 创建完成，耗时 {_time.time()-t0:.2f}s")

            self._loop.run_until_complete(setup())
            self._is_ready.set()
            logger.info(f"[ConnectionManager] 事件循环就绪")

            # Keep loop running
            self._loop.run_forever()

            # Cleanup when loop stops
            async def cleanup():
                if self._session:
                    await self._session.close()
                    self._session = None

            self._loop.run_until_complete(cleanup())
            self._loop.close()

        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
        logger.info("[ConnectionManager] 后台事件循环线程已启动")

    def ensure_ready(self):
        """Ensure the connection manager is ready."""
        if not self._is_ready.wait(timeout=5):
            logger.warning("ConnectionManager: timeout waiting for ready")
            self._start_loop()
            self._is_ready.wait(timeout=5)

    def run_coroutine(self, coro):
        """Run a coroutine in the persistent event loop."""
        self.ensure_ready()
        if self._loop is None:
            raise RuntimeError("Event loop not available")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def get_headers(self) -> dict:
        """Generate request headers."""
        return {
            "X-Api-Resource-Id": "volc.seedasr.sauc.duration",
            "X-Api-Request-Id": str(uuid.uuid4()),
            "X-Api-Access-Key": self._access_key,
            "X-Api-App-Key": self._app_key,
        }

    @property
    def session(self) -> Optional[aiohttp.ClientSession]:
        return self._session

    @property
    def ws_url(self) -> str:
        return self._ws_url

    def warmup_websocket(self):
        """Pre-establish WebSocket connection for faster first request.

        This creates a WebSocket connection in advance so that when the user
        presses the hotkey, the connection is already ready.
        """
        if self._warming_up:
            logger.info("[WebSocket预热] 已在预热中，跳过")
            return
        self._warming_up = True
        self._warm_ws_ready.clear()

        async def do_warmup():
            import time as _time
            t0 = _time.time()
            try:
                headers = self.get_headers()
                logger.info(f"[WebSocket预热] 开始连接 {self._ws_url}")
                ws = await self._session.ws_connect(
                    self._ws_url,
                    headers=headers,
                    heartbeat=30,
                )
                self._warm_ws = ws
                self._warm_ws_created_at = _time.time()
                self._warm_ws_ready.set()
                logger.info(f"[WebSocket预热] 连接就绪，耗时 {_time.time()-t0:.2f}s")
            except Exception as e:
                logger.error(f"[WebSocket预热] 连接失败: {e}，耗时 {_time.time()-t0:.2f}s")
                self._warming_up = False

        self.run_coroutine(do_warmup())

    def _is_warm_ws_valid(self) -> bool:
        """检查预热连接是否仍然有效"""
        import time as _time
        if not self._warm_ws_ready.is_set():
            return False
        if self._warm_ws is None:
            return False
        # 检查连接是否超时
        age = _time.time() - self._warm_ws_created_at
        if age > self._warm_ws_max_age:
            logger.info(f"[WebSocket预热] 连接已过期（{age:.1f}s > {self._warm_ws_max_age}s），将重新预热")
            return False
        # 检查连接是否已关闭
        if self._warm_ws.closed:
            logger.info("[WebSocket预热] 连接已关闭，将重新预热")
            return False
        return True

    def _invalidate_warm_ws(self):
        """使当前预热连接失效并关闭"""
        if self._warm_ws:
            async def close_ws():
                try:
                    if not self._warm_ws.closed:
                        await self._warm_ws.close()
                except:
                    pass
            if self._loop:
                asyncio.run_coroutine_threadsafe(close_ws(), self._loop)
        self._warm_ws = None
        self._warm_ws_ready.clear()
        self._warming_up = False

    def get_warm_websocket(self, timeout: float = 2.0):
        """Get the pre-warmed WebSocket connection if available.

        Returns the pre-warmed WebSocket or None if not ready.
        After returning, starts warming up a new connection.
        """
        ws = None
        if self._warm_ws_ready.wait(timeout=timeout):
            ws = self._warm_ws
            self._warm_ws = None
            self._warm_ws_ready.clear()
            self._warming_up = False
            # Start warming up next connection in background
            self.warmup_websocket()
        return ws

    def shutdown(self):
        """Shutdown the connection manager."""
        # Close warm WebSocket if exists
        if self._warm_ws:
            async def close_ws():
                try:
                    await self._warm_ws.close()
                except:
                    pass
            if self._loop:
                asyncio.run_coroutine_threadsafe(close_ws(), self._loop)

        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._loop_thread:
            self._loop_thread.join(timeout=2)
        logger.info("ConnectionManager: shutdown complete")


class VolcRealtimeSession(RealtimeSession):
    """Real-time streaming ASR session for Volcengine BigModel.

    Uses ConnectionManager for faster startup by:
    1. Reusing persistent event loop
    2. Reusing aiohttp session
    """

    SAMPLE_RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2  # 16-bit

    def __init__(
        self,
        connection_manager: VolcConnectionManager,
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        self._manager = connection_manager
        self._on_partial = on_partial
        self._on_final = on_final
        self._on_error = on_error

        self._audio_queue: Queue[Optional[bytes]] = Queue()
        self._result_text = ""
        self._is_running = False
        self._session_future = None
        self._seq = 1
        self._final_received = False  # Track if on_final was called

    def start(self):
        """Start the session using the persistent connection manager."""
        if self._is_running:
            return
        self._is_running = True
        self._result_text = ""
        self._seq = 1
        self._final_received = False

        # Clear any stale data in queue
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except Empty:
                break

        # Start session in persistent loop
        self._session_future = self._manager.run_coroutine(self._session_loop())
        logger.info("VolcRealtimeSession started (using persistent loop)")

    def send_audio(self, audio_data: bytes):
        """Send raw PCM audio data chunk."""
        if self._is_running:
            self._audio_queue.put(audio_data)

    def finish(self) -> str:
        """Signal end of audio and wait for final result."""
        if not self._is_running:
            return self._result_text

        # Signal end of audio
        self._audio_queue.put(None)

        # Wait for session to complete with shorter timeout
        # If on_final was already called, don't wait long
        if self._session_future:
            try:
                timeout = 1 if self._final_received else 5
                self._session_future.result(timeout=timeout)
            except Exception as e:
                if not self._final_received:
                    logger.error(f"Session finish error: {e}")

        self._is_running = False
        logger.info(f"VolcRealtimeSession finished: {self._result_text}")
        return self._result_text

    def cancel(self):
        """Cancel the session."""
        self._is_running = False
        self._audio_queue.put(None)
        if self._session_future:
            self._session_future.cancel()

    async def _session_loop(self):
        """Main async session loop."""
        import time as _time
        session_start = _time.time()
        ws = None

        # 检查预热连接是否有效（包括超时检测）
        warm_valid = self._manager._is_warm_ws_valid()
        logger.info(f"[会话循环] 检查预热连接: valid={warm_valid}, warming_up={self._manager._warming_up}")

        if warm_valid:
            ws = self._manager._warm_ws
            self._manager._warm_ws = None
            self._manager._warm_ws_ready.clear()
            self._manager._warming_up = False
            age = _time.time() - self._manager._warm_ws_created_at
            logger.info(f"[会话循环] 使用预热的 WebSocket 连接（age={age:.1f}s）")
            # Start warming up next connection
            self._manager.warmup_websocket()
        else:
            # 预热连接无效，清理并准备新建
            self._manager._invalidate_warm_ws()

        try:
            if ws is None:
                # No valid pre-warmed connection, create new one
                t0 = _time.time()
                headers = self._manager.get_headers()
                logger.info(f"[会话循环] 无有效预热连接，开始新建连接...")
                ws = await self._manager.session.ws_connect(
                    self._manager.ws_url,
                    headers=headers,
                    heartbeat=30,
                )
                logger.info(f"[会话循环] 新建连接完成，耗时 {_time.time()-t0:.2f}s")
                # 新建连接成功后，启动下一个预热
                self._manager.warmup_websocket()

            # Send initial full request
            t0 = _time.time()
            full_request = self._build_full_request()
            await ws.send_bytes(full_request)
            self._seq += 1
            logger.info(f"[会话循环] 发送初始请求完成，耗时 {_time.time()-t0:.3f}s")

            # Wait for initial response
            t0 = _time.time()
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.BINARY:
                resp = parse_response(msg.data)
                logger.info(f"[会话循环] 初始响应: code={resp['code']}, is_last={resp['is_last']}, payload={resp.get('payload')}")
                if resp["code"] != 0:
                    logger.error(f"[会话循环] 初始请求失败: {resp}")
                    if self._on_error:
                        self._on_error(f"Connection failed: {resp}")
                    return
                logger.info(f"[会话循环] 收到初始响应，耗时 {_time.time()-t0:.3f}s，开始音频流")
                logger.info(f"[会话循环] 会话就绪，总耗时 {_time.time()-session_start:.2f}s")
            elif msg.type == aiohttp.WSMsgType.TEXT:
                logger.warning(f"[会话循环] 收到文本响应: {msg.data}")
            else:
                logger.warning(f"[会话循环] 收到未知类型响应: {msg.type}")

            # Start sender and receiver tasks
            sender_task = asyncio.create_task(self._send_audio_loop(ws))
            receiver_task = asyncio.create_task(self._receive_loop(ws))

            # Wait for both to complete
            await asyncio.gather(sender_task, receiver_task)

        except Exception as e:
            logger.error(f"[会话循环] WebSocket 错误: {e}", exc_info=True)
            if self._on_error:
                self._on_error(str(e))
        finally:
            # Close WebSocket if we created it (warm WS is managed separately)
            if ws and not ws.closed:
                await ws.close()

    async def _send_audio_loop(self, ws):
        """Send audio data from queue to WebSocket."""
        audio_buffer = bytearray()
        bytes_per_200ms = self.SAMPLE_RATE * self.CHANNELS * self.SAMPLE_WIDTH * 200 // 1000
        logger.info(f"[音频发送] 开始发送循环，每包 {bytes_per_200ms} 字节 (200ms)")

        while self._is_running:
            try:
                # Non-blocking get with timeout
                loop = asyncio.get_event_loop()
                audio_data = await loop.run_in_executor(
                    None, lambda: self._audio_queue.get(timeout=0.1)
                )

                if audio_data is None:
                    # End of audio - send remaining buffer as last packet
                    if audio_buffer:
                        await self._send_audio_packet(ws, bytes(audio_buffer), is_last=True)
                    else:
                        await self._send_audio_packet(ws, b"", is_last=True)
                    logger.info(f"[音频发送] 发送最后一个音频包，总共发送 {self._seq} 个包")
                    break

                audio_buffer.extend(audio_data)

                # Send when we have enough data (~200ms)
                while len(audio_buffer) >= bytes_per_200ms:
                    chunk = bytes(audio_buffer[:bytes_per_200ms])
                    audio_buffer = audio_buffer[bytes_per_200ms:]
                    await self._send_audio_packet(ws, chunk, is_last=False)

            except Empty:
                continue
            except Exception as e:
                logger.error(f"[音频发送] 发送错误: {e}")
                break

    async def _send_audio_packet(self, ws, audio_data: bytes, is_last: bool):
        """Send a single audio packet."""
        seq = self._seq
        if not is_last:
            self._seq += 1

        request, compressed = build_audio_request(seq, audio_data, is_last)
        await ws.send_bytes(request)

        # 日志记录
        actual_seq = -seq if is_last else seq
        # 第2个包详细记录数据头（跳过第1个包因为是初始请求后的第一个音频包，seq已经是2）
        if abs(actual_seq) == 2 and audio_data:
            logger.info(f"[音频发送] 首个音频包头16字节: {audio_data[:16].hex()}")
            # 计算音频电平
            samples = [int.from_bytes(audio_data[i:i+2], 'little', signed=True) for i in range(0, min(len(audio_data), 200), 2)]
            max_val = max(abs(s) for s in samples) if samples else 0
            avg_val = sum(abs(s) for s in samples) // len(samples) if samples else 0
            logger.info(f"[音频发送] 首个音频包电平: max={max_val}, avg={avg_val} (静音阈值约100)")
        if is_last or abs(actual_seq) % 10 == 0:  # 每10个包或最后一个包记录日志
            logger.info(f"[音频发送] seq={actual_seq}, 原始={len(audio_data)}字节, 压缩={len(compressed)}字节, last={is_last}")

    async def _receive_loop(self, ws):
        """Receive results from WebSocket."""
        import time as _time
        first_result_time = None
        result_count = 0
        msg_count = 0
        loop_start = _time.time()

        try:
            async for msg in ws:
                msg_count += 1
                if msg.type == aiohttp.WSMsgType.BINARY:
                    resp = parse_response(msg.data)
                    logger.info(f"[识别接收] 消息#{msg_count}: code={resp['code']}, seq={resp['sequence']}, is_last={resp['is_last']}, payload_keys={list(resp['payload'].keys()) if resp['payload'] else None}")

                    if resp["code"] != 0:
                        logger.error(f"[识别接收] 错误响应: code={resp['code']}, payload={resp.get('payload')}")
                        if self._on_error:
                            self._on_error(f"ASR error: {resp['code']}")
                        break

                    if resp["payload"]:
                        payload = resp["payload"]
                        logger.info(f"[识别接收] payload详情: {payload}")
                        if "result" in payload:
                            res = payload["result"]
                            if isinstance(res, list) and res:
                                text = res[0].get("text", "")
                            elif isinstance(res, dict):
                                text = res.get("text", "")
                            else:
                                text = ""

                            if text:
                                result_count += 1
                                if first_result_time is None:
                                    first_result_time = _time.time()
                                    logger.info(f"[识别接收] 首次结果，延迟 {first_result_time - loop_start:.2f}s: {text[:30]}...")
                                self._result_text = text
                                if self._on_partial:
                                    self._on_partial(text)

                    if resp["is_last"]:
                        elapsed = _time.time() - loop_start
                        logger.info(f"[识别接收] 最终结果，总耗时 {elapsed:.2f}s，收到 {msg_count} 条消息，{result_count} 次识别结果: {self._result_text[:50] if self._result_text else 'None'}...")
                        self._final_received = True
                        if self._on_final:
                            self._on_final(self._result_text)
                        break

                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    logger.warning(f"[识别接收] WebSocket 关闭: {msg.type}")
                    break
                else:
                    logger.warning(f"[识别接收] 未知消息类型: {msg.type}, data={msg.data if hasattr(msg, 'data') else 'N/A'}")

        except Exception as e:
            logger.error(f"[识别接收] 错误: {e}", exc_info=True)

    def _build_full_request(self) -> bytes:
        """Build full client request."""
        return build_full_request(
            seq=1,
            audio_format="pcm",
            rate=self.SAMPLE_RATE,
            bits=self.SAMPLE_WIDTH * 8,
            channels=self.CHANNELS,
            log_payload=True,
        )
