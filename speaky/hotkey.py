import logging
import platform
import threading
import time
from typing import Callable, Dict, Optional, Tuple
from pynput import keyboard

logger = logging.getLogger(__name__)

# 全局共享的键盘监听器（避免多个 X11 连接导致冲突）
_shared_listener: Optional[keyboard.Listener] = None
_shared_listener_lock = threading.Lock()
_hotkey_handlers: Dict[str, "HotkeyListener"] = {}
_listener_paused = False


def _get_shared_listener() -> keyboard.Listener:
    """获取或创建共享的键盘监听器"""
    global _shared_listener
    with _shared_listener_lock:
        if _shared_listener is None:
            _shared_listener = keyboard.Listener(
                on_press=_shared_on_press,
                on_release=_shared_on_release,
            )
            _shared_listener.start()
            logger.info("Created shared keyboard listener")
        return _shared_listener


def pause_listener():
    """暂停监听器（完全停止 pynput 线程，避免与其他 X11 操作冲突）"""
    global _shared_listener, _listener_paused
    _listener_paused = True
    with _shared_listener_lock:
        if _shared_listener is not None:
            try:
                _shared_listener.stop()
                _shared_listener = None
                logger.info("Keyboard listener stopped")
            except Exception as e:
                logger.error(f"Error stopping listener: {e}")


def resume_listener():
    """恢复监听器"""
    global _listener_paused
    _listener_paused = False
    # 重新创建监听器
    _get_shared_listener()
    logger.info("Keyboard listener resumed")


def _shared_on_press(key):
    """共享的按键按下处理"""
    if _listener_paused:
        return
    for handler in list(_hotkey_handlers.values()):
        try:
            handler._on_key_press(key)
        except Exception as e:
            logger.error(f"Error in hotkey press handler: {e}")


def _shared_on_release(key):
    """共享的按键释放处理"""
    if _listener_paused:
        return
    for handler in list(_hotkey_handlers.values()):
        try:
            handler._on_key_release(key)
        except Exception as e:
            logger.error(f"Error in hotkey release handler: {e}")


KEY_MAP = {
    # Modifier keys
    "ctrl": keyboard.Key.ctrl,
    "ctrl_l": keyboard.Key.ctrl_l,
    "ctrl_r": keyboard.Key.ctrl_r,
    "alt": keyboard.Key.alt,
    "alt_l": keyboard.Key.alt_l,
    "alt_r": keyboard.Key.alt_r,
    "alt_gr": keyboard.Key.alt_gr,
    "shift": keyboard.Key.shift,
    "shift_l": keyboard.Key.shift_l,
    "shift_r": keyboard.Key.shift_r,
    "super": keyboard.Key.cmd,
    "cmd": keyboard.Key.cmd,
    "cmd_r": keyboard.Key.cmd_r,
    # Function keys
    "f1": keyboard.Key.f1,
    "f2": keyboard.Key.f2,
    "f3": keyboard.Key.f3,
    "f4": keyboard.Key.f4,
    "f5": keyboard.Key.f5,
    "f6": keyboard.Key.f6,
    "f7": keyboard.Key.f7,
    "f8": keyboard.Key.f8,
    "f9": keyboard.Key.f9,
    "f10": keyboard.Key.f10,
    "f11": keyboard.Key.f11,
    "f12": keyboard.Key.f12,
    "f13": keyboard.Key.f13,
    "f14": keyboard.Key.f14,
    "f15": keyboard.Key.f15,
    "f16": keyboard.Key.f16,
    "f17": keyboard.Key.f17,
    "f18": keyboard.Key.f18,
    "f19": keyboard.Key.f19,
    "f20": keyboard.Key.f20,
    # Special keys
    "space": keyboard.Key.space,
    "tab": keyboard.Key.tab,
    "caps_lock": keyboard.Key.caps_lock,
    "esc": keyboard.Key.esc,
    "enter": keyboard.Key.enter,
    "backspace": keyboard.Key.backspace,
    "delete": keyboard.Key.delete,
    "insert": keyboard.Key.insert,
    "home": keyboard.Key.home,
    "end": keyboard.Key.end,
    "page_up": keyboard.Key.page_up,
    "page_down": keyboard.Key.page_down,
    # Arrow keys
    "up": keyboard.Key.up,
    "down": keyboard.Key.down,
    "left": keyboard.Key.left,
    "right": keyboard.Key.right,
    # Media keys
    "media_play_pause": keyboard.Key.media_play_pause,
    "media_volume_mute": keyboard.Key.media_volume_mute,
    "media_volume_down": keyboard.Key.media_volume_down,
    "media_volume_up": keyboard.Key.media_volume_up,
    "media_previous": keyboard.Key.media_previous,
    "media_next": keyboard.Key.media_next,
    # Other
    "menu": keyboard.Key.menu,
    "num_lock": keyboard.Key.num_lock,
    "pause": keyboard.Key.pause,
    "print_screen": keyboard.Key.print_screen,
    "scroll_lock": keyboard.Key.scroll_lock,
}


class HotkeyListener:
    _instance_counter = 0

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        hold_time: float = 1.0,
    ):
        self._hotkey = hotkey.lower()
        self._on_press_callback = on_press
        self._on_release_callback = on_release
        self._hold_time = hold_time
        self._is_pressed = False
        self._is_recording = False
        self._press_time: Optional[float] = None
        self._hold_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()
        # 唯一标识符
        HotkeyListener._instance_counter += 1
        self._id = f"hotkey_{HotkeyListener._instance_counter}_{hotkey}"

    def _get_target_key(self):
        if self._hotkey in KEY_MAP:
            return KEY_MAP[self._hotkey]
        if len(self._hotkey) == 1:
            return keyboard.KeyCode.from_char(self._hotkey)
        return None

    def _on_key_press(self, key):
        target = self._get_target_key()
        if target is None:
            logger.warning(f"Target key is None for hotkey: {self._hotkey}")
            return
        is_match = False
        if isinstance(target, keyboard.Key):
            is_match = key == target or (
                self._hotkey == "ctrl" and key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
            ) or (
                self._hotkey == "alt" and key in (keyboard.Key.alt_l, keyboard.Key.alt_r)
            ) or (
                self._hotkey == "shift" and key in (keyboard.Key.shift_l, keyboard.Key.shift_r)
            )
        else:
            is_match = key == target

        if is_match:
            with self._lock:
                if not self._is_pressed:
                    logger.info(f"Hotkey {self._hotkey} pressed, waiting {self._hold_time}s...")
                    self._is_pressed = True
                    self._press_time = time.time()
                    # Start timer to trigger recording after hold_time
                    self._hold_timer = threading.Timer(self._hold_time, self._trigger_recording)
                    self._hold_timer.start()

    def _trigger_recording(self):
        with self._lock:
            if self._is_pressed and not self._is_recording:
                logger.info(f"Hold time reached, starting recording")
                self._is_recording = True
                self._on_press_callback()

    def _on_key_release(self, key):
        target = self._get_target_key()
        if target is None:
            return
        is_match = False
        if isinstance(target, keyboard.Key):
            is_match = key == target or (
                self._hotkey == "ctrl" and key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r)
            ) or (
                self._hotkey == "alt" and key in (keyboard.Key.alt_l, keyboard.Key.alt_r)
            ) or (
                self._hotkey == "shift" and key in (keyboard.Key.shift_l, keyboard.Key.shift_r)
            )
        else:
            is_match = key == target

        if is_match:
            with self._lock:
                if self._is_pressed:
                    logger.info(f"Hotkey {self._hotkey} released")
                    self._is_pressed = False
                    # Cancel hold timer if still waiting
                    if self._hold_timer:
                        self._hold_timer.cancel()
                        self._hold_timer = None
                    # Only trigger release if recording was started
                    if self._is_recording:
                        self._is_recording = False
                        self._on_release_callback()
                    else:
                        logger.info("Released before hold time, ignoring")

    def start(self):
        # 注册到共享监听器
        _hotkey_handlers[self._id] = self
        # 确保共享监听器已启动
        _get_shared_listener()
        logger.info(f"Registered hotkey handler: {self._id}")

    def stop(self):
        # 从共享监听器注销
        if self._id in _hotkey_handlers:
            del _hotkey_handlers[self._id]
            logger.info(f"Unregistered hotkey handler: {self._id}")
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None

    def update_hotkey(self, hotkey: str):
        self._hotkey = hotkey.lower()

    def update_hold_time(self, hold_time: float):
        self._hold_time = hold_time
