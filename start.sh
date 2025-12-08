#!/bin/bash
cd "$(dirname "$0")"

# China PyPI mirror
export UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple
export UV_HTTP_TIMEOUT=300

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

uv run --with PyQt5 --with pynput --with pyaudio --with numpy --with pyyaml --with openai --with requests --with websockets python -m speaky.main "$@"
