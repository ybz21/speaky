"""Data types for LLM Agent."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentStatus(Enum):
    """Agent processing status."""
    IDLE = "idle"                # 空闲
    LISTENING = "listening"      # 聆听中
    RECOGNIZING = "recognizing"  # 识别中
    THINKING = "thinking"        # 思考中
    EXECUTING = "executing"      # 执行工具中
    DONE = "done"               # 完成
    ERROR = "error"             # 错误


@dataclass
class ToolCall:
    """Represents a tool call in the agent execution."""
    name: str                   # 工具名称
    summary: str                # 参数摘要（简短显示）
    status: str = "running"     # running / success / error


@dataclass
class AgentContent:
    """Content to display in the floating window for agent mode."""
    user_input: str = ""                    # 用户语音输入
    thinking: str = ""                      # 思考过程
    tool_calls: list[ToolCall] = field(default_factory=list)
    result: str = ""                        # 最终结果
    status: AgentStatus = AgentStatus.IDLE
    error: str = ""                         # 错误信息
