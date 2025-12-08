import os
from pathlib import Path
from typing import Any
import yaml

DEFAULT_CONFIG = {
    "hotkey": "ctrl",
    "engine": "whisper",
    "language": "zh",
    "whisper": {
        "model": "base",
        "device": "auto",
    },
    "openai": {
        "api_key": "",
        "model": "whisper-1",
        "base_url": "https://api.openai.com/v1",
    },
    "volcengine": {
        "app_id": "",
        "access_key": "",
        "secret_key": "",
    },
    "aliyun": {
        "app_key": "",
        "access_token": "",
    },
    "tencent": {
        "secret_id": "",
        "secret_key": "",
    },
    "ui": {
        "show_waveform": True,
        "window_opacity": 0.9,
    },
}


class Config:
    def __init__(self):
        self.config_dir = Path.home() / ".config" / "speek-input"
        self.config_file = self.config_dir / "config.yaml"
        self._config = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if self.config_file.exists():
            with open(self.config_file, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
                self._deep_merge(self._config, user_config)

    def save(self):
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)

    def _deep_merge(self, base: dict, override: dict):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
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
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    @property
    def hotkey(self) -> str:
        return self.get("hotkey", "ctrl")

    @property
    def engine(self) -> str:
        return self.get("engine", "whisper")

    @property
    def language(self) -> str:
        return self.get("language", "zh")


config = Config()
