import logging
import math
import platform
from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QGraphicsDropShadowEffect, QScrollArea
)
from PySide6.QtCore import Qt, Signal, QTimer, QPointF, QSize, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QPainterPath, QRadialGradient, QPen,
    QFont, QKeyEvent, QPixmap, QBrush
)

from speaky.i18n import t
from speaky.window_info import get_focused_window_info, WindowInfo
from speaky.llm.types import AgentStatus, AgentContent

logger = logging.getLogger(__name__)


def format_result_text(text: str) -> tuple[str, str]:
    """将结果文本分割为主信息和次要信息

    Args:
        text: 原始文本

    Returns:
        (primary, secondary): 主信息和次要信息
    """
    if not text:
        return "", ""

    # 清理文本
    text = text.strip()

    # 短文本：直接显示
    if len(text) <= 30:
        return text, ""

    # 分割为多行
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    if len(lines) == 1:
        # 单行长文本：尝试按句号分割
        sentences = text.split('。')
        if len(sentences) > 1 and sentences[0]:
            primary = sentences[0] + "。"
            rest = "。".join(sentences[1:]).strip()
            if rest:
                secondary = rest[:40]
                if len(rest) > 40:
                    secondary += "..."
                return primary, secondary
            return primary, ""
        else:
            # 无句号：截断显示
            return text[:30] + "...", ""

    # 多行文本
    primary = lines[0]
    if len(primary) > 40:
        primary = primary[:37] + "..."

    if len(lines) == 2:
        secondary = lines[1][:40]
        if len(lines[1]) > 40:
            secondary += "..."
    else:
        # 3行以上：显示数量
        secondary = f"共 {len(lines)} 项内容"

    return primary, secondary


# LLM 状态颜色配置 - 用颜色区分不同状态类型
LLM_STATE_COLORS = {
    # 聆听中 - 青蓝色
    "listening": {
        "label": "#00D9FF",
        "text": "rgba(255,255,255,0.6)",
        "gradient_start": "rgba(0, 180, 220, 0.10)",
        "gradient_end": "rgba(15, 25, 35, 0.95)",
    },

    # 识别中 - 青蓝 + 黄色文本
    "recognizing": {
        "label": "#00D9FF",
        "text": "#FFE066",
        "gradient_start": "rgba(0, 180, 220, 0.10)",
        "gradient_end": "rgba(15, 25, 35, 0.95)",
    },

    # 用户输入回显 - 中性灰
    "user_input": {
        "label": "#888888",
        "text": "rgba(255,255,255,0.9)",
        "gradient_start": "rgba(100, 100, 100, 0.08)",
        "gradient_end": "rgba(25, 25, 30, 0.95)",
    },

    # 思考中 - Material Purple
    "thinking": {
        "label": "#BB86FC",
        "text": "#E1BEE7",
        "gradient_start": "rgba(150, 100, 220, 0.10)",
        "gradient_end": "rgba(25, 15, 35, 0.95)",
    },

    # 执行中 - Material Orange
    "executing": {
        "label": "#FF9800",
        "text": "#FFE0B2",
        "gradient_start": "rgba(255, 150, 0, 0.10)",
        "gradient_end": "rgba(35, 25, 15, 0.95)",
    },

    # 完成 - Material Green
    "done": {
        "label": "#00E676",
        "text": "rgba(255,255,255,0.95)",
        "gradient_start": "rgba(0, 200, 100, 0.10)",
        "gradient_end": "rgba(15, 30, 20, 0.95)",
    },

    # 错误 - Material Red
    "error": {
        "label": "#FF5252",
        "text": "#FFCDD2",
        "gradient_start": "rgba(255, 80, 80, 0.10)",
        "gradient_end": "rgba(35, 15, 15, 0.95)",
    },
}


def force_window_to_top(hwnd):
    """Windows: Force window to top using Win32 API"""
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        HWND_TOPMOST = -1
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040
        SWP_NOACTIVATE = 0x0010

        user32.SetWindowPos(
            hwnd, HWND_TOPMOST, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW | SWP_NOACTIVATE
        )
        user32.BringWindowToTop(hwnd)
        user32.ShowWindow(hwnd, 4)  # SW_SHOWNOACTIVATE
    except Exception as e:
        logger.debug(f"force_window_to_top failed: {e}")


class AppIconOrbWidget(QWidget):
    """应用图标 + 脉动光环动画"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(64, 64)
        self._audio_level = 0.0
        self._target_level = 0.0
        self._phase = 0.0
        self._is_animating = False
        self._mode = "recording"
        self._app_pixmap = None  # 应用图标

        # 颜色过渡
        self._current_primary = QColor("#00D9FF")
        self._target_primary = QColor("#00D9FF")

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)

        # 状态颜色
        self._colors = {
            "recording": QColor("#00D9FF"),
            "recognizing": QColor("#FFB84D"),
            "done": QColor("#00E676"),
            "error": QColor("#FF5252"),
            "idle": QColor("#666666"),
        }

    def set_app_icon(self, pixmap: QPixmap):
        """设置应用图标"""
        if pixmap and not pixmap.isNull():
            # 缩放到 32x32
            self._app_pixmap = pixmap.scaled(
                QSize(32, 32),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        else:
            self._app_pixmap = None
        self.update()

    def clear_app_icon(self):
        """清除应用图标"""
        self._app_pixmap = None
        self.update()

    def set_audio_level(self, level: float):
        self._target_level = min(1.0, max(0.0, level))

    def set_mode(self, mode: str):
        self._mode = mode
        self._target_primary = self._colors.get(mode, self._colors["idle"])
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
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
        )

    def _update_animation(self):
        self._audio_level += (self._target_level - self._audio_level) * 0.2
        self._current_primary = self._lerp_color(self._current_primary, self._target_primary, 0.15)
        self._phase += 0.1
        if self._phase > 6.283:
            self._phase -= 6.283
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx, cy = w / 2, h / 2
        color = self._current_primary

        # 呼吸节奏
        breath = 0.5 + 0.5 * math.sin(self._phase * 0.8)

        # === 1. 图标背景圆 ===
        bg_radius = 24
        bg_gradient = QRadialGradient(cx - 4, cy - 4, bg_radius * 1.5)
        bg_gradient.setColorAt(0, QColor(70, 70, 75, 250))
        bg_gradient.setColorAt(1, QColor(40, 40, 45, 250))
        painter.setBrush(bg_gradient)

        # 简单边框（浅色，不发光）
        border_pen = QPen(QColor(255, 255, 255, 25))
        border_pen.setWidth(1)
        painter.setPen(border_pen)
        painter.drawEllipse(QPointF(cx, cy), bg_radius, bg_radius)

        # === 2. 应用图标或默认图标 ===
        if self._app_pixmap and not self._app_pixmap.isNull():
            icon_size = 32
            icon_x = cx - icon_size / 2
            icon_y = cy - icon_size / 2
            # 圆形裁剪
            path = QPainterPath()
            path.addEllipse(QRectF(icon_x, icon_y, icon_size, icon_size))
            painter.setClipPath(path)
            painter.drawPixmap(
                int(icon_x), int(icon_y), icon_size, icon_size,
                self._app_pixmap
            )
            painter.setClipping(False)
        else:
            # 默认图标：麦克风
            painter.setPen(QPen(QColor(220, 220, 220), 2.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            mic_w, mic_h = 10, 14
            mic_x, mic_y = cx - mic_w/2, cy - mic_h/2 - 2
            painter.drawRoundedRect(QRectF(mic_x, mic_y, mic_w, mic_h), 5, 5)
            painter.drawArc(QRectF(cx - 8, cy + 4, 16, 10), 0, -180 * 16)
            painter.drawLine(QPointF(cx, cy + 9), QPointF(cx, cy + 14))

        # === 3. 右下角状态指示点 ===
        dot_r = 5
        dot_x = cx + 17
        dot_y = cy + 17

        # 点的发光效果
        glow_alpha = int(60 + 40 * breath)
        glow_gradient = QRadialGradient(dot_x, dot_y, dot_r + 4)
        glow_gradient.setColorAt(0, QColor(color.red(), color.green(), color.blue(), glow_alpha))
        glow_gradient.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow_gradient)
        painter.drawEllipse(QPointF(dot_x, dot_y), dot_r + 4, dot_r + 4)

        # 状态点本体
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(QColor(40, 40, 45), 2))
        painter.drawEllipse(QPointF(dot_x, dot_y), dot_r, dot_r)


class FloatingWindow(QWidget):
    """悬浮窗：应用图标动画 + 状态文本"""
    closed = Signal()

    WINDOW_WIDTH = 500
    WINDOW_HEIGHT = 88

    STATE_COLORS = {
        "recording": {"text": "#00D9FF", "gradient_start": "rgba(0, 180, 220, 0.10)", "gradient_end": "rgba(15, 25, 35, 0.95)"},
        "recognizing": {"text": "#FFB84D", "gradient_start": "rgba(255, 150, 50, 0.10)", "gradient_end": "rgba(35, 25, 15, 0.95)"},
        "done": {"text": "#00E676", "gradient_start": "rgba(0, 200, 100, 0.10)", "gradient_end": "rgba(15, 30, 20, 0.95)"},
        "error": {"text": "#FF5252", "gradient_start": "rgba(255, 80, 80, 0.10)", "gradient_end": "rgba(35, 15, 15, 0.95)"},
        # Agent mode colors
        "listening": {"text": "#00D9FF", "gradient_start": "rgba(0, 180, 220, 0.10)", "gradient_end": "rgba(15, 25, 35, 0.95)"},
        "thinking": {"text": "#BB86FC", "gradient_start": "rgba(150, 100, 220, 0.10)", "gradient_end": "rgba(25, 15, 35, 0.95)"},
        "executing": {"text": "#FF9800", "gradient_start": "rgba(255, 150, 0, 0.10)", "gradient_end": "rgba(35, 25, 15, 0.95)"},
    }


    def __init__(self):
        super().__init__()
        self._current_mode = "recording"
        self._window_mode = "normal"  # "normal" or "agent"
        self._setup_timers()
        self._setup_ui()

    def _setup_timers(self):
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._do_hide)

        self._stop_animation_timer = QTimer(self)
        self._stop_animation_timer.setSingleShot(True)
        self._stop_animation_timer.timeout.connect(self._do_stop_animation)


    def _get_container_style(self, mode: str) -> str:
        colors = self.STATE_COLORS.get(mode, self.STATE_COLORS["recording"])
        return f"""
            QWidget#container {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {colors["gradient_start"]},
                    stop:1 {colors["gradient_end"]}
                );
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.12);
            }}
        """

    def _setup_ui(self):
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(self.WINDOW_WIDTH, self.WINDOW_HEIGHT)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        # 容器
        self._container = QWidget()
        self._container.setObjectName("container")
        self._container.setStyleSheet(self._get_container_style("recording"))

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 50))
        shadow.setOffset(0, 4)
        self._container.setGraphicsEffect(shadow)

        h_layout = QHBoxLayout(self._container)
        h_layout.setContentsMargins(12, 4, 16, 4)
        h_layout.setSpacing(12)

        # === 左侧：应用图标动画 + 应用名称 ===
        left_panel = QWidget()
        left_panel.setFixedWidth(80)
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 2, 0, 0)
        left_layout.setSpacing(4)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self._icon_orb = AppIconOrbWidget()
        left_layout.addWidget(self._icon_orb, 0, Qt.AlignmentFlag.AlignCenter)

        # 应用名称标签
        self._app_name_label = QLabel("")
        app_name_font = self._app_name_label.font()
        app_name_font.setPointSize(9)
        self._app_name_label.setFont(app_name_font)
        self._app_name_label.setStyleSheet("color: rgba(255,255,255,0.5); background: transparent;")
        self._app_name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._app_name_label.setFixedWidth(80)
        self._app_name_label.setFixedHeight(16)
        left_layout.addWidget(self._app_name_label)

        h_layout.addWidget(left_panel)

        # === 右侧：状态 + 可滚动文本区域 ===
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 4, 0, 4)
        right_layout.setSpacing(2)

        # 状态行
        self._status_label = QLabel()
        self._status_label.setTextFormat(Qt.TextFormat.RichText)
        status_font = self._status_label.font()
        status_font.setPointSize(11)
        status_font.setWeight(QFont.Weight.Medium)
        self._status_label.setFont(status_font)
        self._status_label.setStyleSheet("background: transparent;")
        self._update_status_text("recording")
        right_layout.addWidget(self._status_label)

        # 可滚动文本区域
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidgetResizable(True)
        self._scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll_area.setStyleSheet("background: transparent;")

        scroll_content = QWidget()
        scroll_content.setStyleSheet("background: transparent;")
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(2)

        # 主信息文本（13pt）
        self._text_label = QLabel("")
        text_font = self._text_label.font()
        text_font.setPointSize(13)
        self._text_label.setFont(text_font)
        self._text_label.setStyleSheet("color: rgba(255,255,255,0.9); background: transparent;")
        self._text_label.setWordWrap(True)
        self._text_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll_layout.addWidget(self._text_label)

        # 次要信息文本（11pt，灰色）
        self._secondary_label = QLabel("")
        secondary_font = self._secondary_label.font()
        secondary_font.setPointSize(11)
        self._secondary_label.setFont(secondary_font)
        self._secondary_label.setStyleSheet("color: rgba(255,255,255,0.5); background: transparent;")
        self._secondary_label.setWordWrap(True)
        self._secondary_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll_layout.addWidget(self._secondary_label)

        scroll_layout.addStretch(1)
        self._scroll_area.setWidget(scroll_content)
        right_layout.addWidget(self._scroll_area, 1)

        h_layout.addWidget(right_panel, 1)
        layout.addWidget(self._container)

    def _update_status_text(self, mode: str):
        colors = self.STATE_COLORS.get(mode, self.STATE_COLORS["recording"])
        status_color = colors["text"]

        status_texts = {
            "recording": t("listening"),
            "recognizing": t("recognizing"),
            "done": t("done"),
            "error": t("error"),
        }
        status_text = status_texts.get(mode, t("listening"))
        self._status_label.setText(f'<span style="color: {status_color}">{status_text}</span>')

    def _update_app_name(self, name: str):
        """更新应用名称显示"""
        if name:
            display_name = name if len(name) <= 8 else name[:7] + "…"
            self._app_name_label.setText(display_name)
        else:
            self._app_name_label.setText("")

    def _update_container_style(self, mode: str):
        self._current_mode = mode
        self._container.setStyleSheet(self._get_container_style(mode))

    def _cancel_all_timers(self):
        self._hide_timer.stop()
        self._stop_animation_timer.stop()

    def _schedule_hide(self, delay_ms: int):
        self._hide_timer.start(delay_ms)

    def _schedule_stop_animation(self, delay_ms: int = 500):
        self._stop_animation_timer.start(delay_ms)

    def _do_stop_animation(self):
        self._icon_orb.stop_animation()

    def update_app_info(self, info: WindowInfo = None):
        if info is None:
            info = get_focused_window_info()

        if info is None:
            self._icon_orb.clear_app_icon()
            self._update_app_name("")
            return

        app_name = info.app_name or info.wm_class or ""
        self._update_app_name(app_name)

        if info.icon_path:
            pixmap = QPixmap(info.icon_path)
            if not pixmap.isNull():
                self._icon_orb.set_app_icon(pixmap)
            else:
                self._icon_orb.clear_app_icon()
        else:
            self._icon_orb.clear_app_icon()

    def show_recording(self):
        logger.info("[浮窗] 显示录音状态")
        self._cancel_all_timers()
        self._update_container_style("recording")
        self._update_status_text("recording")
        self._text_label.setText("")
        self._secondary_label.setText("")
        self._secondary_label.setVisible(False)
        self._icon_orb.set_mode("recording")
        self._icon_orb.start_animation()

        self.update_app_info()

        self._center_on_screen()
        self.show()
        self.raise_()
        self.force_to_top()

    def force_to_top(self):
        try:
            if platform.system() == "Windows":
                hwnd = int(self.winId())
                force_window_to_top(hwnd)
            else:
                self.raise_()
        except Exception as e:
            logger.exception(f"[浮窗] 置顶失败: {e}")

    def show_recognizing(self):
        logger.info("[浮窗] 显示识别中状态")
        self._cancel_all_timers()
        self._update_container_style("recognizing")
        self._update_status_text("recognizing")
        self._secondary_label.setText("")
        self._secondary_label.setVisible(False)
        self._icon_orb.set_mode("recognizing")
        self._icon_orb.start_animation()

    def _scroll_to_bottom(self):
        """滚动到文本底部"""
        vbar = self._scroll_area.verticalScrollBar()
        vbar.setValue(vbar.maximum())

    def update_partial_result(self, text: str):
        if text:
            self._text_label.setText(text)
            self._text_label.setStyleSheet("color: #FFE066; background: transparent;")
            self._secondary_label.setText("")
            self._secondary_label.setVisible(False)
            # 自动滚动到最新内容
            QTimer.singleShot(0, self._scroll_to_bottom)

    def show_result(self, text: str):
        import time
        self._result_show_time = time.time()
        self._cancel_all_timers()
        logger.info(f"[浮窗] 显示最终结果: {repr(text[:50]) if text else 'None'}...")
        self._update_container_style("done")
        self._update_status_text("done")
        # 使用双层显示
        primary, secondary = format_result_text(text)
        self._text_label.setText(primary)
        self._text_label.setStyleSheet("color: rgba(255,255,255,0.95); background: transparent;")
        self._secondary_label.setText(secondary)
        self._secondary_label.setVisible(bool(secondary))
        self._icon_orb.set_mode("done")
        self._schedule_stop_animation(500)
        self._schedule_hide(500)

    def _do_hide(self):
        import time
        if hasattr(self, '_result_show_time') and self._result_show_time:
            self._result_show_time = None
        self.hide()

    def show_error(self, error: str):
        import time
        self._result_show_time = time.time()
        self._cancel_all_timers()
        logger.info(f"[浮窗] 显示错误: {error}")
        self._update_container_style("error")
        self._update_status_text("error")
        # 使用双层显示
        primary, secondary = format_result_text(error)
        self._text_label.setText(primary)
        self._text_label.setStyleSheet("color: rgba(255,255,255,0.7); background: transparent;")
        self._secondary_label.setText(secondary)
        self._secondary_label.setVisible(bool(secondary))
        self._icon_orb.set_mode("error")
        self._schedule_stop_animation(500)
        self._schedule_hide(1500)

    def update_audio_level(self, level: float):
        self._icon_orb.set_audio_level(level * 3)

    def _center_on_screen(self):
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 60
        self.move(x, y)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def hideEvent(self, event):
        self._icon_orb.stop_animation()
        self._cancel_all_timers()
        super().hideEvent(event)

    # ========== Agent Mode Methods ==========

    # 状态文本映射
    _LLM_STATUS_TEXTS = {
        "listening": "正在聆听...",
        "recognizing": "识别中...",
        "user_input": "您说",
        "thinking": "思考中...",
        "executing": "执行中...",
        "done": "完成",
        "error": "错误",
    }

    def set_mode(self, mode: str):
        """Set window mode: 'normal' or 'agent'."""
        self._window_mode = mode
        if mode == "normal":
            self.setFixedHeight(self.WINDOW_HEIGHT)
        # Agent mode uses fixed height

    def set_llm_state(
        self,
        state: str,
        content: str = "",
        tool_name: str = "",
    ):
        """设置 LLM 状态和显示内容 - 支持双层显示

        Args:
            state: 状态类型 (listening/recognizing/user_input/thinking/executing/done/error)
            content: 显示的文本内容
            tool_name: 执行中时的工具名（可选）
        """
        colors = LLM_STATE_COLORS.get(state, LLM_STATE_COLORS["listening"])

        # 1. 更新状态标签
        status_text = self._LLM_STATUS_TEXTS.get(state, "")
        self._status_label.setText(
            f'<span style="color: {colors["label"]}">{status_text}</span>'
        )

        # 2. 构建显示内容（双层显示）
        primary_text = ""
        secondary_text = ""

        if state == "executing" and tool_name:
            # 执行中：工具名 → 参数
            primary_text = f"🔧 {tool_name}"
            if content:
                primary_text += f" → {content[:30]}"
                if len(content) > 30:
                    primary_text += "..."

        elif state == "done":
            # 完成：使用双层显示
            prefix = "✓ " if content and not content.startswith("✓") else ""
            primary, secondary = format_result_text(content)
            primary_text = prefix + primary
            secondary_text = secondary

        elif state == "error":
            # 错误：使用双层显示
            prefix = "✗ " if content and not content.startswith("✗") else ""
            primary, secondary = format_result_text(content)
            primary_text = prefix + primary
            secondary_text = secondary

        elif state == "thinking":
            # 思考中：流式文本，截断显示
            primary_text = content[:50] if content else "正在分析您的请求..."
            if content and len(content) > 50:
                primary_text += "..."

        else:
            # 其他状态：单行显示
            primary_text = content[:50] if content else ""
            if content and len(content) > 50:
                primary_text += "..."

        # 设置主信息
        self._text_label.setText(primary_text)
        self._text_label.setStyleSheet(
            f"color: {colors['text']}; background: transparent;"
        )

        # 设置次要信息
        self._secondary_label.setText(secondary_text)
        # 次要信息始终使用灰色
        self._secondary_label.setVisible(bool(secondary_text))

        # 自动滚动到最新内容
        QTimer.singleShot(0, self._scroll_to_bottom)

        # 3. 更新背景
        self._update_llm_background(state)

        # 4. 更新图标动画
        self._update_llm_icon(state)

    def _update_llm_background(self, state: str):
        """更新 LLM 模式的背景渐变"""
        colors = LLM_STATE_COLORS.get(state, LLM_STATE_COLORS["listening"])
        self._container.setStyleSheet(f"""
            QWidget#container {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 {colors["gradient_start"]},
                    stop:1 {colors["gradient_end"]}
                );
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.12);
            }}
        """)

    def _update_llm_icon(self, state: str):
        """更新 LLM 模式的图标状态"""
        # 映射 LLM 状态到图标模式
        icon_mode_map = {
            "listening": "recording",
            "recognizing": "recording",
            "user_input": "idle",
            "thinking": "recognizing",
            "executing": "recognizing",
            "done": "done",
            "error": "error",
        }
        orb_mode = icon_mode_map.get(state, "idle")
        self._icon_orb.set_mode(orb_mode)

        # 活动状态启动动画
        if state in ["listening", "recognizing", "thinking", "executing"]:
            self._icon_orb.start_animation()
        else:
            self._schedule_stop_animation(300)

    def set_agent_content(self, content: AgentContent):
        """根据 AgentContent 更新显示 - 只显示当前最新状态

        优先级: 错误 > 结果 > 执行中 > 思考中 > 用户输入 > 聆听
        """
        # Auto show window when status is LISTENING
        if content.status == AgentStatus.LISTENING:
            self._window_mode = "agent"
            self.update_app_info()
            self._center_on_screen()
            self.show()
            self.raise_()
            self.force_to_top()

        # 按优先级决定显示内容
        if content.error:
            # 最高优先级：错误
            self.set_llm_state("error", content.error)

        elif content.result:
            # 第二优先级：最终结果
            self.set_llm_state("done", content.result)

        elif content.status == AgentStatus.EXECUTING and content.tool_calls:
            # 第三优先级：执行中 - 显示当前正在执行的工具
            current_tool = next(
                (t for t in reversed(content.tool_calls) if t.status == "running"),
                content.tool_calls[-1] if content.tool_calls else None
            )
            if current_tool:
                self.set_llm_state("executing", current_tool.summary, current_tool.name)
            else:
                self.set_llm_state("executing", "处理中...")

        elif content.status == AgentStatus.THINKING:
            # 第四优先级：思考中
            text = content.thinking if content.thinking else "正在分析您的请求..."
            self.set_llm_state("thinking", text)

        elif content.status == AgentStatus.RECOGNIZING:
            # 识别中 - 显示部分识别结果
            text = content.user_input if content.user_input else ""
            self.set_llm_state("recognizing", text)

        elif content.user_input and content.status not in [AgentStatus.LISTENING]:
            # 用户输入确认（可选状态）
            self.set_llm_state("user_input", content.user_input)

        else:
            # 默认：聆听中
            self.set_llm_state("listening", "请说出您的指令")

