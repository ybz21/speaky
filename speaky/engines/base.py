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

    def supports_realtime_streaming(self) -> bool:
        """Check if this engine supports real-time streaming (send audio while recording)."""
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

    def create_realtime_session(
        self,
        language: str = "zh",
        on_partial: Optional[Callable[[str], None]] = None,
        on_final: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ) -> "RealtimeSession":
        """
        Create a real-time streaming session.
        Audio can be sent while recording, results returned in real-time.

        Returns:
            A RealtimeSession object for sending audio data
        """
        raise NotImplementedError("Real-time streaming not supported by this engine")


class RealtimeSession:
    """Base class for real-time streaming ASR session."""

    def start(self):
        """Start the session (connect to server)."""
        raise NotImplementedError

    def send_audio(self, audio_data: bytes):
        """Send audio data chunk."""
        raise NotImplementedError

    def finish(self) -> str:
        """Signal end of audio and get final result."""
        raise NotImplementedError

    def cancel(self):
        """Cancel the session."""
        raise NotImplementedError
