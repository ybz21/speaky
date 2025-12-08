#!/usr/bin/env python3
"""测试新的 Siri 风格 UI"""
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

    # Simulate partial results after 2 seconds
    def show_partial1():
        print("Showing partial result 1...")
        window.update_partial_result("你好")

    def show_partial2():
        print("Showing partial result 2...")
        window.update_partial_result("你好，世界")

    def show_partial3():
        print("Showing partial result 3...")
        window.update_partial_result("你好，世界！这是一个测试")

    def show_recognizing():
        print("Showing recognizing state...")
        window.show_recognizing()

    def show_result():
        print("Showing final result...")
        level_timer.stop()
        window.show_result("你好，世界！这是一个语音识别测试。")

    QTimer.singleShot(2000, show_partial1)
    QTimer.singleShot(3000, show_partial2)
    QTimer.singleShot(4000, show_partial3)
    QTimer.singleShot(5000, show_recognizing)
    QTimer.singleShot(6500, show_result)

    # Quit after showing result
    QTimer.singleShot(9000, app.quit)

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
