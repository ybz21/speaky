"""Model Download Widget - Generic model download and management UI"""

from typing import Callable, Optional, List, Dict, Any
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PySide6.QtCore import QTimer, Signal, Qt

from qfluentwidgets import (
    ComboBox, PrimaryPushButton, PushButton, BodyLabel,
    ProgressBar, MessageBox, InfoBar, InfoBarPosition
)

from ..i18n import t


class ModelDownloadWidget(QWidget):
    """通用模型下载管理组件

    可用于 Whisper、其他本地模型等需要下载管理的场景。

    使用方式:
        widget = ModelDownloadWidget(
            models=["tiny", "base", "small"],
            model_info={"tiny": {"size": "~75MB"}, ...},
            check_downloaded=lambda m: is_downloaded(m),
            get_model_size=lambda m: get_size(m),
            download_func=lambda m, s, p, c: download(m, s, p, c),
            delete_func=lambda m: delete(m),
        )
    """

    # 信号
    model_changed = Signal(str)  # 模型选择变化
    download_started = Signal(str)  # 开始下载
    download_completed = Signal(str, bool)  # 下载完成 (model, success)

    def __init__(
        self,
        models: List[str],
        model_info: Dict[str, Dict[str, Any]],
        check_downloaded: Callable[[str], bool],
        get_model_size: Callable[[str], Optional[int]],
        download_func: Callable,
        delete_func: Callable[[str], bool],
        download_sources: Optional[List[str]] = None,
        extra_options: Optional[Dict[str, List[str]]] = None,
        cancel_func: Optional[Callable[[], None]] = None,
        parent=None,
    ):
        """
        Args:
            models: 可选模型列表
            model_info: 模型信息字典 {model_name: {"size": "~75MB", "desc": "..."}}
            check_downloaded: 检查模型是否已下载的函数
            get_model_size: 获取已下载模型大小的函数
            download_func: 下载函数 (model, source, on_progress, on_complete)
            delete_func: 删除函数 (model) -> bool
            download_sources: 下载来源列表，如 ["HuggingFace", "ModelScope"]
            extra_options: 额外选项 {label: [options]}，如 {"device": ["auto", "cpu", "cuda"]}
            cancel_func: 取消下载函数
        """
        super().__init__(parent)

        self._models = models
        self._model_info = model_info
        self._check_downloaded = check_downloaded
        self._get_model_size = get_model_size
        self._download_func = download_func
        self._delete_func = delete_func
        self._cancel_func = cancel_func
        self._download_sources = download_sources or ["HuggingFace", "ModelScope"]
        self._extra_options = extra_options or {}
        self._extra_combos: Dict[str, ComboBox] = {}

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        # 模型选择
        model_row = QHBoxLayout()
        model_row.addWidget(BodyLabel(t("model")))
        self.model_combo = ComboBox()
        self.model_combo.addItems(self._models)
        self.model_combo.setMinimumWidth(150)
        self.model_combo.currentTextChanged.connect(self._on_model_changed)
        model_row.addWidget(self.model_combo)
        model_row.addStretch()
        layout.addLayout(model_row)

        # 额外选项（如 device）
        for label, options in self._extra_options.items():
            row = QHBoxLayout()
            row.addWidget(BodyLabel(t(label)))
            combo = ComboBox()
            combo.addItems(options)
            combo.setMinimumWidth(150)
            row.addWidget(combo)
            row.addStretch()
            layout.addLayout(row)
            self._extra_combos[label] = combo

        # 下载来源
        if self._download_sources:
            source_row = QHBoxLayout()
            source_row.addWidget(BodyLabel(t("download_source")))
            self.source_combo = ComboBox()
            self.source_combo.addItems(self._download_sources)
            self.source_combo.setMinimumWidth(150)
            source_row.addWidget(self.source_combo)
            source_row.addStretch()
            layout.addLayout(source_row)

        # 模型状态
        status_row = QHBoxLayout()
        status_row.addWidget(BodyLabel(t("model_status")))
        self.status_label = BodyLabel("")
        self.status_label.setMinimumWidth(200)
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        layout.addLayout(status_row)

        # 操作按钮
        action_row = QHBoxLayout()
        self.download_btn = PrimaryPushButton(t("download"))
        self.download_btn.setMinimumWidth(100)
        self.download_btn.clicked.connect(self._on_download)
        action_row.addWidget(self.download_btn)

        self.cancel_btn = PushButton(t("cancel"))
        self.cancel_btn.setMinimumWidth(100)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.cancel_btn.setVisible(False)
        action_row.addWidget(self.cancel_btn)

        self.delete_btn = PushButton(t("delete"))
        self.delete_btn.setMinimumWidth(100)
        self.delete_btn.clicked.connect(self._on_delete)
        action_row.addWidget(self.delete_btn)

        action_row.addStretch()
        layout.addLayout(action_row)

        # 进度条（默认隐藏）
        self.progress_widget = QWidget()
        progress_layout = QVBoxLayout(self.progress_widget)
        progress_layout.setContentsMargins(0, 10, 0, 0)
        progress_layout.setSpacing(5)

        self.progress_bar = ProgressBar()
        self.progress_bar.setMinimumWidth(300)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.progress_label = BodyLabel("")
        progress_layout.addWidget(self.progress_label)

        self.progress_widget.setVisible(False)
        layout.addWidget(self.progress_widget)

        # 添加弹性空间，让内容靠上
        layout.addStretch()

        # 初始化状态
        QTimer.singleShot(100, self._update_status)

    def _on_model_changed(self, model: str):
        """模型选择变化"""
        self._update_status()
        self.model_changed.emit(model)

    def _update_status(self):
        """更新模型状态显示"""
        model = self.model_combo.currentText()
        is_downloaded = self._check_downloaded(model)
        info = self._model_info.get(model, {})

        if is_downloaded:
            size = self._get_model_size(model)
            size_str = self._format_size(size) if size else ""
            self.status_label.setText(f"✓ {t('downloaded')} ({size_str})")
            self.status_label.setStyleSheet("color: green;")
            self.download_btn.setEnabled(False)
            self.download_btn.setText(t("downloaded"))
            self.download_btn.setVisible(True)
            self.cancel_btn.setVisible(False)
            self.delete_btn.setEnabled(True)
        else:
            size_hint = info.get("size", "")
            self.status_label.setText(f"✗ {t('not_downloaded')} ({size_hint})")
            self.status_label.setStyleSheet("color: orange;")
            self.download_btn.setEnabled(True)
            self.download_btn.setText(t("download"))
            self.download_btn.setVisible(True)
            self.cancel_btn.setVisible(False)
            self.delete_btn.setEnabled(False)

    def _format_size(self, size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def _on_download(self):
        """下载模型"""
        model = self.model_combo.currentText()
        source = self.source_combo.currentText() if hasattr(self, 'source_combo') else None

        # 显示进度条
        self.progress_widget.setVisible(True)
        self.progress_bar.setValue(0)
        self.progress_label.setText(t("preparing_download"))
        self.download_btn.setVisible(False)
        self.cancel_btn.setVisible(True)
        self.delete_btn.setEnabled(False)

        self.download_started.emit(model)

        # 开始下载
        self._download_func(
            model,
            source,
            self._on_progress,
            self._on_complete,
        )

    def _on_progress(self, progress: float, message: str):
        """下载进度回调"""
        QTimer.singleShot(0, lambda: self._update_progress(progress, message))

    def _update_progress(self, progress: float, message: str):
        """更新进度 UI（主线程）"""
        self.progress_bar.setValue(int(progress))
        self.progress_label.setText(message)

    def _on_complete(self, success: bool, message: str):
        """下载完成回调"""
        QTimer.singleShot(0, lambda: self._handle_complete(success, message))

    def _handle_complete(self, success: bool, message: str):
        """处理下载完成（主线程）"""
        model = self.model_combo.currentText()
        self.progress_widget.setVisible(False)
        self.download_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self._update_status()
        self.download_completed.emit(model, success)

        # 如果是取消操作，不显示错误提示
        if "取消" in message or "cancel" in message.lower():
            return

        if success:
            InfoBar.success(
                title=t("download_success"),
                content=message,
                parent=self.window(),
                position=InfoBarPosition.TOP,
                duration=3000,
            )
        else:
            # 格式化错误消息，使其更易读
            error_msg = message
            if "\n" in error_msg:
                # 如果错误消息包含多行，使用 MessageBox 显示更详细的信息
                from qfluentwidgets import MessageBox
                MessageBox(
                    t("download_failed"),
                    error_msg,
                    self.window(),
                ).exec()
            else:
                # 单行错误消息使用 InfoBar
                InfoBar.error(
                    title=t("download_failed"),
                    content=error_msg,
                    parent=self.window(),
                    position=InfoBarPosition.TOP,
                    duration=5000,
                )

    def _on_cancel(self):
        """取消下载"""
        if self._cancel_func:
            self._cancel_func()
        self.progress_widget.setVisible(False)
        self.download_btn.setVisible(True)
        self.cancel_btn.setVisible(False)
        self._update_status()

    def _on_delete(self):
        """删除模型"""
        model = self.model_combo.currentText()

        msg = MessageBox(
            t("confirm_delete"),
            t("confirm_delete_model").format(model=model),
            self.window(),
        )
        if msg.exec():
            success = self._delete_func(model)
            self._update_status()

            if success:
                InfoBar.success(
                    title=t("delete_success"),
                    content=t("model_deleted").format(model=model),
                    parent=self.window(),
                    position=InfoBarPosition.TOP,
                    duration=3000,
                )

    # ========== 公共 API ==========

    def get_model(self) -> str:
        """获取选中的模型"""
        return self.model_combo.currentText()

    def set_model(self, model: str):
        """设置选中的模型"""
        self.model_combo.setCurrentText(model)

    def get_option(self, key: str) -> str:
        """获取额外选项的值"""
        if key in self._extra_combos:
            return self._extra_combos[key].currentText()
        return ""

    def set_option(self, key: str, value: str):
        """设置额外选项的值"""
        if key in self._extra_combos:
            self._extra_combos[key].setCurrentText(value)

    def get_source(self) -> str:
        """获取下载来源"""
        if hasattr(self, 'source_combo'):
            return self.source_combo.currentText()
        return ""

    def refresh_status(self):
        """刷新状态"""
        self._update_status()


def create_whisper_download_widget(parent=None) -> ModelDownloadWidget:
    """创建 Whisper 模型下载组件的工厂函数"""
    from ..engines.whisper_model_manager import (
        whisper_model_manager, WHISPER_MODELS, ModelSource
    )

    # 构建模型信息
    model_info = {
        name: {"size": info.size, "desc": info.description}
        for name, info in WHISPER_MODELS.items()
    }

    def download_func(model, source, on_progress, on_complete):
        src = ModelSource.MODELSCOPE if source == "ModelScope" else ModelSource.HUGGINGFACE
        whisper_model_manager.download_model(
            model_name=model,
            source=src,
            on_progress=on_progress,
            on_complete=on_complete,
        )

    def cancel_func():
        """取消下载"""
        whisper_model_manager.cancel_download()

    return ModelDownloadWidget(
        models=list(WHISPER_MODELS.keys()),
        model_info=model_info,
        check_downloaded=whisper_model_manager.is_model_downloaded,
        get_model_size=whisper_model_manager.get_model_size,
        download_func=download_func,
        delete_func=whisper_model_manager.delete_model,
        download_sources=["HuggingFace", "ModelScope"],
        extra_options={"device": ["auto", "cpu", "cuda"]},
        cancel_func=cancel_func,
        parent=parent,
    )
