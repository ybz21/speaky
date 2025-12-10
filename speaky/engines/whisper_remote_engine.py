"""Remote Whisper Engine - connects to remote Whisper server via standard API"""

import io
import logging
from typing import Optional
from .base import BaseEngine

logger = logging.getLogger(__name__)


class WhisperRemoteEngine(BaseEngine):
    """远程 Whisper 引擎

    支持连接到标准 Whisper API 服务器，如：
    - faster-whisper-server
    - whisper.cpp server
    - OpenAI 兼容的 Whisper API

    API 格式：POST /v1/audio/transcriptions
    - file: 音频文件 (multipart/form-data)
    - model: 模型名称 (可选)
    - language: 语言代码 (可选)
    - response_format: 响应格式 (可选, 默认 json)
    """

    def __init__(
        self,
        server_url: str = "http://localhost:8000",
        model: str = "whisper-1",
        api_key: Optional[str] = None,
    ):
        """初始化远程 Whisper 引擎

        Args:
            server_url: Whisper 服务器地址，如 http://localhost:8000
            model: 模型名称，如 whisper-1, large-v3 等
            api_key: API 密钥（如果服务器需要认证）
        """
        # 确保 URL 不以 / 结尾
        self._server_url = server_url.rstrip("/")
        self._model = model
        self._api_key = api_key

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        """转录音频数据

        Args:
            audio_data: WAV 格式的音频数据
            language: 语言代码，如 zh, en, ja 等

        Returns:
            转录的文本
        """
        import requests

        # 构建请求 URL
        url = f"{self._server_url}/v1/audio/transcriptions"

        # 准备文件
        audio_file = io.BytesIO(audio_data)
        files = {
            "file": ("audio.wav", audio_file, "audio/wav"),
        }

        # 准备表单数据
        data = {
            "model": self._model,
            "language": language,
            "response_format": "json",
        }

        # 准备请求头
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        try:
            logger.info(f"[WhisperRemote] 发送请求到 {url}, model={self._model}, language={language}")
            response = requests.post(
                url,
                files=files,
                data=data,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            result = response.json()
            text = result.get("text", "").strip()
            logger.info(f"[WhisperRemote] 识别结果: {text[:50]}...")
            return text

        except requests.exceptions.ConnectionError as e:
            logger.error(f"[WhisperRemote] 连接失败: {e}")
            raise ConnectionError(f"无法连接到 Whisper 服务器: {self._server_url}") from e
        except requests.exceptions.Timeout as e:
            logger.error(f"[WhisperRemote] 请求超时: {e}")
            raise TimeoutError("Whisper 服务器响应超时") from e
        except requests.exceptions.HTTPError as e:
            logger.error(f"[WhisperRemote] HTTP 错误: {e}")
            raise RuntimeError(f"Whisper 服务器返回错误: {e}") from e
        except Exception as e:
            logger.error(f"[WhisperRemote] 未知错误: {e}")
            raise

    def is_available(self) -> bool:
        """检查服务器是否可用"""
        import requests

        try:
            # 尝试访问服务器根路径或健康检查端点
            response = requests.get(
                f"{self._server_url}/health",
                timeout=5,
            )
            return response.status_code == 200
        except:
            # 如果 /health 不存在，尝试 /v1/models
            try:
                headers = {}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"
                response = requests.get(
                    f"{self._server_url}/v1/models",
                    headers=headers,
                    timeout=5,
                )
                return response.status_code == 200
            except:
                return False

    @property
    def name(self) -> str:
        return "Whisper (Remote)"
