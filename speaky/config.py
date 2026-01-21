import copy
from pathlib import Path
from typing import Any
import yaml

from .paths import get_config_path, get_base_path

DEFAULT_CONFIG = {
    # ========== 核心设置 (Core) ==========
    "core": {
        # 语音识别 (ASR)
        "asr": {
            "hotkey": "ctrl",
            "hotkey_hold_time": 1.0,  # 长按多少秒后开始录音
            "language": "zh",  # 识别语言: zh, en, ja, ko
            "streaming_mode": True,  # 流式识别
            "audio_device": None,  # 音频设备索引，None 表示默认设备
            "audio_gain": 1.0,  # 录音增益，1.0 为原始音量，2.0 为 2 倍放大
            "sound_notification": True,  # 开始/结束录音时播放提示音
        },

        # AI 键
        "ai": {
            "enabled": True,
            "hotkey": "alt",
            "hotkey_hold_time": 0.5,
            "url": "https://chatgpt.com",  # 支持 doubao.com/chat, claude.ai 等
            "page_load_delay": 3.0,  # 页面加载等待时间
            "auto_enter": True,  # 自动发送
        },
    },

    # ========== LLM Agent 设置 ==========
    "llm_agent": {
        "enabled": False,  # 默认关闭，需要配置 LLM 后启用
        "hotkey": "tab",
        "hotkey_hold_time": 0.5,
    },

    # ========== LLM 设置 (OpenAI Compatible) ==========
    "llm": {
        "openai": {
            "api_key": "",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini",
        },
    },

    # ========== MCP Server 设置 ==========
    # NOTE: Run scripts/install_mcp.sh first to install MCP dependencies
    "mcp": {
        "servers": {
            # 浏览器自动化 (Playwright)
            "playwright": {
                "enabled": True,
                "command": "node",
                "args": ["~/.speaky/mcp/node_modules/@playwright/mcp/cli.js"],
            },
            # 文件系统操作
            "filesystem": {
                "enabled": True,
                "command": "node",
                "args": ["~/.speaky/mcp/node_modules/@modelcontextprotocol/server-filesystem/dist/index.js", "/home"],
            },
            # 网页内容获取 (Python-based, 需要: pip install mcp-server-fetch)
            # "fetch": {
            #     "enabled": True,
            #     "command": "uvx",
            #     "args": ["mcp-server-fetch"],
            # },
        },
    },

    # ========== 引擎设置 (Engine) ==========
    "engine": {
        "current": "volc_bigmodel",  # 当前引擎

        # 1. 火山引擎-语音识别大模型 (固定使用 bigmodel_async)
        "volc_bigmodel": {
            "app_key": "",
            "access_key": "",
        },

        # 2. 火山引擎-一句话识别
        "volcengine": {
            "app_id": "",
            "access_key": "",
            "secret_key": "",
        },

        # 3. OpenAI (原生 & 兼容)
        "openai": {
            "api_key": "",
            "model": "gpt-4o-transcribe",
            "base_url": "https://api.openai.com/v1",
        },

        # 4. 本地模式
        "local": {
            "model": "base",  # tiny, base, small, medium, large
            "device": "auto",  # auto, cpu, cuda
        },
    },

    # ========== 外观设置 (Appearance) ==========
    "appearance": {
        "theme": "auto",  # light, dark, auto
        "ui_language": "auto",  # auto, en, zh, zh_TW, ja, ko, etc.
        "show_waveform": True,
        "window_opacity": 0.9,
    },
}


class Config:
    def __init__(self):
        self.config_dir = get_config_path()
        self.config_file = self.config_dir / "config.yaml"
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self._load_defaults()
        self.load()

    def _load_defaults(self):
        """Load from project directory config if exists (开发环境)"""
        # Check project directory for config.yaml or config.example.yaml
        project_dir = get_base_path()
        for name in ["config.yaml", "config.example.yaml"]:
            project_config = project_dir / name
            if project_config.exists():
                with open(project_config, "r", encoding="utf-8") as f:
                    defaults = yaml.safe_load(f) or {}
                    self._deep_merge(self._config, defaults)
                break

        # Load MCP config from mcp.yaml (check user dir first, then project dir)
        user_mcp_config = self.config_dir / "mcp.yaml"
        project_mcp_config = project_dir / "mcp.yaml"

        mcp_config_path = user_mcp_config if user_mcp_config.exists() else project_mcp_config
        if mcp_config_path.exists():
            with open(mcp_config_path, "r", encoding="utf-8") as f:
                mcp_data = yaml.safe_load(f) or {}
                if "servers" in mcp_data:
                    self._deep_merge(self._config.setdefault("mcp", {}), {"servers": mcp_data["servers"]})

    def load(self):
        if self.config_file.exists():
            with open(self.config_file, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
                # 用户配置不允许用空值覆盖默认值（如 API 密钥）
                self._deep_merge(self._config, user_config, allow_empty=False)

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)

    def _deep_merge(self, base: dict, override: dict, allow_empty: bool = True):
        """深度合并配置

        Args:
            base: 基础配置
            override: 覆盖配置
            allow_empty: 是否允许空值覆盖非空值
        """
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value, allow_empty)
            elif allow_empty or (value is not None and value != ""):
                # 如果不允许空值覆盖，跳过空字符串和 None
                base[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    @property
    def hotkey(self) -> str:
        return self.get("core.asr.hotkey", "ctrl")

    @property
    def engine(self) -> str:
        return self.get("engine.current", "volc_bigmodel")

    @property
    def language(self) -> str:
        return self.get("core.asr.language", "zh")


config = Config()
