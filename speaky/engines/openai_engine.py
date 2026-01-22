import io
from speaky.engines.base import BaseEngine


class OpenAIEngine(BaseEngine):
    def __init__(self, api_key: str, model: str = "whisper-1", base_url: str = "https://api.openai.com/v1"):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        from openai import OpenAI
        client = OpenAI(api_key=self._api_key, base_url=self._base_url)
        audio_file = io.BytesIO(audio_data)
        audio_file.name = "audio.wav"
        response = client.audio.transcriptions.create(
            model=self._model,
            file=audio_file,
            language=language,
        )
        return response.text.strip()

    def is_available(self) -> bool:
        return bool(self._api_key)

    @property
    def name(self) -> str:
        return "OpenAI Whisper API"
