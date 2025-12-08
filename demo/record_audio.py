#!/usr/bin/env python3
"""录制音频用于测试 - 使用 ffmpeg"""
import subprocess
import sys

RECORD_SECONDS = 5
OUTPUT_FILE = "demo/recorded.wav"

def main():
    print(f"开始录音 {RECORD_SECONDS} 秒，请说话...")

    # 使用 ffmpeg 从默认麦克风录制
    # Linux: 使用 pulse 或 alsa
    # macOS: 使用 avfoundation
    # Windows: 使用 dshow

    import platform
    system = platform.system()

    if system == "Linux":
        input_device = ["-f", "pulse", "-i", "default"]
    elif system == "Darwin":
        input_device = ["-f", "avfoundation", "-i", ":0"]
    else:  # Windows
        input_device = ["-f", "dshow", "-i", "audio=@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{00000000-0000-0000-0000-000000000000}"]

    cmd = [
        "ffmpeg", "-y",
        *input_device,
        "-t", str(RECORD_SECONDS),
        "-ar", "16000",
        "-ac", "1",
        "-acodec", "pcm_s16le",
        OUTPUT_FILE
    ]

    try:
        subprocess.run(cmd, check=True)
        print(f"\n录音完成! 已保存到: {OUTPUT_FILE}")
    except subprocess.CalledProcessError as e:
        print(f"录音失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
