"""
统一处理资源路径，兼容开发环境和 PyInstaller 打包环境。

PyInstaller 打包后：
- sys._MEIPASS 指向临时解压目录
- 资源文件会被解压到该目录

开发环境：
- 使用项目根目录
"""
import os
import sys
from pathlib import Path


def get_base_path() -> Path:
    """获取应用基础路径（打包后为临时目录，开发时为项目根目录）"""
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # PyInstaller 打包后运行
        return Path(sys._MEIPASS)
    else:
        # 开发环境：speaky/paths.py -> speaky -> project_root
        return Path(__file__).parent.parent


def get_resources_path() -> Path:
    """获取 resources 目录路径"""
    return get_base_path() / "resources"


def get_locales_path() -> Path:
    """获取 locales 目录路径"""
    base = get_base_path()
    # 打包后 locales 在 speaky/locales，开发时也在 speaky/locales
    if getattr(sys, 'frozen', False):
        return base / "speaky" / "locales"
    else:
        return base / "speaky" / "locales"


def get_user_data_path() -> Path:
    """获取用户数据目录（配置、日志、模型等）"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", os.path.expanduser("~")))
        return base / "Speaky"
    elif sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Speaky"
    else:
        return Path.home() / ".speaky"


def get_models_path() -> Path:
    """获取模型存储目录（存放在用户数据目录，而非打包目录）"""
    path = get_user_data_path() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_config_path() -> Path:
    """获取配置文件目录"""
    path = get_user_data_path()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_path() -> Path:
    """获取日志目录"""
    path = get_user_data_path() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path
