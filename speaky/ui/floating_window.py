import logging
import math
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QLinearGradient

from ..i18n import t

logger = logging.getLogger(__name__)


class WaveWidget(QWidget):
    """Siri-style animated waveform widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self._audio_level = 0.0
        self._phase = 0.0
        self._is_animating = False
        self._mode = "recording"  # "recording", "recognizing", "idle"

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)

        # Wave colors for different modes
        self._colors = {
            "recording": [QColor("#4CAF50"), QColor("#81C784"), QColor("#A5D6A7")],
            "recognizing": [QColor("#FFC107"), QColor("#FFD54F"), QColor("#FFE082")],
            "idle": [QColor("#666"), QColor("#888"), QColor("#AAA")],
        }

    def set_audio_level(self, level: float):
        self._audio_level = min(1.0, max(0.0, level))
        if not self._is_animating:
            self.update()

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def start_animation(self):
        self._is_animating = True
        self._timer.start(30)  # ~33 FPS

    def stop_animation(self):
        self._is_animating = False
        self._timer.stop()
        self._audio_level = 0.0
        self.update()

    def _update_animation(self):
        self._phase += 0.15
        if self._phase > 2 * math.pi:
            self._phase -= 2 * math.pi
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        center_y = h / 2

        colors = self._colors.get(self._mode, self._colors["idle"])

        # Draw multiple wave layers
        for i, color in enumerate(colors):
            self._draw_wave(painter, w, h, center_y, color, i)

    def _draw_wave(self, painter, w, h, center_y, color, layer_index):
        path = QPainterPath()

        # Wave parameters
        if self._mode == "recording":
            # Audio-reactive wave
            amplitude = 5 + self._audio_level * 15
            frequency = 0.03 + layer_index * 0.01
            phase_offset = layer_index * 0.5
        else:
            # Smooth animated wave for recognizing
            amplitude = 8 + math.sin(self._phase + layer_index) * 4
            frequency = 0.02 + layer_index * 0.008
            phase_offset = layer_index * 0.8

        # Start path
        path.moveTo(0, center_y)

        # Draw wave
        for x in range(w + 1):
            y = center_y + amplitude * math.sin(frequency * x + self._phase + phase_offset)
            if x == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        # Set pen with gradient
        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 50))
        gradient.setColorAt(0.5, QColor(color.red(), color.green(), color.blue(), 200))
        gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 50))

        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.NoBrush)

        from PyQt5.QtGui import QPen
        pen = QPen(color)
        pen.setWidth(max(1, 2 - layer_index))
        painter.setPen(pen)
        painter.drawPath(path)


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
        self.setFixedSize(320, 120)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                background-color: rgba(30, 30, 30, 240);
                border-radius: 12px;
            }
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(8)

        self._status_label = QLabel("Listening...")
        self._status_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        self._status_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self._status_label)

        # Wave widget instead of progress bar
        self._wave_widget = WaveWidget()
        container_layout.addWidget(self._wave_widget)

        self._text_label = QLabel("")
        self._text_label.setStyleSheet("color: #aaa; font-size: 12px;")
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setWordWrap(True)
        self._text_label.setMaximumHeight(30)
        container_layout.addWidget(self._text_label)

        layout.addWidget(container)

    def show_recording(self):
        logger.info("Showing recording window")
        self._status_label.setText(t("listening"))
        self._status_label.setStyleSheet("color: #4CAF50; font-size: 14px; font-weight: bold;")
        self._text_label.setText("")
        self._wave_widget.set_mode("recording")
        self._wave_widget.start_animation()
        self._center_on_screen()
        self.show()
        self.raise_()
        self.activateWindow()
        logger.info(f"Window shown at position: {self.pos()}, visible: {self.isVisible()}")

    def show_recognizing(self):
        self._status_label.setText(t("recognizing"))
        self._status_label.setStyleSheet("color: #FFC107; font-size: 14px; font-weight: bold;")
        self._wave_widget.set_mode("recognizing")
        self._wave_widget.set_audio_level(0.5)

    def show_result(self, text: str):
        logger.info(f"Showing result: {text}")
        self._status_label.setText(t("done"))
        self._status_label.setStyleSheet("color: #2196F3; font-size: 14px; font-weight: bold;")
        self._text_label.setText(text[:50] + "..." if len(text) > 50 else text)
        self._wave_widget.stop_animation()
        self._wave_widget.set_mode("idle")
        QTimer.singleShot(1500, self.hide)

    def show_error(self, error: str):
        self._status_label.setText(t("error"))
        self._status_label.setStyleSheet("color: #F44336; font-size: 14px; font-weight: bold;")
        self._text_label.setText(error)
        self._wave_widget.stop_animation()
        self._wave_widget.set_mode("idle")
        QTimer.singleShot(2000, self.hide)

    def update_audio_level(self, level: float):
        self._wave_widget.set_audio_level(level * 3)  # Amplify for visibility

    def _center_on_screen(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 100
        self.move(x, y)

    def hideEvent(self, event):
        self._wave_widget.stop_animation()
        super().hideEvent(event)
