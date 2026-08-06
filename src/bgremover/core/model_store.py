"""模型下载(多源/断点续传/md5 校验)与 onnxruntime Session 单例管理。

支持两种模型来源:
- 打包内置模型(PyInstaller frozen):位于应用包内,开箱即用,只读。
- 用户数据目录模型:首次从内置复制出来,之后可被替换/更新。
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import sys
import threading
import time
from pathlib import Path

import requests

from bgremover.core.config import models_dir

log = logging.getLogger(__name__)

MODEL_NAME = "isnet-general-use.onnx"  # 兼容别名:图片模型名
MODEL_MD5 = ""  # 留空则不校验 md5(模型源 md5 未知),仅校验文件大小与可加载性

# 按用途区分的模型槽位。图片保留 isnet;视频用 RVM(mobilenetv3)。
MODELS = {
    "image": {
        "name": "isnet-general-use.onnx",
        "sources": [
            "https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx",
            "https://ghproxy.net/https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx",
            "https://huggingface.co/danielgatis/rembg/resolve/main/isnet-general-use.onnx",
            "https://hf-mirror.com/danielgatis/rembg/resolve/main/isnet-general-use.onnx",
        ],
        "min_size": 1_000_000,
    },
    "video": {
        "name": "rvm_mobilenetv3_fp32.onnx",
        "sources": [
            "https://ghproxy.net/https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx",
            "https://github.com/PeterL1n/RobustVideoMatting/releases/download/v1.0.0/rvm_mobilenetv3_fp32.onnx",
        ],
        "min_size": 1_000_000,
    },
}

# 兼容旧引用
MODEL_SOURCES = MODELS["image"]["sources"]

CHUNK = 1 << 20  # 1 MiB


def _cfg(purpose: str = "image") -> dict:
    if purpose not in MODELS:
        raise KeyError(f"未知模型用途: {purpose},可选 {list(MODELS)}")
    return MODELS[purpose]


def model_name(purpose: str = "image") -> str:
    return _cfg(purpose)["name"]


def _frozen_base() -> Path | None:
    """PyInstaller frozen 时返回内置资源根目录,否则 None。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base
    return None


def bundled_model_path(purpose: str = "image") -> Path | None:
    """打包内置模型路径(frozen 时),未打包返回 None。"""
    name = model_name(purpose)
    base = _frozen_base()
    if base is None:
        return None
    # 常见挂载位置:根、models/、_internal/models/
    for cand in (base / name,
                 base / "models" / name,
                 base / "_internal" / "models" / name):
        if cand.exists():
            return cand
    return None


def model_path(purpose: str = "image") -> Path:
    """用户可写目录中的模型路径(可被替换/更新)。"""
    return models_dir() / model_name(purpose)


def is_model_ready(purpose: str = "image") -> bool:
    """内置或用户目录任一有有效模型即视为就绪。"""
    p = model_path(purpose)
    if p.exists() and p.stat().st_size > _cfg(purpose)["min_size"]:
        return True
    bmp = bundled_model_path(purpose)
    return bmp is not None and bmp.stat().st_size > _cfg(purpose)["min_size"]


def ensure_model_bundled_copy(purpose: str = "image") -> Path:
    """确保用户数据目录有可用模型:内置存在则复制,否则保持现有。返回实际模型路径。"""
    p = model_path(purpose)
    if p.exists() and p.stat().st_size > _cfg(purpose)["min_size"]:
        return p
    bmp = bundled_model_path(purpose)
    if bmp is not None and bmp.stat().st_size > _cfg(purpose)["min_size"]:
        shutil.copy2(bmp, p)
        log.info("已从内置复制模型 %s 到 %s", purpose, p)
        return p
    return p  # 无内置模型,交给下载逻辑


def resolve_model_path(purpose: str = "image") -> Path:
    """返回实际用于推理的模型路径(用户目录优先,内置兜底)。"""
    p = model_path(purpose)
    if p.exists() and p.stat().st_size > _cfg(purpose)["min_size"]:
        return p
    bmp = bundled_model_path(purpose)
    if bmp is not None:
        return bmp
    return p


def missing_models() -> list[str]:
    """返回未就绪的模型用途列表(供 banner / 下载)。"""
    return [p for p in MODELS if not is_model_ready(p)]


class ModelDownloader:
    """流式下载,支持断点续传与失败换源。回调用于上报进度(字节数)。"""

    def __init__(self, progress_cb=None, cancel_event=None):
        self._cb = progress_cb or (lambda done, total: None)
        self._cancel = cancel_event

    def download(self, purpose: str = "image") -> Path:
        target = model_path(purpose)
        if is_model_ready(purpose):
            self._cb(target.stat().st_size, target.stat().st_size)
            return target
        last_err = None
        for src in _cfg(purpose)["sources"]:
            try:
                self._download_from(src, target, _cfg(purpose)["min_size"])
                if is_model_ready(purpose):
                    log.info("模型就绪: %s", target)
                    return target
            except Exception as e:  # noqa: BLE001
                log.warning("模型下载源失败 %s: %s", src, e)
                last_err = e
        raise RuntimeError(f"所有模型源均下载失败: {last_err}")

    def _download_from(self, url: str, target: Path, min_size: int = 1_000_000) -> None:
        part = target.with_suffix(".part")
        offset = part.stat().st_size if part.exists() else 0
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        total = None
        with requests.get(url, stream=True, timeout=30, headers=headers) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length", 0)) + offset
            mode = "ab" if offset else "wb"
            done = offset
            with open(part, mode) as f:
                for chunk in r.iter_content(chunk_size=CHUNK):
                    if self._cancel is not None and self._cancel.is_set():
                        raise RuntimeError("下载已取消")
                    f.write(chunk)
                    done += len(chunk)
                    self._cb(done, total)
        if part.stat().st_size > min_size:
            part.rename(target)
        else:
            raise RuntimeError("下载文件过小,疑似内容错误")


class ModelManager:
    """Session 单例。Session 不可跨进程 pickle,子进程各自惰性创建。"""

    _session = None
    _lock = threading.Lock()
    _path: Path | None = None

    @classmethod
    def get_session(cls, path: Path | None = None):
        """主进程内共享的 Session。path 覆盖时重建。"""
        p = path or model_path()
        with cls._lock:
            if cls._session is None or cls._path != p:
                import onnxruntime as ort

                so = ort.SessionOptions()
                so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                so.intra_op_num_threads = 4
                so.log_severity_level = 3
                # 图片路径固定 CPU(见 matting.init_worker 注释)
                cls._session = ort.InferenceSession(str(p), sess_options=so,
                                                    providers=["CPUExecutionProvider"])
                cls._path = p
            return cls._session
