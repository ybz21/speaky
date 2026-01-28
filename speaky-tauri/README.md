# Speaky Tauri

Cross-platform voice input tool built with Tauri (Rust + Svelte).

## Features

- Press-and-hold hotkey for voice recording
- Real-time speech-to-text with streaming support
- Multiple ASR engines:
  - Volcengine BigModel (火山引擎语音大模型)
  - OpenAI Whisper API
- Auto-paste recognized text to active application
- System tray integration
- Configurable hotkeys and settings

## Prerequisites

### All Platforms
- [Rust](https://rustup.rs/) (1.70+)
- [Node.js](https://nodejs.org/) (18+)

### Linux (Ubuntu/Debian)
```bash
sudo apt install libwebkit2gtk-4.1-dev libappindicator3-dev \
  librsvg2-dev patchelf libasound2-dev
```

### macOS
```bash
xcode-select --install
```

### Windows
- Visual Studio Build Tools 2022 with C++ workload

## Development

```bash
# Install dependencies
npm install

# Run in development mode
npm run tauri dev

# Build for production
npm run tauri build
```

## Project Structure

```
speaky-tauri/
├── src/                      # Svelte frontend
│   ├── App.svelte
│   ├── lib/
│   │   ├── components/       # UI components
│   │   ├── stores/           # State management
│   │   └── utils/            # Tauri IPC utilities
│   └── styles/
├── src-tauri/                # Rust backend
│   ├── src/
│   │   ├── audio/            # Audio recording (cpal)
│   │   ├── commands/         # Tauri IPC commands
│   │   ├── config/           # YAML configuration
│   │   ├── engines/          # ASR engines
│   │   ├── hotkey/           # Hotkey handling
│   │   └── input/            # Clipboard/paste
│   ├── Cargo.toml
│   └── tauri.conf.json
├── locales/                  # i18n YAML files
└── package.json
```

## Configuration

Configuration is stored in `~/.config/speaky/config.yaml` (Linux/macOS) or `%APPDATA%/speaky/config.yaml` (Windows).

### Example Configuration

```yaml
core:
  asr:
    hotkey: ctrl
    hotkey_hold_time: 1.0
    language: zh
    streaming_mode: true

engine:
  current: volc_bigmodel
  volc_bigmodel:
    app_key: your_app_key
    access_key: your_access_key
  openai:
    api_key: sk-xxx
    model: gpt-4o-transcribe
    base_url: https://api.openai.com/v1

appearance:
  theme: auto
  ui_language: auto
  window_opacity: 0.9
```

## License

MIT
