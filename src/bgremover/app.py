"""QApplication 装配、单实例、全局异常钩子。"""
from __future__ import annotations

import logging
import logging.handlers
import sys

from bgremover.core.config import APP_NAME, data_dir, logs_dir
from bgremover.core.util import format_duration


def setup_logging() -> logging.Logger:
    log = logging.getLogger("bgremover")
    log.setLevel(logging.INFO)
    if not log.handlers:
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        fh = logging.handlers.RotatingFileHandler(
            logs_dir() / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        fh.setFormatter(fmt)
        log.addHandler(fh)
        # error.log 独立 handler,仅收集 ERROR+ 级,便于排错时只看错误
        eh = logging.handlers.RotatingFileHandler(
            logs_dir() / "error.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        eh.setLevel(logging.ERROR)
        eh.setFormatter(fmt)
        log.addHandler(eh)
        # 日志头写入环境摘要(系统/芯片/Python/onnxruntime/是否 frozen/版本)
        from bgremover.core.util import collect_env_info
        try:
            log.info("=== 环境信息 ===")
            for k, v in collect_env_info().items():
                log.info("  %s = %s", k, v)
        except Exception:  # noqa: BLE001
            pass
    return log


def _selftest() -> int:
    """无头自检:用实际模型处理一张合成图,验证推理链路与模型可用性。

    顺带验证 multiprocessing.Pool 在 frozen 环境可用(视频处理的关键依赖)。
    """
    import tempfile
    import numpy as np

    try:
        from bgremover.core import matting, model_store

        mp = model_store.resolve_model_path()
        if not mp.exists() or mp.stat().st_size < 1_000_000:
            print(f"FAIL: 模型不可用: {mp}")
            return 1
        matting.init_worker(str(mp))
        img = np.zeros((256, 256, 3), dtype=np.uint8)
        img[:, :] = (0, 0, 200)
        import cv2
        cv2.circle(img, (128, 128), 60, (255, 255, 255), -1)
        rgba, alpha = matting.remove_bg(img, "auto")
        center = int(alpha[128, 128])
        corner = int(alpha[5, 5])
        ok = center > 200 and corner < 50
        print(f"selftest: center_alpha={center} corner_alpha={corner} -> {'OK' if ok else 'FAIL'}")

        # 顺带验证 multiprocessing(视频管线依赖)
        from multiprocessing import Pool
        frames = [np.zeros((128, 128, 3), dtype=np.uint8) for _ in range(2)]
        with Pool(processes=2, initializer=matting.init_worker, initargs=(str(mp),)) as pool:
            results = pool.starmap(matting.remove_bg,
                                   [(f, "auto", 0, None) for f in frames])
        ok_mp = len(results) == 2 and results[0][1].shape == (128, 128)
        print(f"selftest multiprocessing: {'OK' if ok_mp else 'FAIL'}")

        # 顺带验证 ffmpeg 探测与编码器自检(视频管线依赖)
        try:
            import tempfile, os as _os
            from bgremover.core import ffmpeg_tool as ff
            ffp = ff.locate_ffmpeg()
            enc = ff.check_encoders(ffp)
            print(f"selftest ffmpeg: {ffp} encoders={enc}")
            ok_ff = all(enc.values())
            # 用合成的 1 秒视频验证 probe_video(用户报错场景)
            tmp = tempfile.mkdtemp()
            test_mp4 = _os.path.join(tmp, "t.mp4")
            vw = cv2.VideoWriter(test_mp4, cv2.VideoWriter_fourcc(*"mp4v"), 10, (64, 64))
            for _ in range(10):
                vw.write(np.zeros((64, 64, 3), dtype=np.uint8))
            vw.release()
            meta = ff.probe_video(ffp, test_mp4)
            print(f"selftest probe_video: {meta['width']}x{meta['height']} {meta['fps']:.0f}fps")
            ok_ff = ok_ff and meta["frames"] == 10
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception as e:  # noqa: BLE001
            print(f"selftest ffmpeg FAIL: {e!r}")
            ok_ff = False
        print(f"selftest ffmpeg: {'OK' if ok_ff else 'FAIL'}")

        # 验证 _resolve_provider 纯函数 4 平台分支(Windows 上即可验证 Mac 逻辑)
        ok_prov = True
        try:
            from bgremover.core import rvm as _rvm
            cases = [
                # (platform, avail, prefer_gpu, expected)
                ("win32", ["DmlExecutionProvider", "CPUExecutionProvider"], True,
                 ["DmlExecutionProvider", "CPUExecutionProvider"]),
                ("win32", ["CPUExecutionProvider"], True, ["CPUExecutionProvider"]),
                ("darwin", ["CoreMLExecutionProvider", "CPUExecutionProvider"], True,
                 ["CoreMLExecutionProvider", "CPUExecutionProvider"]),
                ("darwin", ["CPUExecutionProvider"], True, ["CPUExecutionProvider"]),
                ("linux", ["CPUExecutionProvider"], True, ["CPUExecutionProvider"]),
                ("win32", ["DmlExecutionProvider", "CPUExecutionProvider"], False,
                 ["CPUExecutionProvider"]),
            ]
            for plat, avail, gpu, exp in cases:
                got = _rvm._resolve_provider(plat, avail, gpu)
                if got != exp:
                    ok_prov = False
                    print(f"selftest provider branch FAIL: {plat}/{avail}/{gpu} -> {got} (exp {exp})")
            print(f"selftest provider branches: {'OK' if ok_prov else 'FAIL'}")
        except Exception as e:  # noqa: BLE001
            print(f"selftest provider branches FAIL: {e!r}")
            ok_prov = False

        # 顺带验证 RVM 视频模型推理链路(CPU 兜底,避免 GPU 环境差异)
        try:
            from bgremover.core import rvm
            mp_video = model_store.resolve_model_path("video")
            if not mp_video.exists() or mp_video.stat().st_size < 1_000_000:
                print(f"FAIL: 视频模型不可用: {mp_video}")
                return 1
            sess = rvm.build_session(str(mp_video), prefer_gpu=False)
            h, w = 128, 128
            rgb = np.random.rand(h, w, 3).astype(np.float32)
            states = rvm.initial_states(sess, h, w)
            fgr, pha, states2 = rvm.infer(sess, rgb, states)
            ok_rvm = (fgr.shape == (3, h, w) and pha.shape == (1, h, w)
                      and np.isfinite(fgr).all() and np.isfinite(pha).all()
                      and len(states2) == len(states))
            backend = rvm.video_backend()
            print(f"selftest RVM: backend={backend} fgr={fgr.shape} pha={pha.shape} -> {'OK' if ok_rvm else 'FAIL'}")
        except Exception as e:  # noqa: BLE001
            print(f"selftest RVM FAIL: {e!r}")
            ok_rvm = False

        return 0 if (ok and ok_mp and ok_ff and ok_prov and ok_rvm) else 1
    except Exception as e:  # noqa: BLE001
        print(f"FAIL: {e}")
        return 1


def main() -> int:
    # 打包(frozen)环境下 multiprocessing 需要此调用,否则 Pool 子进程无法启动。
    # Windows 与 macOS .app 均用 spawn 启动子进程,须无条件调用(非 frozen 是 no-op)。
    import multiprocessing

    multiprocessing.freeze_support()

    log = setup_logging()

    if "--selftest" in sys.argv:
        return _selftest()

    def excepthook(exc_type, exc, tb):
        log.critical("未捕获异常", exc_info=(exc_type, exc, tb))

    sys.excepthook = excepthook

    # 打包场景:把内置模型复制到用户数据目录,开箱即用且可后续替换
    try:
        from bgremover.core import model_store
        for purpose in ("image", "video"):
            model_store.ensure_model_bundled_copy(purpose)
    except Exception:  # noqa: BLE001
        log.warning("内置模型初始化失败,回退下载", exc_info=True)

    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("bgremover")

    from bgremover.ui.main_window import MainWindow
    win = MainWindow()
    win.show()
    return app.exec()
