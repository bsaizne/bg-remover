"""图片批量处理 worker。"""
from __future__ import annotations

import logging
import os

from bgremover.core import image_pipeline
from bgremover.core import model_store
from bgremover.workers.base_worker import BaseWorker
from bgremover.workers.signals import ProgressPayload

log = logging.getLogger(__name__)


class ImageWorker(BaseWorker):
    def __init__(self, files: list[str], out_dir: str, transparent: bool = True,
                 background: str = "", bg_color: str = "#000000",
                 norm_mode: str = "auto", n_workers: int | None = None, parent=None):
        super().__init__(parent)
        self.files = files
        self.out_dir = out_dir
        self.transparent = transparent
        self.background = background
        self.bg_color = bg_color
        self.norm_mode = norm_mode
        self.n_workers = n_workers

    def run(self):
        try:
            mp = str(model_store.resolve_model_path())
            pipe = image_pipeline.ImagePipeline(mp, self.norm_mode, self.n_workers)

            def cb(done, total):
                if self._cancel_event.is_set():
                    return
                self.signals.progress.emit(ProgressPayload(
                    done=done, total=total, task_done=done, task_total=total))

            results = pipe.process_batch(
                self.files, self.out_dir,
                transparent=self.transparent,
                background=self.background,
                bg_color=self.bg_color,
                progress_cb=cb,
                cancel_event=self._cancel_event)
            ok = sum(1 for r in results if r.ok)
            self.signals.finished.emit({
                "ok": ok, "total": len(results),
                "cancelled": self._cancel_event.is_set(),
                "results": [r.__dict__ for r in results],
            })
        except Exception as e:  # noqa: BLE001
            log.exception("图片处理失败")
            import traceback
            self.signals.failed.emit(f"{e}\n{traceback.format_exc()}")
