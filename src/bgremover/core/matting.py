"""isnet-general-use 推理:预处理 / 后处理 / 抠图原子函数。

模块级全局 `_SESSION` 供 multiprocessing 子进程经 initializer 惰性初始化(每进程一份,约170MB)。
模块可被独立 import(无 Qt 依赖)。
"""
from __future__ import annotations

import logging

import cv2
import numpy as np

log = logging.getLogger(__name__)

INPUT_SIZE = 1024
_IMAGE_NET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32).reshape(1, 1, 3)
_IMAGE_NET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32).reshape(1, 1, 3)

_SESSION = None


def init_worker(model_path: str) -> None:
    """Pool initializer:惰性建 Session,不可跨进程 pickle。"""
    global _SESSION
    if _SESSION is None:
        import onnxruntime as ort

        so = ort.SessionOptions()
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        so.intra_op_num_threads = 2  # 多进程下每进程限线程,避免超卖
        so.log_severity_level = 3
        # 图片固定走 CPU:换 onnxruntime-directml 后默认会优先 DML,多进程下每进程建 GPU
        # session 会耗尽显存。GPU 只用于视频路径(core/rvm.py)。
        _SESSION = ort.InferenceSession(str(model_path), sess_options=so,
                                        providers=["CPUExecutionProvider"])
        log.info("worker 进程 Session 就绪(pid=%s)", __import__("os").getpid())


def _preprocess(img_bgr: np.ndarray, norm_mode: str) -> np.ndarray:
    """BGR(H,W,3) -> NCHW float32 [0,1],并缩放到 1024。"""
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    h, w = rgb.shape[:2]
    size = (INPUT_SIZE, INPUT_SIZE)
    if (w, h) != size:
        rgb = cv2.resize(rgb, size, interpolation=cv2.INTER_LINEAR)
    if norm_mode == "imagenet":
        rgb = (rgb - _IMAGE_NET_MEAN) / _IMAGE_NET_STD
    x = rgb.transpose(2, 0, 1)[None, ...]  # 1,3,1024,1024
    return np.ascontiguousarray(x, dtype=np.float32)


def _run_inference(session, img_bgr: np.ndarray, norm_mode: str) -> np.ndarray:
    inp = session.get_inputs()[0]
    name = inp.name
    x = _preprocess(img_bgr, norm_mode)
    y = session.run(None, {name: x})[0]
    # isnet 输出 (1,1,H,W);squeeze 到 (H,W)
    mask = y[0, 0]
    # 输出可能未过 sigmoid(原始 logit)或已过,统一 sigmoid
    if mask.min() < 0:
        mask = 1.0 / (1.0 + np.exp(-mask))
    return np.clip(mask, 0.0, 1.0)


def _postprocess(mask: np.ndarray, img_bgr: np.ndarray, feathered: int = 0) -> np.ndarray:
    """mask(1024,1024) 缩回原图尺寸并羽化,返回 0-255 uint8 alpha。"""
    h, w = img_bgr.shape[:2]
    if (mask.shape[0], mask.shape[1]) != (h, w):
        mask = cv2.resize(mask, (w, h), interpolation=cv2.INTER_LINEAR)
    a = (np.clip(mask, 0, 1) * 255.0).astype(np.uint8)
    if feathered > 0:
        k = feathered * 2 + 1
        a = cv2.GaussianBlur(a, (k, k), 0)
    return a


def _normalize_check(session, sample_bgr: np.ndarray) -> str:
    """单图自检:判定模型期望 /255 还是 imagenet 归一化。

    用前景/背景分离度判别:正确的归一化会产生接近二值的 mask(高方差、均值居中),
    错误的归一化输出接近平坦(方差小)。对一张含前后景的自然图成立。
    """
    m255 = _run_inference(session, sample_bgr, "255")
    mim = _run_inference(session, sample_bgr, "imagenet")
    v255 = float(np.var(m255))
    vim = float(np.var(mim))
    # 合理 mask:方差显著大于噪声级
    ok255 = v255 > 0.01
    okim = vim > 0.01
    if ok255 and not okim:
        return "255"
    if okim and not ok255:
        return "imagenet"
    # 两者都有效时取方差更大者;都无效时默认 255
    return "255" if v255 >= vim else "imagenet"


def remove_bg(img_bgr: np.ndarray, norm_mode: str = "auto", feathered: int = 0,
              session=None) -> tuple[np.ndarray, np.ndarray]:
    """抠图:输入 BGR 图像,输出 (rgba_uint8, alpha_uint8)。norm_mode='auto' 时用全局自检结果。"""
    global _SESSION
    s = session or _SESSION
    if s is None:
        raise RuntimeError("Session 未初始化:请先调用 init_worker()")
    if norm_mode == "auto":
        norm_mode = _normalize_check(s, img_bgr)
    mask = _run_inference(s, img_bgr, norm_mode)
    alpha = _postprocess(mask, img_bgr, feathered)
    b, g, r = cv2.split(img_bgr)
    rgba = cv2.merge([b, g, r, alpha])
    return rgba, alpha


def matte_to_bg(rgba: np.ndarray, bg_bgr: np.ndarray | None = None,
                bg_color: tuple = (0, 0, 0)) -> np.ndarray:
    """RGBA 合成到背景(图片 BGR 或纯色),返回 BGR。"""
    b, g, r, a = cv2.split(rgba)
    af = a.astype(np.float32) / 255.0
    if bg_bgr is None:
        h, w = a.shape[:2]
        bg = np.zeros((h, w, 3), dtype=np.float32)
        bg[..., 0] = bg_color[0]
        bg[..., 1] = bg_color[1]
        bg[..., 2] = bg_color[2]
    else:
        h, w = a.shape[:2]
        bg = cv2.resize(bg_bgr, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32)
    out = (af[..., None] * np.stack([b, g, r], axis=-1).astype(np.float32)
           + (1.0 - af[..., None]) * bg)
    return np.clip(out, 0, 255).astype(np.uint8)


def process_image_file(src: str, out: str, norm_mode: str = "auto",
                       background: str = "", bg_color: str = "#000000") -> dict:
    """子进程可 pickle 的入口:读图->抠图->写 PNG(透明)或合成背景后写 JPEG/PNG。"""
    img_bgr = cv2.imread(src, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise RuntimeError(f"无法读取图像: {src}")
    rgba, alpha = remove_bg(img_bgr, norm_mode)
    if background:
        from PIL import Image
        import os
        if os.path.exists(background) and os.path.splitext(background)[1].lower() in {
            ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
            bg_bgr = cv2.imread(background, cv2.IMREAD_COLOR)
        else:
            bg_bgr = None
        color = _hex_to_bgr(bg_color)
        out_img = matte_to_bg(rgba, bg_bgr, color)
        ext = os.path.splitext(out)[1].lower()
        if ext in {".jpg", ".jpeg"}:
            cv2.imwrite(out, out_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        else:
            cv2.imwrite(out, out_img)
    else:
        cv2.imwrite(out, rgba)
    return {"src": src, "out": out, "ok": True}


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return b, g, r
