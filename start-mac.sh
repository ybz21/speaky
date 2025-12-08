#!/bin/bash
cd "$(dirname "$0")"

echo "Starting Speaky..."
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv is not installed. Installing via brew..."
    if command -v brew &> /dev/null; then
        brew install uv
    else
        echo "Please install uv first: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi

# Note: Accessibility permission check is handled in Python code

# Install portaudio if needed (for pyaudio)
if ! brew list portaudio &> /dev/null 2>&1; then
    echo "Installing portaudio for audio recording..."
    brew install portaudio
fi

# Run with uv
uv run --with PyQt5 --with pynput --with pyaudio --with numpy --with pyyaml --with openai --with requests --with websockets python -m speaky.main "$@"
