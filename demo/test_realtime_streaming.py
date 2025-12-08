#!/usr/bin/env python3
"""测试实时流式 ASR - 边录边识别"""
import sys
import os
import time
import threading

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from speaky.engines.volc_bigmodel_engine import VolcBigModelEngine
from speaky.audio import AudioRecorder

def main():
    engine = VolcBigModelEngine(
        app_key='2400800346',
        access_key='q1QiLqqZ-v4nKhuZbjP-cZT7mCMNt9YW'
    )

    if not engine.supports_realtime_streaming():
        print("Engine does not support real-time streaming")
        return

    print("=" * 60)
    print("实时流式语音识别测试")
    print("说话时会实时显示识别结果")
    print("=" * 60)

    # Create recorder
    recorder = AudioRecorder()

    # Track results
    partial_count = 0
    final_result = None

    def on_partial(text: str):
        nonlocal partial_count
        partial_count += 1
        # Clear line and print partial result
        print(f"\r[实时] {text}" + " " * 20, end="", flush=True)

    def on_final(text: str):
        nonlocal final_result
        final_result = text
        print(f"\n[最终] {text}")

    def on_error(err: str):
        print(f"\n[错误] {err}")

    # Create real-time session
    session = engine.create_realtime_session(
        language="zh",
        on_partial=on_partial,
        on_final=on_final,
        on_error=on_error,
    )

    # Set up audio callback
    def on_audio_data(data: bytes):
        session.send_audio(data)

    recorder.set_audio_data_callback(on_audio_data)

    # Start session and recording
    print("\n按 Enter 开始录音...")
    input()

    print("开始录音，请说话... (3秒后自动停止)")
    session.start()
    recorder.start()

    # Record for 3 seconds
    time.sleep(3)

    # Stop recording and finish session
    print("\n停止录音...")
    recorder.stop()
    recorder.set_audio_data_callback(None)

    print("等待最终结果...")
    result = session.finish()

    print("\n" + "=" * 60)
    print(f"收到 {partial_count} 个中间结果")
    print(f"最终结果: {result}")
    print("=" * 60)

    recorder.close()

if __name__ == "__main__":
    main()
