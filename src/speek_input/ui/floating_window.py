from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QProgressBar
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QFont


class FloatingWindow(QWidget):
    closed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._setup_ui()
        self._audio_level = 0.0

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(300, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: rgba(40, 40, 40, 230);
                border-radius: 10px;
            }
        """)
        container_layout = QVBoxLayout(container)

        self._status_label = QLabel("正在录音...")
        self._status_label.setStyleSheet("color: white; font-size: 14px;")
        self._status_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self._status_label)

        self._level_bar = QProgressBar()
        self._level_bar.setRange(0, 100)
        self._level_bar.setValue(0)
        self._level_bar.setTextVisible(False)
        self._level_bar.setFixedHeight(8)
        self._level_bar.setStyleSheet("""
            QProgressBar {
                background-color: #333;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
        """)
        container_layout.addWidget(self._level_bar)

        self._text_label = QLabel("")
        self._text_label.setStyleSheet("color: #aaa; font-size: 12px;")
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setWordWrap(True)
        container_layout.addWidget(self._text_label)

        layout.addWidget(container)

    def show_recording(self):
        self._status_label.setText("正在录音...")
        self._status_label.setStyleSheet("color: #4CAF50; font-size: 14px;")
        self._text_label.setText("")
        self._center_on_screen()
        self.show()

    def show_recognizing(self):
        self._status_label.setText("识别中...")
        self._status_label.setStyleSheet("color: #FFC107; font-size: 14px;")
        self._level_bar.setValue(0)

    def show_result(self, text: str):
        self._status_label.setText("识别完成")
        self._status_label.setStyleSheet("color: #2196F3; font-size: 14px;")
        self._text_label.setText(text[:50] + "..." if len(text) > 50 else text)
        QTimer.singleShot(1500, self.hide)

    def show_error(self, error: str):
        self._status_label.setText("识别失败")
        self._status_label.setStyleSheet("color: #F44336; font-size: 14px;")
        self._text_label.setText(error)
        QTimer.singleShot(2000, self.hide)

    def update_audio_level(self, level: float):
        self._level_bar.setValue(int(level * 100))

    def _center_on_screen(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 100
        self.move(x, y)
