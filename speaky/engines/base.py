from abc import ABC, abstractmethod
from typing import Optional


class BaseEngine(ABC):
    @abstractmethod
    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        """Transcribe audio data to text."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the engine is properly configured and available."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine display name."""
        pass
