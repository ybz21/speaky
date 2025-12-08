import asyncio
import gzip
import json
import logging
import struct
import uuid
from typing import Optional, Tuple, Callable

import aiohttp
from .base import BaseEngine

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
        model: str = "bigmodel",
        segment_duration: int = 200,
    ):
        self._app_key = app_key
        self._access_key = access_key
        self._model = model  # bigmodel, bigmodel_async, bigmodel_nostream
        self._segment_duration = segment_duration
        # 流式端点和非流式端点
        self._ws_url_streaming = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel"
        self._ws_url_nostream = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_nostream"
        logger.info(f"VolcBigModel initialized: model={model}, app_key={app_key[:4] if app_key else 'None'}..., access_key={access_key[:4] if access_key else 'None'}...")

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

        # Note: bigmodel endpoint requires special streaming ASR access (returns 400 if not granted)
        # bigmodel_nostream works for most accounts but only returns final result
        # For now, always use nostream endpoint for compatibility
        ws_url = self._ws_url_nostream
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
        header = build_header(
            message_type=MessageType.CLIENT_FULL_REQUEST,
            flags=MessageTypeSpecificFlags.POS_SEQUENCE,
        )

        payload = {
            "user": {"uid": "speaky"},
            "audio": {
                "format": "wav",
                "codec": "raw",
                "rate": rate,
                "bits": bits * 8,
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

        payload_bytes = gzip.compress(json.dumps(payload).encode('utf-8'))

        request = bytearray()
        request.extend(header)
        request.extend(struct.pack('>i', seq))
        request.extend(struct.pack('>I', len(payload_bytes)))
        request.extend(payload_bytes)

        return bytes(request)

    def _build_audio_request(self, seq: int, segment: bytes, is_last: bool = False) -> bytes:
        """Build audio-only request"""
        if is_last:
            flags = MessageTypeSpecificFlags.NEG_WITH_SEQUENCE
            seq = -seq
        else:
            flags = MessageTypeSpecificFlags.POS_SEQUENCE

        header = build_header(
            message_type=MessageType.CLIENT_AUDIO_ONLY_REQUEST,
            flags=flags,
        )

        compressed = gzip.compress(segment)

        request = bytearray()
        request.extend(header)
        request.extend(struct.pack('>i', seq))
        request.extend(struct.pack('>I', len(compressed)))
        request.extend(compressed)

        return bytes(request)

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
