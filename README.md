# Speaky

跨平台语音输入工具，支持快捷键唤醒、可视化界面、多种语音识别引擎。

## 功能

- 全局快捷键唤醒（可配置）
- 悬浮窗实时显示录音状态和识别结果
- 系统托盘图标，右键菜单快速配置
- 图形化设置界面
- 识别结果自动输入到当前焦点窗口
- 多语言界面（中、英、日、韩、德、法、西、葡、俄）
- 语音识别引擎：
  - 离线：Whisper / faster-whisper
  - 在线：OpenAI API、火山云、阿里云、腾讯云

## 安装

### 方式一：下载预编译包（推荐，无需 Python）

| 平台 | 下载 | 系统依赖 |
|------|------|----------|
| Windows | `speaky_1.0.0_windows.exe` | 无 |
| macOS (Apple Silicon) | `speaky_1.0.0_macos_arm64.dmg` | `brew install portaudio` |
| macOS (Intel) | `speaky_1.0.0_macos_x86_64.dmg` | `brew install portaudio` |
| Linux (deb) | `speaky_1.0.0_amd64.deb` | 自动安装 |

```bash
# Linux (deb 包会自动安装依赖)
sudo dpkg -i speaky_1.0.0_amd64.deb
sudo apt-get install -f  # 如有缺失依赖

# macOS
brew install portaudio   # 先安装依赖
# 然后打开 DMG 拖入 Applications

# Windows (无需额外依赖)
# 双击运行 exe
```

### 方式二：从源码运行（需要 Python）

```bash
# Linux / macOS (使用 uv)
./start.sh        # Linux
./start-mac.sh    # macOS

# Windows (使用 conda)
start.bat
```

## 使用

1. 启动后，应用在系统托盘显示图标
2. 长按快捷键（默认 `Ctrl`）开始录音
3. 悬浮窗显示录音波形
4. 松开快捷键，结束录音并自动输入识别结果
5. 右键托盘图标打开设置

### macOS 注意事项

首次运行需要授予权限：
- **辅助功能**：系统设置 > 隐私与安全性 > 辅助功能
- **麦克风**：系统设置 > 隐私与安全性 > 麦克风

## 配置

配置文件位置：`~/.config/speaky/config.yaml`

```yaml
hotkey: "ctrl"           # 长按开始，松开结束
hotkey_hold_time: 1.0    # 长按多少秒后开始录音
engine: volcengine       # whisper, openai, volcengine, aliyun, tencent
language: zh             # 识别语言
ui_language: auto        # 界面语言: auto, en, zh, zh_TW, ja, ko, de, fr, es, pt, ru

whisper:
  model: base
  device: auto

openai:
  api_key: ""
  base_url: "https://api.openai.com/v1"

volcengine:
  app_id: ""
  access_key: ""
  secret_key: ""

aliyun:
  app_key: ""
  access_token: ""

tencent:
  secret_id: ""
  secret_key: ""
```

## 构建

```bash
# 跨平台构建（在对应系统上运行）
python build.py

# macOS: 构建双架构版本
python build.py --universal

# macOS: 指定架构
python build.py --arch arm64    # Apple Silicon
python build.py --arch x86_64   # Intel

# 输出:
# - Linux: dist/speaky_1.0.0_amd64.deb
# - macOS: dist/speaky_1.0.0_macos_arm64.dmg (Apple Silicon)
#          dist/speaky_1.0.0_macos_x86_64.dmg (Intel)
# - Windows: dist/speaky_1.0.0_windows.exe
```

## 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行
python -m speaky.main
```
