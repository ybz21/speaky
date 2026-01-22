import logging
import platform
import subprocess
import shutil
import time
import ctypes
import webbrowser

logger = logging.getLogger(__name__)


def check_macos_accessibility() -> bool:
    """Check if the app has macOS Accessibility permission."""
    if platform.system() != "Darwin":
        return True

    try:
        # Try to use System Events - this requires Accessibility permission
        result = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to return (exists process 1)'],
            capture_output=True,
            text=True,
            timeout=5
        )
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"Failed to check accessibility: {e}")
        return False


def open_macos_accessibility_settings():
    """Open macOS System Settings to Accessibility page."""
    if platform.system() != "Darwin":
        return

    # This URL scheme works on macOS Ventura and later
    webbrowser.open("x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility")


class InputMethod:
    """Cross-platform text input using clipboard + paste"""

    def __init__(self):
        self._system = platform.system()
        self._xdotool = shutil.which("xdotool") if self._system == "Linux" else None
        self._xprop = shutil.which("xprop") if self._system == "Linux" else None
        self._keyboard = None
        self._saved_window = None

        # Use pynput for simulating Cmd+V / Ctrl+V
        try:
            from pynput.keyboard import Controller, Key
            self._keyboard = Controller()
            self._Key = Key
            logger.info(f"Using clipboard+paste input method on {self._system}")
            if self._system == "Linux":
                logger.info(f"Linux tools: xdotool={self._xdotool}, xprop={self._xprop}")
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
                time.sleep(0.15)  # Wait for focus to settle
            elif self._system == "Darwin":
                # macOS: with accessory mode, we never steal focus, so no need to restore
                # Calling activate on an already-frontmost app can reset cursor state in some apps
                logger.info(f"macOS accessory mode - skipping restore_focus for: {self._saved_window}")
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
                # Windows: use clip.exe with hidden window
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                process = subprocess.Popen(
                    ["clip"],
                    stdin=subprocess.PIPE,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                process.communicate(text.encode("utf-16"))
                return process.returncode == 0
            return False
        except Exception as e:
            logger.error(f"Failed to copy to clipboard: {e}")
            return False

    def _clear_clipboard(self):
        """Clear the system clipboard"""
        try:
            if self._system == "Darwin":
                # macOS: use pbcopy with empty string
                process = subprocess.Popen(
                    ["pbcopy"],
                    stdin=subprocess.PIPE,
                    env={"LANG": "en_US.UTF-8"}
                )
                process.communicate(b"")
            elif self._system == "Linux":
                # Linux: use xclip with empty string
                xclip = shutil.which("xclip")
                if xclip:
                    process = subprocess.Popen(
                        ["xclip", "-selection", "clipboard"],
                        stdin=subprocess.PIPE
                    )
                    process.communicate(b"")
            elif self._system == "Windows":
                # Windows: use PowerShell to clear clipboard (hidden window)
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = subprocess.SW_HIDE
                subprocess.run(
                    ["powershell", "-command", "Set-Clipboard -Value $null"],
                    check=False, capture_output=True,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            logger.info("Clipboard cleared")
        except Exception as e:
            logger.error(f"Failed to clear clipboard: {e}")

    def _is_terminal_window(self) -> bool:
        """Check if the currently active window is a terminal emulator"""
        if self._system != "Linux":
            return False

        # Common terminal emulators
        terminal_classes = [
            "gnome-terminal",
            "konsole",
            "xfce4-terminal",
            "xterm",
            "urxvt",
            "rxvt",
            "terminator",
            "tilix",
            "alacritty",
            "kitty",
            "st",
            "terminology",
            "guake",
            "yakuake",
            "tilda",
            "termite",
            "sakura",
            "lxterminal",
            "qterminal",
            "mate-terminal",
            "deepin-terminal",
            "hyper",
            "wezterm",
            "foot",
        ]

        window_class = None

        # Try xdotool first
        if self._xdotool:
            try:
                result = subprocess.run(
                    [self._xdotool, "getactivewindow", "getwindowclassname"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0:
                    window_class = result.stdout.strip().lower()
            except Exception as e:
                logger.warning(f"xdotool failed: {e}")

        # Fallback to xprop if xdotool failed or not available
        if window_class is None and self._xprop:
            try:
                # Get active window ID
                result = subprocess.run(
                    [self._xprop, "-root", "_NET_ACTIVE_WINDOW"],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                if result.returncode == 0 and "window id #" in result.stdout:
                    # Extract window ID (format: "_NET_ACTIVE_WINDOW(WINDOW): window id # 0x12345")
                    window_id = result.stdout.strip().split()[-1]
                    # Get WM_CLASS
                    result = subprocess.run(
                        [self._xprop, "-id", window_id, "WM_CLASS"],
                        capture_output=True,
                        text=True,
                        timeout=2
                    )
                    if result.returncode == 0 and "WM_CLASS" in result.stdout:
                        # Format: WM_CLASS(STRING) = "instance", "class"
                        window_class = result.stdout.lower()
            except Exception as e:
                logger.warning(f"xprop failed: {e}")

        if window_class:
            is_terminal = any(term in window_class for term in terminal_classes)
            logger.info(f"Window class: {window_class}, is_terminal: {is_terminal}")
            return is_terminal

        logger.warning("Could not detect window class")
        return False

    def _paste(self):
        """Simulate paste shortcut (Cmd+V on macOS, Ctrl+V or Ctrl+Shift+V on Linux)"""
        try:
            if self._system == "Darwin":
                # macOS: longer delay and use AppleScript for reliable paste
                time.sleep(0.2)
                script = 'tell application "System Events" to keystroke "v" using command down'
                subprocess.run(["osascript", "-e", script], check=False, capture_output=True)
                logger.info("Paste command sent via AppleScript")
            elif self._system == "Linux" and self._xdotool:
                # Linux with xdotool: use Ctrl+Shift+V for terminals, Ctrl+V for others
                time.sleep(0.1)
                if self._is_terminal_window():
                    paste_key = "ctrl+shift+v"
                else:
                    paste_key = "ctrl+v"
                subprocess.run(
                    [self._xdotool, "key", "--clearmodifiers", paste_key],
                    check=False,
                    capture_output=True,
                )
                logger.info(f"Paste command sent via xdotool ({paste_key})")
            elif self._system == "Linux" and self._keyboard:
                # Linux with pynput: use Ctrl+Shift+V for terminals, Ctrl+V for others
                time.sleep(0.1)
                is_terminal = self._is_terminal_window()
                if is_terminal:
                    # Ctrl+Shift+V
                    with self._keyboard.pressed(self._Key.ctrl):
                        with self._keyboard.pressed(self._Key.shift):
                            self._keyboard.press("v")
                            self._keyboard.release("v")
                    logger.info("Paste command sent via pynput (ctrl+shift+v)")
                else:
                    # Ctrl+V
                    with self._keyboard.pressed(self._Key.ctrl):
                        self._keyboard.press("v")
                        self._keyboard.release("v")
                    logger.info("Paste command sent via pynput (ctrl+v)")
            elif self._keyboard:
                # Windows/Other: Ctrl+V via pynput
                time.sleep(0.1)
                with self._keyboard.pressed(self._Key.ctrl):
                    self._keyboard.press("v")
                    self._keyboard.release("v")
                logger.info("Paste command sent via pynput (ctrl+v)")
        except Exception as e:
            logger.error(f"Failed to paste: {e}")

    def type_text(self, text: str, restore_focus: bool = True):
        """Type text via clipboard + paste

        Args:
            text: The text to type
            restore_focus: Whether to restore focus to saved window before typing.
                          Set to False for AI mode where we want to type in browser.
        """
        if not text:
            logger.warning("Empty text, nothing to type")
            return

        logger.info(f"Typing text via clipboard: {text[:50]}...")

        # Restore focus to the original window first (unless disabled)
        if restore_focus:
            self.restore_focus()

        if self._keyboard:
            # Use clipboard + paste (works on all platforms including Chinese input)
            if self._copy_to_clipboard(text):
                self._paste()
                # Wait for paste to complete, then clear clipboard
                time.sleep(0.3)
                self._clear_clipboard()
                logger.info("Text pasted successfully")
            else:
                logger.error("Failed to copy text to clipboard")
        else:
            logger.error("No input method available")


input_method = InputMethod()
