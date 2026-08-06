"""QThread 信号集中定义。"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class ProgressPayload:
    __slots__ = ("done", "total", "eta", "frames_done", "frames_total",
                 "task_done", "task_total", "preview_rgba", "preview_w", "preview_h")

    def __init__(self, done=0, total=0, eta=0.0, frames_done=0, frames_total=0,
                 task_done=0, task_total=0, preview_rgba=None, preview_w=0, preview_h=0):
        self.done = done
        self.total = total
        self.eta = eta
        self.frames_done = frames_done
        self.frames_total = frames_total
        self.task_done = task_done
        self.task_total = task_total
        self.preview_rgba = preview_rgba  # bytes | None:R/G/B/A 各8位 raw bytes,供 QImage 零拷贝
        self.preview_w = preview_w        # 预览帧宽
        self.preview_h = preview_h        # 预览帧高


class WorkerSignals(QObject):
    progress = Signal(object)          # ProgressPayload
    finished = Signal(object)          # 结果 dict
    failed = Signal(str)               # 错误消息
    log = Signal(str)                  # 日志行
    status = Signal(str)               # 状态文字
