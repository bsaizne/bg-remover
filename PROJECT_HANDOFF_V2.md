# AI 智能抠图 / 视频背景移除桌面软件 — 完整项目交接文档

> **用途**:复制到新的 Claude 对话中,让新对话无缝继续开发。
> **项目路径**:`D:\claudework\bg-remover`
> **更新日期**:2026-08-07
> **Git 仓库**:https://github.com/bsaizne/bg-remover(已推送,含 CI)
> **CI 状态**:macOS arm64 构建成功(artifact: AI抠图-arm64, 379MB);x86_64 排队中

---

## 1. 项目概述

跨平台(Windows/macOS)桌面应用,用 onnxruntime 推理 AI 模型自动移除图片与视频背景。支持批量处理、透明导出、背景替换、实时预览、光流帧间平滑、错误恢复与日志排错。

**用户机器配置**:R5 5600 + RX 6750 GRE(12GB),Windows 视频推理用 DirectML GPU。
**用户目标**:发给别人用的打包桌面版;Mac 版通过 CI 构建。

---

## 2. 已完成功能 ✅

### 图片处理
- 批量导入(jpg/jpeg/png/webp/bmp/tif/tiff/gif),拖拽/文件夹递归收集
- 批量抠图→透明 PNG(4 通道 RGBA),背景替换(纯色/图片)
- 棋盘格透明预览(原图/结果切换)
- 并行处理(multiprocessing.Pool,进程数按平台+内存自适应:Windows 核数/2 封顶 4,Mac 固定 2)

### 视频处理
- 导入(mp4/mov/avi/mkv/webm/flv),元信息(分辨率/帧率/时长/大小/有无音频)
- **RVM**(RobustVideoMatting, mobilenetv3)时序循环逐帧抠图,天然连贯
- **GPU 加速(平台化)**:Windows→DML, Mac→CoreML, 其他→CPU;多厂商兼容,无 GPU 自动回退
- 双管道直通(ffmpeg 解码 rawvideo → RVM 推理 → ffmpeg 编码),无中间文件
- 输出:透明 MOV(ProRes 4444+Alpha)、透明 WebM(VP9+Alpha)、背景 MP4(H.264)、PNG 帧序列
- 音频:默认保留,可去除
- 双层进度(帧+总任务)+ EMA 预估剩余时间,暂停/继续/取消
- **实时背景预览**:处理时每 5 帧更新抠像结果到 TransparentPreview
- **光流帧间传播**:仅平滑边缘过渡带(alpha 0.05~0.95),主体/背景完全保留,减少 RVM 闪烁
- **错误帧恢复**:解码中断用最后有效帧补齐,不白跑
- **失败自动重试**:最多 2 次重试(共 3 次尝试)
- 批量视频排队串行(一个完成自动下一个)

### 通用功能
- 明暗主题切换、设置持久化(JSON,跨平台路径)
- 双模型首启自动下载(isnet ~170MB + RVM ~15MB,多源断点续传)
- **日志系统**:app.log(全量) + error.log(仅 ERROR+),日志头含环境摘要
- **失败弹窗**:模态对话框(摘要+明细+「打开日志目录」「导出日志」按钮)
- **导出日志**:一键复制 app.log+error.log 到指定目录
- **工具栏**:导入/开始/暂停/取消/主题/设置/日志/导出日志
- PyInstaller 打包(onedir+zip,内置双模型+ffmpeg,开箱即用)
- `--selftest` 无头自检(isnet/multiprocessing/ffmpeg/RVM/provider 分支)

---

## 3. 未完成功能 ❌

### 待 Mac 真机/CI 验证
- macOS CoreML GPU 加速实际效果(代码已完成,session_timeout 30s 防挂)
- macOS PyInstaller 打包(.app + 代码签名)
- macos-13(x86_64) CI artifact 待出

### P2(后续)
- mask 边缘编辑(交互式腐蚀/膨胀/羽化)
- 代码签名(需付费证书)

### 已砍掉(勿重提)
- 任务队列(多视频并行):与 Mac 统一内存冲突,用户确认不做

---

## 4. 技术栈

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.12.13 | uv 管理 `.venv/` |
| GUI | PySide6 6.11.1 | |
| 图像 | opencv-python-headless 5.0.0.93, numpy 2.5.1, Pillow 12.3.0 | |
| 推理(Windows) | **onnxruntime-directml 1.24.4** | 与 onnxruntime 互斥 |
| 推理(macOS) | **onnxruntime==1.23.0** | 1.24+ 只有 arm64,Intel Mac 必须锁 1.23.0 |
| 视频 | imageio-ffmpeg 0.6.0 | 自带 ffmpeg 7.1(prores_ks/vp9/x264/aac 全可用) |
| 打包 | PyInstaller 6.21.0 | |
| 其他 | requests 2.34.2, psutil 7.2.2 | |

### 模型
- 图片:`isnet-general-use.onnx`(178MB)
- 视频:`rvm_mobilenetv3_fp32.onnx`(15MB)
- 位置:`%LOCALAPPDATA%\bgremover\models\`(Win) / `~/Library/Application Support/bgremover/models/`(Mac)

---

## 5. 目录结构

```
D:\claudework\bg-remover\
├─ pyproject.toml           # 平台标记依赖:win→directml, darwin→onnxruntime==1.23.0
├─ .python-version          # 3.12
├─ README.md                # 用户文档(已更新到最新)
├─ WINDOWS_BUILD.md         # Windows 构建/打包/排错基线
├─ PROJECT_HANDOFF.md       # 本交接文档(v1, 已过时)
├─ bgremover.spec           # PyInstaller spec(平台分支:upx/Win vs Mac,ffmpeg 定位)
├─ make_zip.py              # zip 打包(产出名按平台+架构:AI抠图-{win64|mac}-{x86_64|arm64}.zip)
├─ .github/workflows/mac_build.yml  # CI(macos-14 arm64 + macos-13 x86_64)
├─ .gitignore
├─ _backup_*/               # 历代改动备份(参考用)
├─ _test_videos/            # 测试视频
├─ .venv/                   # uv 虚拟环境
├─ dist/                    # 打包输出
└─ src/bgremover/
   ├─ __init__.py           # 版本号
   ├─ __main__.py           # 入口
   ├─ app.py                # 装配+selftest+setup_logging
   ├─ core/                 # 无 Qt 依赖
   │  ├─ config.py          # AppConfig + 跨平台数据目录
   │  ├─ model_store.py     # 双模型下载/管理
   │  ├─ matting.py         # ISNet 图片推理(CPU)
   │  ├─ rvm.py             # RVM 视频推理(平台化 GPU + 光流融合)
   │  ├─ ffmpeg_tool.py     # ffmpeg 定位/探测/命令生成
   │  ├─ video_pipeline.py  # 视频解码→推理→编码(错误恢复+光流+预览)
   │  ├─ image_pipeline.py  # 批量图片调度(内存自适应)
   │  └─ util.py            # 棋盘格/格式化/ETA/环境信息
   ├─ workers/              # QThread 层
   │  ├─ signals.py         # ProgressPayload + WorkerSignals
   │  ├─ base_worker.py     # 三态状态机
   │  ├─ image_worker.py    # 图片批处理线程
   │  ├─ video_worker.py    # 视频处理线程(自动重试)
   │  └─ download_worker.py # 模型下载线程
   └─ ui/                   # 界面层
      ├─ main_window.py     # 主窗口/工具栏
      ├─ image_tab.py       # 图片页
      ├─ video_tab.py       # 视频页(实时预览)
      ├─ dialogs.py         # 错误对话框 + 导出日志
      ├─ preview.py         # 棋盘格预览组件
      ├─ settings.py        # 设置对话框
      └─ theme.py           # 明暗主题 QSS
```

**分层硬约束**:`core` 不 import PySide6;`workers` 只做起停与信号转发;`ui` 不碰 onnxruntime/ffmpeg。

---

## 6. 文件作用详表

| 文件 | 作用 |
|------|------|
| `pyproject.toml` | 平台标记依赖:Windows→onnxruntime-directml, Mac→onnxruntime==1.23.0 |
| `bgremover.spec` | PyInstaller spec,平台分支:upx(Win True/Mac False),ffmpeg(Win imageio-ffmpeg/Mac brew),onnxruntime DLL(Win 收集/Mac 跳过) |
| `make_zip.py` | 压缩 onedir 为 zip,文件名按平台+架构自动分(如 AI抠图-mac-arm64.zip) |
| `WINDOWS_BUILD.md` | Windows 打包基线(命令/排错/差异对照) |
| `.github/workflows/mac_build.yml` | CI:macos-14+macos-13,先下载模型再 selftest,PyInstaller 打包,上传 artifact |
| `app.py` | freeze_support 无条件调用;setup_logging(app.log+error.log+环境头);--selftest(含 provider 分支断言段);全局异常钩子 |
| `core/config.py` | AppConfig dataclass;跨平台数据目录(win32→%LOCALAPPDATA%,darwin→~/Library/Application Support,XDG) |
| `core/model_store.py` | 双模型槽位(image/video),download 断点续传;ensure_model_bundled_copy |
| `core/matting.py` | ISNet:resize 1024 + /255→推理→sigmoid→与 RGB 合成 RGBA;init_worker 显式 CPU providers |
| `core/rvm.py` | RVM:平台化 provider(Win DML/Mac CoreML/CPU);build_session(GPU 失败降级+session_timeout);infer 状态循环;compose_rgba/bgra/rgb;warp_blend_pha(边缘光流融合) |
| `core/ffmpeg_tool.py` | locate_ffmpeg(用户>打包内置>imageio-ffmpeg>PATH,按 os.name 门控 .exe);check_encoders;probe_video(ffmpeg -i 正则,无 ffprobe);build_read_cmd/audio_cmd/encode_cmd |
| `core/video_pipeline.py` | _Reader/_Writer 双线程;pause/cancel Event;RVM 顺序推理;is_recovery 标志位;错误帧恢复(recovered_frames);光流融合(warp_blend_pha,仅正常帧);实时预览(每5帧 progress_cb 带 preview_rgba) |
| `core/image_pipeline.py` | ImagePipeline:并行/串行;模块级 _worker_one(Avoid Win pickle);_default_workers 内存自适应 |
| `core/util.py` | checkerboard_bgr;format_bytes/duration;ETAEstimator(EMA);collect_env_info(日志头,onnxruntime 延迟 import) |
| `workers/signals.py` | ProgressPayload(含 preview_rgba/preview_w/preview_h);WorkerSignals(progress/finished/failed/log/status) |
| `workers/base_worker.py` | QThread 三态;_pause_event 初始 set()(修复默认暂停 bug) |
| `workers/image_worker.py` | 图片批处理(log.exception) |
| `workers/video_worker.py` | 视频处理(probe 宽高;max_retries=2;preview callback;log.exception) |
| `workers/download_worker.py` | 模型下载(多个 purposes;log.exception) |
| `ui/main_window.py` | 工具栏(导入/开始/暂停/取消/主题/日志/导出日志/设置);ModelBanner;总进度 |
| `ui/image_tab.py` | 图片页(失败弹窗聚合:failed 清单限8条;_on_failed 弹 traceback) |
| `ui/video_tab.py` | 视频页(后端 label 中性化;TransparentPreview 实时更新;_on_progress 解码 preview_rgba→np.frombuffer→show_rgba) |
| `ui/dialogs.py` | show_error_dialog(打开日志/导出日志/确定);export_logs_dialog(选目录→复制 app.log+error.log) |
| `ui/preview.py` | TransparentPreview(QGraphicsView+QPainter.RenderHint,棋盘格背景) |
| `ui/settings.py` | 设置对话框 |
| `ui/theme.py` | 明暗 QSS |

---

## 7. 数据模型

### AppConfig
```python
@dataclass
class AppConfig:
    theme: str = "dark"
    output_dir: str = ""
    last_image_format: str = "png"
    last_video_format: str = "mov"
    max_resolution: int = 1280
    keep_audio: bool = True
    bg_color: str = "#00ff00"
    bg_image: str = ""
    norm_mode: str = "auto"
    frame_step: int = 1        # 遗留
    export_png_sequence: bool = False
```

### 模型槽位
```python
MODELS = {
    "image": {"name": "isnet-general-use.onnx", "sources": [...], "min_size": 1_000_000},
    "video": {"name": "rvm_mobilenetv3_fp32.onnx", "sources": [...], "min_size": 1_000_000},
}
```

### VideoTaskResult
```python
@dataclass
class VideoTaskResult:
    src: str; out: str; ok: bool; error: str
    frames_done: int; frames_total: int; cancelled: bool
    recovered_frames: int = 0   # 错误帧恢复计数
```

### ProgressPayload
```python
class ProgressPayload:
    done, total, eta, frames_done, frames_total, task_done, task_total
    preview_rgba: bytes | None   # 实时预览 RGBA raw bytes
    preview_w, preview_h: int    # 预览宽高
```

### 视频元数据(probe_video)
```python
{"width", "height", "fps", "duration", "frames", "has_audio", "size_bytes"}
```

### RVM IO 约定
```
输入: src(1,3,H,W) RGB float32 /255, r1i..r4i(初始(1,1,1,1)全零), downsample_ratio(0.25)
输出: fgr(1,3,H,W)前景[0,1], pha(1,1,H,W)matte[0,1], r1o..r4o(16/20/40/64通道)
合成: out = fgr*pha + bg*(1-pha)
```

---

## 8. 核心业务逻辑

### 8.1 ISNet 图片抠图(matting.py)
```
BGR → resize 1024×1024 → /255 → [1,3,1024,1024] float32
→ onnxruntime(CPUExecutionProvider) → y[0,0] → sigmoid(if min<0) → clip[0,1]
→ resize 原尺寸 → ×255 → 合成 RGBA
```
**必须 CPU providers**:directml 包下多进程 Pool 若走 GPU 显存爆炸。

### 8.2 视频管线(video_pipeline.py)
```
ffmpeg 解码(rawvideo,rgb24) → _Reader 线程 → 主循环:
  raw→reshape→/255→rvm.infer(session,rgb,states)→更新 states
  → compose_rgba(mov/webm)/compose_rgb(mp4_bg)/compose_bgra(png)
  → wbuf→_Writer 线程→ffmpeg 编码+mux
```
**单进程顺序**:RVM ConvGRU 须逐帧回传状态;DML GPU 单进程独占;Session 不可 pickle。

### 8.3 合成字节序(极易出错)
- mov/webm → **compose_rgba(RGBA)**,编码器 `-pix_fmt rgba`
- mp4_bg → **compose_rgb(RGB)**,编码器 `-pix_fmt rgb24`
- png_seq → **compose_bgra(BGRA)**,cv2.imwrite
- 内部 float[0,1]×255 转 uint8(不乘就全黑)

### 8.4 光流帧间传播(rvm.warp_blend_pha)
- 仅平滑 alpha 过渡带(0.05~0.95):主体/背景完全保留当前帧
- Farneback:灰度→calcOpticalFlowFarneback→remap warp→加权融合(当前70%+上一帧 warp30%)
- 恢复帧(is_recovery=True)跳过光流,清空参考
- 尺寸不匹配/last_pha=None/异常均直通

### 8.5 错误帧恢复(video_pipeline.py)
- `is_recovery` 标志位:坏帧/EOF 填充分支置 True
- `last_rgb` 缓存:深拷贝 `.copy()`,恢复帧复用
- 恢复帧清空 `last_pha_blend`/`last_rgb_flow` 防乱 warp

### 8.6 已踩坑(必读)
1. **BaseWorker._pause_event 初始 .set()**:否则 video 首次 wait 永久卡死
2. **RVM fgr/pha→uint8 必须 ×255**:否则前景全黑
3. **合成字节序**:见 8.3,RGBA/RGB/BGRA 搞错红蓝反转
4. **Win multiprocessing 不能 pickle 闭包**:worker 函数模块级
5. **imageio-ffmpeg 无 ffprobe**:ffmpeg -i stderr 正则解析
6. **PySide6 枚举**:`QPainter.RenderHint` 不用 `Qt.RenderHint`;`QSizePolicy.Expanding` 不用 `.Expanding`
7. **directml 与 onnxruntime 互斥**:不能共存
8. **图片 ISNet 必须 CPU providers**:两处(matting.init_worker + model_store.get_session)
9. **RVM 初始状态 (1,1,1,1)**:不按分辨率推算
10. **QImage bytes→QPixmap 需 .copy()**:PySide6 生命周期
11. **cancel_event 可能 None**:`cancel_event.is_set()` 前检查 `cancel_event is not None`
12. **numpy 数组不能用于 if 条件**:`if last_pha_blend:`→用 `if last_pha_blend is not None:`
13. **ghproxy 下载慢**:curl 多连接并发分片

---

## 9. 下一步计划

| 优先级 | 项目 | 说明 |
|--------|------|------|
| 最高 | **Mac CI x86_64 artifact** | macos-13 排队中,推 fail-fast:false 后应出 |
| 高 | **Mac 真机验证** | CoreML 实际加速效果、frozen .app 多进程 |
| 中 | mask 边缘编辑 | 交互式腐蚀/膨胀/羽化滑块,UI 复杂度最大 |
| 低 | 代码签名 | 需付费证书(Windows+Mac) |
| 不做 | 多视频并行 | 已砍,参见第 8.8 节 |

---

## 10. 开发注意事项

### 环境
- Python `.venv`(3.12),命令带 `PYTHONPATH=src`
- **绝对路径**:`D:\claudework\bg-remover\.venv\Scripts\python.exe`
- uv:`D:\uv\uv-x86_64-pc-windows-msvc\uv.exe`
- 本机 github.com 直连 403→下载走 ghproxy.net
- 打包前关 AI抠图.exe + 播放器(否则 PermissionError)

### 验证命令
```bash
cd /d/claudework/bg-remover
PYTHONPATH=src .venv/Scripts/python.exe -c "import sys; sys.argv=['x','--selftest']; from bgremover.app import _selftest; sys.exit(_selftest())"
# 期望全绿,backend=DirectML GPU
```

### 打包
```bash
taskkill //F //IM "AI抠图.exe"
.venv\Scripts\pyinstaller.exe --noconfirm --clean bgremover.spec
PYTHONPATH=src .venv/Scripts/python.exe make_zip.py
```

### 性能基准(R5 5600+6750 GRE)
| 场景 | 耗时 |
|------|------|
| ISNet 单帧(CPU 1024) | ~1.8s |
| RVM 单帧(CPU 1280×720) | ~0.1s |
| RVM 单帧(DML GPU 1280×720) | ~0.07s |
| 72帧视频 mov_alpha | ~4.3s |

### Mac 差异
| 维度 | Windows | macOS |
|------|---------|-------|
| onnxruntime | directml 1.24.4 | **1.23.0**(1.24+只有arm64) |
| 视频 GPU | DirectML | CoreML(动态shape支持有限,需降级) |
| 图片 Pool | 核数/2 封顶4 | **固定2**(统一内存) |
| 数据目录 | %LOCALAPPDATA%\bgremover | ~/Library/Application Support/bgremover |
| spec upx | True | **False** |
| ffmpeg | imageio-ffmpeg 自带 | brew install ffmpeg |
| CI artifact | 当前无 automate | macos-14 arm64 ✅ 379MB |

### 项目状态(2026-08-07 对话结束点)
- GitHub 仓库:https://github.com/bsaizne/bg-remover(35 files, 5 commits)
- 本地 1 个 commit 未推送(fail-fast:false, commit 1866ac7)
- CI #8:macos-14 arm64 success(artifact AI抠图-arm64 379MB), macos-13 排队中
- Windows dist:旧版 P0 产物被删除,新打包未重做(源码全链路 selftest 通过)
- 备份:`_backup_final_/` 含本轮最终源码+README
