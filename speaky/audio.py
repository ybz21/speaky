import io
import wave
import threading
from typing import Callable, Optional
from queue import Queue, Full
import pyaudio

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
        self._on_audio_data: Optional[Callable[[bytes], None]] = None

        # Non-blocking queue for audio data to avoid callback blocking
        self._audio_queue: Queue = Queue(maxsize=100)
        self._worker_thread: Optional[threading.Thread] = None
        self._level_counter = 0  # Only compute level every N frames

    def set_audio_level_callback(self, callback: Callable[[float], None]):
        self._on_audio_level = callback

    def set_audio_data_callback(self, callback: Optional[Callable[[bytes], None]]):
        """Set callback for real-time audio data (for streaming ASR)"""
        self._on_audio_data = callback

    def start(self):
        with self._lock:
            if self._is_recording:
                return
            self._frames = []
            self._is_recording = True
            self._level_counter = 0

            # Start worker thread for processing audio
            if self._on_audio_data:
                self._worker_thread = threading.Thread(
                    target=self._process_audio_queue, daemon=True
                )
                self._worker_thread.start()

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

            # Signal worker thread to stop
            try:
                self._audio_queue.put_nowait(None)
            except Full:
                pass

            if self._worker_thread:
                self._worker_thread.join(timeout=1)
                self._worker_thread = None

            # Clear queue
            while not self._audio_queue.empty():
                try:
                    self._audio_queue.get_nowait()
                except:
                    break

            return self._get_wav_data()

    def _callback(self, in_data, frame_count, time_info, status):
        """Audio callback - must be fast and non-blocking"""
        if self._is_recording:
            self._frames.append(in_data)

            # Compute audio level only every 4 frames to reduce CPU
            if self._on_audio_level:
                self._level_counter += 1
                if self._level_counter >= 4:
                    self._level_counter = 0
                    # Fast level calculation without numpy
                    level = self._fast_level(in_data)
                    self._on_audio_level(level)

            # Queue audio data non-blocking for ASR
            if self._on_audio_data:
                try:
                    self._audio_queue.put_nowait(in_data)
                except Full:
                    pass  # Drop frame if queue full

        return (in_data, pyaudio.paContinue)

    def _fast_level(self, data: bytes) -> float:
        """Fast audio level calculation without numpy"""
        # Sample every 8th value for speed
        samples = []
        for i in range(0, len(data) - 1, 16):  # 16 bytes = 8 samples
            val = int.from_bytes(data[i:i+2], byteorder='little', signed=True)
            samples.append(abs(val))
        if samples:
            return sum(samples) / len(samples) / 32768.0
        return 0.0

    def _process_audio_queue(self):
        """Worker thread to process audio data without blocking callback"""
        while self._is_recording or not self._audio_queue.empty():
            try:
                data = self._audio_queue.get(timeout=0.1)
                if data is None:  # Stop signal
                    break
                if self._on_audio_data and self._is_recording:
                    self._on_audio_data(data)
            except:
                continue

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
