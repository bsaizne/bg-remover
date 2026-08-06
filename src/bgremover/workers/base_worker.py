"""QThread 基类:三态状态机 + 信号转发。"""
from __future__ import annotations

from multiprocessing import Event

from PySide6.QtCore import QThread

from bgremover.workers.signals import WorkerSignals


class BaseWorker(QThread):
    """在子线程跑 pipeline,cancel/pause 通过 multiprocessing.Event 令牌控制。

    子类实现 `run` 内调用 pipeline,并用 `signals` 发射进度/结果。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = WorkerSignals()
        self._pause_event = Event()
        self._pause_event.set()  # 默认不暂停(wait 不阻塞)
        self._cancel_event = Event()
        self._paused = False

    @property
    def pause_event(self):
        return self._pause_event

    @property
    def cancel_event(self):
        return self._cancel_event

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self):
        self._paused = True
        self._pause_event.clear()
        self.signals.status.emit("已暂停")

    def resume(self):
        self._paused = False
        self._pause_event.set()
        self.signals.status.emit("处理中...")

    def cancel(self):
        self._cancel_event.set()
        self._pause_event.set()  # 避免停在 pause 上无法退出
        self.signals.status.emit("正在取消...")

    def run(self):  # 子类覆写
        raise NotImplementedError
