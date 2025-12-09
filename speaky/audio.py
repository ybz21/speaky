import io
import wave
import time
import logging
import threading
from typing import Callable, Optional
from queue import Queue, Full
import pyaudio

logger = logging.getLogger(__name__)

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

        # Pre-opened stream for faster start
        self._warm_stream: Optional[pyaudio.Stream] = None
        self._warm_stream_ready = threading.Event()

    def set_audio_level_callback(self, callback: Callable[[float], None]):
        self._on_audio_level = callback

    def set_audio_data_callback(self, callback: Optional[Callable[[bytes], None]]):
        """Set callback for real-time audio data (for streaming ASR)"""
        self._on_audio_data = callback

    def warmup(self):
        """预热音频流，加速首次启动"""
        def do_warmup():
            t0 = time.time()
            try:
                logger.info("[录音器预热] 开始预热音频流...")
                stream = self._audio.open(
                    format=FORMAT,
                    channels=CHANNELS,
                    rate=RATE,
                    input=True,
                    frames_per_buffer=CHUNK,
                    stream_callback=self._warmup_callback,
                    start=False,  # 不立即启动
                )
                self._warm_stream = stream
                self._warm_stream_ready.set()
                logger.info(f"[录音器预热] 音频流就绪，耗时 {time.time()-t0:.2f}s")
            except Exception as e:
                logger.error(f"[录音器预热] 失败: {e}")

        threading.Thread(target=do_warmup, daemon=True).start()

    def _warmup_callback(self, in_data, frame_count, time_info, status):
        """预热流的空回调"""
        return (in_data, pyaudio.paContinue)

    def start(self):
        t0 = time.time()
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

            # 尝试使用预热的流
            if self._warm_stream_ready.is_set() and self._warm_stream:
                logger.info("[录音器] 使用预热的音频流")
                # 关闭预热流，重新打开（因为回调函数需要更换）
                try:
                    self._warm_stream.close()
                except:
                    pass
                self._warm_stream = None
                self._warm_stream_ready.clear()

            self._stream = self._audio.open(
                format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK,
                stream_callback=self._callback,
            )
            self._stream.start_stream()
            logger.info(f"[录音器] 启动完成，耗时 {time.time()-t0:.3f}s")

    def stop(self) -> bytes:
        t0 = time.time()
        with self._lock:
            if not self._is_recording:
                logger.info("[录音器] 停止调用，但未在录音")
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

            wav_data = self._get_wav_data()
            frame_count = len(self._frames)
            duration = frame_count * CHUNK / RATE if frame_count > 0 else 0
            logger.info(f"[录音器] 停止完成，录制 {frame_count} 帧，时长 {duration:.2f}s，数据 {len(wav_data)} 字节，耗时 {time.time()-t0:.3f}s")
            return wav_data

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
        chunk_count = 0
        total_bytes = 0
        while self._is_recording or not self._audio_queue.empty():
            try:
                data = self._audio_queue.get(timeout=0.1)
                if data is None:  # Stop signal
                    break
                if self._on_audio_data and self._is_recording:
                    chunk_count += 1
                    total_bytes += len(data)
                    self._on_audio_data(data)
            except:
                continue
        logger.info(f"[录音器] 音频回调线程结束，总共处理 {chunk_count} 个chunk，{total_bytes} 字节")

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
