"""通用工具:棋盘格、尺寸格式化、ETA、环境信息、路径清理。"""
from __future__ import annotations

import platform
import sys

import numpy as np


def collect_env_info() -> dict:
    """收集运行环境摘要,用于日志头与远程排错。

    onnxruntime 延迟 import(缺失时记 N/A),任一字段失败都不抛错。
    本函数供 app.setup_logging 写日志头,也可被 --selftest 直接调用。
    """
    from bgremover import __version__

    info = {
        "app_version": __version__,
        "platform": sys.platform,
        "system": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "onnxruntime": "N/A",
        "providers": [],
    }
    try:
        import onnxruntime as ort
        info["onnxruntime"] = ort.__version__
        info["providers"] = list(ort.get_available_providers())
    except Exception:  # noqa: BLE001
        info["onnxruntime"] = "N/A"
    return info


def checkerboard_bgr(w: int, h: int, cell: int = 16,
                     color1=(45, 45, 45), color2=(120, 120, 120)) -> np.ndarray:
    """生成 BGR 棋盘格背景,用于透明预览。"""
    ys, xs = np.mgrid[0:h, 0:w]
    idx = ((xs // cell) + (ys // cell)) % 2
    c1 = np.array(color1, dtype=np.uint8)
    c2 = np.array(color2, dtype=np.uint8)
    return np.where(idx[..., None].astype(bool), c1, c2).astype(np.uint8)


def format_bytes(n: float) -> str:
    if n < 1024:
        return f"{n:.0f} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024.0
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


def format_duration(sec: float) -> str:
    if not sec or sec < 0:
        return "0:00"
    s = int(round(sec))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


class ETAEstimator:
    """基于累计平均速率的剩余时间估计器。

    用整体平均帧速率估算,避免批内瞬时抖动导致 ETA 失真;用 EMA 平滑。
    """

    def __init__(self, alpha: float = 0.3):
        self._alpha = alpha
        self._t0 = None
        self._d0 = 0
        self._avg_fps = None
        self._remaining = 0.0

    def update(self, done: int, total: int, now: float) -> float:
        """传入累计完成帧数与时间,返回剩余秒数(EMA 平滑后的整体速率)。"""
        if self._t0 is None:
            self._t0 = now
            self._d0 = done
            return 0.0
        elapsed = max(now - self._t0, 1e-6)
        done_delta = done - self._d0
        inst = done_delta / elapsed if done_delta > 0 else 0.0
        if self._avg_fps is None:
            self._avg_fps = inst
        else:
            self._avg_fps = self._alpha * inst + (1 - self._alpha) * self._avg_fps
        remaining = total - done
        self._remaining = remaining / self._avg_fps if self._avg_fps > 0 else 0.0
        return self._remaining

    @property
    def remaining(self) -> float:
        return self._remaining
