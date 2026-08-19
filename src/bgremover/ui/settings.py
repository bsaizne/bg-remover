"""设置对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout,
                               QWidget)

from bgremover.core.config import AppConfig


class SettingsDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(460)
        self.config = config

        form = QFormLayout()

        self.theme = QComboBox()
        self.theme.addItems(["深色", "亮色"])
        self.theme.setCurrentIndex(0 if config.theme == "dark" else 1)
        form.addRow("主题:", self.theme)

        self.output_edit = QLineEdit(config.output_dir)
        out_btn = QPushButton("浏览...")
        out_btn.clicked.connect(self._pick_dir)
        out_row = QHBoxLayout()
        out_row.addWidget(self.output_edit, 1)
        out_row.addWidget(out_btn)
        form.addRow("默认输出目录:", self._wrap(out_row))

        self.max_res = QSpinBox()
        self.max_res.setRange(0, 8192)
        self.max_res.setValue(config.max_resolution)
        self.max_res.setSpecialValueText("不限")
        form.addRow("视频长边限制(px):", self.max_res)

        self.keep_audio = QComboBox()
        self.keep_audio.addItems(["保留", "去除"])
        self.keep_audio.setCurrentIndex(0 if config.keep_audio else 1)
        form.addRow("默认音频:", self.keep_audio)

        import sys as _sys
        self.shutdown_on_done = QCheckBox("全部视频处理完成后自动关机(Windows)")
        self.shutdown_on_done.setChecked(config.shutdown_on_done)
        if _sys.platform != "win32":
            self.shutdown_on_done.setEnabled(False)  # 非 Windows 不支持
        form.addRow("自动关机:", self.shutdown_on_done)

        self.norm_mode = QComboBox()
        self.norm_mode.addItems(["自动检测", "/255", "ImageNet"])
        idx = {"auto": 0, "255": 1, "imagenet": 2}.get(config.norm_mode, 0)
        self.norm_mode.setCurrentIndex(idx)
        form.addRow("模型归一化:", self.norm_mode)

        # RVM 解码精细度:实测 0.5 边缘精度无明显提升且更慢,保持默认 0.25 即可
        self.downsample = QDoubleSpinBox()
        self.downsample.setRange(0.1, 1.0)
        self.downsample.setSingleStep(0.05)
        self.downsample.setDecimals(2)
        self.downsample.setValue(config.downsample_ratio)
        form.addRow("RVM 解码精细度(默认 0.25,不建议调大):", self.downsample)

        # 视频边缘去白边:腐蚀强度(0=关,1=推荐,2-3=更强但细节损失)
        self.edge_erode = QSpinBox()
        self.edge_erode.setRange(0, 3)
        self.edge_erode.setValue(config.edge_erode)
        form.addRow("边缘去白边强度(0=关,1=推荐):", self.edge_erode)

        # 边缘优化:羽化+去色溢组合(磨平锯齿+去白边),透明视频克制羽化
        self.edge_soften = QDoubleSpinBox()
        self.edge_soften.setRange(0.0, 2.0)
        self.edge_soften.setSingleStep(0.1)
        self.edge_soften.setDecimals(1)
        self.edge_soften.setValue(config.edge_soften)
        form.addRow("边缘优化强度(0=关,1=推荐,羽化+去白边):", self.edge_soften)

        # 实验性 CoreML 加速(Mac)。默认关闭:CoreML 对 RVM 状态循环不可靠。
        import sys as _sys
        if _sys.platform == "darwin":
            self.enable_coreml = QCheckBox("实验性:启用 CoreML 视频加速(可能画面异常)")
            self.enable_coreml.setChecked(config.enable_coreml)
            form.addRow("视频加速:", self.enable_coreml)

        self.ffmpeg_edit = QLineEdit()
        ff_btn = QPushButton("浏览...")
        ff_btn.clicked.connect(self._pick_ffmpeg)
        ff_row = QHBoxLayout()
        ff_row.addWidget(self.ffmpeg_edit, 1)
        ff_row.addWidget(ff_btn)
        form.addRow("FFmpeg 路径(可选):", self._wrap(ff_row))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(buttons)

    def _wrap(self, layout):
        w = QWidget()
        w.setLayout(layout)
        return w

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if d:
            self.output_edit.setText(d)

    def _pick_ffmpeg(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择 FFmpeg 可执行文件")
        if f:
            self.ffmpeg_edit.setText(f)

    def apply(self):
        self.config.theme = "dark" if self.theme.currentIndex() == 0 else "light"
        self.config.output_dir = self.output_edit.text().strip()
        self.config.max_resolution = self.max_res.value()
        self.config.keep_audio = self.keep_audio.currentIndex() == 0
        self.config.norm_mode = ["auto", "255", "imagenet"][self.norm_mode.currentIndex()]
        self.config.downsample_ratio = self.downsample.value()
        self.config.edge_erode = self.edge_erode.value()
        self.config.edge_soften = self.edge_soften.value()
        self.config.shutdown_on_done = self.shutdown_on_done.isChecked()
        if getattr(self, "enable_coreml", None) is not None:
            self.config.enable_coreml = self.enable_coreml.isChecked()
        if self.ffmpeg_edit.text().strip():
            from bgremover.core import ffmpeg_tool
            ffmpeg_tool.FFMPEG_OVERRIDE = self.ffmpeg_edit.text().strip()
        self.config.save()
