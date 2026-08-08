"""ffmpeg 二进制定位、编码器自检、全部合成命令生成。"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

FFMPEG_OVERRIDE = ""  # 运行时覆盖 ffmpeg 路径

REQUIRED_ENCODERS = {
    "prores_ks": "透明 MOV(ProRes 4444 Alpha)",
    "libvpx-vp9": "透明 WebM(VP9 + Alpha)",
    "libx264": "背景替换 MP4(H.264)",
}


def locate_ffmpeg(override: str = "") -> str:
    """定位 ffmpeg 二进制:用户覆盖 > 打包内置 > imageio-ffmpeg 自带 > 系统 PATH。"""
    if override or FFMPEG_OVERRIDE:
        p = Path(override or FFMPEG_OVERRIDE)
        if p.exists():
            return str(p)
    # 打包场景:查找 _internal/ffmpeg 或 _MEIPASS/ffmpeg
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for cand in (base / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg"),
                     base / "_internal" / "ffmpeg" / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")):
            if cand.exists():
                return str(cand)
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        pass
    p = shutil.which("ffmpeg")
    if p:
        return p
    raise RuntimeError("找不到 FFmpeg,请安装或在设置中指定路径")


def check_encoders(ffmpeg: str) -> dict[str, bool]:
    """运行 `ffmpeg -encoders`,返回各必需编码器是否可用。"""
    try:
        out = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"], capture_output=True, text=True, timeout=30
        ).stdout
    except Exception as e:  # noqa: BLE001
        log.warning("ffmpeg -encoders 运行失败: %s", e)
        return {k: False for k in REQUIRED_ENCODERS}
    avail = {k: f" {k} " in f" {out} " or f"\n{k} " in f"\n{out} " for k in REQUIRED_ENCODERS}
    return avail


def probe_video(ffmpeg: str, video_path: str) -> dict:
    """读取视频元数据(不依赖 ffprobe,imageio-ffmpeg 只带 ffmpeg)。

    用 `ffmpeg -i file` 的 stderr 解析流信息。
    """
    cmd = [ffmpeg, "-hide_banner", "-i", video_path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    err = r.stderr or ""
    if r.returncode not in (0, 1):
        raise RuntimeError(f"ffmpeg 探测失败(exit {r.returncode}): {err[-400:]}")
    vstream = _parse_video_stream(err)
    if not vstream:
        raise RuntimeError(f"未找到视频流: {err[-400:]}")
    w, h = vstream["width"], vstream["height"]
    fps = _parse_fps(vstream.get("avg_frame_rate", "0"))
    dur = float(vstream.get("duration", 0) or 0) or _parse_duration(err)
    has_audio = _has_audio_stream(err)
    return {
        "width": w,
        "height": h,
        "fps": fps or 30.0,
        "duration": dur,
        "frames": int(round((fps or 30.0) * dur)) if dur else 0,
        "has_audio": has_audio,
        "size_bytes": os.path.getsize(video_path),
    }


def _parse_video_stream(err: str) -> dict | None:
    """从 ffmpeg -i 输出解析第一个视频流。"""
    for line in err.splitlines():
        if " Video: " not in line:
            continue
        # 形如: Stream #0:0: Video: h264 (High), yuv420p, 320x240 [SAR 1:1 DAR 4:3], 20 fps, 20 tbr, 10240 tbn
        dims = _find_dimensions(line)
        if not dims:
            continue
        w, h = dims
        return {"width": w, "height": h,
                "avg_frame_rate": _find_fps(line)}
    return None


def _find_dimensions(line: str) -> tuple[int, int] | None:
    import re
    m = re.search(r"(\d{2,5})x(\d{2,5})", line)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _find_fps(line: str) -> str:
    import re
    # 优先 fps 前面的数字,可能带小数: "20 fps"
    m = re.search(r"([\d.]+) fps", line)
    if m:
        return f"{m.group(1)}/1"
    # 形如 "25 tbr" 或 "50 tbr"
    m = re.search(r"([\d.]+) tbr", line)
    if m:
        return f"{m.group(1)}/1"
    return "0"


def _parse_duration(err: str) -> float:
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    return 0.0


def _has_audio_stream(err: str) -> bool:
    return " Audio: " in err


def _parse_fps(s: str) -> float:
    try:
        if "/" in s:
            n, d = s.split("/")
            return float(n) / float(d) if float(d) else 0.0
        return float(s)
    except Exception:  # noqa: BLE001
        return 0.0


def build_read_cmd(ffmpeg: str, src: str, fps: float,
                   width: int = 0, height: int = 0) -> list[str]:
    """读端:rawvideo pipe,固定帧率归一 + 可选缩放。

    width/height > 0 时在 -vf 里加 scale,使读端输出尺寸与编码端 `-s`
    一致,避免帧字节错位(源分辨率 > max_resolution 时曾导致扫描线/模糊)。
    """
    vf = [f"fps={fps:.6f}"]
    if width > 0 and height > 0:
        vf.append(f"scale={width}:{height}")
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", src,
        "-map", "0:v:0", "-an",
        "-vf", ",".join(vf),
        "-pix_fmt", "rgb24",
        "-c:v", "rawvideo",
        "-f", "rawvideo", "pipe:1",
    ]


def build_audio_cmd(ffmpeg: str, src: str, out_wav: str) -> list[str]:
    """抽音频为 PCM WAV(无音频则失败,由调用方按 has_audio 判断)。"""
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", src,
        "-vn", "-map", "0:a:0",
        "-c:a", "pcm_s16le", "-ac", "2", "-ar", "48000",
        "-f", "wav", out_wav,
    ]


def build_encode_cmd(ffmpeg: str, dst: str, width: int, height: int, fps: float,
                     fmt: str, audio_wav: str | None = None,
                     norm_mode: str = "255") -> list[str]:
    """写端:从 rawvideo pipe 读 RGBA 帧,编码为指定格式。返回 (cmd, used_pix_fmt)。"""
    # 根据格式决定输入像素格式(透明=RGBA,背景替换=RGB24)
    pix_in = "rgba" if fmt in ("mov_alpha", "webm_alpha", "png_seq") else "rgb24"
    has_audio = audio_wav and os.path.exists(audio_wav)
    cmd = [ffmpeg, "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", pix_in,
           "-s", f"{width}x{height}", "-r", f"{fps:.6f}",
           "-i", "pipe:0"]
    if has_audio:
        cmd += ["-i", audio_wav]
    # 透明格式禁止 alpha 压缩劣化或缩放
    if fmt == "mov_alpha":
        cmd += ["-map", "0:v:0", "-c:v", "prores_ks", "-profile:v", "4444",
                "-pix_fmt", "yuva444p10le", "-alpha_bits", "8"]
    elif fmt == "webm_alpha":
        cmd += ["-map", "0:v:0", "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                "-b:v", "0", "-crf", "34", "-auto-alt-ref", "0", "-row-mt", "1"]
    elif fmt == "png_seq":
        cmd += ["-map", "0:v:0", "-c:v", "png"]
    else:  # mp4_bg
        cmd += ["-map", "0:v:0", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-crf", "18", "-preset", "medium"]
    if has_audio:
        if fmt == "mov_alpha":
            cmd += ["-c:a", "pcm_s16le"]
        elif fmt == "webm_alpha":
            cmd += ["-c:a", "libopus"]
        else:
            cmd += ["-c:a", "aac"]
        cmd += ["-map", "1:a:0"]
    cmd += ["-shortest", "-movflags", "+faststart"] if fmt == "mp4_bg" else ["-shortest"]
    cmd += ["-y", dst]
    return cmd
