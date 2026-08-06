# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec:AI 智能抠图桌面版(onedir,含模型与 ffmpeg)。"""

# ===== Windows 打包关键配置快照(勿删;Mac/CI 改动时参照 WINDOWS_BUILD.md 核对)=====
# console=False(GUI) | upx=True | datas: models/ + ffmpeg/ | binaries: onnxruntime/
# onnxruntime-directml 的 DLL 通过 binaries=(_ort_dir, "onnxruntime") 显式进包
# Mac 打包需:upx=False、BUNDLE/INFO.plist、代码签名、依赖 onnxruntime==1.23.0
# 完整基线见 WINDOWS_BUILD.md
# ============================================================================

import os
import sys as _sys
import shutil
from pathlib import Path

IS_MAC = _sys.platform == "darwin"

# ---- 打包资源定位 ----
# ---- 打包资源定位 ----
SRC_ROOT = Path(os.path.abspath(SPECPATH))
VENV = Path(os.environ.get("VIRTUAL_ENV", SRC_ROOT / ".venv"))

# 模型:用 config 模块定位用户数据目录
import sys as _sys2
_sys2.path.insert(0, str(SRC_ROOT / "src"))
from bgremover.core.config import models_dir  # noqa: E402
from bgremover.core import model_store  # noqa: E402

model_file = models_dir() / "isnet-general-use.onnx"
if not model_file.exists():
    raise SystemExit(
        f"图片模型未找到: {model_file}\n请先运行 `python -m bgremover` 完成首次模型下载后再打包。")

video_model_file = model_store.model_path("video")
if not video_model_file.exists():
    raise SystemExit(
        f"视频模型未找到: {video_model_file}\n请先运行 `python -m bgremover` 完成首次模型下载后再打包。")

# ffmpeg 二进制:Mac CI 用 brew 安装,Windows 用 imageio-ffmpeg 自带
if IS_MAC:
    import subprocess
    result = subprocess.run(["brew", "--prefix", "ffmpeg"], capture_output=True, text=True)
    ffmpeg_dir = Path(result.stdout.strip()) / "bin"
    ffmpeg_exe = ffmpeg_dir / "ffmpeg"
    if not ffmpeg_exe.exists():
        ffmpeg_exe = Path("/opt/homebrew/bin/ffmpeg")  # Apple Silicon
    if not ffmpeg_exe.exists():
        ffmpeg_exe = Path("/usr/local/bin/ffmpeg")     # Intel
else:
    try:
        import imageio_ffmpeg
        ffmpeg_exe = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"找不到 ffmpeg 二进制: {e}")

# 资源目标布局(onedir):放到 _internal/ 下
datas = [
    (str(model_file), "models"),              # 图片模型 isnet -> _internal/models/
    (str(video_model_file), "models"),        # 视频模型 RVM -> _internal/models/
    (str(ffmpeg_exe), "ffmpeg"),              # ffmpeg -> _internal/ffmpeg/
]

# onnxruntime 原生 DLL:Windows 用 directml,Mac 用标准包(版本 1.23.0)
binaries = []
if not IS_MAC:
    try:
        import onnxruntime as _ort
        _ort_dir = os.path.dirname(_ort.__file__)
        if os.path.isdir(_ort_dir):
            binaries.append((_ort_dir, "onnxruntime"))
    except Exception as _e:  # noqa: BLE001
        print(f"警告: 无法收集 onnxruntime 原生库: {_e}")

# 需要显式收集的原生/隐式依赖
hiddenimports = [
    "onnxruntime",
    "opencv",
    "PIL._tkinter_finder",
    "imageio_ffmpeg",
]

a = Analysis(
    [str(SRC_ROOT / "src" / "bgremover" / "__main__.py")],
    pathex=[str(SRC_ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="AI抠图",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False if IS_MAC else True,
    console=False,          # GUI,不弹控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False if IS_MAC else True,
    upx_exclude=[],
    name="AI抠图",
)
