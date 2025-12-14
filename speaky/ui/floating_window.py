import logging
import math
import platform
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGraphicsDropShadowEffect, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QTimer, QPointF
from PySide6.QtGui import QPainter, QColor, QPainterPath, QRadialGradient, QPen, QFont, QKeyEvent

from ..i18n import t

logger = logging.getLogger(__name__)


def force_window_to_top(hwnd):
    """Windows: Force window to top using Win32 API

    使用多种方法确保窗口置顶：
    1. SetWindowPos with HWND_TOPMOST - 设置为最顶层
    2. SetForegroundWindow - 尝试获取前台焦点（可能失败）
    3. BringWindowToTop - 将窗口带到Z序顶部
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32

        # Constants
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        SWP_NOACTIVATE = 0x0010  # 不激活窗口（避免抢焦点）

        # 方法1: SetWindowPos - 设置为 TOPMOST 层级
        result = user32.SetWindowPos(
            hwnd,
            HWND_TOPMOST,
            0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE
        )
        logger.debug(f"SetWindowPos result: {result}")

        # 方法2: BringWindowToTop - 将窗口带到顶部
        user32.BringWindowToTop(hwnd)

        # 方法3: ShowWindow - 确保窗口可见
        SW_SHOWNOACTIVATE = 4
        user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)

    except Exception as e:
        logger.debug(f"force_window_to_top failed: {e}")


class WaveOrbWidget(QWidget):
    """Optimized animated orb widget with smooth color transitions"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(60, 60)
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
        logger.info(f"[动画] 切换模式: {self._mode} -> {mode}")
        self._mode = mode
        # Set target colors for smooth transition
        colors = self._colors.get(mode, self._colors["idle"])
        self._target_primary, self._target_secondary = colors
        self.update()

    def start_animation(self):
        if not self._is_animating:
            logger.info(f"[动画] 启动动画 (模式={self._mode})")
            self._is_animating = True
            self._timer.start(33)  # ~30 FPS

    def stop_animation(self):
        if self._is_animating:
            logger.info(f"[动画] 停止动画 (模式={self._mode})")
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
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2

        # Use smoothly interpolated colors
        primary = self._current_primary
        secondary = self._current_secondary

        # Simple glow (just 2 layers instead of 5)
        base_r = 15 + self._audio_level * 6
        for i in range(2):
            r = base_r + i * 8
            alpha = int(50 * (1 - i * 0.5))
            gradient = QRadialGradient(cx, cy, r)
            gradient.setColorAt(0, QColor(primary.red(), primary.green(), primary.blue(), alpha))
            gradient.setColorAt(1, QColor(primary.red(), primary.green(), primary.blue(), 0))
            painter.setBrush(gradient)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(cx, cy), r, r)

        # Main orb with simple wave deformation (fewer points)
        path = QPainterPath()
        num_points = 24  # Reduced from 64
        orb_r = 12 + self._audio_level * 7

        for i in range(num_points + 1):
            angle = (i / num_points) * 6.283
            # Simpler wave calculation
            wave = math.sin(angle * 3 + self._phase) * (1 + self._audio_level * 3)
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
        bar_r = orb_r + 4 + self._audio_level * 2
        pen = QPen(primary)
        pen.setWidth(1)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        for i in range(num_bars):
            angle = (i / num_bars) * 6.283 - 1.57  # -pi/2
            h_factor = abs(math.sin(angle * 2 + self._phase))
            bar_h = 2 + h_factor * (4 + self._audio_level * 6)

            x1 = cx + bar_r * math.cos(angle)
            y1 = cy + bar_r * math.sin(angle)
            x2 = cx + (bar_r + bar_h) * math.cos(angle)
            y2 = cy + (bar_r + bar_h) * math.sin(angle)
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


class FloatingWindow(QWidget):
    """Floating window with layout: [animation + status] | [text]"""
    closed = Signal()

    # Fixed size (reduced to 1/2)
    WINDOW_WIDTH = 630
    WINDOW_HEIGHT = 90

    def __init__(self):
        super().__init__()
        self._setup_timers()
        self._setup_ui()

    def _setup_timers(self):
        """初始化所有定时器（复用而非每次创建）"""
        # 隐藏窗口定时器
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide)

        # 停止动画定时器
        self._stop_animation_timer = QTimer(self)
        self._stop_animation_timer.setSingleShot(True)
        self._stop_animation_timer.timeout.connect(self._do_stop_animation)

        # 滚动定时器
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.timeout.connect(self._scroll_to_bottom)

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        # Container with glassmorphism
        container = QWidget()
        container.setObjectName("container")
        container.setStyleSheet("""
            QWidget#container {
                background-color: rgba(25, 25, 30, 240);
                border-radius: 10px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }
        """)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 3)
        container.setGraphicsEffect(shadow)

        # Horizontal layout: [left: animation+status] [right: text]
        h_layout = QHBoxLayout(container)
        h_layout.setContentsMargins(10, 8, 10, 8)
        h_layout.setSpacing(10)

        # Left panel: animation on top, status below
        left_panel = QWidget()
        left_panel.setFixedWidth(70)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(2)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Wave orb
        self._wave_widget = WaveOrbWidget()
        left_layout.addWidget(self._wave_widget, 0, Qt.AlignmentFlag.AlignCenter)

        # Status label below animation
        self._status_label = QLabel(t("listening"))
        status_font = self._status_label.font()
        status_font.setPointSize(9)
        status_font.setWeight(QFont.Weight.Medium)
        self._status_label.setFont(status_font)
        self._status_label.setStyleSheet("color: #00D4FF; background: transparent;")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self._status_label)

        h_layout.addWidget(left_panel)

        # Right panel: scrollable text area (vertically centered)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
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

        # Text label inside scroll area
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
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._text_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        scroll_area.setWidget(self._text_label)
        scroll_area.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        h_layout.addWidget(scroll_area, 1)

        layout.addWidget(container)

        # Store scroll area reference for auto-scroll
        self._scroll_area = scroll_area

    def _scroll_to_bottom(self):
        """Auto scroll to bottom when text updates"""
        scrollbar = self._scroll_area.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _schedule_scroll(self):
        """安排滚动到底部（可取消）"""
        self._scroll_timer.start(10)

    def _cancel_all_timers(self):
        """取消所有待执行的定时器"""
        self._hide_timer.stop()
        self._stop_animation_timer.stop()
        self._scroll_timer.stop()

    def _schedule_hide(self, delay_ms: int):
        """安排延迟隐藏窗口"""
        self._hide_timer.start(delay_ms)

    def _schedule_stop_animation(self, delay_ms: int = 500):
        """安排延迟停止动画"""
        self._stop_animation_timer.start(delay_ms)

    def _do_stop_animation(self):
        """执行停止动画"""
        logger.info("[浮窗] 定时器触发：停止动画")
        self._wave_widget.stop_animation()

    def show_recording(self):
        logger.info("[浮窗] 显示录音状态")
        self._cancel_all_timers()
        self._status_label.setText(t("listening"))
        self._status_label.setStyleSheet("color: #00D4FF; background: transparent;")
        self._text_label.setText("")
        self._wave_widget.set_mode("recording")
        self._wave_widget.start_animation()
        self._center_on_screen()
        self.show()
        self.raise_()
        self.force_to_top()

    def force_to_top(self):
        """Force window to stay on top (Windows specific)"""
        try:
            if platform.system() == "Windows":
                # Get native window handle
                hwnd = int(self.winId())
                logger.debug(f"[浮窗] 置顶窗口: hwnd={hwnd}")
                force_window_to_top(hwnd)
            else:
                # Linux/macOS: just raise, don't activate to avoid stealing focus
                self.raise_()
        except Exception as e:
            logger.exception(f"[浮窗] 置顶失败: {e}")

    def show_recognizing(self):
        logger.info("[浮窗] 显示识别中状态")
        self._cancel_all_timers()
        self._status_label.setText(t("recognizing"))
        self._status_label.setStyleSheet("color: #FFB347; background: transparent;")
        self._wave_widget.set_mode("recognizing")
        # 确保动画在运行（可能之前被停止了）
        self._wave_widget.start_animation()

    def update_partial_result(self, text: str):
        if text:
            logger.debug(f"[浮窗] 更新部分结果: {text[:30]}...")
            self._text_label.setText(text)
            self._text_label.setStyleSheet("""
                color: #FFE066;
                background: transparent;
            """)
            # Auto scroll to see latest text
            self._schedule_scroll()

    def show_result(self, text: str):
        import time
        self._result_show_time = time.time()  # 记录结果显示时间
        self._cancel_all_timers()
        text_preview = repr(text[:50]) if text else 'None'
        text_len = len(text) if text else 0
        logger.info(f"[浮窗] 显示最终结果: {text_preview}... (长度={text_len})")
        self._status_label.setText(t("done"))
        self._status_label.setStyleSheet("color: #00E676; background: transparent;")
        self._text_label.setText(text)
        self._text_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.95);
            background: transparent;
        """)
        self._wave_widget.set_mode("done")
        self._schedule_scroll()
        # Stop animation after brief transition to show "done" color
        self._schedule_stop_animation(500)
        # 固定显示 500ms 后隐藏
        display_time = 500
        logger.info(f"[浮窗] 计划: 500ms后停止动画, {display_time}ms后隐藏")
        self._schedule_hide(display_time)

    def _do_hide(self):
        """执行隐藏操作"""
        import time
        if hasattr(self, '_result_show_time') and self._result_show_time:
            elapsed = time.time() - self._result_show_time
            logger.info(f"[浮窗] 定时器触发：隐藏窗口，距离显示结果 {elapsed:.2f}s")
            self._result_show_time = None
        else:
            logger.info("[浮窗] 定时器触发：隐藏窗口")
        self.hide()

    def show_error(self, error: str):
        import time
        self._result_show_time = time.time()  # 记录显示时间
        self._cancel_all_timers()
        logger.info(f"[浮窗] 显示错误: {error}")
        self._status_label.setText(t("error"))
        self._status_label.setStyleSheet("color: #FF5252; background: transparent;")
        self._text_label.setText(error)
        self._text_label.setStyleSheet("color: rgba(255,255,255,0.7); background: transparent;")
        self._wave_widget.set_mode("error")
        # Stop animation after brief transition to show "error" color
        self._schedule_stop_animation(500)
        # 与成功结果一样，显示 1500ms 后隐藏（错误稍微长一点让用户看清）
        display_time = 1500
        logger.info(f"[浮窗] 计划: 500ms后停止动画, {display_time}ms后隐藏")
        self._schedule_hide(display_time)

    def update_audio_level(self, level: float):
        self._wave_widget.set_audio_level(level * 3)

    def _center_on_screen(self):
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 40
        self.move(x, y)

    def keyPressEvent(self, event: QKeyEvent):
        """Handle ESC key to close window"""
        if event.key() == Qt.Key.Key_Escape:
            logger.info("[浮窗] ESC键按下，隐藏窗口")
            self.hide()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        logger.info("[浮窗] 窗口隐藏事件触发")
        self._wave_widget.stop_animation()
        self._cancel_all_timers()
        super().hideEvent(event)
