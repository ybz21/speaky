from abc import ABC, abstractmethod
from typing import Optional, Callable, AsyncIterator


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

    def supports_streaming(self) -> bool:
        """Check if this engine supports streaming ASR."""
        return False

    def transcribe_streaming(
        self,
        audio_data: bytes,
        language: str = "zh",
        on_partial: Optional[Callable[[str], None]] = None,
    ) -> str:
        """
        Transcribe audio data with streaming support.

        Args:
            audio_data: Audio data bytes
            language: Recognition language
            on_partial: Callback for partial/intermediate results

        Returns:
            Final transcription text
        """
        # Default implementation falls back to non-streaming
        return self.transcribe(audio_data, language)
