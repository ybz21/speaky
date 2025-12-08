#!/usr/bin/env python3
"""测试实时流式 ASR - 用文件模拟实时音频"""
import sys
import os
import time
import wave

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from speaky.engines.volc_bigmodel_engine import VolcBigModelEngine

def main():
    engine = VolcBigModelEngine(
        app_key='2400800346',
        access_key='q1QiLqqZ-v4nKhuZbjP-cZT7mCMNt9YW'
    )

    audio_file = 'demo/recorded.wav'
    if not os.path.exists(audio_file):
        print(f"Audio file not found: {audio_file}")
        return

    # Read WAV file
    with wave.open(audio_file, 'rb') as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())

    print(f"Audio: {sample_rate}Hz, {channels}ch, {sample_width*8}bit, {len(frames)} bytes")

    # Track results
    partial_count = 0

    def on_partial(text: str):
        nonlocal partial_count
        partial_count += 1
        print(f"[Partial {partial_count}] {text}")

    def on_final(text: str):
        print(f"[Final] {text}")

    def on_error(err: str):
        print(f"[Error] {err}")

    # Create real-time session
    session = engine.create_realtime_session(
        language="zh",
        on_partial=on_partial,
        on_final=on_final,
        on_error=on_error,
    )

    print("Starting real-time session...")
    session.start()

    # Simulate real-time audio by sending chunks every ~100ms
    # chunk_size = bytes for 100ms of audio
    bytes_per_sec = sample_rate * channels * sample_width
    chunk_size = bytes_per_sec * 100 // 1000  # 100ms

    print(f"Sending audio in {chunk_size}-byte chunks (~100ms each)...")

    for i in range(0, len(frames), chunk_size):
        chunk = frames[i:i + chunk_size]
        session.send_audio(chunk)
        time.sleep(0.1)  # Simulate real-time

    print("Finishing session...")
    result = session.finish()

    print("-" * 50)
    print(f"Final result: {result}")
    print(f"Total partial results: {partial_count}")

if __name__ == "__main__":
    main()
