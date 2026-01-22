"""Audio recording module using miniaudio for cross-platform support.

miniaudio provides zero-dependency audio capture:
- macOS: CoreAudio
- Windows: WASAPI
- Linux: PulseAudio/ALSA (system built-in)
"""

import io
import wave
import time
import logging
import threading
from typing import Callable, Optional, List, Tuple
from queue import Queue, Full, Empty

import miniaudio

logger = logging.getLogger(__name__)

# Audio format constants
CHUNK = 1024
SAMPLE_FORMAT = miniaudio.SampleFormat.SIGNED16
CHANNELS = 1
RATE = 16000
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes


class AudioRecorder:
    """Cross-platform audio recorder using miniaudio."""

    def __init__(self, device_index: Optional[int] = None, gain: float = 1.0):
        self._device_id: Optional[miniaudio.DeviceId] = None
        self._device_index: Optional[int] = device_index
        self._gain: float = gain

        self._capture: Optional[miniaudio.CaptureDevice] = None
        self._frames: List[bytes] = []
        self._is_recording = False
        self._lock = threading.Lock()

        self._on_audio_level: Optional[Callable[[float], None]] = None
        self._on_audio_data: Optional[Callable[[bytes], None]] = None

        # Non-blocking queue for audio data
        self._audio_queue: Queue = Queue(maxsize=100)
        self._worker_thread: Optional[threading.Thread] = None
        self._level_counter = 0

        # Silence detection
        self._max_level: float = 0.0
        self._silence_threshold: float = 0.005

        # Cache device list
        self._cached_devices: Optional[List[Tuple[int, str]]] = None

    def _get_devices(self) -> List[dict]:
        """Get list of capture devices from miniaudio."""
        devices = miniaudio.Devices()
        return devices.get_captures()

    def get_input_devices(self) -> List[Tuple[int, str]]:
        """Get all available input devices.

        Returns:
            list of (device_index, device_name) tuples
        """
        if self._cached_devices is not None:
            return self._cached_devices

        devices = []
        try:
            capture_devices = self._get_devices()
            for i, dev in enumerate(capture_devices):
                name = dev.get("name", f"Device {i}")
                devices.append((i, name))
            self._cached_devices = devices
        except Exception as e:
            logger.error(f"Failed to get input devices: {e}")

        return devices

    def get_default_input_device(self) -> Optional[int]:
        """Get default input device index."""
        # miniaudio uses None for default device
        return None

    def set_device(self, device_index: Optional[int]):
        """Set recording device.

        Args:
            device_index: Device index, None for default device
        """
        self._device_index = device_index
        self._device_id = None

        if device_index is not None:
            try:
                capture_devices = self._get_devices()
                if 0 <= device_index < len(capture_devices):
                    self._device_id = capture_devices[device_index].get("id")
            except Exception as e:
                logger.error(f"Failed to set device: {e}")

        logger.info(f"Audio device set to: {device_index}")

    def set_gain(self, gain: float):
        """Set recording gain.

        Args:
            gain: Gain multiplier, 1.0 = original volume
        """
        self._gain = max(0.1, min(5.0, gain))
        logger.info(f"Audio gain set to: {self._gain}")

    def set_audio_level_callback(self, callback: Callable[[float], None]):
        """Set callback for audio level updates."""
        self._on_audio_level = callback

    def set_audio_data_callback(self, callback: Optional[Callable[[bytes], None]]):
        """Set callback for real-time audio data (for streaming ASR)."""
        self._on_audio_data = callback

    def warmup(self):
        """Pre-warm audio system for faster first start."""
        def do_warmup():
            t0 = time.time()
            try:
                logger.info("[Recorder warmup] Starting...")
                # Just enumerate devices to warm up the audio subsystem
                _ = self._get_devices()
                logger.info(f"[Recorder warmup] Done in {time.time()-t0:.2f}s")
            except Exception as e:
                logger.error(f"[Recorder warmup] Failed: {e}")

        threading.Thread(target=do_warmup, daemon=True).start()

    def start(self):
        """Start recording."""
        t0 = time.time()
        with self._lock:
            if self._is_recording:
                return

            self._frames = []
            self._is_recording = True
            self._level_counter = 0
            self._max_level = 0.0

            # Start worker thread for processing audio
            if self._on_audio_data:
                self._worker_thread = threading.Thread(
                    target=self._process_audio_queue, daemon=True
                )
                self._worker_thread.start()

            # Create capture device
            try:
                self._capture = miniaudio.CaptureDevice(
                    device_id=self._device_id,
                    sample_rate=RATE,
                    nchannels=CHANNELS,
                    output_format=SAMPLE_FORMAT,
                    buffersize_msec=int(CHUNK * 1000 / RATE),
                )
                self._capture.start(self._audio_callback)
                logger.info(f"[Recorder] Started in {time.time()-t0:.3f}s")
            except Exception as e:
                logger.error(f"[Recorder] Failed to start: {e}")
                self._is_recording = False
                raise

    def stop(self) -> bytes:
        """Stop recording and return WAV data."""
        t0 = time.time()
        with self._lock:
            if not self._is_recording:
                logger.info("[Recorder] Stop called but not recording")
                return b""

            self._is_recording = False

            if self._capture:
                try:
                    self._capture.stop()
                    self._capture.close()
                except Exception as e:
                    logger.warning(f"[Recorder] Error stopping capture: {e}")
                self._capture = None

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
                except Empty:
                    break

            wav_data = self._get_wav_data()
            frame_count = len(self._frames)
            duration = sum(len(f) for f in self._frames) / (RATE * SAMPLE_WIDTH) if frame_count > 0 else 0
            logger.info(f"[Recorder] Stopped, {frame_count} frames, {duration:.2f}s, {len(wav_data)} bytes, took {time.time()-t0:.3f}s")
            return wav_data

    def _apply_gain(self, data: bytes) -> bytes:
        """Apply gain to audio data."""
        if self._gain == 1.0:
            return data

        result = bytearray(len(data))
        for i in range(0, len(data) - 1, 2):
            sample = int.from_bytes(data[i:i+2], byteorder='little', signed=True)
            sample = int(sample * self._gain)
            sample = max(-32768, min(32767, sample))
            result[i:i+2] = sample.to_bytes(2, byteorder='little', signed=True)
        return bytes(result)

    def _audio_callback(self, data: bytes):
        """Audio capture callback - must be fast."""
        if not self._is_recording:
            return

        # Apply gain
        processed_data = self._apply_gain(data)
        self._frames.append(processed_data)

        # Compute audio level every 4 callbacks
        self._level_counter += 1
        if self._level_counter >= 4:
            self._level_counter = 0
            level = self._fast_level(processed_data)
            if level > self._max_level:
                self._max_level = level
            if self._on_audio_level:
                self._on_audio_level(level)

        # Queue audio data for ASR
        if self._on_audio_data:
            try:
                self._audio_queue.put_nowait(processed_data)
            except Full:
                pass

    def _fast_level(self, data: bytes) -> float:
        """Fast audio level calculation."""
        samples = []
        for i in range(0, len(data) - 1, 16):
            val = int.from_bytes(data[i:i+2], byteorder='little', signed=True)
            samples.append(abs(val))
        if samples:
            return sum(samples) / len(samples) / 32768.0
        return 0.0

    def _process_audio_queue(self):
        """Worker thread to process audio data."""
        chunk_count = 0
        total_bytes = 0
        while self._is_recording or not self._audio_queue.empty():
            try:
                data = self._audio_queue.get(timeout=0.1)
                if data is None:
                    break
                if self._on_audio_data and self._is_recording:
                    chunk_count += 1
                    total_bytes += len(data)
                    level = self._fast_level(data)
                    if level > self._max_level:
                        self._max_level = level
                    self._on_audio_data(data)
            except Empty:
                continue
            except Exception:
                continue
        logger.info(f"[Recorder] Audio worker done, {chunk_count} chunks, {total_bytes} bytes, max_level={self._max_level:.4f}")

    def _get_wav_data(self) -> bytes:
        """Convert raw frames to WAV format."""
        if not self._frames:
            return b""

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(RATE)
            wf.writeframes(b"".join(self._frames))
        return buffer.getvalue()

    def get_audio_data(self) -> bytes:
        """Get current recorded audio as WAV data."""
        with self._lock:
            return self._get_wav_data()

    def is_recording(self) -> bool:
        """Check if currently recording."""
        return self._is_recording

    def is_silent(self) -> bool:
        """Check if recording is silent."""
        return self._max_level < self._silence_threshold

    def get_max_level(self) -> float:
        """Get maximum audio level during recording."""
        return self._max_level

    def close(self):
        """Close and cleanup resources."""
        self.stop()
