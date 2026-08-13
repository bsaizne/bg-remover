"""视频处理 worker:双层进度 + 暂停/继续/取消。"""
from __future__ import annotations

import logging
import os
import time

from bgremover.core import video_pipeline, ffmpeg_tool as ff
from bgremover.core import model_store
from bgremover.workers.base_worker import BaseWorker
from bgremover.workers.signals import ProgressPayload

log = logging.getLogger(__name__)


class VideoWorker(BaseWorker):
    """处理单个视频。task_index/task_total 用于多任务场景的总进度。

    失败自动重试:非用户取消时最多重试 `max_retries` 次(默认 2 次重试,共 3 次尝试),
    应对 ffmpeg 偶发解码/编码抖动。每次重试重置任务耗时基准。
    """

    def __init__(self, src: str, dst: str, fmt: str,
                 max_resolution: int = 1280, keep_audio: bool = True,
                 background: str = "", bg_color: str = "#000000",
                 task_index: int = 1, task_total: int = 1,
                 max_retries: int = 2, parent=None,
                 enable_coreml: bool = False,
                 downsample_ratio: float = 0.25,
                 edge_erode: int = 1):
        super().__init__(parent)
        self.src = src
        self.dst = dst
        self.fmt = fmt
        self.max_resolution = max_resolution
        self.keep_audio = keep_audio
        self.background = background
        self.bg_color = bg_color
        self.task_index = task_index
        self.task_total = task_total
        self.max_retries = max_retries
        self.enable_coreml = enable_coreml
        self.downsample_ratio = downsample_ratio
        self.edge_erode = edge_erode

    def run(self):
        t0 = time.monotonic()
        try:
            mp = str(model_store.resolve_model_path("video"))
            pipe = video_pipeline.VideoPipeline(mp)
            try:
                pmeta = ff.probe_video(ff.locate_ffmpeg(), self.src)
                pw0, ph0 = pmeta["width"], pmeta["height"]
            except Exception:  # noqa: BLE001
                pw0, ph0 = 0, 0  # CI 无测试视频时 selftest 不依赖本路径

            def cb(frames_done, frames_total, eta, preview_rgba=None):
                if self._cancel_event.is_set():
                    return
                elapsed = time.monotonic() - t0
                self.signals.progress.emit(ProgressPayload(
                    frames_done=frames_done, frames_total=frames_total,
                    task_done=self.task_index - 1 + (frames_done / frames_total if frames_total else 0),
                    task_total=self.task_total,
                    eta=eta, done=frames_done, total=frames_total,
                    preview_rgba=preview_rgba,
                    preview_w=pw0, preview_h=ph0))

            res = None
            attempts = 0
            while res is None or (not res.ok and not res.cancelled and attempts <= self.max_retries):
                attempts += 1
                if attempts > 1:
                    log.warning("视频处理失败,重试 %d/%d: %s (err=%s)",
                                attempts - 1, self.max_retries, self.src, res.error)
                    t0 = time.monotonic()  # 重置耗时基准,避免重试进度 ETA 失真
                res = pipe.process(
                    self.src, self.dst, self.fmt,
                    max_resolution=self.max_resolution,
                    keep_audio=self.keep_audio,
                    background=self.background,
                    bg_color=self.bg_color,
                    progress_cb=cb,
                    pause_event=self.pause_event,
                    cancel_event=self.cancel_event,
                    enable_coreml=self.enable_coreml,
                    downsample_ratio=self.downsample_ratio,
                    edge_erode=self.edge_erode)
            if res.cancelled:
                res.ok = False  # 保持 finished 语义:取消也算未成功
            self.signals.finished.emit({
                "ok": res.ok, "cancelled": res.cancelled, "error": res.error,
                "out": res.out, "frames_done": res.frames_done,
                "frames_total": res.frames_total, "elapsed": time.monotonic() - t0,
                "attempts": attempts,
            })
        except Exception as e:  # noqa: BLE001
            log.exception("视频处理失败: %s", self.src)
            import traceback
            self.signals.failed.emit(f"{e}\n{traceback.format_exc()}")
