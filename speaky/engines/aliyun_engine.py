import json
import requests
from .base import BaseEngine


class AliyunEngine(BaseEngine):
    """阿里云语音识别"""

    def __init__(self, app_key: str, access_token: str):
        self._app_key = app_key
        self._access_token = access_token
        self._api_url = "https://nls-gateway.cn-shanghai.aliyuncs.com/stream/v1/asr"

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        headers = {
            "Content-Type": "application/octet-stream",
            "X-NLS-Token": self._access_token,
        }
        params = {
            "appkey": self._app_key,
            "format": "wav",
            "sample_rate": 16000,
            "enable_punctuation_prediction": True,
            "enable_inverse_text_normalization": True,
        }
        response = requests.post(
            self._api_url, headers=headers, params=params, data=audio_data, timeout=30
        )
        result = response.json()
        if result.get("status") == 20000000:
            return result.get("result", "")
        return ""

    def is_available(self) -> bool:
        return bool(self._app_key and self._access_token)

    @property
    def name(self) -> str:
        return "阿里云"
