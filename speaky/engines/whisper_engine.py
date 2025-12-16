"""Local Whisper Engine using faster-whisper for optimized performance"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional, Callable
from .base import BaseEngine

logger = logging.getLogger(__name__)

# 模型存储路径：项目目录下的 models 文件夹
MODELS_DIR = Path(__file__).parent.parent.parent / "models"


class WhisperEngine(BaseEngine):
    """本地 Whisper 引擎 (使用 faster-whisper)

    相比 openai-whisper:
    - 速度快 4-5 倍
    - 显存降低 50-75%
    - 识别效果完全一致
    """

    def __init__(
        self,
        model_name: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
    ):
        """初始化 Whisper 引擎

        Args:
            model_name: 模型名称 (tiny, base, small, medium, large-v3, large-v3-turbo)
            device: 运行设备 (auto, cpu, cuda)
            compute_type: 计算精度 (auto, int8, float16, float32)
                - int8: 最省显存，速度最快
                - float16: 平衡选择 (需要 GPU)
                - float32: CPU 默认
        """
        self._model_name = model_name
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def _get_local_model_path(self) -> Optional[str]:
        """获取本地已下载模型的路径"""
        # 检查 HuggingFace 格式目录
        hf_dir = MODELS_DIR / f"models--Systran--faster-whisper-{self._model_name}"
        if hf_dir.exists():
            snapshots = hf_dir / "snapshots"
            if snapshots.exists():
                for snapshot in snapshots.iterdir():
                    model_bin = snapshot / "model.bin"
                    if model_bin.exists():
                        logger.info(f"[Whisper] 找到 HuggingFace 格式模型: {snapshot}")
                        return str(snapshot)

        # 检查 ModelScope 格式目录
        ms_dir = MODELS_DIR / f"faster-whisper-{self._model_name}"
        if ms_dir.exists():
            model_bin = ms_dir / "model.bin"
            if model_bin.exists():
                logger.info(f"[Whisper] 找到 ModelScope 格式模型: {ms_dir}")
                return str(ms_dir)

        return None

    def _load_model(self):
        """懒加载模型"""
        if self._model is not None:
            return

        from faster_whisper import WhisperModel

        # 自动检测设备
        device = self._device
        if device == "auto":
            try:
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"

        # 自动选择计算精度
        compute_type = self._compute_type
        if compute_type == "auto":
            if device == "cuda":
                compute_type = "float16"  # GPU 用 float16
            else:
                compute_type = "int8"  # CPU 用 int8 更快

        # 确保模型目录存在
        MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # 优先使用本地已下载的模型
        local_model_path = self._get_local_model_path()

        if not local_model_path:
            logger.warning(f"[Whisper] 模型 {self._model_name} 未下载，请先在设置中下载模型")
            raise RuntimeError(f"模型 {self._model_name} 未下载，请先在设置中下载模型")

        logger.info(f"[Whisper] 加载模型: {local_model_path}, device={device}, compute_type={compute_type}")

        self._model = WhisperModel(
            local_model_path,
            device=device,
            compute_type=compute_type,
        )
        logger.info(f"[Whisper] 模型加载完成")

    def transcribe(self, audio_data: bytes, language: str = "zh") -> str:
        """转录音频（非流式）

        Args:
            audio_data: WAV 格式音频数据
            language: 语言代码 (zh, en, ja 等)

        Returns:
            转录文本
        """
        self._load_model()

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as f:
            f.write(audio_data)
            f.flush()

            segments, info = self._model.transcribe(
                f.name,
                language=language,
                beam_size=5,
                vad_filter=True,  # 过滤静音
            )

            # 合并所有片段
            text = "".join(segment.text for segment in segments)
            return text.strip()

    def preload(self):
        """预加载模型（在应用启动时调用，避免第一次识别时卡顿）"""
        logger.info(f"[Whisper] 预加载模型: {self._model_name}")
        self._load_model()

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self._model is not None

    def is_model_downloaded(self) -> bool:
        """检查模型是否已下载"""
        return self._get_local_model_path() is not None

    def is_available(self) -> bool:
        """检查 faster-whisper 是否可用"""
        try:
            from faster_whisper import WhisperModel
            return True
        except ImportError:
            return False

    @property
    def name(self) -> str:
        return "Whisper (Local)"
