"""视频页:导入、元信息、输出格式/背景/音频选项、双层进度、暂停/继续/取消、结果预览。"""
from __future__ import annotations

import os
import time
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QFileDialog,
                               QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QProgressBar,
                               QPushButton, QSplitter, QVBoxLayout, QWidget)

from bgremover.core import ffmpeg_tool as ff
from bgremover.core import image_pipeline
from bgremover.core.util import format_bytes, format_duration
from bgremover.ui.preview import TransparentPreview
from bgremover.workers.video_worker import VideoWorker

FORMAT_LABELS = {
    "mov_alpha": "透明 MOV (ProRes 4444 Alpha, 推荐)",
    "webm_alpha": "透明 WebM (VP9 + Alpha)",
    "mp4_bg": "替换背景 MP4 (H.264)",
    "png_seq": "PNG 帧序列 (透明)",
}


class VideoTab(QWidget):
    def __init__(self, main_win):
        super().__init__()
        self.mw = main_win
        self.config = main_win.config
        self.worker: VideoWorker | None = None
        self.videos: list[dict] = []  # 待处理队列
        self.queue_index = 0
        self._paused = False
        self._encoder_map = {}
        self._all_ok = True  # 当前队列是否全部处理成功(关机判断用)
        self._build_ui()
        self.setAcceptDrops(True)
        self._check_encoders()

    # ---------- UI ----------
    def _build_ui(self):
        splitter = QSplitter(Qt.Horizontal)

        # 左:视频队列
        left = QWidget()
        lv = QVBoxLayout(left)
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._on_select)
        lv.addWidget(QLabel("视频队列(双击预览原图)"))
        lv.addWidget(self.list, 1)
        self.info = QLabel("未选择视频")
        self.info.setWordWrap(True)
        lv.addWidget(self.info)

        self.btn_import = QPushButton("导入视频")
        self.btn_import.clicked.connect(self.import_dialog)
        self.btn_remove = QPushButton("移除选中")
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear = QPushButton("清空")
        self.btn_clear.clicked.connect(self._clear_all)
        lv.addLayout(_row(self.btn_import, self.btn_remove, self.btn_clear))

        # 右:选项 + 预览 + 进度
        right = QWidget()
        rv = QVBoxLayout(right)

        # 输出设置
        opts = QGroupBox("输出设置")
        of = QFormLayout(opts)
        self.cb_format = QComboBox()
        for k, v in FORMAT_LABELS.items():
            self.cb_format.addItem(v, k)
        self.cb_format.setCurrentIndex(0)
        self.cb_format.currentIndexChanged.connect(self._on_format_changed)
        of.addRow("输出格式:", self.cb_format)

        self.rb_bg_color = QCheckBox("替换背景使用纯色")
        self.rb_bg_color.setChecked(True)
        self.rb_bg_color.toggled.connect(self._on_bg_mode)
        of.addRow("背景:", self.rb_bg_color)

        bg_row = QHBoxLayout()
        self.btn_bg_color = QPushButton(self.config.bg_color)
        self.btn_bg_color.clicked.connect(self._pick_color)
        self.btn_bg_image = QPushButton("选择背景图...")
        self.btn_bg_image.setEnabled(False)
        self.btn_bg_image.clicked.connect(self._pick_bg_image)
        bg_row.addWidget(self.btn_bg_color)
        bg_row.addWidget(self.btn_bg_image)
        of.addRow("", _wrap(bg_row))

        self.cb_audio = QCheckBox("保留原始音频")
        self.cb_audio.setChecked(self.config.keep_audio)
        of.addRow("音频:", self.cb_audio)

        from bgremover.core import rvm
        self.backend_label = QLabel(f"视频加速: {rvm.video_backend()} (GPU 自动)")
        self.backend_label.setStyleSheet("color: #888;")
        of.addRow("", self.backend_label)

        self.cb_png_seq = QCheckBox("额外导出 PNG 帧序列(调试)")
        self.cb_png_seq.setChecked(False)
        of.addRow("", self.cb_png_seq)
        rv.addWidget(opts)

        # 控制 + 进度
        ctrl = QHBoxLayout()
        self.btn_run = QPushButton("开始处理")
        self.btn_run.setObjectName("primary")
        self.btn_run.setEnabled(False)
        self.btn_run.clicked.connect(self.start)
        self.btn_pause = QPushButton("暂停")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self.toggle_pause)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_all)
        ctrl.addWidget(self.btn_run)
        ctrl.addWidget(self.btn_pause)
        ctrl.addWidget(self.btn_cancel)
        ctrl.addStretch(1)
        rv.addLayout(ctrl)

        self.frame_progress = QProgressBar()
        rv.addWidget(self.frame_progress)
        self.status_label = QLabel("")
        rv.addWidget(self.status_label)

        self.preview = TransparentPreview()
        self.preview.setMinimumWidth(480)
        rv.addWidget(self.preview, 1)
        self.verify_label = QLabel("处理完成后,结果文件默认用系统播放器打开,透明视频需在支持 Alpha 的播放器中查看")
        self.verify_label.setWordWrap(True)
        self.verify_label.setStyleSheet("color: #888;")
        rv.addWidget(self.verify_label)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        outer = QVBoxLayout(self)
        outer.addWidget(splitter)

    # ---------- 编码器自检 ----------
    def _check_encoders(self):
        try:
            ffp = ff.locate_ffmpeg()
            self._encoder_map = ff.check_encoders(ffp)
        except Exception as e:  # noqa: BLE001
            self._encoder_map = {k: False for k in ("prores_ks", "libvpx-vp9", "libx264")}
        idx = self.cb_format.currentIndex()
        self._on_format_changed(idx)

    def _on_format_changed(self, idx):
        fmt = self.cb_format.itemData(idx)
        need = {"mov_alpha": "prores_ks", "webm_alpha": "libvpx-vp9",
                "mp4_bg": "libx264"}.get(fmt, "")
        if need and not self._encoder_map.get(need):
            self.cb_format.setItemText(
                idx, FORMAT_LABELS[fmt] + " (⚠ 编码器不可用)")
        if fmt == "mp4_bg":
            self.rb_bg_color.setEnabled(True)
            self.btn_bg_color.setEnabled(self.rb_bg_color.isChecked())
            self.btn_bg_image.setEnabled(not self.rb_bg_color.isChecked())
        else:
            self.rb_bg_color.setEnabled(False)
            self.btn_bg_color.setEnabled(False)
            self.btn_bg_image.setEnabled(False)

    def _on_bg_mode(self):
        self.btn_bg_color.setEnabled(self.rb_bg_color.isChecked())
        self.btn_bg_image.setEnabled(not self.rb_bg_color.isChecked())

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(self.config.bg_color), self, "选择背景颜色")
        if c.isValid():
            self.config.bg_color = c.name()
            self.btn_bg_color.setText(c.name())
            self.config.save()

    def _pick_bg_image(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择背景图片", "",
                                           "图片 (*.jpg *.jpeg *.png *.webp *.bmp)")
        if f:
            self.config.bg_image = f
            self.btn_bg_image.setText(f"背景: {Path(f).name}")
            self.config.save()

    # ---------- 导入 ----------
    def import_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择视频", "", "视频 (*.mp4 *.mov *.avi *.mkv *.webm *.flv)")
        if files:
            self.add_videos(files)

    def add_videos(self, files):
        for f in files:
            if any(v["path"] == f for v in self.videos):
                continue
            self.videos.append({"path": f})
            self.list.addItem(QListWidgetItem(Path(f).name))
        self._update_buttons()

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls()]
        videos, dirs = [], []
        for p in paths:
            if os.path.isdir(p):
                dirs.append(p)
            elif Path(p).suffix.lower() in VIDEO_EXTS:
                videos.append(p)
        # 文件夹:递归收集视频
        for d in dirs:
            for root, _, fs in os.walk(d):
                for f in fs:
                    if Path(f).suffix.lower() in VIDEO_EXTS:
                        videos.append(os.path.join(root, f))
        self.add_videos(videos)

    # ---------- 元信息 ----------
    def _on_select(self, cur, _prev):
        if cur is None:
            return
        idx = self.list.row(cur)
        v = self.videos[idx]
        try:
            ffp = ff.locate_ffmpeg()
            meta = ff.probe_video(ffp, v["path"])
            v["meta"] = meta
            v["frames_total"] = meta["frames"]
            self.info.setText(
                f"{Path(v['path']).name}\n"
                f"{meta['width']}×{meta['height']} | {meta['fps']:.1f} fps | "
                f"{format_duration(meta['duration'])} | {format_bytes(meta['size_bytes'])}\n"
                f"音频: {'有' if meta['has_audio'] else '无'} | 预计 {meta['frames']} 帧")
        except Exception as e:  # noqa: BLE001
            self.info.setText(f"读取失败: {e}")

    # ---------- 控制 ----------
    def set_model_ready(self, ready: bool):
        self.btn_run.setEnabled(ready and len(self.videos) > 0)

    def _update_buttons(self):
        self.btn_run.setEnabled(self.mw._model_ready and len(self.videos) > 0)

    def start(self):
        if self.worker and self.worker.isRunning():
            return
        if not self.videos:
            return
        if not self.config.output_dir or not os.path.isdir(self.config.output_dir):
            out_dir = QFileDialog.getExistingDirectory(self, "选择输出目录",
                                                       self.config.output_dir or "")
            if not out_dir:
                return
            self.config.output_dir = out_dir
            self.config.save()
        self.queue_index = 0
        self._all_ok = True  # 整批开始时重置成功标志
        self._process_next()

    def _process_next(self):
        if self.queue_index >= len(self.videos):
            self._set_running(False)
            self.mw.show_total_progress(0, 0)
            self.mw.statusBar().showMessage("视频处理全部完成", 8000)
            # 可选:全部成功后自动关机(仅用户开启且全部任务成功)
            if (self.config.shutdown_on_done and self._all_ok
                    and len(self.videos) > 0):
                from bgremover.ui.dialogs import shutdown_countdown_dialog
                if shutdown_countdown_dialog(self, seconds=30):
                    self.mw.statusBar().showMessage("已关机", 8000)
            return
        v = self.videos[self.queue_index]
        src = v["path"]
        fmt = self.cb_format.currentData()
        ext = {"mov_alpha": "mov", "webm_alpha": "webm", "mp4_bg": "mp4",
               "png_seq": ""}.get(fmt, "mov")
        if fmt == "png_seq":
            out = os.path.join(self.config.output_dir, Path(src).stem + "_frames")
        else:
            out = os.path.join(self.config.output_dir, Path(src).stem + f"_bg.{ext}")
        keep_audio = self.cb_audio.isChecked()
        background = self.config.bg_image if not self.rb_bg_color.isChecked() else ""
        bg_color = self.config.bg_color if self.rb_bg_color.isChecked() else "#000000"

        self.worker = VideoWorker(
            src=src, dst=out, fmt=fmt,
            max_resolution=self.config.max_resolution, keep_audio=keep_audio,
            background=background, bg_color=bg_color,
            task_index=self.queue_index + 1, task_total=len(self.videos), parent=self,
            enable_coreml=self.config.enable_coreml,
            downsample_ratio=self.config.downsample_ratio,
            edge_erode=self.config.edge_erode,
            edge_soften=self.config.edge_soften)
        self.worker.signals.progress.connect(self._on_progress)
        self.worker.signals.finished.connect(self._on_finished)
        self.worker.signals.failed.connect(self._on_failed)
        self._set_running(True)
        self.frame_progress.setValue(0)
        self.status_label.setText(f"正在处理: {Path(src).name} ({self.queue_index + 1}/{len(self.videos)})")
        self.worker.start()

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
        self.btn_run.setEnabled(not running and len(self.videos) > 0)
        self.btn_pause.setEnabled(running)
        self.btn_cancel.setEnabled(running)

    # ---------- 进度/完成 ----------
    def _on_progress(self, p):
        self.frame_progress.setRange(0, max(p.frames_total, 1))
        self.frame_progress.setValue(p.frames_done)
        txt = f"帧: {p.frames_done}/{p.frames_total}"
        if p.eta > 0:
            txt += f" | 剩余 {format_duration(p.eta)}"
        self.status_label.setText(txt)
        self.mw.show_total_progress(p.task_done, p.task_total, p.eta * (p.task_total - p.task_done + 1))
        # 实时预览:每 5 帧更新一次抠像结果
        if p.preview_rgba is not None and p.preview_w > 0 and p.preview_h > 0:
            try:
                rgba = np.frombuffer(p.preview_rgba, dtype=np.uint8).reshape(
                    p.preview_h, p.preview_w, 4)
                self.preview.show_rgba(rgba)
            except Exception:  # noqa: BLE001
                pass

    def _on_finished(self, result):
        if result.get("cancelled"):
            self._all_ok = False  # 取消不算全部成功
            self.status_label.setText("已取消")
            self.mw.show_total_progress(0, 0)
            self._set_running(False)
            self.mw.statusBar().showMessage("已取消", 4000)
            return
        if result.get("ok"):
            out = result.get("out", "")
            self.status_label.setText(f"完成: {Path(out).name}")
            self.mw.statusBar().showMessage(f"完成: {Path(out).name}", 8000)
            self._show_result_preview(out)
        else:
            self._all_ok = False  # 失败不算全部成功
            err = result.get("error", "未知错误")
            self.status_label.setText(f"失败: {err}")
            from bgremover.core.config import logs_dir
            self.mw.statusBar().showMessage(f"处理失败,日志已保存到 {logs_dir()}", 6000)
            self.mw.log_line(f"视频处理失败: {self.videos[self.queue_index]['path']} -> {err}")
            from bgremover.ui.dialogs import show_error_dialog
            show_error_dialog(self, "视频处理失败", "视频处理失败", err.splitlines()[:8])
        self.queue_index += 1
        self._process_next()

    def _on_failed(self, err):
        self._all_ok = False  # 异常不算全部成功
        self.status_label.setText("异常: " + (err.splitlines()[0] if err else ""))
        self.mw.log_line(f"视频 worker 异常: {err}")
        from bgremover.ui.dialogs import show_error_dialog
        show_error_dialog(self, "处理出错", "视频处理遇到未预期错误,详见日志",
                          err.splitlines()[:8])
        self.queue_index += 1
        self._process_next()

    def _show_result_preview(self, out):
        """结果预览:MP4 显示首帧;透明格式显示棋盘格合成首帧。"""
        if not os.path.exists(out):
            return
        if out.endswith((".mov", ".webm")):
            self.verify_label.setText(
                "透明视频已导出。请在支持 Alpha 的播放器(VLC / Premiere / After Effects)中查看,网页端请用 WebM 格式。")
        cap = cv2.VideoCapture(out)
        if cap.isOpened():
            ok, frame = cap.read()
            cap.release()
            if ok:
                self.preview.show_bgr(frame, frame.shape[1], frame.shape[0])

    def _remove_selected(self):
        cur = self.list.currentRow()
        if cur >= 0:
            self.videos.pop(cur)
            self.list.takeItem(cur)

    def _clear_all(self):
        self.videos.clear()
        self.list.clear()
        self.info.setText("未选择视频")
        self._update_buttons()


VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}


def _row(*widgets):
    l = QHBoxLayout()
    for w in widgets:
        l.addWidget(w)
    return l


def _wrap(layout):
    w = QWidget()
    w.setLayout(layout)
    return w
