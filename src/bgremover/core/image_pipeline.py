"""批量图片抠图调度:串行(单图)或并行(multiprocessing)。"""
from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from multiprocessing import Pool, Event
from pathlib import Path

import cv2

from bgremover.core import matting
from bgremover.core.util import format_bytes

log = logging.getLogger(__name__)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}


def _default_workers() -> int:
    """按平台 + 内存自适应的默认并行进程数。

    macOS 统一内存:进程数与内存共享,过大易 OOM,固定 2 进程最稳。
    Windows 物理机:核数减半(留系统余量),最高 4。
    每子进程独立加载 isnet(~178MB)+ 图像缓冲,故上限保守。
    """
    if sys.platform == "darwin":
        return 2
    # CI 环境(os.cpu_count()可能返回容器配额),保底 2
    cpu = os.cpu_count() or 2
    if cpu <= 2:
        return 1  # 小核数机器不做多进程
    return max(1, min(cpu // 2, 4))


@dataclass
class ImageTaskResult:
    src: str
    ok: bool
    error: str = ""
    out: str = ""


class ImagePipeline:
    """批量图片处理。cancel_event 可中断。"""

    def __init__(self, model_path: str, norm_mode: str = "auto", n_workers: int | None = None):
        self.model_path = model_path
        self.norm_mode = norm_mode
        self.n_workers = n_workers or _default_workers()

    def process_batch(self, files: list[str], out_dir: str,
                      transparent: bool = True,
                      background: str = "", bg_color: str = "#000000",
                      progress_cb=None, cancel_event: Event | None = None) -> list[ImageTaskResult]:
        """并行处理一批图片。progress_cb(done, total)。返回逐项结果。"""
        total = len(files)
        results: list[ImageTaskResult] = []

        if self.n_workers > 1 and len(files) > 1:
            with Pool(processes=self.n_workers, initializer=matting.init_worker,
                      initargs=(self.model_path,)) as pool:
                args = [(f, out_dir, transparent, background, bg_color, self.norm_mode)
                        for f in files]
                for i, res in enumerate(pool.imap(_worker_one, args)):
                    results.append(res)
                    if cancel_event and cancel_event.is_set():
                        pool.terminate()
                        break
                    if progress_cb:
                        progress_cb(i + 1, total)
        else:
            matting.init_worker(self.model_path)
            for i, src in enumerate(files):
                if cancel_event and cancel_event.is_set():
                    break
                results.append(_worker_one(
                    (src, out_dir, transparent, background, bg_color, self.norm_mode)))
                if progress_cb:
                    progress_cb(i + 1, total)
        return results


def _worker_one(args) -> ImageTaskResult:
    src, out_dir, transparent, background, bg_color, norm_mode = args
    try:
        img = cv2.imread(src, cv2.IMREAD_COLOR)
        if img is None:
            return ImageTaskResult(src=src, ok=False, error="无法读取图像")
        rgba, _ = matting.remove_bg(img, norm_mode)
        if transparent:
            out_name = Path(src).stem + "_bg.png"
            out = str(Path(out_dir) / out_name)
            cv2.imwrite(out, rgba)
        else:
            if background and os.path.exists(background):
                bg_bgr = cv2.imread(background, cv2.IMREAD_COLOR)
            else:
                bg_bgr = None
            color = _hex_to_bgr(bg_color)
            out_img = matting.matte_to_bg(rgba, bg_bgr, color)
            ext = Path(src).suffix.lower()
            if ext in {".jpg", ".jpeg"}:
                out = str(Path(out_dir) / (Path(src).stem + "_bg.jpg"))
                cv2.imwrite(out, out_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
            else:
                out = str(Path(out_dir) / (Path(src).stem + "_bg.png"))
                cv2.imwrite(out, out_img)
        return ImageTaskResult(src=src, ok=True, out=out)
    except Exception as e:  # noqa: BLE001
        log.exception("图片处理失败: %s", src)
        return ImageTaskResult(src=src, ok=False, error=str(e))


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)
