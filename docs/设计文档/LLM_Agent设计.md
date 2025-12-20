# LLM Agent 功能设计文档

> 目的：添加大模型配置、MCP 工具集成和基于意图识别的智能操作功能

---

## 一、功能概述

### 1.1 核心功能

| 功能 | 说明 |
|------|------|
| **LLM 配置** | 支持配置 Base URL、API Key、Model，Model 列表自动从 API 拉取 |
| **MCP 配置** | 支持配置 MCP Server，扩展 Agent 能力（文件操作、网页浏览等） |
| **Agent 快捷键** | 默认 Tab 键，长按后语音识别 → LLM 意图理解 → 调用 MCP 工具执行 |

### 1.2 用户交互流程

```
用户长按 Tab 键 → 开始录音 → 释放 → 语音识别 →
发送给 LLM（带 MCP 工具列表）→ LLM 决定调用哪个工具 → 执行
```

---

## 二、配置设计

### 2.1 配置结构 (config.yaml)

```yaml
core:
  # ... 现有配置 ...

  # LLM Agent 配置
  llm_agent:
    enabled: true
    hotkey: "tab"              # 触发快捷键
    hotkey_hold_time: 0.5      # 长按触发时间

# LLM 引擎配置（独立于语音识别引擎）
llm:
  provider: "openai"           # openai / ollama / custom

  openai:
    api_key: ""
    base_url: "https://api.openai.com/v1"
    model: "gpt-4o-mini"       # 从 API 自动拉取可选列表

  ollama:
    base_url: "http://localhost:11434"
    model: "llama3.2"

  custom:
    api_key: ""
    base_url: ""
    model: ""

# MCP Server 配置
mcp:
  servers:
    # 内置文件系统服务
    filesystem:
      enabled: true
      command: "npx"
      args: ["-y", "@anthropic/mcp-filesystem", "/home/user"]

    # 内置浏览器服务
    browser:
      enabled: true
      command: "npx"
      args: ["-y", "@anthropic/mcp-browser"]

    # 自定义服务示例
    # custom_server:
    #   enabled: false
    #   command: "python"
    #   args: ["-m", "my_mcp_server"]
    #   env:
    #     API_KEY: "xxx"
```

### 2.2 设置界面设计

在 SettingsDialog 中新增 **"LLM Agent"** 页面：

```
┌─────────────────────────────────────────────────────────────┐
│  LLM Agent 设置                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ── Agent 快捷键 ──                                          │
│  [✓] 启用 LLM Agent                                          │
│  快捷键:          [ Tab        ▼ ]                           │
│  长按时间:        [ 0.5 ] 秒                                  │
│                                                              │
│  ── LLM 配置 ──                                              │
│  服务提供商:      [ OpenAI 兼容 ▼ ]                           │
│  Base URL:        [ https://api.openai.com/v1    ]           │
│  API Key:         [ ●●●●●●●●●●●●                 ]           │
│  模型:            [ gpt-4o-mini    ▼ ] [ 刷新 ]              │
│                                                              │
│  ── MCP Server 配置 ──                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ [✓] filesystem    /home/user              [ 编辑 ] │    │
│  │ [✓] browser       @anthropic/mcp-browser  [ 编辑 ] │    │
│  │ [ ] fetch         @anthropic/mcp-fetch    [ 编辑 ] │    │
│  └─────────────────────────────────────────────────────┘    │
│                            [ + 添加 MCP Server ]             │
│                                                              │
│                                        [ 保存 ]              │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 MCP Server 编辑对话框

```
┌─────────────────────────────────────────────────────────────┐
│  编辑 MCP Server                                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  名称:            [ filesystem                   ]           │
│  命令:            [ npx                          ]           │
│  参数:            [ -y @anthropic/mcp-filesystem ]           │
│                   [ /home/user                   ]           │
│                                        [ + 添加参数 ]        │
│                                                              │
│  环境变量:                                                   │
│  ┌──────────────┬────────────────────────┐                  │
│  │ KEY          │ VALUE                  │                  │
│  ├──────────────┼────────────────────────┤                  │
│  │ PATH         │ /usr/bin               │                  │
│  └──────────────┴────────────────────────┘                  │
│                                        [ + 添加变量 ]        │
│                                                              │
│                     [ 测试连接 ]  [ 取消 ]  [ 确定 ]          │
└─────────────────────────────────────────────────────────────┘
```

---

## 三、模型列表自动拉取

### 3.1 OpenAI 兼容 API

```python
# GET /v1/models
async def fetch_models(base_url: str, api_key: str) -> list[str]:
    """从 OpenAI 兼容 API 获取模型列表"""
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                # 过滤出 chat 模型
                models = [m["id"] for m in data.get("data", [])]
                return sorted(models)
            return []
```

### 3.2 Ollama API

```python
# GET /api/tags
async def fetch_ollama_models(base_url: str) -> list[str]:
    """从 Ollama 获取本地模型列表"""
    url = f"{base_url.rstrip('/')}/api/tags"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                return [m["name"] for m in data.get("models", [])]
            return []
```

### 3.3 UI 刷新逻辑

```python
class LLMAgentPage(SettingsPage):
    def _on_refresh_models_clicked(self):
        """点击刷新按钮时拉取模型列表"""
        base_url = self.base_url_input.text()
        api_key = self.api_key_input.text()
        provider = self.provider_combo.currentData()

        # 显示加载状态
        self.model_combo.clear()
        self.model_combo.addItem("加载中...")
        self.refresh_btn.setEnabled(False)

        # 异步拉取
        self._fetch_models_async(provider, base_url, api_key)

    def _on_models_fetched(self, models: list[str]):
        """模型列表拉取完成"""
        self.model_combo.clear()
        if models:
            self.model_combo.addItems(models)
        else:
            self.model_combo.addItem("(无可用模型)")
        self.refresh_btn.setEnabled(True)
```

---

## 四、MCP 工具集成

### 4.1 MCP 协议简介

MCP (Model Context Protocol) 是 Anthropic 推出的开放协议，允许 LLM 连接外部工具和数据源。

通过 `langchain-mcp-adapters` 库，可以将 MCP Server 提供的工具无缝转换为 LangChain Tools。

```
┌─────────────────────────────────────────────────────────┐
│                    LangChain Agent                       │
│                           │                              │
│                           ▼                              │
│            ┌──────────────────────────┐                  │
│            │ langchain-mcp-adapters   │                  │
│            │   (load_mcp_tools)       │                  │
│            └──────────────────────────┘                  │
└─────────────────────────────────────────────────────────┘
                            │
             ┌──────────────┼──────────────┐
             ▼              ▼              ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │filesystem│  │ browser  │  │  fetch   │
       │  Server  │  │  Server  │  │  Server  │
       └──────────┘  └──────────┘  └──────────┘
```

### 4.2 使用 langchain-mcp-adapters

```python
from langchain_mcp_adapters.tools import load_mcp_tools

# 加载 MCP Server 提供的工具
tools = await load_mcp_tools(
    command="npx",
    args=["-y", "@anthropic/mcp-filesystem", "/home/user"],
)

# tools 是标准的 LangChain Tools 列表，可直接用于 Agent
```

### 4.3 常用 MCP Server

| Server | 功能 | 配置示例 |
|--------|------|----------|
| `@anthropic/mcp-filesystem` | 文件读写、目录操作 | `command: npx`, `args: [-y, @anthropic/mcp-filesystem, /home/user]` |
| `@anthropic/mcp-browser` | 浏览器控制 | `command: npx`, `args: [-y, @anthropic/mcp-browser]` |
| `@anthropic/mcp-fetch` | HTTP 请求 | `command: npx`, `args: [-y, @anthropic/mcp-fetch]` |
| `@anthropic/mcp-github` | GitHub 操作 | `command: npx`, `args: [-y, @anthropic/mcp-github]` |
| `@anthropic/mcp-puppeteer` | 网页自动化 | `command: npx`, `args: [-y, @anthropic/mcp-puppeteer]` |

### 4.4 自定义 MCP Server

用户也可以添加自定义 MCP Server：

```yaml
mcp:
  servers:
    my_custom_server:
      enabled: true
      command: "python"
      args: ["-m", "my_mcp_server"]
      env:
        API_KEY: "xxx"
```

---

## 五、Agent 浮窗界面（复用 FloatingWindow）

### 5.1 设计理念

复用现有的 FloatingWindow，保持"小而精"的风格：
- 保持紧凑的窗口尺寸
- 高度根据内容动态调整（有上限）
- 统一的视觉风格
- 流畅的状态切换动画

### 5.2 界面布局

**基础状态（聆听中）- 与语音模式一致：**
```
┌──────────────────────────────────────────────────────────┐
│  ┌────────┐                                              │
│  │  App   │   Agent · 聆听中                             │
│  │  Icon  │   ──────────────────────────────────         │
│  │   🎤   │   正在聆听...                                │
│  └────────┘                                              │
└──────────────────────────────────────────────────────────┘
```

**处理状态（高度自适应扩展）：**
```
┌──────────────────────────────────────────────────────────┐
│  ┌────────┐                                              │
│  │  App   │   Agent · 处理中                             │
│  │  Icon  │   ──────────────────────────────────         │
│  │   🤖   │   🎤 帮我打开GitHub搜索langchain             │
│  │   ⏳   │   ──────────────────────────────────         │
│  └────────┘   ⏳ 正在思考...                             │
│               🔧 browser.open → github.com  ✅           │
│               🔧 browser.type → langchain   ⏳           │
└──────────────────────────────────────────────────────────┘
```

**完成状态：**
```
┌──────────────────────────────────────────────────────────┐
│  ┌────────┐                                              │
│  │  App   │   Agent · 完成                               │
│  │  Icon  │   ──────────────────────────────────         │
│  │   🤖   │   🎤 帮我打开GitHub搜索langchain             │
│  │   ✅   │   ──────────────────────────────────         │
│  └────────┘   ✅ 已打开GitHub并搜索langchain             │
└──────────────────────────────────────────────────────────┘
```

### 5.3 状态图标（左侧 Orb）

| 状态 | 图标/动画 | 颜色 |
|------|-----------|------|
| 聆听中 | 🎤 + 脉动 | 蓝色 |
| 识别中 | 📝 + 旋转 | 蓝色 |
| 思考中 | 🤖 + ⏳ | 紫色 |
| 执行中 | 🤖 + 🔧 | 橙色 |
| 完成 | 🤖 + ✅ | 绿色 |
| 错误 | 🤖 + ❌ | 红色 |

### 5.4 右侧内容区域

```python
# 扩展现有的 FloatingWindow

class FloatingWindow(QWidget):
    # ... 现有代码 ...

    # 新增：Agent 模式的内容显示
    def set_agent_content(self, content: AgentContent):
        """设置 Agent 模式的内容"""
        html = self._build_agent_html(content)
        self._text_area.setHtml(html)
        self._adjust_height()  # 动态调整高度

    def _build_agent_html(self, content: AgentContent) -> str:
        """构建 Agent 内容的 HTML"""
        html = []

        # 用户输入
        if content.user_input:
            html.append(f'<div style="color:#888;">🎤 {content.user_input}</div>')
            html.append('<hr style="border:none;border-top:1px solid #333;margin:4px 0;">')

        # 状态/思考
        if content.thinking:
            html.append(f'<div>⏳ {content.thinking}</div>')

        # 工具调用
        for tool in content.tool_calls:
            icon = "✅" if tool.status == "success" else "❌" if tool.status == "error" else "⏳"
            html.append(f'<div style="font-size:12px;">🔧 {tool.name} → {tool.summary} {icon}</div>')

        # 最终结果
        if content.result:
            html.append(f'<div style="margin-top:4px;">✅ {content.result}</div>')

        return ''.join(html)

    def _adjust_height(self):
        """根据内容动态调整窗口高度"""
        content_height = self._text_area.document().size().height()
        # 最小高度 88px，最大高度 300px
        new_height = min(max(88, int(content_height) + 60), 300)
        self.setFixedHeight(new_height)
```

### 5.5 数据结构

```python
# speaky/llm/types.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentStatus(Enum):
    LISTENING = "listening"      # 聆听中
    RECOGNIZING = "recognizing"  # 识别中
    THINKING = "thinking"        # 思考中
    EXECUTING = "executing"      # 执行工具中
    DONE = "done"               # 完成
    ERROR = "error"             # 错误


@dataclass
class ToolCall:
    name: str                   # 工具名称
    summary: str                # 参数摘要（简短显示）
    status: str = "running"     # running / success / error


@dataclass
class AgentContent:
    user_input: str = ""                    # 用户语音输入
    thinking: str = ""                      # 思考过程
    tool_calls: list[ToolCall] = field(default_factory=list)
    result: str = ""                        # 最终结果
    status: AgentStatus = AgentStatus.LISTENING
```

### 5.6 流式更新逻辑

```python
# speaky/handlers/llm_agent.py

class LLMAgentHandler:
    # ...

    async def _run_agent_stream(self, text: str):
        """流式运行 Agent 并实时更新浮窗"""
        content = AgentContent(user_input=text, status=AgentStatus.THINKING)
        self._update_floating_window(content)

        async for event in self._llm_client.agent_executor.astream_events(
            {"input": text},
            version="v2",
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                # LLM 正在输出
                chunk = event["data"]["chunk"].content
                if chunk:
                    content.thinking += chunk
                    self._update_floating_window(content)

            elif kind == "on_tool_start":
                # 开始调用工具
                tool_name = event["name"]
                tool_input = event["data"].get("input", {})
                summary = self._summarize_tool_input(tool_input)
                content.tool_calls.append(ToolCall(tool_name, summary, "running"))
                content.status = AgentStatus.EXECUTING
                self._update_floating_window(content)

            elif kind == "on_tool_end":
                # 工具调用完成
                for tool in content.tool_calls:
                    if tool.status == "running":
                        tool.status = "success"
                        break
                self._update_floating_window(content)

            elif kind == "on_tool_error":
                # 工具调用失败
                for tool in content.tool_calls:
                    if tool.status == "running":
                        tool.status = "error"
                        break
                self._update_floating_window(content)

        # 获取最终结果
        content.result = await self._get_final_result()
        content.status = AgentStatus.DONE
        content.thinking = ""  # 清除思考过程，只显示结果
        self._update_floating_window(content)

    def _update_floating_window(self, content: AgentContent):
        """更新浮窗显示（需要在主线程执行）"""
        self._signals.agent_content.emit(content)

    def _summarize_tool_input(self, tool_input: dict) -> str:
        """简化工具参数显示"""
        if "url" in tool_input:
            return tool_input["url"][:30]
        if "path" in tool_input:
            return tool_input["path"][:30]
        if "query" in tool_input:
            return tool_input["query"][:20]
        return str(tool_input)[:30]
```

### 5.7 窗口高度动画

```python
# 平滑的高度变化动画
def _animate_height(self, target_height: int):
    """动画过渡到目标高度"""
    self._height_animation = QPropertyAnimation(self, b"minimumHeight")
    self._height_animation.setDuration(150)  # 150ms
    self._height_animation.setStartValue(self.height())
    self._height_animation.setEndValue(target_height)
    self._height_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
    self._height_animation.start()
```

---

## 六、LLM 客户端（基于 LangChain）

### 6.1 为什么使用 LangChain

| 优势 | 说明 |
|------|------|
| **统一接口** | 支持 OpenAI、Ollama、Anthropic、Azure 等多种 LLM |
| **Tool Calling** | 内置工具调用支持，自动处理多轮调用 |
| **Agent 框架** | 成熟的 Agent 实现，支持 ReAct 等模式 |
| **MCP 集成** | 通过 `langchain-mcp-adapters` 无缝集成 MCP |
| **流式输出** | 支持流式响应，提升用户体验 |

### 6.2 LangChain + MCP 架构

```
┌─────────────────────────────────────────────────────────────┐
│                      LangChain Agent                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐      │
│  │ ChatOpenAI  │    │ ChatOllama  │    │ ChatAnthropic│     │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘      │
│         └──────────────────┼──────────────────┘              │
│                            ▼                                 │
│                   ┌─────────────────┐                        │
│                   │  Agent Executor │                        │
│                   └────────┬────────┘                        │
│                            ▼                                 │
│              ┌─────────────────────────┐                     │
│              │   MCP Tools (Adapter)   │                     │
│              └─────────────────────────┘                     │
└─────────────────────────────────────────────────────────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │filesystem│  │ browser  │  │  fetch   │
        │  Server  │  │  Server  │  │  Server  │
        └──────────┘  └──────────┘  └──────────┘
```

### 6.3 LLM 客户端封装

```python
# speaky/llm/client.py

from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_mcp_adapters.tools import load_mcp_tools

from .prompts import AGENT_SYSTEM_PROMPT


class LLMClient:
    """基于 LangChain 的 LLM 客户端"""

    def __init__(self, config: dict):
        self.config = config
        self.provider = config.get("provider", "openai")
        self._llm = None
        self._agent_executor: Optional[AgentExecutor] = None

    def _create_llm(self):
        """根据配置创建 LLM 实例"""
        provider_config = self.config.get(self.provider, {})

        if self.provider == "openai":
            return ChatOpenAI(
                model=provider_config.get("model", "gpt-4o-mini"),
                api_key=provider_config.get("api_key"),
                base_url=provider_config.get("base_url"),
                temperature=0.7,
            )
        elif self.provider == "ollama":
            return ChatOllama(
                model=provider_config.get("model", "llama3.2"),
                base_url=provider_config.get("base_url", "http://localhost:11434"),
            )
        else:
            # 自定义 OpenAI 兼容接口
            return ChatOpenAI(
                model=provider_config.get("model"),
                api_key=provider_config.get("api_key"),
                base_url=provider_config.get("base_url"),
                temperature=0.7,
            )

    async def initialize(self, mcp_servers: dict):
        """初始化 Agent，加载 MCP 工具"""
        self._llm = self._create_llm()

        # 从 MCP Server 加载工具
        tools = []
        for name, server_config in mcp_servers.items():
            if server_config.get("enabled", False):
                try:
                    server_tools = await load_mcp_tools(
                        command=server_config["command"],
                        args=server_config.get("args", []),
                        env=server_config.get("env"),
                    )
                    tools.extend(server_tools)
                except Exception as e:
                    logger.error(f"Failed to load MCP tools from {name}: {e}")

        # 创建 Agent
        prompt = ChatPromptTemplate.from_messages([
            ("system", AGENT_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        agent = create_tool_calling_agent(self._llm, tools, prompt)
        self._agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=True,
            max_iterations=10,
            handle_parsing_errors=True,
        )

    async def chat(self, user_message: str) -> str:
        """发送消息并获取响应"""
        if self._agent_executor is None:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        result = await self._agent_executor.ainvoke({
            "input": user_message,
        })
        return result.get("output", "")

    async def chat_stream(self, user_message: str):
        """流式发送消息"""
        if self._agent_executor is None:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        async for event in self._agent_executor.astream_events(
            {"input": user_message},
            version="v2",
        ):
            kind = event["event"]
            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    yield content
```

### 6.4 模型列表获取

```python
# speaky/llm/models.py

import aiohttp
from typing import Optional


async def fetch_openai_models(base_url: str, api_key: str) -> list[str]:
    """从 OpenAI 兼容 API 获取模型列表"""
    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                models = [m["id"] for m in data.get("data", [])]
                # 过滤出 chat 模型
                chat_models = [m for m in models if any(
                    x in m.lower() for x in ["gpt", "chat", "claude", "llama", "qwen", "deepseek"]
                )]
                return sorted(chat_models) if chat_models else sorted(models)
            return []


async def fetch_ollama_models(base_url: str) -> list[str]:
    """从 Ollama 获取本地模型列表"""
    url = f"{base_url.rstrip('/')}/api/tags"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return [m["name"] for m in data.get("models", [])]
            return []
```

### 6.5 系统提示词

```python
# speaky/llm/prompts.py

AGENT_SYSTEM_PROMPT = """你是一个桌面语音助手。用户会用语音给你指令，你需要理解意图并使用可用的工具来完成任务。

## 工作原则

1. 理解用户的真实意图，即使表述不够精确
2. 优先使用工具完成任务，而不是只给建议
3. 如果任务无法完成，清晰说明原因
4. 回复简洁，适合语音播报（控制在 50 字以内）

## 常见任务示例

- "打开 GitHub" → 使用浏览器工具打开 github.com
- "搜索 Python 教程" → 使用浏览器打开搜索页面
- "读取桌面上的 readme 文件" → 使用文件系统工具读取文件
- "帮我创建一个笔记" → 使用文件系统工具创建文件

## 注意事项

- 如果没有合适的工具，直接回答用户问题
- 工具调用失败时，告知用户原因并提供替代方案
"""
```

---

## 六、Handler 集成

### 6.1 LLMAgentHandler

```python
# speaky/handlers/llm_agent.py

import asyncio
import logging
import threading
from typing import Optional

from PySide6.QtCore import QTimer

from ..llm.client import LLMClient

logger = logging.getLogger(__name__)


class LLMAgentHandler:
    """LLM Agent 模式处理器（基于 LangChain）"""

    def __init__(self, signals, recorder, engine_getter, floating_window, config):
        self._signals = signals
        self._recorder = recorder
        self._engine_getter = engine_getter
        self._floating_window = floating_window
        self._config = config

        self._llm_client: Optional[LLMClient] = None
        self._is_recording = False
        self._initialized = False

    async def initialize(self):
        """初始化 LLM Client 和 MCP 工具"""
        if self._initialized:
            return

        self._llm_client = LLMClient(self._config.get("llm", {}))

        # 获取 MCP Server 配置并初始化
        mcp_servers = self._config.get("mcp", {}).get("servers", {})
        await self._llm_client.initialize(mcp_servers)

        self._initialized = True
        logger.info("LLM Agent initialized with MCP tools")

    def on_hotkey_press(self):
        """快捷键按下 - 开始录音"""
        if not self._config.get("core.llm_agent.enabled", True):
            return

        self._is_recording = True
        self._floating_window.show()
        self._floating_window.set_status("listening")
        self._floating_window.set_text("正在聆听...")
        self._recorder.start()

    def on_hotkey_release(self):
        """快捷键释放 - 停止录音并处理"""
        if not self._is_recording:
            return

        self._is_recording = False
        audio_data = self._recorder.stop()

        # 异步处理
        threading.Thread(
            target=self._process_audio,
            args=(audio_data,),
            daemon=True
        ).start()

    def _process_audio(self, audio_data):
        """处理音频：ASR → LangChain Agent → 返回结果"""
        try:
            # 0. 确保已初始化
            if not self._initialized:
                asyncio.run(self.initialize())

            # 1. 语音识别
            self._signals.partial_result.emit("正在识别语音...")
            engine = self._engine_getter()
            text = engine.recognize(audio_data)

            if not text:
                self._signals.partial_result.emit("未识别到语音")
                QTimer.singleShot(2000, self._floating_window.hide)
                return

            self._signals.partial_result.emit(f"🎤 {text}\n\n⏳ 正在处理...")

            # 2. LangChain Agent 处理（支持流式输出）
            result = asyncio.run(self._run_agent(text))

            # 3. 显示结果
            self._signals.partial_result.emit(f"🎤 {text}\n\n✅ {result}")

        except Exception as e:
            logger.error(f"LLM Agent error: {e}", exc_info=True)
            self._signals.partial_result.emit(f"❌ 错误: {e}")
        finally:
            # 延迟隐藏窗口
            QTimer.singleShot(3000, self._floating_window.hide)

    async def _run_agent(self, text: str) -> str:
        """运行 LangChain Agent"""
        return await self._llm_client.chat(text)

    async def _run_agent_stream(self, text: str):
        """运行 LangChain Agent（流式）"""
        full_response = ""
        async for chunk in self._llm_client.chat_stream(text):
            full_response += chunk
            self._signals.partial_result.emit(f"🎤 {text}\n\n{full_response}")
        return full_response
```

---

## 七、实现计划

### P0 - 基础功能（必须）

1. **配置结构**
   - 在 `config.py` 添加 `core.llm_agent`、`llm`、`mcp` 配置项

2. **设置界面**
   - 新增 `LLMAgentPage` 页面
   - LLM 配置：Base URL / API Key / Model（自动拉取）
   - MCP 配置：Server 列表、添加/编辑/删除

3. **LLM 客户端**
   - 支持 OpenAI 兼容 API
   - 支持 Tool Calling（function calling）
   - 实现 `fetch_models()` 拉取模型列表

4. **MCP 客户端**
   - 实现 `MCPManager` 管理多个 Server
   - 支持 stdio 传输方式
   - 工具列表获取和调用

5. **Agent Handler**
   - 快捷键监听（默认 Tab）
   - 语音识别 → LLM + MCP → 显示结果

### P1 - 扩展功能

1. **Ollama 支持**
   - 本地模型调用（需要支持 Tool Calling 的模型）

2. **MCP Server 管理**
   - 测试连接功能
   - 查看可用工具列表

3. **执行历史**
   - 保存执行历史
   - 快速重复执行

### P2 - 高级功能

1. **多轮对话**
   - 支持追问和澄清

2. **上下文感知**
   - 结合当前焦点应用提供上下文

3. **自定义 MCP Server**
   - 提供模板快速创建自定义 Server

---

## 九、文件结构

```
speaky/
├── llm/
│   ├── __init__.py
│   ├── client.py           # LangChain LLM 客户端
│   ├── models.py           # 模型列表获取
│   ├── prompts.py          # 系统提示词
│   └── types.py            # AgentContent, ToolCall 等数据结构
├── handlers/
│   ├── llm_agent.py        # LLM Agent Handler（新增）
│   └── ...
├── ui/
│   ├── floating_window.py  # 扩展支持 Agent 模式显示
│   ├── settings_dialog.py  # 添加 LLMAgentPage
│   ├── mcp_server_dialog.py # MCP Server 编辑对话框（新增）
│   └── ...
└── config.py               # 添加 llm_agent / llm / mcp 配置
```

---

## 十、依赖

```toml
# pyproject.toml 新增依赖
[project]
dependencies = [
    # ... 现有依赖

    # LangChain 核心
    "langchain>=0.3.0",
    "langchain-core>=0.3.0",

    # LLM 提供商
    "langchain-openai>=0.2.0",      # OpenAI / 兼容 API
    "langchain-ollama>=0.2.0",      # Ollama 本地模型

    # MCP 集成
    "langchain-mcp-adapters>=0.1.0", # MCP 工具适配器
    "mcp>=1.0.0",                    # MCP Python SDK

    # 异步 HTTP
    "aiohttp>=3.9.0",
]
```

### 依赖说明

| 包名 | 用途 |
|------|------|
| `langchain` | LangChain 核心框架 |
| `langchain-openai` | OpenAI ChatGPT 支持 |
| `langchain-ollama` | Ollama 本地模型支持 |
| `langchain-mcp-adapters` | 将 MCP 工具转换为 LangChain Tools |
| `mcp` | MCP 协议 Python SDK |
| `aiohttp` | 异步 HTTP 客户端（获取模型列表等） |

---

## 十一、安全考虑

1. **MCP Server 权限控制**
   - 文件系统 Server 限制访问目录
   - 敏感操作需要用户确认

2. **API Key 安全**
   - 密码输入框隐藏显示
   - 配置文件权限控制（600）

3. **工具调用审计**
   - 记录所有工具调用日志
   - 可查看执行历史
