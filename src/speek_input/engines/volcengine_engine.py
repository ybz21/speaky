import base64
import requests
from .base import BaseEngine


class VolcEngineEngine(BaseEngine):
    """火山引擎语音识别"""

    def __init__(self, app_id: str, access_token: str):
        self._app_id = app_id
        self._access_token = access_token
        self._api_url = "https://openspeech.bytedance.com/api/v1/auc"

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer; {self._access_token}",
        }
        payload = {
            "app": {"appid": self._app_id, "cluster": "volcengine_input_common"},
            "user": {"uid": "speek-input"},
            "audio": {
                "format": "wav",
                "rate": 16000,
                "bits": 16,
                "channel": 1,
                "language": "zh-CN" if language == "zh" else "en-US",
            },
            "request": {"reqid": "speek-input-request", "sequence": 1},
            "data": audio_base64,
        }
        response = requests.post(self._api_url, headers=headers, json=payload, timeout=30)
        result = response.json()
        if result.get("code") == 0:
            return result.get("result", "")
        return ""

    def is_available(self) -> bool:
        return bool(self._app_id and self._access_token)

    @property
    def name(self) -> str:
        return "火山引擎"
