#!/bin/bash
cd "$(dirname "$0")"

# China PyPI mirror
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export UV_HTTP_TIMEOUT=300

# Fix: Use system libstdc++ to resolve GLIBCXX version issues with conda/miniconda
# This fixes: "version `GLIBCXX_3.4.32' not found" error
if [ -f /usr/lib/x86_64-linux-gnu/libstdc++.so.6 ]; then
    export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libstdc++.so.6
fi

# Check and install system dependencies for Qt/PySide6
check_system_deps() {
    missing_deps=""

    # Check for libxcb-cursor0 (required by Qt 6.5+)
    if ! dpkg -s libxcb-cursor0 >/dev/null 2>&1; then
        missing_deps="$missing_deps libxcb-cursor0"
    fi

    # Check for portaudio (required by pyaudio)
    if ! dpkg -s portaudio19-dev >/dev/null 2>&1; then
        missing_deps="$missing_deps portaudio19-dev"
    fi

    if [ -n "$missing_deps" ]; then
        echo "Missing system dependencies:$missing_deps"
        echo "Please install them with:"
        echo "  sudo apt-get install$missing_deps"
        exit 1
    fi
}

check_system_deps

# WSL2 display setup (Windows 11 WSLg)
if grep -qi microsoft /proc/version 2>/dev/null; then
    if [ -z "$DISPLAY" ]; then
        export DISPLAY=:0
    fi
    export QT_QPA_PLATFORM=wayland
    export XDG_RUNTIME_DIR=/mnt/wslg/runtime-dir

    # WSLg PulseAudio
    export PULSE_SERVER=unix:/mnt/wslg/PulseServer
fi

uv run python -m speaky.main "$@"
