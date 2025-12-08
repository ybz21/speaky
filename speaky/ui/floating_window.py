import logging
import math
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGraphicsDropShadowEffect, QScrollArea, QSizePolicy
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPointF, QRectF, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QLinearGradient, QRadialGradient, QPen, QFont, QBrush, QFontMetrics

from ..i18n import t

logger = logging.getLogger(__name__)


class SiriWaveWidget(QWidget):
    """Apple Siri-style animated waveform widget with glowing orb effect"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(280, 140)
        self._audio_level = 0.0
        self._target_audio_level = 0.0
        self._phase = 0.0
        self._is_animating = False
        self._mode = "recording"  # "recording", "recognizing", "done", "error", "idle"
        self._glow_intensity = 0.0
        self._pulse_phase = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)

        # Siri-style gradient colors
        self._mode_colors = {
            "recording": {
                "primary": QColor("#00D4FF"),      # Cyan
                "secondary": QColor("#00FF88"),    # Green
                "tertiary": QColor("#7B68EE"),     # Purple
                "glow": QColor("#00D4FF"),
            },
            "recognizing": {
                "primary": QColor("#FF6B6B"),      # Coral
                "secondary": QColor("#FFE66D"),    # Yellow
                "tertiary": QColor("#FF8E53"),     # Orange
                "glow": QColor("#FFB347"),
            },
            "done": {
                "primary": QColor("#00E676"),      # Green
                "secondary": QColor("#69F0AE"),    # Light green
                "tertiary": QColor("#00BFA5"),     # Teal
                "glow": QColor("#00E676"),
            },
            "error": {
                "primary": QColor("#FF5252"),      # Red
                "secondary": QColor("#FF8A80"),    # Light red
                "tertiary": QColor("#FF6E6E"),     # Pink red
                "glow": QColor("#FF5252"),
            },
            "idle": {
                "primary": QColor("#666666"),
                "secondary": QColor("#888888"),
                "tertiary": QColor("#AAAAAA"),
                "glow": QColor("#666666"),
            },
        }

    def set_audio_level(self, level: float):
        self._target_audio_level = min(1.0, max(0.0, level))

    def set_mode(self, mode: str):
        self._mode = mode
        self.update()

    def start_animation(self):
        self._is_animating = True
        self._timer.start(16)  # ~60 FPS for smooth animation

    def stop_animation(self):
        self._is_animating = False
        self._timer.stop()
        self._audio_level = 0.0
        self._target_audio_level = 0.0
        self.update()

    def _update_animation(self):
        # Smooth interpolation for audio level
        self._audio_level += (self._target_audio_level - self._audio_level) * 0.15

        # Phase animation
        self._phase += 0.08
        if self._phase > 2 * math.pi:
            self._phase -= 2 * math.pi

        # Pulse animation
        self._pulse_phase += 0.05
        if self._pulse_phase > 2 * math.pi:
            self._pulse_phase -= 2 * math.pi

        # Glow intensity
        self._glow_intensity = 0.5 + 0.5 * math.sin(self._pulse_phase)

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()
        center_x = w / 2
        center_y = h / 2

        colors = self._mode_colors.get(self._mode, self._mode_colors["idle"])

        # Draw outer glow
        self._draw_glow(painter, center_x, center_y, colors)

        # Draw the main orb/blob
        self._draw_orb(painter, center_x, center_y, colors)

        # Draw wave bars (Siri-style)
        self._draw_wave_bars(painter, center_x, center_y, colors)

    def _draw_glow(self, painter, cx, cy, colors):
        """Draw outer glow effect"""
        glow_color = colors["glow"]
        base_radius = 50 + self._audio_level * 20

        for i in range(5):
            radius = base_radius + i * 15
            alpha = int(40 * (1 - i / 5) * (0.5 + 0.5 * self._glow_intensity))

            gradient = QRadialGradient(cx, cy, radius)
            gradient.setColorAt(0, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), alpha))
            gradient.setColorAt(1, QColor(glow_color.red(), glow_color.green(), glow_color.blue(), 0))

            painter.setBrush(gradient)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), radius, radius)

    def _draw_orb(self, painter, cx, cy, colors):
        """Draw the central animated orb"""
        # Base radius affected by audio level
        base_radius = 35 + self._audio_level * 25

        # Create organic blob shape
        path = QPainterPath()
        num_points = 64

        for i in range(num_points + 1):
            angle = (i / num_points) * 2 * math.pi

            # Multiple wave frequencies for organic look
            wave1 = math.sin(angle * 3 + self._phase) * (3 + self._audio_level * 8)
            wave2 = math.sin(angle * 5 - self._phase * 1.5) * (2 + self._audio_level * 5)
            wave3 = math.sin(angle * 7 + self._phase * 0.8) * (1 + self._audio_level * 3)

            radius = base_radius + wave1 + wave2 + wave3

            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)

            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        path.closeSubpath()

        # Gradient fill
        gradient = QRadialGradient(cx - 10, cy - 10, base_radius * 1.5)
        gradient.setColorAt(0, QColor(255, 255, 255, 180))
        gradient.setColorAt(0.3, colors["primary"])
        gradient.setColorAt(0.6, colors["secondary"])
        gradient.setColorAt(1, colors["tertiary"])

        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)
        painter.drawPath(path)

        # Inner highlight
        highlight_radius = base_radius * 0.4
        highlight_gradient = QRadialGradient(cx - 8, cy - 8, highlight_radius)
        highlight_gradient.setColorAt(0, QColor(255, 255, 255, 120))
        highlight_gradient.setColorAt(1, QColor(255, 255, 255, 0))

        painter.setBrush(highlight_gradient)
        painter.drawEllipse(QPointF(cx - 5, cy - 5), highlight_radius, highlight_radius)

    def _draw_wave_bars(self, painter, cx, cy, colors):
        """Draw Siri-style frequency bars around the orb"""
        num_bars = 32
        bar_base_radius = 55 + self._audio_level * 15
        bar_width = 3

        for i in range(num_bars):
            angle = (i / num_bars) * 2 * math.pi - math.pi / 2

            # Different height based on position and audio
            height_factor = abs(math.sin(angle * 2 + self._phase))
            bar_height = 8 + height_factor * (15 + self._audio_level * 25)

            # Calculate bar position
            inner_radius = bar_base_radius
            outer_radius = bar_base_radius + bar_height

            x1 = cx + inner_radius * math.cos(angle)
            y1 = cy + inner_radius * math.sin(angle)
            x2 = cx + outer_radius * math.cos(angle)
            y2 = cy + outer_radius * math.sin(angle)

            # Color gradient along bar
            alpha = int(150 + 100 * height_factor)
            color = QColor(
                colors["primary"].red(),
                colors["primary"].green(),
                colors["primary"].blue(),
                alpha
            )

            pen = QPen(color)
            pen.setWidth(bar_width)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


class FloatingWindow(QWidget):
    closed = pyqtSignal()

    # Window size constants
    MIN_WIDTH = 360
    MAX_WIDTH = 500
    MIN_HEIGHT = 200
    MAX_HEIGHT = 400
    WAVE_HEIGHT = 140
    TEXT_PADDING = 40  # Padding for text area

    def __init__(self):
        super().__init__()
        self._audio_level = 0.0
        self._current_text = ""
        self._is_expanded = False
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMinimumSize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self.setMaximumSize(self.MAX_WIDTH, self.MAX_HEIGHT)
        self.resize(self.MIN_WIDTH, self.MIN_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(0)

        # Main container with glassmorphism effect
        self._container = QWidget()
        self._container.setObjectName("container")
        self._container.setStyleSheet("""
            QWidget#container {
                background-color: rgba(20, 20, 25, 235);
                border-radius: 24px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)

        # Add shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 8)
        self._container.setGraphicsEffect(shadow)

        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(20, 15, 20, 15)
        container_layout.setSpacing(6)

        # Status label - minimal, elegant
        self._status_label = QLabel("Listening...")
        self._status_label.setFont(QFont("SF Pro Display", 13, QFont.Medium))
        self._status_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.9);
            background: transparent;
            padding: 0;
        """)
        self._status_label.setAlignment(Qt.AlignCenter)
        self._status_label.setFixedHeight(24)
        container_layout.addWidget(self._status_label)

        # Siri wave widget - the star of the show
        self._wave_widget = SiriWaveWidget()
        container_layout.addWidget(self._wave_widget, alignment=Qt.AlignCenter)

        # Text container for results with smooth expansion
        self._text_container = QWidget()
        self._text_container.setStyleSheet("background: transparent;")
        text_container_layout = QVBoxLayout(self._text_container)
        text_container_layout.setContentsMargins(0, 0, 0, 0)
        text_container_layout.setSpacing(0)

        # Text label for results - elegant and subtle
        self._text_label = QLabel("")
        self._text_label.setFont(QFont("SF Pro Text", 12))
        self._text_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.85);
            background: transparent;
            padding: 8px 5px;
            line-height: 1.4;
        """)
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setWordWrap(True)
        self._text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        text_container_layout.addWidget(self._text_label)

        container_layout.addWidget(self._text_container)

        layout.addWidget(self._container)

    def _calculate_text_height(self, text: str) -> int:
        """Calculate required height for text"""
        if not text:
            return 0

        font = QFont("SF Pro Text", 12)
        metrics = QFontMetrics(font)
        # Available width for text (container width - padding)
        available_width = self.MIN_WIDTH - 60

        # Calculate wrapped text height
        rect = metrics.boundingRect(
            0, 0, available_width, 1000,
            Qt.AlignCenter | Qt.TextWordWrap,
            text
        )
        return rect.height() + 20  # Add padding

    def _adjust_window_size(self, text: str):
        """Smoothly adjust window size based on text length"""
        text_height = self._calculate_text_height(text)

        # Calculate new window height
        base_height = self.WAVE_HEIGHT + 60  # Wave + status + margins
        new_height = min(self.MAX_HEIGHT, max(self.MIN_HEIGHT, base_height + text_height))

        # Calculate new width if text is long
        if len(text) > 50:
            new_width = min(self.MAX_WIDTH, self.MIN_WIDTH + (len(text) - 50) * 2)
        else:
            new_width = self.MIN_WIDTH

        # Resize window
        if new_height != self.height() or new_width != self.width():
            self.resize(new_width, new_height)
            self._center_on_screen()

    def show_recording(self):
        logger.info("Showing recording window")
        self._current_text = ""
        self._status_label.setText(t("listening"))
        self._status_label.setStyleSheet("""
            color: #00D4FF;
            background: transparent;
            font-size: 14px;
            font-weight: 500;
        """)
        self._text_label.setText("")
        self._text_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.7);
            background: transparent;
        """)
        self._wave_widget.set_mode("recording")
        self._wave_widget.start_animation()
        # Reset to minimum size
        self.resize(self.MIN_WIDTH, self.MIN_HEIGHT)
        self._center_on_screen()
        self.show()
        self.raise_()
        logger.info(f"Window shown at position: {self.pos()}, visible: {self.isVisible()}")

    def show_recognizing(self):
        self._status_label.setText(t("recognizing"))
        self._status_label.setStyleSheet("""
            color: #FFB347;
            background: transparent;
            font-size: 14px;
            font-weight: 500;
        """)
        self._wave_widget.set_mode("recognizing")
        self._wave_widget.set_audio_level(0.5)

    def update_partial_result(self, text: str):
        """Update with partial/intermediate recognition result"""
        if text:
            self._current_text = text
            self._text_label.setText(text)
            self._text_label.setStyleSheet("""
                color: #FFE066;
                background: transparent;
                font-size: 12px;
            """)
            # Adjust window size for long text
            self._adjust_window_size(text)

    def show_result(self, text: str):
        logger.info(f"Showing result: {text}")
        self._current_text = text
        self._status_label.setText(t("done"))
        self._status_label.setStyleSheet("""
            color: #00E676;
            background: transparent;
            font-size: 14px;
            font-weight: 500;
        """)
        self._text_label.setText(text)
        self._text_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.95);
            background: transparent;
            font-size: 12px;
        """)
        self._wave_widget.set_mode("done")
        # Adjust window size for full text
        self._adjust_window_size(text)
        # Longer display time for longer text
        display_time = max(1500, min(4000, 1500 + len(text) * 20))
        QTimer.singleShot(display_time, self.hide)

    def show_error(self, error: str):
        self._status_label.setText(t("error"))
        self._status_label.setStyleSheet("""
            color: #FF5252;
            background: transparent;
            font-size: 14px;
            font-weight: 500;
        """)
        self._text_label.setText(error)
        self._text_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.7);
            background: transparent;
            font-size: 12px;
        """)
        self._wave_widget.set_mode("error")
        self._adjust_window_size(error)
        QTimer.singleShot(2500, self.hide)

    def update_audio_level(self, level: float):
        self._wave_widget.set_audio_level(level * 4)  # Amplify for visibility

    def _center_on_screen(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 100
        self.move(x, y)

    def hideEvent(self, event):
        self._wave_widget.stop_animation()
        # Reset size for next show
        self.resize(self.MIN_WIDTH, self.MIN_HEIGHT)
        super().hideEvent(event)
