import io
import wave
import threading
from typing import Callable, Optional
import pyaudio
import numpy as np

CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000


class AudioRecorder:
    def __init__(self):
        self._audio = pyaudio.PyAudio()
        self._stream: Optional[pyaudio.Stream] = None
        self._frames: list[bytes] = []
        self._is_recording = False
        self._lock = threading.Lock()
        self._on_audio_level: Optional[Callable[[float], None]] = None

    def set_audio_level_callback(self, callback: Callable[[float], None]):
        self._on_audio_level = callback

    def start(self):
        with self._lock:
            if self._is_recording:
                return
            self._frames = []
            self._is_recording = True
            self._stream = self._audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                stream_callback=self._callback,
            )
            self._stream.start_stream()

    def stop(self) -> bytes:
        with self._lock:
            if not self._is_recording:
                return b""
            self._is_recording = False
            if self._stream:
                self._stream.stop_stream()
                self._stream.close()
                self._stream = None
            return self._get_wav_data()

    def _callback(self, in_data, frame_count, time_info, status):
        if self._is_recording:
            self._frames.append(in_data)
            if self._on_audio_level:
                audio_data = np.frombuffer(in_data, dtype=np.int16)
                level = np.abs(audio_data).mean() / 32768.0
                self._on_audio_level(level)
        return (in_data, pyaudio.paContinue)

    def _get_wav_data(self) -> bytes:
        if not self._frames:
            return b""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(self._audio.get_sample_size(FORMAT))
            wf.setframerate(RATE)
            wf.writeframes(b"".join(self._frames))
        return buffer.getvalue()

    def get_audio_data(self) -> bytes:
        with self._lock:
            return self._get_wav_data()

    def is_recording(self) -> bool:
        return self._is_recording

    def close(self):
        self.stop()
        self._audio.terminate()
