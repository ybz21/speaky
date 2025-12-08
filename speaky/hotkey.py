import logging
import threading
import time
from typing import Callable, Optional
from pynput import keyboard

logger = logging.getLogger(__name__)

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
    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        hold_time: float = 1.0,
    ):
        self._hotkey = hotkey.lower()
        self._on_press = on_press
        self._on_release = on_release
        self._hold_time = hold_time
        self._listener: Optional[keyboard.Listener] = None
        self._is_pressed = False
        self._is_recording = False
        self._press_time: Optional[float] = None
        self._hold_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

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
                self._on_press()

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
                        self._on_release()
                    else:
                        logger.info("Released before hold time, ignoring")

    def start(self):
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release,
        )
        self._listener.start()

    def stop(self):
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        if self._hold_timer:
            self._hold_timer.cancel()
            self._hold_timer = None

    def update_hotkey(self, hotkey: str):
        self._hotkey = hotkey.lower()

    def update_hold_time(self, hold_time: float):
        self._hold_time = hold_time
