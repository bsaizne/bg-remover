"""视频管线:ffmpeg 解码(rawvideo pipe) → RVM 顺序抠像 → ffmpeg 编码合成。

双管道直通,避免中间 PNG 序列占用磁盘。支持 pause/resume/cancel。
RVM 是循环网络,必须逐帧回传状态,因此视频推理为**单进程顺序**(不再用
multiprocessing.Pool);DirectML GPU 也由单进程独占,架构一致。
"""
from __future__ import annotations

import logging
import os
import queue
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from multiprocessing import Event

import numpy as np
import psutil
import cv2

from bgremover.core import ffmpeg_tool as ff
from bgremover.core import rvm
from bgremover.core.util import ETAEstimator

log = logging.getLogger(__name__)


@dataclass
class VideoTaskResult:
    src: str
    out: str
    ok: bool
    error: str = ""
    frames_done: int = 0
    frames_total: int = 0
    cancelled: bool = False
    recovered_frames: int = 0  # 解码中断后用最后有效帧填充的帧数


class _Reader(threading.Thread):
    """后台线程:从 ffmpeg 解码进程 stdout 读取 rawvideo 帧(blocking),drain stderr。

    读到短帧视为解码流结束(可能是文件截断/损坏,也可能只是正常 EOF),
    不设 error(由主循环依据 ffmpeg 退出码判断是否需填充恢复)。
    """

    def __init__(self, proc: subprocess.Popen, frame_bytes: int, buf: queue.Queue,
                 stop_flag, pause_event: Event | None):
        super().__init__(daemon=True)
        self.proc = proc
        self.frame_bytes = frame_bytes
        self.buf = buf
        self.stop_flag = stop_flag
        self.pause_event = pause_event
        self.error = ""

    def run(self):
        try:
            while not self.stop_flag.is_set():
                if self.pause_event is not None:
                    self.pause_event.wait()  # 暂停时阻塞读取
                data = self.proc.stdout.read(self.frame_bytes)
                if not data:
                    break
                if len(data) != self.frame_bytes:
                    log.warning("RVM 读帧:短帧 %d/%d 字节,解码流提前结束",
                                len(data), self.frame_bytes)
                    break
                self.buf.put(np.frombuffer(data, dtype=np.uint8).copy())
        except Exception as e:  # noqa: BLE001
            self.error = str(e)


class _Writer(threading.Thread):
    """后台线程:从队列取编码帧写入 ffmpeg 编码进程,使推理与编码重叠。"""

    def __init__(self, proc: subprocess.Popen, wbuf: queue.Queue, stop_flag):
        super().__init__(daemon=True)
        self.proc = proc
        self.wbuf = wbuf
        self.stop_flag = stop_flag
        self.error = ""

    def run(self):
        try:
            while not self.stop_flag.is_set():
                try:
                    data = self.wbuf.get(timeout=0.5)
                except queue.Empty:
                    continue
                if data is None:  # 结束哨兵
                    break
                self.proc.stdin.write(data)
        except Exception as e:  # noqa: BLE001
            self.error = str(e)


def _drain_stderr(proc: subprocess.Popen):
    """独立线程持续读取 stderr,防止管道写满导致 ffmpeg 阻塞死锁。"""
    def _run():
        try:
            for _ in iter(proc.stderr.readline, b""):
                if not _:
                    break
        except Exception:  # noqa: BLE001
            pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


class VideoPipeline:
    """单视频逐帧抠图并导出(RVM 顺序推理,带循环状态)。

    pause/cancel 由外部传入的 multiprocessing.Event 控制(跨进程共享)。
    """

    def __init__(self, model_path: str):
        self.model_path = model_path

    def process(self, src: str, dst: str, fmt: str,
                max_resolution: int = 1280,
                keep_audio: bool = True, background: str = "", bg_color: str = "#000000",
                progress_cb=None, pause_event: Event | None = None,
                cancel_event: Event | None = None) -> VideoTaskResult:
        t0 = time.monotonic()
        ffmpeg = ff.locate_ffmpeg()
        meta = ff.probe_video(ffmpeg, src)
        w, h = meta["width"], meta["height"]
        fps = meta["fps"]
        total = meta["frames"] or int(round(fps * meta["duration"]))
        scale = min(1.0, max_resolution / max(w, h)) if max_resolution > 0 else 1.0
        pw, ph = int(round(w * scale)), int(round(h * scale))
        if pw % 2:
            pw -= 1
        if ph % 2:
            ph -= 1
        tmp = tempfile.mkdtemp(prefix="bgremover_")
        audio_wav = os.path.join(tmp, "audio.wav")
        eta = ETAEstimator()
        done = 0
        cancelled = False
        frames_total = total
        error = ""
        reader = None
        writer = None
        proc_in = None
        proc_out = None

        try:
            # 背景合成图片预读
            bg_bgr = None
            if fmt == "mp4_bg":
                if background and os.path.exists(background):
                    bg_bgr = cv2.imread(background, cv2.IMREAD_COLOR)
                else:
                    bg_bgr = None

            # ---- 抽音频(可选)----
            if keep_audio and meta["has_audio"]:
                r = subprocess.run(ff.build_audio_cmd(ffmpeg, src, audio_wav),
                                   capture_output=True, timeout=300)
                if r.returncode != 0:
                    log.warning("音频抽取失败,将静音输出: %s", r.stderr.decode("utf-8", "ignore"))
                    audio_wav = ""

            # ---- 解码进程 ----
            read_cmd = ff.build_read_cmd(ffmpeg, src, fps)
            proc_in = subprocess.Popen(
                read_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
            _drain_stderr(proc_in)

            # ---- 编码进程(透明视频/背景视频走 ffmpeg;PNG 序列在 Python 内逐帧写)----
            is_png_seq = (fmt == "png_seq")
            if not is_png_seq:
                encode_cmd = ff.build_encode_cmd(ffmpeg, dst, pw, ph, fps, fmt,
                                                 audio_wav if audio_wav else None)
                proc_out = subprocess.Popen(
                    encode_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
                _drain_stderr(proc_out)

            frame_bytes = pw * ph * 3
            buf = queue.Queue(maxsize=4)
            wbuf = queue.Queue(maxsize=4)
            stop = threading.Event()
            reader = _Reader(proc_in, frame_bytes, buf, stop, pause_event)
            reader.start()
            if is_png_seq:
                os.makedirs(dst, exist_ok=True)  # dst 是目录
            else:
                writer = _Writer(proc_out, wbuf, stop)
                writer.start()

            # ---- RVM 单进程顺序推理(带循环状态)----
            # probe_hw=实际处理分辨率:真机实测 1.23 CoreML EP 小图正常、大图全黑,
            # 必须用真实分辨率 warmup 自检,输出过弱自动降级 CPU。
            session = rvm.build_session(self.model_path, probe_hw=(ph, pw))
            states = rvm.initial_states(session, ph, pw)
            down = rvm.DOWNSAMPLE_RATIO
            recovered = 0  # 因解码中断用最后有效帧填充的帧数
            last_rgb = None  # 最后解码出的完整 RGB 帧(损坏帧恢复用)
            last_rgb_flow = None   # 光流参考:上一帧 RGB(正常帧)
            last_pha_blend = None  # 光流参考:上一帧融合后的 matte
            while done < total:
                if cancel_event and cancel_event.is_set():
                    cancelled = True
                    break
                if pause_event is not None:
                    pause_event.wait()
                is_recovery = False  # 本帧是否是用最后有效帧填充的恢复帧
                try:
                    raw = buf.get(timeout=5)
                except queue.Empty:
                    # 解码端已结束:正常 EOF 或损坏截断。若还有剩余帧且有过有效帧,
                    # 用最后有效帧补齐(错误帧恢复),避免整个任务失败。
                    if reader.error or proc_in.poll() is not None:
                        if (last_rgb is not None and done < total
                                and not (cancel_event is not None and cancel_event.is_set())):
                            log.warning("解码提前结束(done=%d/total=%d),用最后有效帧补齐",
                                        done, total)
                            rgb = last_rgb
                            is_recovery = True
                            recovered += total - done  # 剩余帧全部用最后有效帧补齐
                        else:
                            break
                    else:
                        continue
                if raw.size != frame_bytes:
                    # 坏帧:丢弃并用最后有效帧填充
                    if last_rgb is not None:
                        log.warning("第 %d 帧解码不完整,用最后有效帧填充", done)
                        rgb = last_rgb
                        is_recovery = True
                        recovered += 1
                    else:
                        # 首帧就坏,无有效帧可参考:跳帧等待下一帧
                        continue
                else:
                    rgb = raw.reshape(ph, pw, 3).astype(np.float32) / 255.0
                    last_rgb = rgb.copy()
                fgr, pha, states = rvm.infer(session, rgb, states, down)
                # 光流帧间传播:平滑 matte 闪烁(仅在正常帧,错误恢复帧跳过)
                if not is_recovery:
                    pha = rvm.warp_blend_pha(pha,
                                             last_pha_blend if last_pha_blend is not None else None,
                                             last_rgb_flow, rgb)
                    last_pha_blend = pha.copy()
                    last_rgb_flow = rgb.copy()
                else:
                    # 恢复帧内容未变:清掉融合参考,避免累计乱 warp
                    last_pha_blend = None
                    last_rgb_flow = None
                if is_png_seq:
                    # PNG 走 cv2.imwrite,期望 BGRA 字节序
                    cv2.imwrite(os.path.join(dst, f"frame_{done:05d}.png"),
                                rvm.compose_bgra(fgr, pha))
                else:
                    if fmt in ("mov_alpha", "webm_alpha"):
                        # 编码器 -pix_fmt rgba:RGBA 字节序
                        data = rvm.compose_rgba(fgr, pha)
                    else:
                        # mp4_bg 编码器 -pix_fmt rgb24:RGB 字节序
                        data = rvm.compose_rgb(fgr, pha, bg_bgr, _hex_to_bgr(bg_color))
                    wbuf.put(data.astype(np.uint8).tobytes())
                done += 1
                # 实时预览:每 5 帧附一次合成后的 RGBA/RGB bytes
                preview_frame = None
                if progress_cb and done % 5 == 0:
                    preview_frame = (
                        rvm.compose_rgba(fgr, pha).tobytes()
                        if fmt in ("mov_alpha", "webm_alpha", "png_seq")
                        else rvm.compose_rgb(fgr, pha, bg_bgr, _hex_to_bgr(bg_color)).tobytes())
                if progress_cb:
                    rem = eta.update(done, total, time.monotonic())
                    progress_cb(done, total, rem, preview_frame)

            proc_in.terminate()  # 解码端由编码端 -shortest 控制结束,这里兜底
            if writer is not None:
                wbuf.put(None)  # 写端结束哨兵
                writer.join(timeout=30)
            if proc_out is not None:
                proc_out.stdin.close()
                proc_out.wait(timeout=60)
            if writer is not None and writer.error:
                log.warning("编码写端错误: %s", writer.error)
            if proc_out is not None and proc_out.returncode != 0 and not cancelled:
                error = f"编码失败(exit {proc_out.returncode})"
        except Exception as e:  # noqa: BLE001
            log.exception("视频处理失败")
            error = str(e)
        finally:
            stop.set()
            _kill_tree(proc_in) if proc_in else None
            _kill_tree(proc_out) if proc_out else None
            # 清理临时目录
            try:
                import shutil
                shutil.rmtree(tmp, ignore_errors=True)
            except Exception:  # noqa: BLE001
                pass

        ok = (error == "" and not cancelled)
        return VideoTaskResult(src=src, out=dst, ok=ok, error=error,
                               frames_done=done, frames_total=frames_total,
                               cancelled=cancelled, recovered_frames=recovered)


def _hex_to_bgr(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16)


def _kill_tree(proc: subprocess.Popen | None):
    if proc is None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                           capture_output=True)
        else:
            p = psutil.Process(proc.pid)
            for child in p.children(recursive=True):
                child.kill()
            p.kill()
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass
