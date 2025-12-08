import asyncio
import base64
import gzip
import json
import logging
import uuid
import wave
from io import BytesIO
import websockets
from .base import BaseEngine

logger = logging.getLogger(__name__)

# Protocol constants
PROTOCOL_VERSION = 0b0001
DEFAULT_HEADER_SIZE = 0b0001

# Message Type
CLIENT_FULL_REQUEST = 0b0001
CLIENT_AUDIO_ONLY_REQUEST = 0b0010
SERVER_FULL_RESPONSE = 0b1001
SERVER_ACK = 0b1011
SERVER_ERROR_RESPONSE = 0b1111

# Message Type Specific Flags
NO_SEQUENCE = 0b0000
NEG_SEQUENCE = 0b0010

# Message Serialization
JSON_SERIAL = 0b0001

# Message Compression
GZIP_COMPRESS = 0b0001


def generate_header(
    message_type=CLIENT_FULL_REQUEST,
    message_type_specific_flags=NO_SEQUENCE,
):
    header = bytearray()
    header.append((PROTOCOL_VERSION << 4) | DEFAULT_HEADER_SIZE)
    header.append((message_type << 4) | message_type_specific_flags)
    header.append((JSON_SERIAL << 4) | GZIP_COMPRESS)
    header.append(0x00)
    return header


def parse_response(res):
    header_size = res[0] & 0x0f
    message_type = res[1] >> 4
    message_compression = res[2] & 0x0f
    payload = res[header_size * 4:]
    result = {}
    payload_msg = None

    if message_type == SERVER_FULL_RESPONSE:
        payload_msg = payload[4:]
    elif message_type == SERVER_ACK:
        seq = int.from_bytes(payload[:4], "big", signed=True)
        result['seq'] = seq
        if len(payload) >= 8:
            payload_msg = payload[8:]
    elif message_type == SERVER_ERROR_RESPONSE:
        code = int.from_bytes(payload[:4], "big", signed=False)
        result['code'] = code
        payload_msg = payload[8:]

    if payload_msg is None:
        return result

    if message_compression == GZIP_COMPRESS:
        payload_msg = gzip.decompress(payload_msg)
    payload_msg = json.loads(str(payload_msg, "utf-8"))
    result['payload_msg'] = payload_msg
    return result


class VolcEngineEngine(BaseEngine):
    """火山引擎语音识别 (豆包语音 ASR)

    使用一句话识别 WebSocket API v2
    文档: https://www.volcengine.com/docs/6561/80818
    """

    def __init__(self, app_id: str, access_key: str, secret_key: str, cluster: str = "volcengine_input_common"):
        self._app_id = app_id
        self._access_key = access_key
        self._secret_key = secret_key
        self._cluster = cluster
        self._ws_url = "wss://openspeech.bytedance.com/api/v2/asr"
        logger.info(f"VolcEngine initialized: app_id={app_id}, cluster={cluster}")

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._transcribe_async(audio_data, language)
            )
        finally:
            loop.close()

    async def _transcribe_async(self, audio_data: bytes, language: str) -> str:
        request_id = str(uuid.uuid4())
        logger.info(f"Starting transcription, request_id={request_id}")

        # 读取 wav 信息
        with BytesIO(audio_data) as f:
            wave_fp = wave.open(f, 'rb')
            nchannels, sampwidth, framerate, nframes = wave_fp.getparams()[:4]
            wav_bytes = wave_fp.readframes(nframes)

        logger.info(f"Audio info: channels={nchannels}, sampwidth={sampwidth}, framerate={framerate}, frames={nframes}")

        # 构建请求参数 - 使用 access_key 作为 token
        request_params = {
            "app": {
                "appid": self._app_id,
                "cluster": self._cluster,
                "token": self._access_key,
            },
            "user": {"uid": "speaky"},
            "request": {
                "reqid": request_id,
                "nbest": 1,
                "workflow": "audio_in,resample,partition,vad,fe,decode,itn,nlu_punctuate",
                "show_utterances": True,
                "result_type": "full",
                "sequence": 1,
            },
            "audio": {
                "format": "raw",
                "rate": framerate,
                "language": "zh-CN" if language == "zh" else "en-US",
                "bits": sampwidth * 8,
                "channel": nchannels,
                "codec": "raw",
            },
        }

        logger.debug(f"Request params: {json.dumps(request_params, indent=2)}")

        # 构建 full client request
        payload_bytes = gzip.compress(json.dumps(request_params).encode())
        full_request = bytearray(generate_header(CLIENT_FULL_REQUEST, NO_SEQUENCE))
        full_request.extend(len(payload_bytes).to_bytes(4, 'big'))
        full_request.extend(payload_bytes)

        headers = {"Authorization": f"Bearer; {self._access_key}"}

        result_text = ""
        try:
            logger.info(f"Connecting to {self._ws_url}")
            async with websockets.connect(self._ws_url, additional_headers=headers, max_size=1000000000) as ws:
                # 发送 full client request
                logger.info("Sending full client request")
                await ws.send(full_request)
                res = await ws.recv()
                result = parse_response(res)
                logger.info(f"Full request response: {result}")
                if 'payload_msg' in result:
                    code = result['payload_msg'].get('code')
                    if code != 1000:
                        logger.error(f"Full request failed with code {code}: {result['payload_msg']}")
                        return ""

                # 分段发送音频数据
                segment_size = nchannels * sampwidth * framerate  # 1秒的数据
                offset = 0
                segment_count = 0
                while offset < len(wav_bytes):
                    chunk = wav_bytes[offset:offset + segment_size]
                    is_last = offset + segment_size >= len(wav_bytes)

                    payload_bytes = gzip.compress(chunk)
                    if is_last:
                        audio_request = bytearray(generate_header(CLIENT_AUDIO_ONLY_REQUEST, NEG_SEQUENCE))
                    else:
                        audio_request = bytearray(generate_header(CLIENT_AUDIO_ONLY_REQUEST, NO_SEQUENCE))
                    audio_request.extend(len(payload_bytes).to_bytes(4, 'big'))
                    audio_request.extend(payload_bytes)

                    await ws.send(audio_request)
                    res = await ws.recv()
                    result = parse_response(res)
                    segment_count += 1
                    logger.debug(f"Segment {segment_count} response: {result}")

                    if 'payload_msg' in result:
                        payload = result['payload_msg']
                        logger.debug(f"Payload: {payload}")
                        if payload.get('code') == 1000 and 'result' in payload:
                            res = payload['result']
                            # result can be a list of utterances or a dict
                            if isinstance(res, list) and len(res) > 0:
                                result_text = res[0].get('text', '')
                            elif isinstance(res, dict):
                                result_text = res.get('text', '')
                            logger.info(f"Got result text: {result_text}")

                    offset += segment_size

                logger.info(f"Transcription complete, final text: {result_text}")

        except Exception as e:
            logger.error(f"VolcEngine ASR error: {e}", exc_info=True)
            return ""

        return result_text.strip()

    def is_available(self) -> bool:
        return bool(self._app_id and self._access_key)

    @property
    def name(self) -> str:
        return "火山引擎-一句话识别"
