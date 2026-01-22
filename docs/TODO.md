# Speaky 未来技术方案分析

## 背景

当前 Speaky 使用 Python + PySide6 技术栈，存在以下跨平台打包问题：
- 依赖系统级音频库（已通过 miniaudio 解决）
- 打包体积较大（~100MB+）
- 启动速度较慢
- 不同平台打包流程差异大

本文档分析未来可能的技术栈迁移方案。

---

## 方案 B: Tauri (Rust + WebView)

### 概述

[Tauri](https://tauri.app/) 是基于 Rust 的桌面应用框架，前端使用 Web 技术（HTML/CSS/JS），后端使用 Rust 处理系统交互。

### 架构设计

```
┌─────────────────────────────────────────┐
│           Tauri Application             │
├─────────────────────────────────────────┤
│  Frontend (WebView)                     │
│  ├── React/Vue/Svelte                   │
│  ├── UI Components                      │
│  └── State Management                   │
├─────────────────────────────────────────┤
│  IPC Bridge (Commands & Events)         │
├─────────────────────────────────────────┤
│  Rust Backend                           │
│  ├── Audio Capture (cpal)               │
│  ├── ASR Engine Integration             │
│  ├── Hotkey Listener                    │
│  ├── Clipboard / Input Method           │
│  └── System Tray                        │
└─────────────────────────────────────────┘
```

### 核心依赖

| 功能 | Rust Crate | 说明 |
|------|------------|------|
| 音频录制 | `cpal` | 零依赖，直接调用系统 API |
| 热键监听 | `global-hotkey` | Tauri 官方插件 |
| 系统托盘 | `tauri-plugin-system-tray` | 内置支持 |
| HTTP 请求 | `reqwest` | ASR API 调用 |
| WebSocket | `tokio-tungstenite` | 流式 ASR |
| 本地 Whisper | `whisper-rs` | whisper.cpp 绑定 |

### 优势

1. **极小体积**: 打包后仅 ~10MB（对比 Electron ~150MB）
2. **零外部依赖**: cpal 直接使用系统原生音频 API
   - macOS: CoreAudio
   - Windows: WASAPI
   - Linux: ALSA/PulseAudio
3. **高性能**: Rust 后端，启动快、内存占用低
4. **安全性**: Rust 内存安全 + Tauri 权限系统
5. **现代前端**: 可复用现有 Web 生态（React、Vue、Tailwind）

### 劣势

1. **开发门槛高**: 需要掌握 Rust
2. **生态较新**: 相比 Electron 社区较小
3. **WebView 兼容性**: 依赖系统 WebView（Windows 需要 WebView2）
4. **迁移成本高**: 需要重写后端逻辑

### 迁移工作量评估

| 模块 | 工作量 | 说明 |
|------|--------|------|
| 音频录制 | 2-3天 | 用 cpal 重写 |
| ASR 集成 | 3-5天 | HTTP/WebSocket 调用 |
| 本地 Whisper | 5-7天 | whisper-rs 集成 |
| 热键系统 | 1-2天 | global-hotkey 插件 |
| UI 重写 | 5-7天 | 前端框架 + 样式 |
| 系统托盘 | 1天 | Tauri 内置 |
| 输入法集成 | 3-5天 | 平台相关代码 |
| **总计** | **20-30天** | |

### 示例代码

```rust
// src-tauri/src/audio.rs
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};

pub fn record_audio() -> Vec<i16> {
    let host = cpal::default_host();
    let device = host.default_input_device().unwrap();
    let config = cpal::StreamConfig {
        channels: 1,
        sample_rate: cpal::SampleRate(16000),
        buffer_size: cpal::BufferSize::Default,
    };

    let samples = Arc::new(Mutex::new(Vec::new()));
    let samples_clone = samples.clone();

    let stream = device.build_input_stream(
        &config,
        move |data: &[i16], _| {
            samples_clone.lock().unwrap().extend_from_slice(data);
        },
        |err| eprintln!("Error: {}", err),
        None,
    ).unwrap();

    stream.play().unwrap();
    // ... recording logic
    samples.lock().unwrap().clone()
}
```

---

## 方案 C: Electron (Node.js + Chromium)

### 概述

[Electron](https://www.electronjs.org/) 是使用 Web 技术构建桌面应用的成熟框架，内嵌 Chromium 浏览器和 Node.js 运行时。

### 架构设计

```
┌─────────────────────────────────────────┐
│           Electron Application          │
├─────────────────────────────────────────┤
│  Renderer Process (Chromium)            │
│  ├── React/Vue UI                       │
│  ├── Web Audio API (备用)               │
│  └── IPC Communication                  │
├─────────────────────────────────────────┤
│  Main Process (Node.js)                 │
│  ├── Audio Capture (node-audiorecorder) │
│  ├── ASR Integration                    │
│  ├── Global Hotkey                      │
│  ├── Clipboard / Robot.js               │
│  └── System Tray                        │
└─────────────────────────────────────────┘
```

### 核心依赖

| 功能 | NPM 包 | 说明 |
|------|--------|------|
| 音频录制 | `node-audiorecorder` / Web Audio API | 跨平台 |
| 热键监听 | `electron-globalShortcut` | 内置 API |
| 系统托盘 | `electron-tray` | 内置 API |
| HTTP 请求 | `axios` / `fetch` | ASR API |
| WebSocket | `ws` | 流式 ASR |
| 本地 Whisper | `whisper-node` | whisper.cpp Node 绑定 |
| 输入模拟 | `robotjs` | 跨平台键盘输入 |

### 优势

1. **开发效率高**: JavaScript/TypeScript，前端开发者友好
2. **生态成熟**: 大量现成组件和解决方案
3. **跨平台一致性**: Chromium 保证 UI 一致
4. **调试方便**: Chrome DevTools 支持
5. **社区庞大**: 问题容易找到解决方案

### 劣势

1. **体积巨大**: 打包后 ~150MB+（包含完整 Chromium）
2. **内存占用高**: 通常 200MB+ 起步
3. **启动较慢**: 需要初始化 Chromium
4. **安全顾虑**: Node.js 完整权限
5. **音频依赖**: node-audiorecorder 可能需要系统依赖

### 迁移工作量评估

| 模块 | 工作量 | 说明 |
|------|--------|------|
| 音频录制 | 1-2天 | Web Audio API 或 node-audiorecorder |
| ASR 集成 | 2-3天 | fetch/axios 调用 |
| 本地 Whisper | 3-5天 | whisper-node 集成 |
| 热键系统 | 0.5天 | Electron 内置 |
| UI 重写 | 3-5天 | React/Vue 组件 |
| 系统托盘 | 0.5天 | Electron 内置 |
| 输入法集成 | 2-3天 | robotjs |
| **总计** | **12-20天** | |

### 示例代码

```javascript
// main.js
const { app, globalShortcut, Tray } = require('electron');
const { Recorder } = require('node-audiorecorder');

const recorder = new Recorder({
  sampleRate: 16000,
  channels: 1,
  bitDepth: 16,
});

// 全局热键
app.whenReady().then(() => {
  globalShortcut.register('Control+Space', () => {
    if (recorder.isRecording) {
      const audio = recorder.stop();
      sendToASR(audio);
    } else {
      recorder.start();
    }
  });
});

// 系统托盘
const tray = new Tray('icon.png');
tray.setContextMenu(Menu.buildFromTemplate([
  { label: 'Settings', click: openSettings },
  { label: 'Quit', click: app.quit },
]));
```

---

## 方案对比总结

| 维度 | Python + PySide6 | Tauri | Electron |
|------|------------------|-------|----------|
| **打包体积** | ~100MB | ~10MB | ~150MB |
| **启动速度** | 中等 | 快 | 慢 |
| **内存占用** | ~150MB | ~50MB | ~200MB |
| **开发难度** | 低 | 高 | 低 |
| **生态成熟度** | 中等 | 较新 | 成熟 |
| **跨平台一致性** | 中等 | 高 | 高 |
| **外部依赖** | 无 (miniaudio) | 无 | 可能有 |
| **迁移成本** | - | 高 | 中等 |

## 建议

### 短期 (当前)

保持 Python + PySide6 技术栈，使用 miniaudio 解决音频依赖问题。

### 中期 (如果需要更好的用户体验)

考虑迁移到 **Electron**：
- 开发成本较低
- 可以渐进式迁移
- 社区支持好

### 长期 (如果追求极致体验)

考虑迁移到 **Tauri**：
- 更小的体积和更好的性能
- 更现代的技术栈
- 更好的安全性

---

## 参考资源

### Tauri
- [Tauri 官方文档](https://tauri.app/v1/guides/)
- [cpal - Rust 音频库](https://github.com/RustAudio/cpal)
- [whisper-rs](https://github.com/tazz4843/whisper-rs)
- [global-hotkey](https://github.com/tauri-apps/global-hotkey)

### Electron
- [Electron 官方文档](https://www.electronjs.org/docs/latest/)
- [node-audiorecorder](https://github.com/AlejandroSuero/node-audiorecorder)
- [robotjs](https://github.com/octalmage/robotjs)
- [whisper-node](https://github.com/ariym/whisper-node)

### 通用
- [miniaudio](https://github.com/mackron/miniaudio) - 单头文件音频库
- [whisper.cpp](https://github.com/ggerganov/whisper.cpp) - 高性能本地 ASR
