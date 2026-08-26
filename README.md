<div align="center">

# 🎙️ Speaky

**一键唤醒的语音输入工具 · 快速 · 准确 · 跨平台**

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](https://github.com/ybz21/speaky)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

---

### 长按快捷键 → 开口说话 → 自动输入

无需打字，让语音识别为你高效工作

[📥 下载安装](#安装) · [🚀 快速开始](#使用) · [📖 文档](#配置) · [🤝 参与贡献](#贡献)

</div>

---

## ✨ 特性

<table>
<tr>
<td width="50%">

### 🎯 即用即走
- **全局快捷键**：随时随地，长按即录
- **悬浮窗显示**：实时波形 + 识别结果
- **自动输入**：识别完成后自动填入当前光标位置
- **AI 键**：一键唤醒 AI 对话（支持 ChatGPT、Claude、豆包等）
- **系统托盘**：隐藏在后台，右键快速配置

</td>
<td width="50%">

### 🌍 多引擎 · 多语言
- **火山引擎**：语音识别大模型 ✅ / 一句话识别 ✅（已适配）
- **OpenAI**：Whisper API（待测试 🔄）
- **本地引擎**：Whisper / faster-whisper（待测试 🔄）
- **多语言识别**：支持中英日韩等多种语言
- **多语言界面**：中、英、日、韩、德、法、西、葡、俄

</td>
</tr>
<tr>
<td width="50%">

### ⚡ 高性能 · 原生体验
- **轻量级**：基于 PySide6/Qt6，启动快速，资源占用低
- **一键打包**：PyInstaller 单文件，无需 Python 环境
- **原生性能**：比 Electron 方案快 3-5 倍

</td>
<td width="50%">

### 🎨 简洁 · 现代
- **Fluent Design**：现代化的流畅设计语言
- **暗色模式**：自动适配系统主题
- **可视化配置**：图形化设置界面，无需编辑配置文件

</td>
</tr>
</table>

## 📥 安装

### 方式一：预编译包（推荐）

> 💡 无需安装 Python，开箱即用

<table>
<tr>
<th>平台</th>
<th>下载</th>
<th>安装方式</th>
</tr>
<tr>
<td>🐧 <b>Linux</b></td>
<td><code>Speaky_1.0.1_amd64.deb</code></td>
<td>

```bash
# 一键安装（自动处理依赖）
sudo apt install ./Speaky_1.0.1_amd64.deb
```

</td>
</tr>
<tr>
<td>🍎 <b>macOS</b></td>
<td>
<code>Speaky_1.0.1_aarch64.dmg</code> (Apple Silicon)<br>
<code>Speaky_1.0.1_x64.dmg</code> (Intel)
</td>
<td>

```bash
# 安装系统依赖
brew install portaudio
# 打开 DMG，拖入 Applications
```

</td>
</tr>
<tr>
<td>🪟 <b>Windows</b></td>
<td><code>Speaky_1.0.1_x64-setup.exe</code></td>
<td>

```powershell
# 双击运行（无需额外依赖）
```

</td>
</tr>
</table>

### 方式二：从源码运行

> 🔧 适合开发者和想要最新功能的用户

```bash
# 克隆仓库
git clone https://github.com/ybz21/speaky.git
cd speaky

# Linux / macOS (使用 uv)
./start.sh        # Linux
./start-mac.sh    # macOS

# Windows (使用 conda)
start.bat
```

## 🚀 使用

### 基本流程

```mermaid
graph LR
    A[长按快捷键] --> B[开始录音]
    B --> C[说话]
    C --> D[松开快捷键]
    D --> E[识别完成]
    E --> F[自动输入]
```

1. **启动应用** - 应用会最小化到系统托盘
2. **长按快捷键** - 默认 `Ctrl`，可在设置中修改
3. **开口说话** - 悬浮窗显示实时波形
4. **松开快捷键** - 自动识别并输入到光标位置
5. **右键托盘图标** - 打开设置、查看日志、退出应用

### 💡 快捷操作

| 操作 | 说明 |
|------|------|
| 长按 `Ctrl` | 开始录音（默认） |
| 松开快捷键 | 结束录音并识别 |
| 长按 `Alt` | AI 键：打开 AI 对话并输入识别结果 |
| 右键托盘图标 | 打开菜单 |
| 点击悬浮窗 | 拖动位置 |

### 🤖 AI 键使用

AI 键可以让你快速与 AI 对话：

1. **长按 AI 键**（默认 `Alt`）并说话
2. 自动打开配置的 AI 网站（ChatGPT / Claude / 豆包等）
3. 将识别结果填入输入框并发送
4. 适合快速提问、翻译、写作等场景

> 💡 在配置文件中可以自定义 AI 网站 URL 和行为

### ⚠️ macOS 用户须知

首次运行需要授予权限（系统会自动弹出提示）：

- **🎤 麦克风权限**：`系统设置` > `隐私与安全性` > `麦克风`
- **⌨️ 辅助功能权限**：`系统设置` > `隐私与安全性` > `辅助功能`

> 💡 如果自动输入不工作，请检查是否已授予辅助功能权限

## ⚙️ 配置

### 图形化配置（推荐）

右键托盘图标 > **设置**，在图形界面中配置所有选项。

### 配置文件（高级）

配置文件位置：`~/.config/speaky/config.yaml`

<details>
<summary>点击展开完整配置示例</summary>

```yaml
# ========== 核心设置 ==========
core:
  # 语音识别 (ASR)
  asr:
    hotkey: ctrl              # 唤醒键: ctrl, alt, shift, cmd, f1-f12, space
    hotkey_hold_time: 1.0     # 长按延迟(秒)，0 表示立即开始
    language: zh              # 识别语言: zh, en, ja, ko
    streaming_mode: true      # 流式识别，边说边显示结果

  # AI 键（实验性功能）
  ai:
    enabled: true             # 是否启用 AI 键
    hotkey: alt               # AI 热键
    hotkey_hold_time: 0.5     # AI 键长按延迟(秒)
    url: https://chatgpt.com  # AI 网站地址
    page_load_delay: 3.0      # 页面加载等待时间(秒)
    auto_enter: true          # 自动发送(回车)

# ========== 引擎设置 ==========
engine:
  current: volc_bigmodel      # 当前使用的引擎

  # ✅ 火山引擎-语音识别大模型（推荐，已适配）
  volc_bigmodel:
    app_key: ""               # 应用 Key
    access_key: ""            # Access Key
    model: bigmodel           # 模型: bigmodel, bigmodel_async, bigmodel_nostream

  # ✅ 火山引擎-一句话识别（已适配）
  volcengine:
    app_id: ""                # App ID
    access_key: ""            # Access Key
    secret_key: ""            # Secret Key

  # 🔄 OpenAI Whisper（待测试）
  openai:
    api_key: ""               # OpenAI API Key
    model: whisper-1          # 模型名称
    base_url: https://api.openai.com/v1

  # 🔄 本地 Whisper 模型（待测试）
  whisper:
    model: base               # 模型: tiny, base, small, medium, large
    device: auto              # 设备: auto, cpu, cuda

# ========== 外观设置 ==========
appearance:
  theme: auto                 # 主题: light, dark, auto
  ui_language: auto           # 界面语言: auto, en, zh, zh_TW, ja, ko, de, fr, es, pt, ru
  show_waveform: true         # 显示波形
  window_opacity: 0.9         # 窗口透明度 (0.5-1.0)
```

</details>

### 引擎选择建议

| 引擎 | 状态 | 适用场景 | 优点 | 缺点 |
|------|------|----------|------|------|
| **火山引擎大模型** | ✅ 已适配 | 高准确率需求、国内用户 | 识别准确、延迟低、支持流式 | 需要申请账号 |
| **火山引擎一句话** | ✅ 已适配 | 短句识别 | 响应快、稳定 | 不支持长句 |
| **OpenAI Whisper** | 🔄 待测试 | 英文识别、国际用户 | 国际通用、准确率高 | 需要付费、国内访问慢 |
| **本地 Whisper** | 🔄 待测试 | 隐私敏感、离线场景 | 完全本地、免费、隐私 | 首次下载模型较大、性能要求高 |

> 💡 **推荐使用火山引擎大模型**：已经过充分测试，识别准确率高，支持流式输出。

## 🔨 构建

### 快速构建

```bash
# 在对应平台上运行（会自动检测并构建）
python build.py
```

### 跨架构构建（macOS）

```bash
# 构建 Universal Binary（同时支持 Intel 和 Apple Silicon）
python build.py --universal

# 指定架构
python build.py --arch arm64    # Apple Silicon
python build.py --arch x86_64   # Intel
```

### 构建产物

| 平台 | 输出文件 | 大小（约） |
|------|----------|-----------|
| Linux | `target/release/bundle/deb/Speaky_1.0.1_amd64.deb` | 80-120 MB |
| macOS (Apple Silicon) | `target/release/bundle/dmg/Speaky_1.0.1_aarch64.dmg` | 60-100 MB |
| macOS (Intel) | `target/release/bundle/dmg/Speaky_1.0.1_x64.dmg` | 60-100 MB |
| Windows | `target/release/bundle/nsis/Speaky_1.0.1_x64-setup.exe` | 70-110 MB |

> 💡 **为什么这么小？** 相比 Electron 应用（200-300MB），PyInstaller 打包的应用不包含完整浏览器引擎，体积小 50-60%。

---

## 🛠️ 开发

### 技术栈

- **UI 框架**: [PySide6](https://doc.qt.io/qtforpython-6/) (Qt6)
- **UI 组件库**: [PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) (qfluentwidgets)
- **音频处理**: PyAudio + NumPy
- **语音识别**: faster-whisper / OpenAI API
- **输入模拟**: pynput
- **打包工具**: PyInstaller

### 开发环境搭建

```bash
# 克隆仓库
git clone https://github.com/ybz21/speaky.git
cd speaky

# 安装开发依赖（推荐使用 uv）
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"

# 运行
python -m speaky.main
```

### 项目结构

```
speaky/
├── speaky/              # 主程序代码
│   ├── main.py         # 入口文件
│   ├── ui/             # UI 组件
│   ├── core/           # 核心功能（录音、识别）
│   ├── engines/        # 识别引擎适配器
│   └── locales/        # 多语言翻译文件
├── resources/          # 图标等资源文件
├── build.py           # 构建脚本
├── start.sh           # Linux 启动脚本
└── start-mac.sh       # macOS 启动脚本
```

### 调试技巧

```bash
# 查看实时日志
tail -f ~/.config/speaky/logs/speaky.log

# 启用详细日志
export SPEAKY_DEBUG=1
python -m speaky.main
```

---

## 🤝 贡献

欢迎各种形式的贡献！无论是新功能、Bug 修复、文档改进还是问题反馈。

### 贡献方式

1. 🐛 **报告 Bug**: [提交 Issue](https://github.com/yourusername/speaky/issues/new?template=bug_report.md)
2. 💡 **功能建议**: [提交 Issue](https://github.com/yourusername/speaky/issues/new?template=feature_request.md)
3. 📖 **改进文档**: 修改 README 或 Wiki
4. 🔨 **提交代码**: Fork 项目，提交 Pull Request

### 开发规范

- 遵循 [PEP 8](https://pep8.org/) 代码规范
- 提交前运行 `black` 和 `ruff` 格式化代码
- 重要功能请添加测试用例
- PR 描述清楚修改内容和原因

### 添加新的识别引擎

```python
# speaky/engines/your_engine.py
from .base import EngineBase

class YourEngine(EngineBase):
    def recognize(self, audio_data: bytes) -> str:
        # 实现识别逻辑
        return "识别结果"
```

---

## 📝 许可证

本项目采用 [MIT License](LICENSE) 开源。

---

## 🙏 致谢

- [PySide6-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) - 现代化的 Fluent Design 组件库
- [faster-whisper](https://github.com/guillaumekln/faster-whisper) - 高性能的 Whisper 实现
- [pynput](https://github.com/moses-palmer/pynput) - 跨平台输入模拟库

---

## 💬 社区与支持

- 📧 **邮件**: bingzhengyan93@gmail.com
- 💬 **讨论**: [GitHub Discussions](https://github.com/ybz21/speaky/discussions)
- 🐛 **问题反馈**: [GitHub Issues](https://github.com/ybz21/speaky/issues)

---

<div align="center">

**如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！**

Made with ❤️ by [ybz21](https://github.com/ybz21)

</div>
