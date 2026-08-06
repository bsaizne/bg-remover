"""图片页:拖拽导入、批量抠图、透明/替换背景导出、原图/结果预览。"""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QFileDialog,
                               QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QPushButton, QRadioButton, QSplitter, QVBoxLayout,
                               QWidget)

from bgremover.core import image_pipeline
from bgremover.core.config import AppConfig
from bgremover.ui.preview import TransparentPreview
from bgremover.workers.image_worker import ImageWorker


class ImageTab(QWidget):
    def __init__(self, main_win):
        super().__init__()
        self.mw = main_win
        self.config: AppConfig = main_win.config
        self.worker: ImageWorker | None = None
        self._paused = False
        self._img_cache: dict[str, np.ndarray] = {}  # path -> BGR
        self._build_ui()
        self.setAcceptDrops(True)

    # ---------- UI ----------
    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # 左:文件列表
        left = QWidget()
        lv = QVBoxLayout(left)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        lv.addWidget(QLabel("图片列表(拖拽或导入)"))
        lv.addWidget(self.list, 1)
        lv.addWidget(QLabel("提示:拖拽文件/文件夹到这里,自动递归收集图片"))

        # 右:预览 + 选项
        right = QWidget()
        rv = QVBoxLayout(right)

        self.preview = TransparentPreview()
        self.preview.setMinimumWidth(480)
        rv.addWidget(self.preview, 1)

        mode_row = QHBoxLayout()
        self.rb_original = QRadioButton("原图")
        self.rb_result = QRadioButton("结果")
        self.rb_result.setChecked(True)
        self.rb_original.toggled.connect(self._on_preview_mode)
        self.rb_result.toggled.connect(self._on_preview_mode)
        bg = QButtonGroup(self)
        bg.addButton(self.rb_original)
        bg.addButton(self.rb_result)
        mode_row.addWidget(self.rb_original)
        mode_row.addWidget(self.rb_result)
        mode_row.addStretch(1)
        self.cur_info = QLabel("")
        mode_row.addWidget(self.cur_info)
        rv.addLayout(mode_row)

        opt_row = QHBoxLayout()
        self.cb_transparent = QCheckBox("输出透明 PNG")
        self.cb_transparent.setChecked(True)
        opt_row.addWidget(self.cb_transparent)
        self.rb_bg_color = QRadioButton("纯色背景")
        self.rb_bg_image = QRadioButton("图片背景")
        self.rb_bg_image.setEnabled(False)
        self.rb_bg_color.setChecked(True)
        opt_row.addWidget(self.rb_bg_color)
        opt_row.addWidget(self.rb_bg_image)
        self.btn_bg = QPushButton("选择背景")
        self.btn_bg.setEnabled(False)
        self.btn_bg.clicked.connect(self._pick_bg)
        opt_row.addWidget(self.btn_bg)
        self.color_dot = QLabel("●")
        self.color_dot.setStyleSheet(f"color: {self.config.bg_color}; font-size: 18px;")
        opt_row.addWidget(self.color_dot)
        opt_row.addStretch(1)
        rv.addLayout(opt_row)

        self.cb_transparent.toggled.connect(self._on_mode_toggled)
        self.rb_bg_color.toggled.connect(self._on_mode_toggled)

        self.btn_import = QPushButton("导入图片")
        self.btn_import.clicked.connect(self.import_dialog)
        self.btn_run = QPushButton("开始抠图")
        self.btn_run.setObjectName("primary")
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self.start)
        self.btn_pause = QPushButton("暂停")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_all)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_import)
        btn_row.addWidget(self.btn_run)
        btn_row.addWidget(self.btn_pause)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch(1)
        rv.addLayout(btn_row)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        outer = QVBoxLayout(self)
        outer.addWidget(splitter)

    # ---------- 导入 ----------
    def import_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择图片", "",
            "图片 (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.gif)")
        if files:
            self.add_files(files)

    def add_files(self, files):
        for f in files:
            ext = Path(f).suffix.lower()
            if ext not in image_pipeline.IMAGE_EXTS:
                continue
            if any(self.list.item(i).text() == f for i in range(self.list.count())):
                continue
            it = QListWidgetItem(f"{Path(f).name}\n{Path(f).parent}")
            it.setData(Qt.UserRole, f)
            self.list.addItem(it)
            self._img_cache[f] = None
        self._update_buttons()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        files = []
        for p in paths:
            if os.path.isdir(p):
                files.extend(self._collect_dir(p))
            elif Path(p).suffix.lower() in image_pipeline.IMAGE_EXTS:
                files.append(p)
        self.add_files(files)

    @staticmethod
    def _collect_dir(d: str):
        out = []
        for root, _, fs in os.walk(d):
            for f in fs:
                if Path(f).suffix.lower() in image_pipeline.IMAGE_EXTS:
                    out.append(os.path.join(root, f))
        return out

    # ---------- 预览 ----------
    def _on_select(self, cur: QListWidgetItem, _prev):
        if cur is None:
            return
        path = cur.data(Qt.UserRole)
        if path and self._img_cache.get(path) is None:
            img = cv2.imread(path, cv2.IMREAD_COLOR)
            if img is not None:
                self._img_cache[path] = img
        self._on_preview_mode()

    def _on_preview_mode(self):
        cur = self.list.currentItem()
        if cur is None:
            return
        path = cur.data(Qt.UserRole)
        img = self._img_cache.get(path)
        if img is None:
            return
        h, w = img.shape[:2]
        self.cur_info.setText(f"{w}×{h}")
        if self.rb_original.isChecked():
            self.preview.show_bgr(img, w, h)
        else:
            # 结果预览:未处理时显示原图;处理过且有缓存则显示结果
            out_path = Path(path).stem + "_bg.png"
            out_full = os.path.join(self.config.output_dir or os.path.dirname(path), out_path)
            if os.path.exists(out_full):
                self.preview.show_bgr(cv2.imread(out_full, cv2.IMREAD_UNCHANGED), w, h)
            else:
                self.preview.show_bgr(img, w, h)

    def _on_mode_toggled(self):
        transparent = self.cb_transparent.isChecked()
        use_image = not transparent and self.rb_bg_image.isChecked()
        self.rb_bg_color.setEnabled(not transparent)
        self.rb_bg_image.setEnabled(not transparent)
        self.btn_bg.setEnabled(not transparent and use_image)
        self.color_dot.setVisible(not transparent and not use_image)

    def _pick_bg(self):
        f, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "", "图片 (*.jpg *.jpeg *.png *.webp *.bmp)")
        if f:
            self.config.bg_image = f
            self.config.save()

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.config.bg_color), self, "选择背景颜色")
        if c.isValid():
            self.config.bg_color = c.name()
            self.color_dot.setStyleSheet(f"color: {self.config.bg_color}; font-size: 18px;")
            self.config.save()

    # ---------- 控制 ----------
    def set_model_ready(self, ready: bool):
        self.btn_run.setEnabled(ready and self.list.count() > 0)

    def _update_buttons(self):
        self.btn_run.setEnabled(self.mw._model_ready and self.list.count() > 0)

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        if self.list.count() == 0:
            return
        files = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        if not self.config.output_dir or not os.path.isdir(self.config.output_dir):
            out_dir = QFileDialog.getExistingDirectory(self, "选择输出目录",
                                                       self.config.output_dir or "")
            if not out_dir:
                return
            self.config.output_dir = out_dir
            self.config.save()
        transparent = self.cb_transparent.isChecked()
        background = self.config.bg_image if (not transparent and self.rb_bg_image.isChecked()) else ""
        color = self.config.bg_color if (not transparent and self.rb_bg_color.isChecked()) else "#000000"
        self.worker = ImageWorker(
            files=files, out_dir=self.config.output_dir, transparent=transparent,
            background=background, bg_color=color, norm_mode=self.config.norm_mode,
            parent=self)
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.signals.failed.connect(self._on_failed)
        self.worker.start()
        self._set_running(True)

    def toggle_pause(self):
        if not self.worker:
            return
        if self.worker.paused:
            self.worker.resume()
            self.btn_pause.setText("暂停")
        else:
            self.worker.pause()
            self.btn_pause.setText("继续")

    def cancel_all(self):
        if self.worker:
            self.worker.cancel()

    def _set_running(self, running: bool):
        self.mw.set_running_state(running)
        self.btn_import.setEnabled(not running)
        self.btn_run.setEnabled(not running)
        self.btn_pause.setEnabled(running)
        self.btn_cancel.setEnabled(running)

    def _on_progress(self, p):
        self.mw.show_total_progress(p.done, p.total, p.eta)
        self.mw.statusBar().showMessage(f"图片处理中: {p.done}/{p.total}")

    def _on_finished(self, result):
        self._set_running(False)
        if result.get("cancelled"):
            self.mw.statusBar().showMessage("已取消")
            self.mw.show_total_progress(0, 0)
            return
        ok, total = result.get("ok", 0), result.get("total", 0)
        self.mw.statusBar().showMessage(f"完成: 成功 {ok}/{total} 张", 8000)
        self.mw.show_total_progress(0, 0)
        # 部分/全部失败时弹窗(聚合为一条,列出失败文件)
        failed = [r for r in result.get("results", []) if not r.get("ok")]
        if failed:
            from bgremover.ui.dialogs import show_error_dialog
            detail = [f"{Path(r['src']).name}: {r['error'] or '未知错误'}" for r in failed]
            show_error_dialog(self, "图片处理失败",
                              f"{len(failed)}/{total} 张图片处理失败", detail)
        self._refresh_preview_result()

    def _on_failed(self, err):
        self._set_running(False)
        from bgremover.core.config import logs_dir
        self.mw.statusBar().showMessage(f"处理失败,日志已保存到 {logs_dir()}", 6000)
        self.mw.log_line(f"图片处理失败: {err}")
        from bgremover.ui.dialogs import show_error_dialog
        show_error_dialog(self, "处理出错", "图片处理遇到未预期错误,详见日志",
                          err.splitlines()[:8])

    def _refresh_preview_result(self):
        if self.rb_result.isChecked():
            self._on_preview_mode()
