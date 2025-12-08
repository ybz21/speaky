#!/usr/bin/env python3
"""测试流式 ASR 输出效果"""
import asyncio
import sys
import os

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

    with open(audio_file, 'rb') as f:
        audio_data = f.read()

    print(f"Audio file size: {len(audio_data)} bytes")
    print("Starting streaming recognition...")
    print("-" * 50)

    partial_count = 0

    def on_partial(text: str):
        nonlocal partial_count
        partial_count += 1
        print(f"[Partial {partial_count}] {text}")

    result = engine.transcribe_streaming(audio_data, on_partial=on_partial)

    print("-" * 50)
    print(f"Final result: {result}")
    print(f"Total partial results: {partial_count}")

if __name__ == "__main__":
    main()
