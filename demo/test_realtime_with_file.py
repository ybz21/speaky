#!/usr/bin/env python3
"""测试实时流式 ASR - 用文件模拟实时音频

测试连接管理器的性能优化效果
"""
import sys
import os
import time
import wave

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from speaky.engines.volc_bigmodel_engine import VolcBigModelEngine

def run_session(engine, frames, sample_rate, channels, sample_width, session_num=1):
    """运行一次识别会话"""
    print(f"\n{'='*50}")
    print(f"Session {session_num}")
    print('='*50)

    partial_count = 0
    start_time = time.time()

    def on_partial(text: str):
        nonlocal partial_count
        partial_count += 1
        elapsed = time.time() - start_time
        print(f"[{elapsed:.2f}s] Partial {partial_count}: {text}")

    def on_final(text: str):
        elapsed = time.time() - start_time
        print(f"[{elapsed:.2f}s] Final: {text}")

    def on_error(err: str):
        print(f"[Error] {err}")

    # Create real-time session
    session = engine.create_realtime_session(
        language="zh",
        on_partial=on_partial,
        on_final=on_final,
        on_error=on_error,
    )

    connect_start = time.time()
    session.start()
    connect_time = time.time() - connect_start
    print(f"Session started in {connect_time*1000:.0f}ms")

    # Send audio chunks
    bytes_per_sec = sample_rate * channels * sample_width
    chunk_size = bytes_per_sec * 100 // 1000  # 100ms

    for i in range(0, len(frames), chunk_size):
        chunk = frames[i:i + chunk_size]
        session.send_audio(chunk)
        time.sleep(0.1)

    result = session.finish()
    total_time = time.time() - start_time

    print(f"\nSession {session_num} complete:")
    print(f"  - Connect time: {connect_time*1000:.0f}ms")
    print(f"  - Total time: {total_time:.2f}s")
    print(f"  - Partial results: {partial_count}")
    print(f"  - Final: {result}")

    return connect_time, total_time


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

    # Pre-warm connection manager
    print("\nWarming up connection manager...")
    warm_start = time.time()
    engine.warmup()
    print(f"Warmup complete in {(time.time()-warm_start)*1000:.0f}ms")

    # Run multiple sessions to test connection reuse
    results = []
    for i in range(3):
        connect_time, total_time = run_session(
            engine, frames, sample_rate, channels, sample_width, i+1
        )
        results.append((connect_time, total_time))
        time.sleep(1)  # Brief pause between sessions

    # Summary
    print("\n" + "="*50)
    print("Performance Summary")
    print("="*50)
    for i, (ct, tt) in enumerate(results):
        print(f"Session {i+1}: connect={ct*1000:.0f}ms, total={tt:.2f}s")

    avg_connect = sum(r[0] for r in results) / len(results)
    print(f"\nAverage connect time: {avg_connect*1000:.0f}ms")


if __name__ == "__main__":
    main()
