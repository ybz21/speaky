#!/usr/bin/env python3
"""测试新的 Siri 风格 UI - 包含长文本测试"""
import sys
import os
import math

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from speaky.ui.floating_window import FloatingWindow

def main():
    app = QApplication(sys.argv)

    window = FloatingWindow()

    # Simulate recording state
    print("Showing recording state...")
    window.show_recording()

    # Simulate varying audio levels
    phase = 0
    def update_level():
        nonlocal phase
        phase += 0.1
        level = 0.3 + 0.5 * abs(math.sin(phase))
        window.update_audio_level(level)

    level_timer = QTimer()
    level_timer.timeout.connect(update_level)
    level_timer.start(50)

    # Simulate partial results with increasing text length
    def show_partial1():
        print("Showing partial result 1...")
        window.update_partial_result("今天")

    def show_partial2():
        print("Showing partial result 2...")
        window.update_partial_result("今天天气")

    def show_partial3():
        print("Showing partial result 3...")
        window.update_partial_result("今天天气真不错")

    def show_partial4():
        print("Showing partial result 4 (medium)...")
        window.update_partial_result("今天天气真不错，我想出去走走，看看外面的风景")

    def show_partial5():
        print("Showing partial result 5 (long)...")
        window.update_partial_result("今天天气真不错，我想出去走走，看看外面的风景。春天的花开得很美，空气中弥漫着花香的味道")

    def show_recognizing():
        print("Showing recognizing state...")
        window.show_recognizing()

    def show_result():
        print("Showing final result (long text)...")
        level_timer.stop()
        # 测试长文本
        long_text = "今天天气真不错，我想出去走走，看看外面的风景。春天的花开得很美，空气中弥漫着花香的味道。这真是一个适合散步的好日子。"
        window.show_result(long_text)

    QTimer.singleShot(1500, show_partial1)
    QTimer.singleShot(2500, show_partial2)
    QTimer.singleShot(3500, show_partial3)
    QTimer.singleShot(4500, show_partial4)
    QTimer.singleShot(5500, show_partial5)
    QTimer.singleShot(6500, show_recognizing)
    QTimer.singleShot(8000, show_result)

    # Quit after showing result (longer time for long text)
    QTimer.singleShot(14000, app.quit)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
