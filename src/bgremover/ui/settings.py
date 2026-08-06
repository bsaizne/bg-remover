"""设置对话框。"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

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

        self.norm_mode = QComboBox()
        self.norm_mode.addItems(["自动检测", "/255", "ImageNet"])
        idx = {"auto": 0, "255": 1, "imagenet": 2}.get(config.norm_mode, 0)
        self.norm_mode.setCurrentIndex(idx)
        form.addRow("模型归一化:", self.norm_mode)

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
        if self.ffmpeg_edit.text().strip():
            from bgremover.core import ffmpeg_tool
            ffmpeg_tool.FFMPEG_OVERRIDE = self.ffmpeg_edit.text().strip()
        self.config.save()
