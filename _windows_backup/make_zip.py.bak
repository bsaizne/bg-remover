# -*- coding: utf-8 -*-
"""把 PyInstaller 的 onedir 输出压缩为可分发的 zip(文件名按平台自动分)。"""
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist" / "AI抠图"

_PLATFORM = {"win32": "win64", "darwin": "mac"}.get(sys.platform, sys.platform)
_ARCH = {"AMD64": "x86_64", "arm64": "arm64"}.get(
    __import__("platform").machine(), "unknown")
ZIP = ROOT / "dist" / f"AI抠图-{_PLATFORM}-{_ARCH}.zip"


def make_zip() -> None:
    if not DIST.exists():
        raise SystemExit(f"找不到打包输出: {DIST},请先运行 pyinstaller bgremover.spec")
    if ZIP.exists():
        ZIP.unlink()
    print(f"压缩 {DIST} -> {ZIP}")
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(DIST):
            for f in files:
                full = Path(root) / f
                arc = "AI抠图/" + str(full.relative_to(DIST))
                zf.write(full, arc)
    size_mb = ZIP.stat().st_size / 1048576
    print(f"完成: {ZIP} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    make_zip()
