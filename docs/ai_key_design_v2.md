# AI 键功能设计 v2

## 问题分析

当前问题：浮窗不显示（或被遮挡）

### 根本原因

```
按下 Alt
  ↓
_on_ai_hotkey_press()
  ├── show_recording()  ← 显示浮窗
  └── webbrowser.open() ← 打开浏览器，浏览器抢占焦点！
                          浏览器窗口在最前面，遮挡浮窗
```

虽然浮窗有 `WindowStaysOnTopHint`，但在 Windows 上：
1. 新打开的程序会获得焦点和置顶
2. 浏览器窗口可能遮挡浮窗
3. 需要在浏览器打开后重新 raise 浮窗

## 解决方案

### 方案：延迟打开浏览器 + 定时 raise 浮窗

```
按下 Alt
    │
    ▼
┌─────────────────────────────┐
│ 1. 显示录音浮窗              │
│ 2. 开始录音                  │
│ 3. 延迟 500ms 后打开浏览器   │  ← 让浮窗先稳定显示
│ 4. 打开浏览器后定时 raise    │  ← 每隔 500ms raise 一次，持续到松开
└─────────────────────────────┘
    │
    │ (用户说话中，浮窗始终保持在最前)
    │
松开 Alt
    │
    ▼
┌─────────────────────────────┐
│ 5. 停止录音                  │
│ 6. 停止 raise 定时器         │
│ 7. 显示识别中...             │
└─────────────────────────────┘
    │
    │ (识别中，浮窗继续显示)
    │
识别完成
    │
    ▼
┌─────────────────────────────┐
│ 8. 显示识别结果              │
│ 9. 等待页面加载完成          │
│ 10. 隐藏浮窗                 │
│ 11. 输入文字 + 回车          │
└─────────────────────────────┘
```

### 关键代码改动

```python
class SpeakyApp:
    def __init__(self):
        # ...
        self._ai_raise_timer = None  # 定时 raise 浮窗

    def _on_ai_hotkey_press(self):
        self._ai_mode = True
        self._ai_browser_open_time = time.time()

        # 1. 先显示浮窗并开始录音
        self._floating_window.show_recording()
        self._recorder.start()

        # 2. 延迟打开浏览器（让浮窗先稳定）
        QTimer.singleShot(300, self._ai_open_browser)

        # 3. 启动定时 raise，确保浮窗始终在最前
        self._start_ai_raise_timer()

    def _ai_open_browser(self):
        ai_url = config.get("ai_url", "https://chatgpt.com")
        webbrowser.open(ai_url)
        # 打开后立即 raise 一次
        QTimer.singleShot(100, self._floating_window.raise_)

    def _start_ai_raise_timer(self):
        if self._ai_raise_timer is None:
            self._ai_raise_timer = QTimer()
            self._ai_raise_timer.timeout.connect(self._floating_window.raise_)
            self._ai_raise_timer.start(500)  # 每 500ms raise 一次

    def _stop_ai_raise_timer(self):
        if self._ai_raise_timer:
            self._ai_raise_timer.stop()
            self._ai_raise_timer = None

    def _on_ai_hotkey_release(self):
        self._stop_ai_raise_timer()  # 停止 raise
        self._signals.ai_stop_recording.emit()
```

## 时序图

```
时间轴:
0ms     ─┬─ 按下 Alt
         │  显示录音浮窗
         │  开始录音
         │
300ms   ─┼─ 打开浏览器
         │
400ms   ─┼─ raise 浮窗（浏览器打开后）
         │
500ms   ─┼─ 定时 raise
         │
1000ms  ─┼─ 定时 raise
         │
~2000ms ─┼─ 松开 Alt
         │  停止录音
         │  停止 raise 定时器
         │  显示"识别中..."
         │
~2500ms ─┼─ 识别完成
         │  显示结果
         │
~3000ms ─┼─ 页面加载等待完成
         │  隐藏浮窗
         │  输入文字
         │  按回车
```

## 优点

1. **浮窗始终可见**：通过定时 raise 确保不被浏览器遮挡
2. **用户体验好**：看到浮窗后才打开浏览器，心理预期清晰
3. **兼容性强**：不依赖特定窗口管理行为
