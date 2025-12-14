"""Sound notification system for recording feedback"""

import io
import math
import struct
import wave
import logging
from typing import Optional

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect

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
    """Sound player for recording feedback notifications"""

    _instance: Optional["SoundPlayer"] = None

    def __init__(self):
        self._enabled = True
        self._start_sound: Optional[QSoundEffect] = None
        self._end_sound: Optional[QSoundEffect] = None
        self._error_sound: Optional[QSoundEffect] = None
        self._initialized = False

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
        """Lazy initialization of sound effects"""
        if self._initialized:
            return

        import os
        import tempfile

        try:
            # Create temporary WAV files for sounds
            self._temp_dir = tempfile.mkdtemp(prefix="speaky_sounds_")

            # Start sound: higher pitch, short beep
            start_wav = generate_beep(frequency=1000, duration_ms=80, volume=0.25)
            start_path = os.path.join(self._temp_dir, "start.wav")
            with open(start_path, 'wb') as f:
                f.write(start_wav)
            self._start_sound = QSoundEffect()
            self._start_sound.setSource(QUrl.fromLocalFile(start_path))
            self._start_sound.setVolume(1.0)

            # End sound: lower pitch, slightly longer
            end_wav = generate_beep(frequency=600, duration_ms=100, volume=0.25)
            end_path = os.path.join(self._temp_dir, "end.wav")
            with open(end_path, 'wb') as f:
                f.write(end_wav)
            self._end_sound = QSoundEffect()
            self._end_sound.setSource(QUrl.fromLocalFile(end_path))
            self._end_sound.setVolume(1.0)

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

            error_path = os.path.join(self._temp_dir, "error.wav")
            with open(error_path, 'wb') as f:
                f.write(error_buffer.getvalue())
            self._error_sound = QSoundEffect()
            self._error_sound.setSource(QUrl.fromLocalFile(error_path))
            self._error_sound.setVolume(1.0)

            self._initialized = True
            logger.info("Sound player initialized")

        except Exception as e:
            logger.error(f"Failed to initialize sounds: {e}")
            self._initialized = True  # Mark as initialized to avoid repeated attempts

    def play_start(self):
        """Play recording start sound"""
        if not self._enabled:
            return
        self._ensure_initialized()
        if self._start_sound:
            self._start_sound.play()

    def play_end(self):
        """Play recording end sound"""
        if not self._enabled:
            return
        self._ensure_initialized()
        if self._end_sound:
            self._end_sound.play()

    def play_error(self):
        """Play error sound"""
        if not self._enabled:
            return
        self._ensure_initialized()
        if self._error_sound:
            self._error_sound.play()

    def cleanup(self):
        """Clean up temporary files"""
        import shutil
        if hasattr(self, '_temp_dir'):
            try:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
            except Exception:
                pass


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
