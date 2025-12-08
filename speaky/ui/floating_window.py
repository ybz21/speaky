import logging
import math
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGraphicsDropShadowEffect, QScrollArea, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QPointF
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QRadialGradient, QPen, QFont

from ..i18n import t

logger = logging.getLogger(__name__)


class WaveOrbWidget(QWidget):
    """Optimized animated orb widget with smooth color transitions"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 150)  # Adjusted for 1.5x height
        self._audio_level = 0.0
        self._target_level = 0.0
        self._phase = 0.0
        self._is_animating = False
        self._mode = "recording"

        # Color transition support
        self._current_primary = QColor("#00D4FF")
        self._current_secondary = QColor("#00FF88")
        self._target_primary = QColor("#00D4FF")
        self._target_secondary = QColor("#00FF88")

        # Use faster timer interval (30fps instead of 60fps for less CPU)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update)

        # Pre-computed colors to avoid creating objects each frame
        self._colors = {
            "recording": (QColor("#00D4FF"), QColor("#00FF88")),
            "recognizing": (QColor("#FFB347"), QColor("#FF6B6B")),
            "done": (QColor("#00E676"), QColor("#69F0AE")),
            "error": (QColor("#FF5252"), QColor("#FF8A80")),
            "idle": (QColor("#666666"), QColor("#888888")),
        }

    def set_audio_level(self, level: float):
        self._target_level = min(1.0, max(0.0, level))

    def set_mode(self, mode: str):
        self._mode = mode
        # Set target colors for smooth transition
        colors = self._colors.get(mode, self._colors["idle"])
        self._target_primary, self._target_secondary = colors
        self.update()

    def start_animation(self):
        if not self._is_animating:
            self._is_animating = True
            self._timer.start(33)  # ~30 FPS

    def stop_animation(self):
        self._is_animating = False
        self._timer.stop()
        self._audio_level = 0.0
        self._target_level = 0.0
        self.update()

    def _lerp_color(self, c1: QColor, c2: QColor, t: float) -> QColor:
        """Linear interpolation between two colors"""
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
            int(c1.alpha() + (c2.alpha() - c1.alpha()) * t)
        )

    def _update(self):
        # Smooth interpolation for audio level
        self._audio_level += (self._target_level - self._audio_level) * 0.2

        # Smooth color transition (slower for visual effect)
        self._current_primary = self._lerp_color(self._current_primary, self._target_primary, 0.15)
        self._current_secondary = self._lerp_color(self._current_secondary, self._target_secondary, 0.15)

        self._phase += 0.12
        if self._phase > 6.283:  # 2*pi
            self._phase -= 6.283
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2

        # Use smoothly interpolated colors
        primary = self._current_primary
        secondary = self._current_secondary

        # Simple glow (just 2 layers instead of 5)
        base_r = 38 + self._audio_level * 15  # Scaled for 1.5x
        for i in range(2):
            r = base_r + i * 18  # Scaled for 1.5x
            alpha = int(50 * (1 - i * 0.5))
            gradient = QRadialGradient(cx, cy, r)
            gradient.setColorAt(0, QColor(primary.red(), primary.green(), primary.blue(), alpha))
            gradient.setColorAt(1, QColor(primary.red(), primary.green(), primary.blue(), 0))
            painter.setBrush(gradient)
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # Main orb with simple wave deformation (fewer points)
        path = QPainterPath()
        num_points = 24  # Reduced from 64
        orb_r = 30 + self._audio_level * 18  # Scaled for 1.5x

        for i in range(num_points + 1):
            angle = (i / num_points) * 6.283
            # Simpler wave calculation
            wave = math.sin(angle * 3 + self._phase) * (2 + self._audio_level * 6)
            r = orb_r + wave
            x = cx + r * math.cos(angle)
            y = cy + r * math.sin(angle)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        path.closeSubpath()

        # Gradient fill
        gradient = QRadialGradient(cx - 5, cy - 5, orb_r * 1.2)
        gradient.setColorAt(0, QColor(255, 255, 255, 200))
        gradient.setColorAt(0.4, primary)
        gradient.setColorAt(1, secondary)
        painter.setBrush(gradient)
        painter.drawPath(path)

        # Simple bars (only 12 instead of 32)
        num_bars = 12
        bar_r = orb_r + 8 + self._audio_level * 5
        pen = QPen(primary)
        pen.setWidth(2)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        for i in range(num_bars):
            angle = (i / num_bars) * 6.283 - 1.57  # -pi/2
            h_factor = abs(math.sin(angle * 2 + self._phase))
            bar_h = 4 + h_factor * (8 + self._audio_level * 12)

            x1 = cx + bar_r * math.cos(angle)
            y1 = cy + bar_r * math.sin(angle)
            x2 = cx + (bar_r + bar_h) * math.cos(angle)
            y2 = cy + (bar_r + bar_h) * math.sin(angle)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


class FloatingWindow(QWidget):
    """Floating window with horizontal layout: animation left, text right"""
    closed = pyqtSignal()

    # Fixed size - enlarged: width 3x (420*3=1260), height 1.5x (120*1.5=180)
    WINDOW_WIDTH = 1260
    WINDOW_HEIGHT = 180

    def __init__(self):
        super().__init__()
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowStaysOnTopHint
            | Qt.FramelessWindowHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        # Container with glassmorphism
        container = QWidget()
        container.setObjectName("container")
        container.setStyleSheet("""
            QWidget#container {
                background-color: rgba(25, 25, 30, 240);
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 6)
        container.setGraphicsEffect(shadow)

        # Horizontal layout: [orb] [text area]
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(15, 12, 15, 12)
        h_layout.setSpacing(15)

        # Left: Wave orb
        self._wave_widget = WaveOrbWidget()
        h_layout.addWidget(self._wave_widget)

        # Right: Status + scrollable text
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)

        # Status label - use system default font
        self._status_label = QLabel(t("listening"))
        status_font = self._status_label.font()
        status_font.setPointSize(12)
        status_font.setWeight(QFont.Medium)
        self._status_label.setFont(status_font)
        self._status_label.setStyleSheet("color: #00D4FF; background: transparent;")
        self._status_label.setFixedHeight(20)
        right_layout.addWidget(self._status_label)

        # Scrollable text area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll_area.setStyleSheet("""
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(255,255,255,0.05);
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255,255,255,0.3);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        # Text label inside scroll area - use system default font
        self._text_label = QLabel("")
        text_font = self._text_label.font()
        text_font.setPointSize(11)
        self._text_label.setFont(text_font)
        self._text_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.85);
            background: transparent;
            padding: 2px 0;
        """)
        self._text_label.setWordWrap(True)
        self._text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        scroll_area.setWidget(self._text_label)
        right_layout.addWidget(scroll_area, 1)

        h_layout.addWidget(right_panel, 1)
        layout.addWidget(container)

        # Store scroll area reference for auto-scroll
        self._scroll_area = scroll_area

    def _scroll_to_bottom(self):
        """Auto scroll to bottom when text updates"""
        scrollbar = self._scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def show_recording(self):
        self._status_label.setText(t("listening"))
        self._status_label.setStyleSheet("color: #00D4FF; background: transparent;")
        self._text_label.setText("")
        self._wave_widget.set_mode("recording")
        self._wave_widget.start_animation()
        self._center_on_screen()
        self.show()
        self.raise_()

    def show_recognizing(self):
        self._status_label.setText(t("recognizing"))
        self._status_label.setStyleSheet("color: #FFB347; background: transparent;")
        self._wave_widget.set_mode("recognizing")

    def update_partial_result(self, text: str):
        if text:
            self._text_label.setText(text)
            self._text_label.setStyleSheet("""
                color: #FFE066;
                background: transparent;
            """)
            # Auto scroll to see latest text
            QTimer.singleShot(10, self._scroll_to_bottom)

    def show_result(self, text: str):
        self._status_label.setText(t("done"))
        self._status_label.setStyleSheet("color: #00E676; background: transparent;")
        self._text_label.setText(text)
        self._text_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.95);
            background: transparent;
        """)
        self._wave_widget.set_mode("done")
        QTimer.singleShot(10, self._scroll_to_bottom)
        # Stop animation after brief transition to show "done" color
        QTimer.singleShot(500, self._wave_widget.stop_animation)
        # Display time based on text length
        display_time = max(1500, min(3500, 1200 + len(text) * 15))
        QTimer.singleShot(display_time, self.hide)

    def show_error(self, error: str):
        self._status_label.setText(t("error"))
        self._status_label.setStyleSheet("color: #FF5252; background: transparent;")
        self._text_label.setText(error)
        self._text_label.setStyleSheet("color: rgba(255,255,255,0.7); background: transparent;")
        self._wave_widget.set_mode("error")
        # Stop animation after brief transition to show "error" color
        QTimer.singleShot(500, self._wave_widget.stop_animation)
        QTimer.singleShot(2500, self.hide)

    def update_audio_level(self, level: float):
        self._wave_widget.set_audio_level(level * 3)

    def _center_on_screen(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 80
        self.move(x, y)

    def hideEvent(self, event):
        self._wave_widget.stop_animation()
        super().hideEvent(event)
