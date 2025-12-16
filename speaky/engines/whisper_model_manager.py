"""Whisper Model Manager - Download and manage Whisper models"""

import logging
import os
import shutil
import threading
from enum import Enum
from pathlib import Path
from typing import Callable, Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 模型存储路径
MODELS_DIR = Path(__file__).parent.parent.parent / "models"


class ModelSource(Enum):
    """模型下载来源"""
    HUGGINGFACE = "huggingface"
    MODELSCOPE = "modelscope"


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    size: str  # 模型大小描述
    description: str
    huggingface_repo: str
    modelscope_repo: str


# 支持的模型列表
# ModelScope 仓库使用 gpustack 提供的镜像
WHISPER_MODELS: Dict[str, ModelInfo] = {
    "tiny": ModelInfo(
        name="tiny",
        size="~75MB",
        description="最小模型，速度最快，适合测试",
        huggingface_repo="Systran/faster-whisper-tiny",
        modelscope_repo="gpustack/faster-whisper-tiny",
    ),
    "base": ModelInfo(
        name="base",
        size="~145MB",
        description="基础模型，平衡速度和效果",
        huggingface_repo="Systran/faster-whisper-base",
        modelscope_repo="",  # ModelScope 上暂无此模型
    ),
    "small": ModelInfo(
        name="small",
        size="~488MB",
        description="小型模型，效果较好",
        huggingface_repo="Systran/faster-whisper-small",
        modelscope_repo="gpustack/faster-whisper-small",
    ),
    "medium": ModelInfo(
        name="medium",
        size="~1.5GB",
        description="中型模型，效果很好",
        huggingface_repo="Systran/faster-whisper-medium",
        modelscope_repo="gpustack/faster-whisper-medium",
    ),
    "large-v3": ModelInfo(
        name="large-v3",
        size="~3GB",
        description="大型模型 v3，效果最好",
        huggingface_repo="Systran/faster-whisper-large-v3",
        modelscope_repo="gpustack/faster-whisper-large-v3",
    ),
}


class WhisperModelManager:
    """Whisper 模型管理器"""

    def __init__(self):
        self._models_dir = MODELS_DIR
        self._models_dir.mkdir(parents=True, exist_ok=True)
        self._download_thread: Optional[threading.Thread] = None
        self._cancel_download = False

    def get_models_dir(self) -> Path:
        """获取模型目录"""
        return self._models_dir

    def get_available_models(self) -> List[str]:
        """获取支持的模型列表"""
        return list(WHISPER_MODELS.keys())

    def get_model_info(self, model_name: str) -> Optional[ModelInfo]:
        """获取模型信息"""
        return WHISPER_MODELS.get(model_name)

    def is_model_downloaded(self, model_name: str) -> bool:
        """检查模型是否已下载"""
        model_dir = self._models_dir / f"models--Systran--faster-whisper-{model_name}"
        if model_dir.exists():
            # 检查是否有 snapshots 目录和模型文件
            snapshots = model_dir / "snapshots"
            if snapshots.exists():
                for snapshot in snapshots.iterdir():
                    model_bin = snapshot / "model.bin"
                    if model_bin.exists():
                        return True

        # 也检查 ModelScope 下载的目录结构
        model_dir_ms = self._models_dir / f"faster-whisper-{model_name}"
        if model_dir_ms.exists():
            model_bin = model_dir_ms / "model.bin"
            if model_bin.exists():
                return True

        return False

    def get_model_size(self, model_name: str) -> Optional[int]:
        """获取已下载模型的大小（字节）"""
        if not self.is_model_downloaded(model_name):
            return None

        total_size = 0
        # HuggingFace 格式
        model_dir = self._models_dir / f"models--Systran--faster-whisper-{model_name}"
        if model_dir.exists():
            for f in model_dir.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size

        # ModelScope 格式
        model_dir_ms = self._models_dir / f"faster-whisper-{model_name}"
        if model_dir_ms.exists():
            for f in model_dir_ms.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size

        return total_size if total_size > 0 else None

    def delete_model(self, model_name: str) -> bool:
        """删除模型"""
        deleted = False

        # 删除 HuggingFace 格式
        model_dir = self._models_dir / f"models--Systran--faster-whisper-{model_name}"
        if model_dir.exists():
            try:
                shutil.rmtree(model_dir)
                deleted = True
                logger.info(f"Deleted model directory: {model_dir}")
            except Exception as e:
                logger.error(f"Failed to delete {model_dir}: {e}")

        # 删除 ModelScope 格式
        model_dir_ms = self._models_dir / f"faster-whisper-{model_name}"
        if model_dir_ms.exists():
            try:
                shutil.rmtree(model_dir_ms)
                deleted = True
                logger.info(f"Deleted model directory: {model_dir_ms}")
            except Exception as e:
                logger.error(f"Failed to delete {model_dir_ms}: {e}")

        return deleted

    def download_model(
        self,
        model_name: str,
        source: ModelSource = ModelSource.HUGGINGFACE,
        on_progress: Optional[Callable[[float, str], None]] = None,
        on_complete: Optional[Callable[[bool, str], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        """下载模型（异步）

        Args:
            model_name: 模型名称
            source: 下载来源 (huggingface/modelscope)
            on_progress: 进度回调 (progress: 0-100, message: str)
            on_complete: 完成回调 (success: bool, message: str)
            on_log: 日志回调 (message: str)
        """
        if self._download_thread and self._download_thread.is_alive():
            if on_complete:
                on_complete(False, "另一个下载正在进行中")
            return

        self._cancel_download = False
        self._download_thread = threading.Thread(
            target=self._download_model_sync,
            args=(model_name, source, on_progress, on_complete, on_log),
            daemon=True,
        )
        self._download_thread.start()

    def cancel_download(self):
        """取消下载"""
        self._cancel_download = True

    def is_downloading(self) -> bool:
        """是否正在下载"""
        return self._download_thread is not None and self._download_thread.is_alive()

    def _download_model_sync(
        self,
        model_name: str,
        source: ModelSource,
        on_progress: Optional[Callable[[float, str], None]],
        on_complete: Optional[Callable[[bool, str], None]],
        on_log: Optional[Callable[[str], None]] = None,
    ):
        """同步下载模型"""
        model_info = WHISPER_MODELS.get(model_name)
        if not model_info:
            if on_complete:
                on_complete(False, f"未知模型: {model_name}")
            return

        try:
            if on_progress:
                on_progress(0, f"准备下载 {model_name}...")
            if on_log:
                on_log(f"开始下载模型: {model_name}")
                on_log(f"下载来源: {'HuggingFace' if source == ModelSource.HUGGINGFACE else 'ModelScope'}")

            if source == ModelSource.HUGGINGFACE:
                self._download_from_huggingface(model_name, model_info, on_progress, on_log)
            else:
                self._download_from_modelscope(model_name, model_info, on_progress, on_log)

            if self._cancel_download:
                if on_log:
                    on_log("下载已取消")
                if on_complete:
                    on_complete(False, "下载已取消")
                return

            if on_progress:
                on_progress(100, "下载完成")
            if on_log:
                on_log("✓ 下载完成")

            if on_complete:
                on_complete(True, f"模型 {model_name} 下载完成")

        except Exception as e:
            logger.error(f"Download failed: {e}", exc_info=True)
            if on_log:
                on_log(f"✗ 下载失败: {str(e)}")
            if on_complete:
                on_complete(False, f"下载失败: {str(e)}")

    def _download_from_huggingface(
        self,
        model_name: str,
        model_info: ModelInfo,
        on_progress: Optional[Callable[[float, str], None]],
        on_log: Optional[Callable[[str], None]] = None,
    ):
        """从 HuggingFace 下载"""
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            raise RuntimeError("请先安装 huggingface_hub: pip install huggingface_hub")

        if on_log:
            on_log(f"仓库: {model_info.huggingface_repo}")
        if on_progress:
            on_progress(5, f"从 HuggingFace 下载 {model_info.huggingface_repo}...")

        # HuggingFace 下载目录
        local_dir = self._models_dir / f"models--Systran--faster-whisper-{model_name}"

        # 预估模型大小（用于进度计算）
        estimated_sizes = {
            "tiny": 75 * 1024 * 1024,      # 75MB
            "base": 145 * 1024 * 1024,     # 145MB
            "small": 488 * 1024 * 1024,    # 488MB
            "medium": 1500 * 1024 * 1024,  # 1.5GB
            "large-v3": 3000 * 1024 * 1024,  # 3GB
        }
        estimated_size = estimated_sizes.get(model_name, 500 * 1024 * 1024)

        # 启动进度监控线程
        stop_monitor = threading.Event()

        def monitor_progress():
            last_size = 0
            while not stop_monitor.is_set():
                try:
                    current_size = sum(
                        f.stat().st_size for f in local_dir.rglob("*") if f.is_file()
                    ) if local_dir.exists() else 0
                    if current_size > 0:
                        pct = min(5 + (current_size / estimated_size) * 85, 90)
                        size_mb = current_size / (1024 * 1024)
                        if on_progress:
                            on_progress(pct, f"下载中... {size_mb:.1f} MB ({pct:.0f}%)")
                        # 每 5MB 输出一次日志
                        if on_log and current_size - last_size >= 5 * 1024 * 1024:
                            on_log(f"已下载: {size_mb:.1f} MB")
                            last_size = current_size
                except Exception:
                    pass
                stop_monitor.wait(0.5)

        monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
        monitor_thread.start()

        try:
            if on_log:
                on_log("正在连接 HuggingFace...")
            snapshot_download(
                repo_id=model_info.huggingface_repo,
                local_dir=None,
                cache_dir=str(self._models_dir),
                local_dir_use_symlinks=False,
            )
        finally:
            stop_monitor.set()
            monitor_thread.join(timeout=1)

        if on_log:
            on_log("验证模型文件...")
        if on_progress:
            on_progress(95, "验证模型文件...")

    def _download_from_modelscope(
        self,
        model_name: str,
        model_info: ModelInfo,
        on_progress: Optional[Callable[[float, str], None]],
        on_log: Optional[Callable[[str], None]] = None,
    ):
        """从 ModelScope 下载"""
        # 检查是否有对应的 ModelScope 仓库
        if not model_info.modelscope_repo:
            raise RuntimeError(
                f"模型 {model_name} 在 ModelScope 上不可用。\n"
                f"请使用 HuggingFace 作为下载来源。"
            )

        try:
            from modelscope import snapshot_download
        except ImportError:
            raise RuntimeError("请先安装 modelscope: pip install modelscope")

        if on_log:
            on_log(f"仓库: {model_info.modelscope_repo}")
        if on_progress:
            on_progress(5, f"从 ModelScope 下载 {model_info.modelscope_repo}...")

        # ModelScope 下载
        local_dir = self._models_dir / f"faster-whisper-{model_name}"

        # 预估模型大小（用于进度计算）
        estimated_sizes = {
            "tiny": 75 * 1024 * 1024,      # 75MB
            "base": 145 * 1024 * 1024,     # 145MB
            "small": 488 * 1024 * 1024,    # 488MB
            "medium": 1500 * 1024 * 1024,  # 1.5GB
            "large-v3": 3000 * 1024 * 1024,  # 3GB
        }
        estimated_size = estimated_sizes.get(model_name, 500 * 1024 * 1024)

        # 启动进度监控线程
        stop_monitor = threading.Event()

        def monitor_progress():
            last_size = 0
            while not stop_monitor.is_set():
                try:
                    current_size = sum(
                        f.stat().st_size for f in local_dir.rglob("*") if f.is_file()
                    ) if local_dir.exists() else 0
                    if current_size > 0:
                        pct = min(5 + (current_size / estimated_size) * 85, 90)
                        size_mb = current_size / (1024 * 1024)
                        if on_progress:
                            on_progress(pct, f"下载中... {size_mb:.1f} MB ({pct:.0f}%)")
                        # 每 5MB 输出一次日志
                        if on_log and current_size - last_size >= 5 * 1024 * 1024:
                            on_log(f"已下载: {size_mb:.1f} MB")
                            last_size = current_size
                except Exception:
                    pass
                stop_monitor.wait(0.5)

        monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
        monitor_thread.start()

        try:
            if on_log:
                on_log("正在连接 ModelScope...")
            snapshot_download(
                model_id=model_info.modelscope_repo,
                cache_dir=str(self._models_dir),
                local_dir=str(local_dir),
            )
        finally:
            stop_monitor.set()
            monitor_thread.join(timeout=1)

        if on_log:
            on_log("验证模型文件...")
        if on_progress:
            on_progress(95, "验证模型文件...")


# 单例
whisper_model_manager = WhisperModelManager()
