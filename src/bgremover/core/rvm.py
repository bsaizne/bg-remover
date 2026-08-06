"""RobustVideoMatting(RVM) 推理:有状态循环网络,用于视频逐帧抠像。

RVM 是 ConvGRU 循环模型,必须逐帧回传 rnn 隐藏状态才能保持时序连贯。
本模型(rvm_mobilenetv3_fp32.onnx)有 4 个循环状态(r1i..r4i),通道数 16/20/40/64,
维度全部动态。推理不硬编码状态数量,运行时按输入声明自省。
输入帧为 RGB float32 [0,1],输出前景 fgr 与 matte pha(均 [0,1])。
GPU 加速按平台:Windows 走 onnxruntime-directml(DmlExecutionProvider),
macOS 走标准 onnxruntime(CoreMLExecutionProvider,内置 CoreML 后端),
均多厂商/多架构统一,无 GPU 自动回退 CPU。本模块无 Qt 依赖。
"""
from __future__ import annotations

import logging
import sys

import cv2
import numpy as np

log = logging.getLogger(__name__)

DOWNSAMPLE_RATIO = 0.25
RVM_MODEL_NAME = "rvm_mobilenetv3_fp32.onnx"
_IO_CACHE: dict[int, dict] = {}  # 按 session id 缓存输入输出规格,避免重复自省


def _resolve_provider(platform_name: str, avail: list[str], prefer_gpu: bool) -> list[str]:
    """纯函数:按平台与可用 provider 决定推理 providers 优先级(可单测)。

    platform_name 取 sys.platform("win32"/"darwin"/其他);
    avail 为 ort.get_available_providers() 结果。
    Windows 优先 DmlExecutionProvider,达尔文优先 CoreMLExecutionProvider,
    无可用 GPU 或 prefer_gpu=False → CPU。
    """
    if not prefer_gpu:
        return ["CPUExecutionProvider"]
    if platform_name == "darwin" and "CoreMLExecutionProvider" in avail:
        return ["CoreMLExecutionProvider", "CPUExecutionProvider"]
    if platform_name == "win32" and "DmlExecutionProvider" in avail:
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def detect_provider(prefer_gpu: bool = True) -> list[str]:
    """检测可用 provider:Windows 优先 DML,Mac 优先 CoreML,无则 CPU。"""
    import onnxruntime as ort
    return _resolve_provider(sys.platform, ort.get_available_providers(), prefer_gpu)


def video_backend() -> str:
    """只读返回当前环境视频推理后端(供 UI 显示)。"""
    try:
        p = detect_provider(prefer_gpu=True)
        if p and p[0] == "DmlExecutionProvider":
            return "DirectML GPU"
        if p and p[0] == "CoreMLExecutionProvider":
            return "CoreML GPU"
        return "CPU"
    except Exception:  # noqa: BLE001
        return "CPU"


def _io_spec(session) -> dict:
    key = id(session)
    if key not in _IO_CACHE:
        inputs = {i.name: i for i in session.get_inputs()}
        outputs = {o.name: o for o in session.get_outputs()}
        # 状态输入:除 src/downsample_ratio 之外的全部输入
        state_names = [n for n in inputs if n not in ("src", "downsample_ratio")]
        _IO_CACHE[key] = {
            "input_names": [i.name for i in session.get_inputs()],
            "inputs": inputs,
            "output_names": [o.name for o in session.get_outputs()],
            "outputs": outputs,
            "state_names": state_names,
        }
    return _IO_CACHE[key]


def build_session(model_path: str, prefer_gpu: bool = True):
    """创建 RVM Session(prefer_gpu=True 优先平台 GPU:Windows DML / Mac CoreML)。

    CoreML 对动态 shape / ConvGRU 支持有限,Session 创建失败(含算子不可用)
    自动回退 CPU;成功后 log 实际生效 provider。末尾 warmup 一次前置图编译。
    """
    import onnxruntime as ort

    so = ort.SessionOptions()
    so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    so.log_severity_level = 3
    providers = detect_provider(prefer_gpu)
    try:
        session = ort.InferenceSession(str(model_path), sess_options=so, providers=providers)
    except Exception as e:  # noqa: BLE001
        if providers[0] != "CPUExecutionProvider":
            log.warning("RVM GPU provider 创建失败,回退 CPU: %s", e)
            providers = ["CPUExecutionProvider"]
            session = ort.InferenceSession(str(model_path), sess_options=so,
                                           providers=providers)
        else:
            raise
    log.info("RVM Session 就绪, provider=%s", providers)
    # warmup:小尺寸黑帧 + 零状态,把 GPU 首次图编译的延迟前置到任务开头
    try:
        states = initial_states(session, 128, 128)
        black = np.zeros((128, 128, 3), dtype=np.float32)
        infer(session, black, states)
    except Exception as e:  # noqa: BLE001
        log.warning("RVM warmup 失败: %s", e)
    return session


def _state_shape(session, name: str, h: int, w: int,
                 downsample_ratio: float) -> tuple[int, ...]:
    """RVM 官方导出约定:循环状态初始为 (1,1,1,1) 全零,维度由模型内部自适应。

    因此不按帧尺寸推算,直接返回 (1,1,1,1)。后续帧回传上一帧输出即可。
    """
    return (1, 1, 1, 1)


def initial_states(session, height: int, width: int,
                   downsample_ratio: float = DOWNSAMPLE_RATIO) -> list[np.ndarray]:
    """创建全部循环状态的全零张量(RVM 官方约定初始 (1,1,1,1))。"""
    spec = _io_spec(session)
    states = [np.zeros((1, 1, 1, 1), dtype=np.float32) for _ in spec["state_names"]]
    if not states:
        raise RuntimeError(f"RVM 未找到循环状态输入: {spec['input_names']}")
    return states


def infer(session, rgb: np.ndarray, states: list[np.ndarray],
          downsample_ratio: float = DOWNSAMPLE_RATIO) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """推理一帧。rgb: (H,W,3) float32 [0,1] RGB。返回 (fgr, pha, new_states)。"""
    spec = _io_spec(session)
    h, w = rgb.shape[:2]
    src = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None, ...], dtype=np.float32)
    ds = np.asarray([downsample_ratio], dtype=np.float32)  # 模型声明 shape=[1]
    feed = {"src": src, "downsample_ratio": ds}
    for name, st in zip(spec["state_names"], states):
        feed[name] = st
    out = session.run(None, feed)
    outs = dict(zip(spec["output_names"], out))
    fgr = np.clip(outs["fgr"][0], 0.0, 1.0)       # (3,H,W)
    pha = np.clip(outs["pha"][0], 0.0, 1.0)       # (1,H,W)
    new_states = [outs[n[:-1] + "o"] for n in spec["state_names"] if n[:-1] + "o" in outs]
    if not new_states:
        new_states = states  # 无状态输出时原样返回(理论不会发生)
    return fgr, pha, new_states


def compose_rgba(fgr: np.ndarray, pha: np.ndarray) -> np.ndarray:
    """前景 RGB + matte → (H,W,4) uint8 RGBA。

    与 mov/webm 编码器的 `-pix_fmt rgba` 字节序一致(R,G,B,A)。
    """
    fgr_hwc = np.clip(fgr.transpose(1, 2, 0), 0.0, 1.0)  # (H,W,3) RGB
    rgb_u8 = (fgr_hwc * 255.0).astype(np.uint8)
    a = (np.clip(pha[0], 0.0, 1.0) * 255.0).astype(np.uint8)
    return np.dstack([rgb_u8, a]).astype(np.uint8)


def compose_bgra(fgr: np.ndarray, pha: np.ndarray) -> np.ndarray:
    """RGBA 版,供 cv2.imwrite 写透明 PNG(cv2 期望 BGRA 字节序)。"""
    rgba = compose_rgba(fgr, pha)
    return rgba[..., [2, 1, 0, 3]].copy()


def compose_rgb(fgr: np.ndarray, pha: np.ndarray,
                bg_bgr: np.ndarray | None = None,
                bg_color: tuple[int, int, int] = (0, 0, 0)) -> np.ndarray:
    """RVM 复合:out = fgr*pha + bg*(1-pha)。返回 (H,W,3) uint8 RGB。

    与 mp4_bg 编码器的 `-pix_fmt rgb24` 字节序一致(R,G,B)。
    bg_color 为 (b,g,r) 元组(与 video_pipeline._hex_to_bgr 一致);
    合成在 RGB 空间进行,故纯色与 bg_bgr 都先转 RGB。
    """
    fgr_rgb = fgr.transpose(1, 2, 0).astype(np.float32)  # (H,W,3)
    pha3 = np.clip(pha[0], 0.0, 1.0)[..., None]
    h, w = pha[0].shape[:2]
    if bg_bgr is None:
        bg = np.zeros((h, w, 3), dtype=np.float32)
        bg[..., 0], bg[..., 1], bg[..., 2] = (bg_color[2], bg_color[1], bg_color[0])
    else:
        bg_rgb = cv2.cvtColor(cv2.resize(bg_bgr, (w, h),
                                         interpolation=cv2.INTER_AREA),
                              cv2.COLOR_BGR2RGB).astype(np.float32)
        bg = bg_rgb / 255.0
    out_rgb = fgr_rgb * pha3 + bg * (1.0 - pha3)
    return (np.clip(out_rgb, 0, 1) * 255.0).astype(np.uint8)


def warp_blend_pha(pha: np.ndarray, last_pha: np.ndarray | None,
                   last_rgb: np.ndarray, rgb: np.ndarray,
                   blend_weight: float = 0.3,
                   edge_lo: float = 0.05, edge_hi: float = 0.95) -> np.ndarray:
    """光流帧间 matte 平滑:仅对边缘过渡带平滑,主体/背景完全保留。

    上一轮实机发现:全图光流融合会把移动主体 alpha 稀释(1.0→0.7,看起来
    主体变淡/抠不干净)。RVM 的边缘本来就偏柔,所以只对 alpha 处于过渡带
    [edge_lo, edge_hi] 的像素做「当前帧 + 上一帧光流 warp」加权,主体内部
    (alpha≈1)与背景(alpha≈0)完全取当前帧,避免稀释。

    Args:
        pha: 当前帧 matte (1,H,W) float32 [0,1]
        last_pha: 上一帧 matte (1,H,W) float32,或 None(首帧/恢复帧)
        last_rgb: 上一帧 RGB (H,W,3) float32 [0,1]
        rgb: 当前帧 RGB (H,W,3) float32 [0,1]
        blend_weight: 边缘处上一帧 warp 后的权重(0.3 = 当前帧 70% + 上一帧 30%)
        edge_lo/edge_hi: 边缘过渡带 alpha 阈值,越窄融合越保守

    Returns:
        融合后的 pha (1,H,W) float32 [0,1]

    若 last_pha 为 None 或尺寸不一致则直接返回 pha。
    """
    if last_pha is None:
        return pha
    if last_rgb.shape != rgb.shape:
        return pha

    h, w = pha.shape[1], pha.shape[2]
    # 边缘过渡带掩膜:alpha 处于 (edge_lo, edge_hi) 的像素才是待平滑边缘
    edge_mask = ((pha[0] > edge_lo) & (pha[0] < edge_hi)).astype(np.float32)
    if float(edge_mask.mean()) < 1e-4:
        return pha  # 无边缘(全透明或全不透明),直接返回
    # Farneback 需要灰度 uint8
    try:
        prev_gray = cv2.cvtColor((last_rgb * 255.0).astype(np.uint8),
                                 cv2.COLOR_RGB2GRAY)
        curr_gray = cv2.cvtColor((rgb * 255.0).astype(np.uint8),
                                 cv2.COLOR_RGB2GRAY)
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
        # 用光流 warp 上一帧 matte
        warped = cv2.remap(
            last_pha[0], flow[..., 0], flow[..., 1],
            cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        warped = np.clip(warped, 0.0, 1.0)
        # 融合:边缘处混合,主体/背景完全取当前帧
        blended = pha[0] * (1.0 - blend_weight) + warped * blend_weight
        out = pha[0] * (1.0 - edge_mask) + blended * edge_mask
        return np.clip(out, 0.0, 1.0).reshape(1, h, w).astype(np.float32)
    except Exception as e:  # noqa: BLE001
        log.warning("光流融合失败,回退原始 matte: %s", e)
        return pha
