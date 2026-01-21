"""Auto-start management for different platforms"""
import logging
import os
import sys
import platform

logger = logging.getLogger(__name__)


def get_app_path() -> str:
    """Get the path to the application executable"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return sys.executable
    else:
        # Running as script - use python + module
        return f'"{sys.executable}" -m speaky'


def is_autostart_enabled() -> bool:
    """Check if auto-start is enabled"""
    system = platform.system()
    if system == "Windows":
        return _windows_is_autostart()
    elif system == "Darwin":
        return _macos_is_autostart()
    else:  # Linux
        return _linux_is_autostart()


def set_autostart(enabled: bool):
    """Enable or disable auto-start"""
    system = platform.system()
    if system == "Windows":
        _windows_set_autostart(enabled)
    elif system == "Darwin":
        _macos_set_autostart(enabled)
    else:  # Linux
        _linux_set_autostart(enabled)


# Windows implementation
def _windows_is_autostart() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_READ
        )
        try:
            winreg.QueryValueEx(key, "Speaky")
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def _windows_set_autostart(enabled: bool):
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0, winreg.KEY_SET_VALUE
        )
        try:
            if enabled:
                app_path = get_app_path()
                winreg.SetValueEx(key, "Speaky", 0, winreg.REG_SZ, app_path)
            else:
                try:
                    winreg.DeleteValue(key, "Speaky")
                except FileNotFoundError:
                    pass
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        logger.error(f"Failed to set Windows autostart: {e}")


# macOS implementation
def _macos_is_autostart() -> bool:
    plist_path = os.path.expanduser("~/Library/LaunchAgents/com.speaky.plist")
    return os.path.exists(plist_path)


def _macos_set_autostart(enabled: bool):
    plist_path = os.path.expanduser("~/Library/LaunchAgents/com.speaky.plist")

    if enabled:
        app_path = get_app_path()
        plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.speaky</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>-m</string>
        <string>speaky</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
'''
        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
        with open(plist_path, 'w') as f:
            f.write(plist_content)
    else:
        if os.path.exists(plist_path):
            os.remove(plist_path)


# Linux implementation
def _linux_is_autostart() -> bool:
    desktop_path = os.path.expanduser("~/.config/autostart/speaky.desktop")
    return os.path.exists(desktop_path)


def _linux_set_autostart(enabled: bool):
    desktop_path = os.path.expanduser("~/.config/autostart/speaky.desktop")

    if enabled:
        app_path = get_app_path()
        desktop_content = f'''[Desktop Entry]
Type=Application
Name=Speaky
Exec={app_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
'''
        os.makedirs(os.path.dirname(desktop_path), exist_ok=True)
        with open(desktop_path, 'w') as f:
            f.write(desktop_content)
    else:
        if os.path.exists(desktop_path):
            os.remove(desktop_path)
