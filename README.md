# SpeekInput

Linux 语音输入法，支持快捷键唤醒、可视化界面、多种语音识别引擎。

## 功能

- 全局快捷键唤醒（可配置）
- 悬浮窗实时显示录音状态和识别结果
- 系统托盘图标，右键菜单快速配置
- 图形化设置界面
- 识别结果自动输入到当前焦点窗口
- 语音识别引擎：
  - 离线：Whisper / faster-whisper
  - 在线：OpenAI API、火山云、阿里云、腾讯云

## 安装

```bash
# 下载 deb 包安装（无需其他依赖）
sudo dpkg -i speek-input_1.0.0_amd64.deb
```

## 使用

- 从应用菜单启动，或命令行运行 `speek-input`
- 长按快捷键（默认 `Ctrl`）开始录音
- 悬浮窗显示录音波形和识别文字
- 松开快捷键，结束录音并自动输入识别结果
- 右键托盘图标打开设置

## 配置

`~/.config/speek-input/config.yaml`

```yaml
hotkey: "ctrl"  # 长按开始，松开结束
engine: whisper
whisper:
  model: base
openai:
  api_key: "sk-xxx"
```

## 构建

```bash
# 构建 deb 包（使用 PyInstaller 打包，内置所有依赖）
./build-deb.sh
```