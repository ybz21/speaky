import io
import tempfile
from typing import Optional
from .base import BaseEngine


class WhisperEngine(BaseEngine):
    def __init__(self, model_name: str = "base", device: str = "auto"):
        self._model_name = model_name
        self._device = device
        self._model = None

    def _load_model(self):
        if self._model is None:
            import whisper
            device = self._device
            if device == "auto":
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            self._model = whisper.load_model(self._model_name, device=device)

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        self._load_model()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            f.write(audio_data)
            f.flush()
            result = self._model.transcribe(f.name, language=language)
            return result.get("text", "").strip()

    def is_available(self) -> bool:
        try:
            import whisper
            return True
        except ImportError:
            return False

    @property
    def name(self) -> str:
        return "Whisper (Local)"
