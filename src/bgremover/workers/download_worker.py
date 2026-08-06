"""模型下载 worker。"""
from __future__ import annotations

import logging

from bgremover.core import model_store
from bgremover.workers.base_worker import BaseWorker
from bgremover.workers.signals import ProgressPayload

log = logging.getLogger(__name__)


class DownloadWorker(BaseWorker):
    def __init__(self, purposes=None, parent=None):
        """purposes: 需下载的模型用途列表(默认 image+video 全部缺失项)。"""
        super().__init__(parent)
        self.purposes = purposes or ["image", "video"]

    def run(self):
        try:
            path = None
            for purpose in self.purposes:
                downloader = model_store.ModelDownloader(
                    progress_cb=lambda done, total: self.signals.progress.emit(
                        ProgressPayload(done=done, total=total)),
                    cancel_event=self._cancel_event)
                path = downloader.download(purpose)
                self.signals.status.emit(f"模型已就绪: {model_store.model_name(purpose)}")
            self.signals.finished.emit({"ok": True, "path": str(path) if path else "",
                                        "cancelled": self._cancel_event.is_set()})
        except Exception as e:  # noqa: BLE001
            log.exception("模型下载失败: %s", self.purposes)
            import traceback
            self.signals.failed.emit(f"{e}\n{traceback.format_exc()}")
