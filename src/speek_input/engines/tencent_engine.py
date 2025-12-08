import base64
import hashlib
import hmac
import json
import time
import requests
from .base import BaseEngine


class TencentEngine(BaseEngine):
    """腾讯云语音识别"""

    def __init__(self, secret_id: str, secret_key: str):
        self._secret_id = secret_id
        self._secret_key = secret_key
        self._api_url = "https://asr.tencentcloudapi.com"

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        timestamp = int(time.time())
        audio_base64 = base64.b64encode(audio_data).decode("utf-8")
        params = {
            "ProjectId": 0,
            "SubServiceType": 2,
            "EngSerViceType": "16k_zh" if language == "zh" else "16k_en",
            "SourceType": 1,
            "VoiceFormat": "wav",
            "UsrAudioKey": "speek-input",
            "Data": audio_base64,
            "DataLen": len(audio_data),
        }
        headers = self._sign_request(params, timestamp)
        response = requests.post(
            self._api_url, headers=headers, json=params, timeout=30
        )
        result = response.json()
        if "Response" in result and "Result" in result["Response"]:
            return result["Response"]["Result"]
        return ""

    def _sign_request(self, params: dict, timestamp: int) -> dict:
        service = "asr"
        host = "asr.tencentcloudapi.com"
        algorithm = "TC3-HMAC-SHA256"
        date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))

        canonical_uri = "/"
        canonical_querystring = ""
        payload = json.dumps(params)
        canonical_headers = f"content-type:application/json\nhost:{host}\n"
        signed_headers = "content-type;host"
        hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        canonical_request = f"POST\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_payload}"

        credential_scope = f"{date}/{service}/tc3_request"
        hashed_request = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
        string_to_sign = f"{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_request}"

        def sign(key, msg):
            return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

        secret_date = sign(("TC3" + self._secret_key).encode("utf-8"), date)
        secret_service = sign(secret_date, service)
        secret_signing = sign(secret_service, "tc3_request")
        signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

        authorization = f"{algorithm} Credential={self._secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

        return {
            "Content-Type": "application/json",
            "Host": host,
            "X-TC-Action": "SentenceRecognition",
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Version": "2019-06-14",
            "X-TC-Region": "ap-shanghai",
            "Authorization": authorization,
        }

    def is_available(self) -> bool:
        return bool(self._secret_id and self._secret_key)

    @property
    def name(self) -> str:
        return "腾讯云"
