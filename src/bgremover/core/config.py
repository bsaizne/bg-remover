"""配置持久化与数据目录解析。

core 层不依赖 Qt,但 QSettings 是 Qt 组件,故此处用平台无关的 JSON 文件持久化,
避免在 core 引入 PySide6(子进程无法安全 import Qt)。
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

APP_NAME = "bgremover"
APP_VERSION = "0.1.0"


def data_dir() -> Path:
    """跨平台应用数据目录(模型/临时/日志/输出)。"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData/Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local/share")
    d = Path(base) / APP_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def models_dir() -> Path:
    d = data_dir() / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def logs_dir() -> Path:
    d = data_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def tmp_dir() -> Path:
    d = data_dir() / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_file() -> Path:
    return data_dir() / "settings.json"


@dataclass
class AppConfig:
    """应用设置。MVP 字段:主题、输出目录、默认导出格式、分辨率限制、音频、模型归一化。"""

    theme: str = "dark"  # dark / light
    output_dir: str = ""  # 空 => 每次询问,否则默认输出目录
    last_image_format: str = "png"  # png / 背景合成
    last_video_format: str = "mov"  # mov_alpha / webm_alpha / mp4_bg
    max_resolution: int = 1280  # 视频长边限制,默认 1280px
    keep_audio: bool = True
    bg_color: str = "#00ff00"  # 替换背景纯色(默认绿幕)
    bg_image: str = ""  # 替换背景图片路径(空=纯色)
    norm_mode: str = "auto"  # 模型归一化模式: auto / 255 / imagenet
    frame_step: int = 1  # 视频跳帧:每 N 帧处理一帧,其余复用前帧(1=不跳帧)
    export_png_sequence: bool = False  # 调试:同时导出 PNG 帧序列

    @classmethod
    def load(cls) -> "AppConfig":
        cfg = cls()
        p = config_file()
        try:
            if p.exists():
                data = json.loads(p.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(cfg, k):
                        setattr(cfg, k, v)
        except Exception:
            pass
        return cfg

    def save(self) -> None:
        try:
            config_file().write_text(
                json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
