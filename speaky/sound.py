"""Sound notification system for recording feedback"""

import io
import math
import struct
import wave
import logging
import platform
import threading
from typing import Optional

logger = logging.getLogger(__name__)


def generate_beep(frequency: int = 800, duration_ms: int = 100, volume: float = 0.3) -> bytes:
    """Generate a simple beep sound as WAV data

    Args:
        frequency: Frequency in Hz (default 800)
        duration_ms: Duration in milliseconds (default 100)
        volume: Volume from 0.0 to 1.0 (default 0.3)

    Returns:
        WAV audio data as bytes
    """
    sample_rate = 16000
    num_samples = int(sample_rate * duration_ms / 1000)
    amplitude = int(32767 * volume)

    # Generate sine wave samples
    samples = []
    for i in range(num_samples):
        t = i / sample_rate
        # Apply fade in/out for smooth sound
        fade_samples = int(sample_rate * 0.01)  # 10ms fade
        fade = 1.0
        if i < fade_samples:
            fade = i / fade_samples
        elif i > num_samples - fade_samples:
            fade = (num_samples - i) / fade_samples
        sample = int(amplitude * fade * math.sin(2 * math.pi * frequency * t))
        samples.append(struct.pack('<h', sample))

    # Create WAV file in memory
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(samples))
    return buffer.getvalue()


class SoundPlayer:
    """Sound player for recording feedback notifications using PyAudio"""

    _instance: Optional["SoundPlayer"] = None

    def __init__(self):
        self._enabled = True
        self._start_wav: Optional[bytes] = None
        self._end_wav: Optional[bytes] = None
        self._error_wav: Optional[bytes] = None
        self._initialized = False
        self._pyaudio = None

    @classmethod
    def instance(cls) -> "SoundPlayer":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_enabled(self, enabled: bool):
        """Enable or disable sound notifications"""
        self._enabled = enabled
        logger.info(f"Sound notifications {'enabled' if enabled else 'disabled'}")

    def is_enabled(self) -> bool:
        """Check if sounds are enabled"""
        return self._enabled

    def _ensure_initialized(self):
        """Lazy initialization of sound data"""
        if self._initialized:
            return

        try:
            # Generate sound data (just keep in memory, no temp files)
            # Start sound: higher pitch, short beep
            self._start_wav = generate_beep(frequency=1000, duration_ms=80, volume=0.25)

            # End sound: lower pitch, slightly longer
            self._end_wav = generate_beep(frequency=600, duration_ms=100, volume=0.25)

            # Error sound: two short low beeps
            error_samples = []
            sample_rate = 16000
            for beep_num in range(2):
                for i in range(int(sample_rate * 0.08)):  # 80ms per beep
                    t = i / sample_rate
                    fade = 1.0
                    fade_samples = int(sample_rate * 0.01)
                    if i < fade_samples:
                        fade = i / fade_samples
                    elif i > int(sample_rate * 0.08) - fade_samples:
                        fade = (int(sample_rate * 0.08) - i) / fade_samples
                    sample = int(8000 * fade * math.sin(2 * math.pi * 400 * t))
                    error_samples.append(struct.pack('<h', sample))
                # Add 50ms silence between beeps
                if beep_num == 0:
                    for _ in range(int(sample_rate * 0.05)):
                        error_samples.append(struct.pack('<h', 0))

            error_buffer = io.BytesIO()
            with wave.open(error_buffer, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(b''.join(error_samples))
            self._error_wav = error_buffer.getvalue()

            self._initialized = True
            logger.info("Sound player initialized")

        except Exception as e:
            logger.error(f"Failed to initialize sounds: {e}")
            self._initialized = True  # Mark as initialized to avoid repeated attempts

    def _play_wav_async(self, wav_data: bytes):
        """Play WAV data asynchronously using PyAudio"""
        def play_thread():
            try:
                import pyaudio

                # Parse WAV data
                wav_io = io.BytesIO(wav_data)
                with wave.open(wav_io, 'rb') as wf:
                    if self._pyaudio is None:
                        self._pyaudio = pyaudio.PyAudio()

                    stream = self._pyaudio.open(
                        format=self._pyaudio.get_format_from_width(wf.getsampwidth()),
                        channels=wf.getnchannels(),
                        rate=wf.getframerate(),
                        output=True
                    )

                    # Read and play in chunks
                    chunk_size = 1024
                    data = wf.readframes(chunk_size)
                    while data:
                        stream.write(data)
                        data = wf.readframes(chunk_size)

                    stream.stop_stream()
                    stream.close()
            except Exception as e:
                logger.debug(f"Sound playback error (non-critical): {e}")

        # Run in background thread to not block
        threading.Thread(target=play_thread, daemon=True).start()

    def play_start(self):
        """Play recording start sound"""
        if not self._enabled:
            return
        self._ensure_initialized()
        if self._start_wav:
            self._play_wav_async(self._start_wav)

    def play_end(self):
        """Play recording end sound"""
        if not self._enabled:
            return
        self._ensure_initialized()
        if self._end_wav:
            self._play_wav_async(self._end_wav)

    def play_error(self):
        """Play error sound"""
        if not self._enabled:
            return
        self._ensure_initialized()
        if self._error_wav:
            self._play_wav_async(self._error_wav)

    def cleanup(self):
        """Clean up resources"""
        if self._pyaudio:
            try:
                self._pyaudio.terminate()
            except Exception:
                pass
            self._pyaudio = None


# Convenience functions
def play_start_sound():
    """Play recording start sound"""
    SoundPlayer.instance().play_start()


def play_end_sound():
    """Play recording end sound"""
    SoundPlayer.instance().play_end()


def play_error_sound():
    """Play error sound"""
    SoundPlayer.instance().play_error()


def set_sound_enabled(enabled: bool):
    """Enable or disable sound notifications"""
    SoundPlayer.instance().set_enabled(enabled)


def is_sound_enabled() -> bool:
    """Check if sounds are enabled"""
    return SoundPlayer.instance().is_enabled()
