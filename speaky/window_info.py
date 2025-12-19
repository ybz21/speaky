"""Window information utilities for getting focused app name and icon."""

import logging
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Cache for desktop entries to avoid repeated file system scans
_desktop_cache: dict[str, dict] = {}
_icon_cache: dict[str, Optional[str]] = {}


@dataclass
class WindowInfo:
    """Information about the focused window."""
    wm_class: str  # e.g., "cursor", "Cursor"
    wm_instance: str  # e.g., "cursor"
    window_name: str  # e.g., "file.py - project - Cursor"
    app_name: str  # e.g., "Cursor"
    icon_path: Optional[str] = None  # Path to icon file


def get_focused_window_info() -> Optional[WindowInfo]:
    """Get information about the currently focused window.

    Returns:
        WindowInfo object or None if unable to get info.
    """
    system = platform.system()

    if system == "Linux":
        return _get_linux_window_info()
    elif system == "Darwin":
        return _get_macos_window_info()
    elif system == "Windows":
        return _get_windows_window_info()

    return None


def _get_linux_window_info() -> Optional[WindowInfo]:
    """Get focused window info on Linux using xprop."""
    try:
        # Get active window ID
        result = subprocess.run(
            ['xprop', '-root', '_NET_ACTIVE_WINDOW'],
            capture_output=True, text=True, timeout=1
        )
        if result.returncode != 0:
            return None

        match = re.search(r'0x[0-9a-fA-F]+', result.stdout)
        if not match:
            return None
        window_id = match.group()

        # Get WM_CLASS
        result = subprocess.run(
            ['xprop', '-id', window_id, 'WM_CLASS'],
            capture_output=True, text=True, timeout=1
        )
        wm_class = ""
        wm_instance = ""
        if result.returncode == 0:
            # WM_CLASS(STRING) = "cursor", "Cursor"
            match = re.search(r'"([^"]*)",\s*"([^"]*)"', result.stdout)
            if match:
                wm_instance = match.group(1)  # First is instance (lowercase usually)
                wm_class = match.group(2)  # Second is class (display name)

        # Get window name
        result = subprocess.run(
            ['xprop', '-id', window_id, '_NET_WM_NAME'],
            capture_output=True, text=True, timeout=1
        )
        window_name = ""
        if result.returncode == 0:
            match = re.search(r'"([^"]*)"', result.stdout)
            if match:
                window_name = match.group(1)

        # Find app name and icon from desktop file
        app_name = wm_class or wm_instance or "Unknown"
        icon_path = _find_icon_for_wm_class(wm_class, wm_instance)

        # Try to get a better app name from desktop file
        desktop_info = _find_desktop_entry(wm_class, wm_instance)
        if desktop_info and desktop_info.get('name'):
            app_name = desktop_info['name']

        return WindowInfo(
            wm_class=wm_class,
            wm_instance=wm_instance,
            window_name=window_name,
            app_name=app_name,
            icon_path=icon_path
        )

    except Exception as e:
        logger.debug(f"Failed to get Linux window info: {e}")
        return None


def _get_macos_window_info() -> Optional[WindowInfo]:
    """Get focused window info on macOS using AppleScript."""
    try:
        script = '''
        tell application "System Events"
            set frontApp to first application process whose frontmost is true
            set appName to name of frontApp
            set bundleId to bundle identifier of frontApp
        end tell
        return appName & "|" & bundleId
        '''
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True, text=True, timeout=2
        )
        if result.returncode != 0:
            return None

        parts = result.stdout.strip().split('|')
        app_name = parts[0] if parts else "Unknown"
        bundle_id = parts[1] if len(parts) > 1 else ""

        # Try to find icon
        icon_path = _find_macos_icon(bundle_id, app_name)

        return WindowInfo(
            wm_class=bundle_id,
            wm_instance=app_name.lower(),
            window_name="",
            app_name=app_name,
            icon_path=icon_path
        )

    except Exception as e:
        logger.debug(f"Failed to get macOS window info: {e}")
        return None


def _get_windows_window_info() -> Optional[WindowInfo]:
    """Get focused window info on Windows using ctypes."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        # Get foreground window
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        # Get window title
        length = user32.GetWindowTextLengthW(hwnd) + 1
        buffer = ctypes.create_unicode_buffer(length)
        user32.GetWindowTextW(hwnd, buffer, length)
        window_name = buffer.value

        # Get process ID
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        # Get process name
        app_name = "Unknown"
        try:
            import psutil
            proc = psutil.Process(pid.value)
            app_name = proc.name().replace('.exe', '')
        except Exception:
            pass

        # Try to find icon (Windows icon extraction is complex, skip for now)
        icon_path = None

        return WindowInfo(
            wm_class=app_name,
            wm_instance=app_name.lower(),
            window_name=window_name,
            app_name=app_name.title(),
            icon_path=icon_path
        )

    except Exception as e:
        logger.debug(f"Failed to get Windows window info: {e}")
        return None


def _find_desktop_entry(wm_class: str, wm_instance: str) -> Optional[dict]:
    """Find desktop entry by WM_CLASS."""
    global _desktop_cache

    # Build cache if empty
    if not _desktop_cache:
        _build_desktop_cache()

    # Search by StartupWMClass first (exact match)
    for key, entry in _desktop_cache.items():
        startup_wm_class = entry.get('startup_wm_class', '').lower()
        if startup_wm_class and (
            startup_wm_class == wm_class.lower() or
            startup_wm_class == wm_instance.lower()
        ):
            return entry

    # Search by filename match
    search_terms = [wm_class.lower(), wm_instance.lower()]
    for term in search_terms:
        if term in _desktop_cache:
            return _desktop_cache[term]

    return None


def _build_desktop_cache():
    """Build cache of desktop entries.

    Note: System directories are processed LAST so they take priority over
    user-local entries (which may have broken icon paths).
    """
    global _desktop_cache

    # Process local dirs first, system dirs last (so system wins on conflicts)
    desktop_dirs = [
        os.path.expanduser('~/.local/share/flatpak/exports/share/applications'),
        os.path.expanduser('~/.local/share/applications'),
        '/var/lib/flatpak/exports/share/applications',
        '/usr/local/share/applications',
        '/usr/share/applications',  # System dir last = highest priority
    ]

    for dir_path in desktop_dirs:
        if not os.path.isdir(dir_path):
            continue

        try:
            for filename in os.listdir(dir_path):
                if not filename.endswith('.desktop'):
                    continue

                filepath = os.path.join(dir_path, filename)
                entry = _parse_desktop_file(filepath)
                if entry:
                    # Store by lowercase name without .desktop
                    key = filename[:-8].lower()
                    _desktop_cache[key] = entry
        except Exception as e:
            logger.debug(f"Error reading desktop dir {dir_path}: {e}")


def _parse_desktop_file(filepath: str) -> Optional[dict]:
    """Parse a .desktop file and extract relevant fields."""
    try:
        entry = {'path': filepath}
        in_desktop_entry = False

        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if line == '[Desktop Entry]':
                    in_desktop_entry = True
                    continue
                elif line.startswith('[') and line.endswith(']'):
                    in_desktop_entry = False
                    continue

                if not in_desktop_entry or '=' not in line:
                    continue

                key, value = line.split('=', 1)
                key = key.strip().lower()
                value = value.strip()

                if key == 'name':
                    entry['name'] = value
                elif key == 'icon':
                    entry['icon'] = value
                elif key == 'startupwmclass':
                    entry['startup_wm_class'] = value
                elif key == 'exec':
                    entry['exec'] = value

        return entry if entry.get('name') else None

    except Exception as e:
        logger.debug(f"Error parsing desktop file {filepath}: {e}")
        return None


def _find_icon_for_wm_class(wm_class: str, wm_instance: str) -> Optional[str]:
    """Find icon path for a WM_CLASS."""
    global _icon_cache

    cache_key = f"{wm_class}|{wm_instance}"
    if cache_key in _icon_cache:
        return _icon_cache[cache_key]

    # First, try to find desktop entry
    entry = _find_desktop_entry(wm_class, wm_instance)
    icon_name = entry.get('icon') if entry else None

    # If no icon from desktop entry, use wm_class as icon name
    if not icon_name:
        icon_name = wm_class.lower() or wm_instance.lower()

    # Find actual icon file
    icon_path = _resolve_icon_path(icon_name)
    _icon_cache[cache_key] = icon_path

    return icon_path


def _resolve_icon_path(icon_name: str) -> Optional[str]:
    """Resolve icon name to actual file path."""
    if not icon_name:
        return None

    # If it's already an absolute path and exists
    if os.path.isabs(icon_name):
        if os.path.isfile(icon_name):
            return icon_name
        # If absolute path doesn't exist, extract basename and search
        icon_name = os.path.splitext(os.path.basename(icon_name))[0]

    # Common icon directories and sizes (prefer larger sizes)
    icon_dirs = [
        '/usr/share/pixmaps',
        '/usr/share/icons/hicolor/256x256/apps',
        '/usr/share/icons/hicolor/128x128/apps',
        '/usr/share/icons/hicolor/96x96/apps',
        '/usr/share/icons/hicolor/64x64/apps',
        '/usr/share/icons/hicolor/48x48/apps',
        '/usr/share/icons/hicolor/scalable/apps',
        os.path.expanduser('~/.local/share/icons/hicolor/256x256/apps'),
        os.path.expanduser('~/.local/share/icons/hicolor/128x128/apps'),
        os.path.expanduser('~/.local/share/icons/hicolor/48x48/apps'),
        '/var/lib/flatpak/exports/share/icons/hicolor/256x256/apps',
        '/var/lib/flatpak/exports/share/icons/hicolor/128x128/apps',
    ]

    extensions = ['.png', '.svg', '.xpm', '']

    for icon_dir in icon_dirs:
        if not os.path.isdir(icon_dir):
            continue

        for ext in extensions:
            icon_path = os.path.join(icon_dir, f"{icon_name}{ext}")
            if os.path.isfile(icon_path):
                return icon_path

    return None


def _find_macos_icon(bundle_id: str, app_name: str) -> Optional[str]:
    """Find app icon on macOS."""
    # Common locations for app icons
    app_dirs = [
        '/Applications',
        os.path.expanduser('~/Applications'),
        '/System/Applications',
    ]

    for app_dir in app_dirs:
        app_path = os.path.join(app_dir, f"{app_name}.app")
        if os.path.isdir(app_path):
            # Look for icon in Contents/Resources
            resources_path = os.path.join(app_path, 'Contents', 'Resources')
            if os.path.isdir(resources_path):
                for filename in os.listdir(resources_path):
                    if filename.endswith('.icns'):
                        return os.path.join(resources_path, filename)

    return None
