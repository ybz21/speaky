import logging
import platform
import subprocess
import shutil
import time
import ctypes

logger = logging.getLogger(__name__)


class InputMethod:
    """Cross-platform text input using clipboard + paste"""

    def __init__(self):
        self._system = platform.system()
        self._xdotool = shutil.which("xdotool") if self._system == "Linux" else None
        self._keyboard = None
        self._saved_window = None

        # Use pynput for simulating Cmd+V / Ctrl+V
        try:
            from pynput.keyboard import Controller, Key
            self._keyboard = Controller()
            self._Key = Key
            logger.info(f"Using clipboard+paste input method on {self._system}")
        except ImportError:
            logger.warning("pynput not available for keyboard input")

    def is_available(self) -> bool:
        if self._system == "Linux":
            return self._xdotool is not None
        return self._keyboard is not None

    def save_focus(self):
        """Save the currently focused window"""
        try:
            if self._system == "Windows":
                self._saved_window = ctypes.windll.user32.GetForegroundWindow()
                logger.info(f"Saved focus window: {self._saved_window}")
            elif self._system == "Darwin":
                # macOS: get frontmost application using AppleScript
                script = '''
                    tell application "System Events"
                        set frontApp to name of first application process whose frontmost is true
                    end tell
                    return frontApp
                '''
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    self._saved_window = result.stdout.strip()
                    logger.info(f"Saved focus app: {self._saved_window}")
            elif self._system == "Linux" and self._xdotool:
                result = subprocess.run(
                    [self._xdotool, "getactivewindow"],
                    capture_output=True, text=True
                )
                if result.returncode == 0:
                    self._saved_window = result.stdout.strip()
                    logger.info(f"Saved focus window: {self._saved_window}")
        except Exception as e:
            logger.error(f"Failed to save focus: {e}")

    def restore_focus(self):
        """Restore focus to the saved window"""
        if not self._saved_window:
            return
        try:
            if self._system == "Windows":
                ctypes.windll.user32.SetForegroundWindow(self._saved_window)
                logger.info(f"Restored focus to window: {self._saved_window}")
            elif self._system == "Darwin":
                # macOS: activate the saved application
                script = f'tell application "{self._saved_window}" to activate'
                subprocess.run(
                    ["osascript", "-e", script],
                    check=False, capture_output=True
                )
                logger.info(f"Restored focus to app: {self._saved_window}")
            elif self._system == "Linux" and self._xdotool:
                subprocess.run(
                    [self._xdotool, "windowactivate", "--sync", self._saved_window],
                    check=False
                )
                logger.info(f"Restored focus to window: {self._saved_window}")
            time.sleep(0.15)  # Wait for focus to settle
        except Exception as e:
            logger.error(f"Failed to restore focus: {e}")

    def _copy_to_clipboard(self, text: str) -> bool:
        """Copy text to system clipboard"""
        try:
            if self._system == "Darwin":
                # macOS: use pbcopy
                process = subprocess.Popen(
                    ["pbcopy"],
                    stdin=subprocess.PIPE,
                    env={"LANG": "en_US.UTF-8"}
                )
                process.communicate(text.encode("utf-8"))
                return process.returncode == 0
            elif self._system == "Linux":
                # Linux: use xclip or xsel
                xclip = shutil.which("xclip")
                if xclip:
                    process = subprocess.Popen(
                        ["xclip", "-selection", "clipboard"],
                        stdin=subprocess.PIPE
                    )
                    process.communicate(text.encode("utf-8"))
                    return process.returncode == 0
            elif self._system == "Windows":
                # Windows: use clip.exe
                process = subprocess.Popen(
                    ["clip"],
                    stdin=subprocess.PIPE
                )
                process.communicate(text.encode("utf-16"))
                return process.returncode == 0
            return False
        except Exception as e:
            logger.error(f"Failed to copy to clipboard: {e}")
            return False

    def _paste(self):
        """Simulate paste shortcut (Cmd+V on macOS, Ctrl+V on others)"""
        try:
            if self._system == "Darwin":
                # macOS: longer delay and use AppleScript for reliable paste
                time.sleep(0.2)
                script = 'tell application "System Events" to keystroke "v" using command down'
                subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
                logger.info("Paste command sent via AppleScript")
            elif self._keyboard:
                # Linux/Windows: Ctrl+V via pynput
                time.sleep(0.1)
                with self._keyboard.pressed(self._Key.ctrl):
                    self._keyboard.press("v")
                    self._keyboard.release("v")
                logger.info("Paste command sent via pynput")
        except Exception as e:
            logger.error(f"Failed to paste: {e}")

    def type_text(self, text: str):
        if not text:
            logger.warning("Empty text, nothing to type")
            return

        logger.info(f"Typing text via clipboard: {text}")

        # Restore focus to the original window first
        self.restore_focus()

        if self._system == "Linux" and self._xdotool:
            # Linux with xdotool: use direct typing
            subprocess.run(
                [self._xdotool, "type", "--clearmodifiers", "--", text],
                check=False,
                capture_output=True,
            )
        elif self._keyboard:
            # macOS/Windows: use clipboard + paste
            if self._copy_to_clipboard(text):
                self._paste()
                logger.info("Text pasted successfully")
            else:
                logger.error("Failed to copy text to clipboard")
        else:
            logger.error("No input method available")


input_method = InputMethod()
