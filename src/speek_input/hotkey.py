import threading
from typing import Callable, Optional
from pynput import keyboard

KEY_MAP = {
    "ctrl": keyboard.Key.ctrl,
    "ctrl_l": keyboard.Key.ctrl_l,
    "ctrl_r": keyboard.Key.ctrl_r,
    "alt": keyboard.Key.alt,
    "alt_l": keyboard.Key.alt_l,
    "alt_r": keyboard.Key.alt_r,
    "shift": keyboard.Key.shift,
    "shift_l": keyboard.Key.shift_l,
    "shift_r": keyboard.Key.shift_r,
    "super": keyboard.Key.cmd,
    "cmd": keyboard.Key.cmd,
}


class HotkeyListener:
    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ):
        self._hotkey = hotkey.lower()
        self._on_press = on_press
        self._on_release = on_release
        self._listener: Optional[keyboard.Listener] = None
        self._is_pressed = False
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
                    self._is_pressed = True
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
                    self._is_pressed = False
                    self._on_release()

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

    def update_hotkey(self, hotkey: str):
        self._hotkey = hotkey.lower()
