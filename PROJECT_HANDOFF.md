# AI 智能抠图 / 视频背景移除桌面软件 — 项目交接文档

> 本文件用于将当前开发状态完整交接给新的 Claude 对话,让新对话可以无缝继续开发。
> 项目路径:`D:\claudework\bg-remover`
> 最近更新:2026-08-06(P1.5 日志 + 弹窗 + 稳定性优化已完成;下一步 P2/打包)

---

## 1. 项目概述

跨平台(Windows/macOS/Linux 目标)桌面应用,用 onnxruntime 推理 AI 模型自动移除图片/视频背景。支持批量处理、透明导出(带 Alpha 通道)与背景替换。当前已打包为可分发的 Windows 桌面版(onedir + zip),供他人直接使用。**下一步目标是支持 macOS(用户无 Mac 实体机,靠 CI/代码级验证)**。

**用户机器配置**:R5 5600(6 核 12 线程)+ RX 6750 GRE(AMD GPU,12GB 显存)。开发机上 Windows 视频推理已用 DirectML GPU。

---

## 2. 当前已完成的功能 ✅

### 图片处理
- 批量导入图片(jpg/jpeg/png/webp/bmp/tif/tiff/gif),拖拽/文件夹递归收集
- 批量抠图:输出透明 PNG(4 通道 RGBA)
- 背景替换:纯色或图片背景(自动缩放适配)
- 棋盘格透明预览(原图/结果切换)
- 并行处理(multiprocessing.Pool,默认 4 进程,**固定 CPU**)

### 视频处理(P0:已从 isnet 换成 RVM + DirectML GPU)
- 导入视频(mp4/mov/avi/mkv/webm/flv),显示元信息(分辨率/帧率/时长/大小/有无音频)
- **RVM(RobustVideoMatting, mobilenetv3)时序循环模型逐帧抠图**,天然连贯无闪烁
- **GPU 加速(平台化)**:Windows 走 DmlExecutionProvider,Mac 走 CoreMLExecutionProvider,其余 CPU;多厂商(NVIDIA/AMD/Intel 独显 + 核显)统一;无 GPU 自动回退 CPU
- 双管道直通(ffmpeg 解码 rawvideo pipe → 顺序推理 → ffmpeg 编码),避免中间 PNG 序列占磁盘
- 输出格式:
  - 透明 MOV(ProRes 4444 + Alpha)
  - 透明 WebM(VP9 + Alpha)
  - 替换背景 MP4(H.264,支持纯色/图片背景)
  - PNG 帧序列(透明)
- 音频:默认保留原始音频,可勾选去除
- **跳帧已移除**(RVM 是循环网络,跳帧会切断时序递归;且 GPU 够快无需跳帧)
- 双层进度(当前视频帧 + 总任务)+ 预估剩余时间(EMA 平滑)
- 暂停/继续/取消(通过 multiprocessing.Event 令牌),取消无残留进程
- 批量视频排队处理(顺序串行,一个完成自动下一个)

### 通用
- 明暗主题切换、设置持久化(%LOCALAPPDATA%\bgremover\settings.json,Mac 为 ~/Library/Application Support/bgremover)
- 双模型首启自动下载(isnet 图片 ~170MB + RVM 视频 ~15MB,多源 + 断点续传)
- 日志系统(RotatingFileHandler,**app.log 全量 + error.log 仅 ERROR+**,日志头含环境摘要)
- **P1.5 错误日志(已完成)**:工具栏「日志」按钮打开日志目录;三个 worker 异常补 log.exception;失败提示带日志路径。见第 9.2 节。
- **失败弹窗(已完成,2026-08-06)**:处理任务失败时弹模态对话框(摘要 + 失败明细 + 「打开日志目录」「导出日志」按钮);批量图片失败聚合为一条(限前 8 条);全成功不弹、下载失败不弹。统一对话框在 `ui/dialogs.py`。
- **稳定性优化(已完成,2026-08-06)**:视频解码损坏帧用最后有效帧填充/补齐(不白跑);视频失败自动重试(最多 2 次);图片 Pool 进程数按平台+内存自适应(Windows 核数/2 封顶 4,Mac 固定 2)。见第 8.6 节。
- GUI offscreen 冒烟测试通过
- **PyInstaller 打包**:onedir + zip,内置双模型 + ffmpeg,开箱即用
- `--selftest` 无头自检:验证 isnet 推理/multiprocessing/ffmpeg 探测/RVM 推理 全链路

---

## 3. 当前未完成的功能 ❌

### 已完成但需 Mac 实机/CI 验证
- **macOS 跨平台支持**(代码级已完成,Windows 验证通过):见第 9 节。Mac 打包/签名/真机加速效果留待 CI 或用户有 Mac 时。

### 已确定方向但未实施
(无 — P1.5 错误日志已并入本次改动完成,见第 9 节。)

### P2(PRD 未做,后续迭代)
- ~~错误帧恢复~~ ✅ 已做(见第 8.6 节,损坏帧填充 + 视频失败自动重试)
- ~~任务队列(并行处理多视频)~~ **已砍掉**:与稳定性冲突(Mac 统一内存成倍占用、RVM 单进程独占 GPU、无真机难排错),用户确认不做
- ~~实时背景预览~~ ✅ 已做(见第 8.7 节,视频处理每 5 帧更新抠像结果到 TransparentPreview)
- ~~光流帧间传播~~ ✅ 已做(见第 8.7 节,`rvm.warp_blend_pha` 边缘过渡带光流平滑,减少闪烁)
- GPU 自动检测切换(已被 DirectML/CoreML 自动检测基本覆盖)
- mask 边缘编辑
- 代码签名(当前 zip 的 exe 未签名,Windows SmartScreen 警告;Mac 未签名会被 Gatekeeper 拦截)

---

## 4. 技术栈

| 组件 | 版本/说明 |
|------|----------|
| Python | 3.12.13(uv 管理,`.venv/`) |
| uv | `D:\uv\uv-x86_64-pc-windows-msvc\uv.exe` |
| GUI | PySide6 6.11.1 |
| 图像处理 | opencv-python-headless 5.0.0.93、numpy 2.5.1、Pillow 12.3.0 |
| 推理 | **onnxruntime-directml 1.24.4**(Windows,含 DmlExecutionProvider;与 onnxruntime 包互斥,模块名同为 onnxruntime) |
| 视频 | imageio-ffmpeg 0.6.0(自带 ffmpeg 7.1 静态二进制,83MB) |
| 打包 | PyInstaller 6.21.0 |
| 其他 | requests 2.34.2、psutil 7.2.2 |

**关键结论**:
- imageio-ffmpeg 自带 ffmpeg 编译了 prores_ks / libvpx-vp9 / libx264 / aac / libopus,全部编码器可用。无系统 ffmpeg/ffprobe,全走自带二进制。
- Windows 上 onnxruntime-directml 提供 `import onnxruntime`(providers 含 DmlExecutionProvider + CPUExecutionProvider)。
- **macOS 依赖(下次改动)**:标准 `onnxruntime` 的 mac wheel 内置 `CoreMLExecutionProvider`,**不要引入已停更的 onnxruntime-coreml(1.13.1 仅 cp39)**。**onnxruntime 1.24+ 只有 arm64 wheel,Intel Mac 必须锁 `onnxruntime==1.23.0`**(同时提供 arm64 + x86_64)。

### 模型
- 图片:`isnet-general-use.onnx`(178MB, %LOCALAPPDATA%\bgremover\models\)
- 视频:`rvm_mobilenetv3_fp32.onnx`(15MB, 同上)

---

## 5. 目录结构

```
D:\claudework\bg-remover\
├─ pyproject.toml           # 依赖声明(Windows: onnxruntime-directml)
├─ .python-version          # 3.12
├─ README.md                # 用户文档
├─ bgremover.spec           # PyInstaller 打包配置(内置双模型 + DirectML DLL)
├─ make_zip.py              # dist 目录压缩为 zip(产出名写死 AI抠图-win64.zip)
├─ PROJECT_HANDOFF.md       # 本交接文档
├─ _backup_p0_/             # P0 改动前的备份(src/spec/pyproject)
├─ _backup_mac_/            # Mac 跨平台改动前的备份(src/pyproject/spec/make_zip)
├─ _backup_logging_/        # P1.5 错误日志改动前的备份(src)
├─ _backup_dialog_/         # 失败弹窗改动前的备份(src)
├─ _backup_stability_/      # 稳定性优化改动前的备份(src)
├─ _test_videos/            # 测试视频(test_input.mp4 等)
├─ .venv/                   # uv 虚拟环境
├─ src/bgremover/
│  ├─ __main__.py           # python -m bgremover 入口
│  ├─ app.py                # QApplication 装配 + 全局异常钩子 + --selftest + setup_logging
│  ├─ core/                 # 无 Qt 依赖(可被子进程 import、独立测试)
│  │  ├─ config.py          # 配置持久化 + 数据目录解析(win32/darwin/xdg)
│  │  ├─ model_store.py     # 双模型槽位(image/video)、下载多源断点续传、内置模型复制
│  │  ├─ matting.py         # isnet 推理(图片, CPU, 多进程池)
│  │  ├─ rvm.py             # RVM 推理(视频, 有状态循环, DML/CPU)
│  │  ├─ ffmpeg_tool.py     # ffmpeg 定位/编码器自检/元数据解析/命令生成
│  │  ├─ video_pipeline.py  # 视频「解码→RVM 顺序推理→合成」编排(可暂停/取消)
│  │  ├─ image_pipeline.py  # 批量图片调度
│  │  └─ util.py            # 棋盘格/尺寸格式化/ETA
│  ├─ workers/              # QThread 层
│  │  ├─ signals.py         # 信号集中定义(ProgressPayload)
│  │  ├─ base_worker.py     # QThread 三态状态机(pause/resume/cancel)
│  │  ├─ image_worker.py / video_worker.py / download_worker.py
│  └─ ui/                   # 界面层
│     ├─ main_window.py     # 主窗口/工具栏/模型横幅/总进度
│     ├─ image_tab.py       # 图片页
│     ├─ video_tab.py       # 视频页(后端 label, 无跳帧下拉)
│     ├─ preview.py         # 棋盘格透明预览组件
│     ├─ settings.py        # 设置对话框
│     └─ theme.py           # 明暗主题 QSS
└─ dist/
   ├─ AI抠图/               # onedir 打包输出(~689MB)
   └─ AI抠图-win64.zip      # 分发压缩包(360MB)
```

**分层硬约束**:`core` 不 import PySide6;`workers` 只做起停与信号转发;`ui` 不碰 onnxruntime/ffmpeg。此约束保证 multiprocessing 子进程可安全 import core。

---

## 6. 已创建的所有文件及作用

| 文件 | 作用 |
|------|------|
| `pyproject.toml` | 项目声明 + 依赖列表(平台标记:Windows 用 onnxruntime-directml,Mac 用 onnxruntime==1.23.0) |
| `.python-version` | Python 3.12 |
| `README.md` | 用户使用文档(功能/安装/使用/目录结构/已知限制) |
| `bgremover.spec` | PyInstaller spec:onedir,内置双模型到 `_internal/models/`,ffmpeg 到 `_internal/ffmpeg/`,onnxruntime 原生 DLL 到 `_internal/onnxruntime/`(Mac 打包需 upx=False + BUNDLE/INFO.plist,留 CI) |
| `make_zip.py` | 把 dist/AI抠图 压缩为 AI抠图-win64.zip(产出名需按平台分,留 CI) |
| `src/bgremover/__init__.py` | 版本号 |
| `src/bgremover/__main__.py` | 入口,调 app.main() |
| `src/bgremover/app.py` | QApplication 装配、**`freeze_support()` 无条件调用**、`--selftest` 无头自检(**含 `_resolve_provider` 4 平台断言段**)、`setup_logging()`(**app.log 全量 + error.log 仅 ERROR+ + 日志头环境摘要**)、内置双模型复制 |
| `core/__init__.py` | 空 |
| `core/config.py` | AppConfig dataclass + 跨平台数据目录解析(win32/darwin/XDG,已跨平台) |
| `core/model_store.py` | **双模型槽位**:`MODELS={"image","video"}`,`model_path(purpose)`/`resolve_model_path(purpose)`/`is_model_ready(purpose)`/`ensure_model_bundled_copy(purpose)`/`missing_models()`,`ModelDownloader.download(purpose)` 断点续传。保留 `MODEL_NAME` 别名兼容 |
| `core/matting.py` | isnet 推理:预处理(resize 1024 + /255)、后处理(sigmoid + resize)、`remove_bg()` 原子函数、`init_worker()` Pool initializer(**显式 providers=["CPUExecutionProvider"]**)、`matte_to_bg()` 背景合成、`process_image_file()` |
| `core/rvm.py` | **RVM 推理(核心新增)**:`_resolve_provider` 纯函数(**平台化:win32→DML,darwin→CoreML,其他→CPU**)、`detect_provider`/`video_backend`(**返回 DirectML GPU/CoreML GPU/CPU**)/`build_session`(**GPU 失败自动降级 CPU**)/`initial_states`/`infer`/`compose_rgba`/`compose_bgra`/`compose_rgb`。有状态循环,状态 (1,1,1,1) 初始化逐帧回传 |
| `core/ffmpeg_tool.py` | `locate_ffmpeg()`(用户覆盖 > 打包内置 > imageio-ffmpeg > PATH,`.exe` 已按 os.name 门控)、`check_encoders()`、`probe_video()`(ffmpeg -i stderr 解析,无 ffprobe)、`build_read_cmd`/`build_audio_cmd`/`build_encode_cmd` |
| `core/video_pipeline.py` | **单进程 RVM 顺序推理**(去掉了 Pool/BATCH/跳帧):`_Reader`/`_Writer` 双线程、pause/cancel(Event)、音频抽取、`_kill_tree`(nt 用 taskkill,posix 用 psutil 递归)、**错误帧恢复(解码中断用最后有效帧补齐,recovered_frames 计数)** |
| `core/image_pipeline.py` | 批量图片:并行(模块级 `_worker_one` 避免 Windows pickle 闭包问题)或串行。**进程数 `_default_workers()` 按平台+内存自适应(Windows 核数/2 封顶 4,Mac 固定 2)** |
| `core/util.py` | `checkerboard_bgr`、`format_bytes`、`format_duration`、`ETAEstimator`(累计平均速率 EMA)、**`collect_env_info()`(日志头环境摘要,onnxruntime 延迟 import)** |
| `workers/signals.py` | `WorkerSignals`(progress/finished/failed/log/status)+ `ProgressPayload` |
| `workers/base_worker.py` | QThread 基类,**`_pause_event` 初始 set()**(修复:默认不暂停否则视频处理卡死) |
| `workers/image_worker.py` | 图片批量处理线程(except 用 traceback 拼 failed,**补 log.exception**) |
| `workers/video_worker.py` | 单视频处理线程(`resolve_model_path("video")`,已去 norm_mode/frame_step,**补 log.exception**、**失败自动重试 max_retries=2,结果带 attempts**) |
| `workers/download_worker.py` | 双模型下载线程(支持 purposes 列表,逐个下载,**补 log.exception**) |
| `ui/main_window.py` | 工具栏(导入/开始/暂停/取消/主题/设置/**日志**)、ModelBanner(双模型就绪判断)、QTabWidget、总进度条 |
| `ui/image_tab.py` | 图片页:列表/预览/模式选择/背景选择/控制按钮,**失败弹窗(_on_finished 聚合失败清单 + _on_failed)** |
| `ui/video_tab.py` | 视频页:队列/元信息/输出格式/背景/音频/**后端 label(视频加速: DirectML GPU/CoreML GPU/CPU,已中性化)**、双层进度、暂停取消。跳帧下拉已移除,**失败弹窗(_on_finished else 分支 + _on_failed)** |
| `ui/dialogs.py` | **统一对话框 `show_error_dialog`**(摘要+明细+「打开日志目录」「导出日志」+「确定」)+ **`export_logs_dialog`**(用户选目录,复制 app.log+error.log,带时间戳目录名) |
| `ui/preview.py` | TransparentPreview(QGraphicsView + QPainter.RenderHint,注意 PySide6 枚举坑) |
| `ui/settings.py` | 设置对话框(主题/输出目录/分辨率/音频/归一化/ffmpeg 路径) |
| `ui/theme.py` | 明暗两套 QSS |

---

## 7. 数据模型结构

### AppConfig(core/config.py)
```python
@dataclass
class AppConfig:
    theme: str = "dark"            # dark / light
    output_dir: str = ""           # 空 => 每次询问
    last_image_format: str = "png"
    last_video_format: str = "mov"
    max_resolution: int = 1280     # 视频长边限制
    keep_audio: bool = True
    bg_color: str = "#00ff00"
    bg_image: str = ""
    norm_mode: str = "auto"        # 图片模型归一化
    frame_step: int = 1            # 遗留字段,视频不再使用(兼容旧 settings.json)
    export_png_sequence: bool = False
```
持久化:`%LOCALAPPDATA%\bgremover\settings.json`(Windows)/ `~/Library/Application Support/bgremover/settings.json`(Mac)。

### 模型槽位(core/model_store.py)
```python
MODELS = {
    "image": {"name": "isnet-general-use.onnx", "sources": [4 个 URL], "min_size": 1_000_000},
    "video": {"name": "rvm_mobilenetv3_fp32.onnx", "sources": [ghproxy 主源, github 直连备选], "min_size": 1_000_000},
}
```

### 视频元数据(probe_video 返回 dict)
```python
{"width": int, "height": int, "fps": float, "duration": float,
 "frames": int, "has_audio": bool, "size_bytes": int}
```

### VideoTaskResult(video_pipeline.py)
```python
@dataclass
class VideoTaskResult:
    src: str; out: str; ok: bool; error: str
    frames_done: int; frames_total: int; cancelled: bool
```

### 信号负载(ProgressPayload, workers/signals.py)
```python
class ProgressPayload:
    done, total, eta, frames_done, frames_total, task_done, task_total
```

### RVM IO 约定(rvm.py, 已踩坑确认)
```
输入: src(1,3,H,W) RGB float32 /255 归一化、r1i..r4i(循环状态,初始 (1,1,1,1) 全零)、downsample_ratio([1] float32 = 0.25)
输出: fgr(1,3,H,W) 前景 RGB [0,1]、pha(1,1,H,W) matte [0,1]、r1o..r4o(16/20/40/64 通道,空间维随帧自适应)
合成: out = fgr*pha + bg*(1-pha)
```

---

## 8. 已实现的重要业务逻辑

### 8.1 isnet 图片抠图链(matting.py)
```
BGR 图 → cv2.resize 到 1024×1024 → /255 归一化 → [1,3,1024,1024] float32
→ onnxruntime 推理(CPUExecutionProvider)→ 取 y[0,0] → 若 min<0 则 sigmoid → clip[0,1]
→ resize 回原尺寸 → ×255 → 与 RGB 合成 RGBA
```
- **显式 providers=["CPUExecutionProvider"]**:换 onnxruntime-directml 包后,图片多进程 Pool 必须锁 CPU,否则每子进程建 GPU session 显存爆炸。
- auto 归一化自检:用方差判别 /255 vs imagenet(isnet 是 /255)。

### 8.2 视频管线(video_pipeline.py,RVM 单进程)
```
ffmpeg#1 解码(rawvideo pipe, rgb24) → _Reader 线程 → 主循环逐帧:
  raw.reshape(ph,pw,3) → /255 → rvm.infer(session, rgb, states) → 更新 states
  → compose_rgba(mov/webm) 或 compose_rgb(mp4_bg) 或 compose_bgra(png_seq)
  → wbuf → _Writer 线程 → ffmpeg#2 编码+mux
```
- **为什么单进程顺序**:RVM 是 ConvGRU 循环网络,必须逐帧回传 rnn 状态;且 DirectML GPU 设备单进程独占、Session 不可跨进程 pickle。视频推理不用 multiprocessing.Pool。
- pause:`pause_event.wait()` 阻塞(读端 + 主循环);cancel:`cancel_event.is_set()` 轮询退出 + `_kill_tree` 杀 ffmpeg 树。
- 编码命令(ffmpeg_tool.build_encode_cmd):
  - 透明 MOV:`prores_ks -profile 4444 -pix_fmt yuva444p10le -alpha_bits 8`,输入 `-pix_fmt rgba`(RGBA 字节序)
  - 透明 WebM:`libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0`
  - MP4 背景:`libx264 -pix_fmt yuv420p`,输入 `-pix_fmt rgb24`(RGB 字节序)
  - PNG 序列:Python 内 cv2.imwrite 逐帧写(BGRA)

### 8.3 RVM 推理关键(rvm.py)
- 初始状态必须是 `(1,1,1,1)` 全零 ×4,不按分辨率推算(否则 Expand_174 报错)。模型内部自适应,输出状态空间维随帧变(如 1280×720/0.25 → r1o (1,16,90,160))。
- 状态名映射:输入 `r1i` → 输出 `r1o`(即 `name[:-1]+"o"` 而非 `name+"o"`)。
- fgr 输出是标准 RGB 顺序(纯红输入 → fgr[0] 高)。
- GPU provider 检测:`detect_provider()` 平台化:Windows 返回 DML 优先列表,Mac 返回 CoreML 优先列表,无则 CPU。

### 8.4 合成字节序(已修,勿重蹈)
- **mov/webm → `compose_rgba`(RGBA)**,编码器 `-pix_fmt rgba`。
- **mp4_bg → `compose_rgb`(RGB)**,编码器 `-pix_fmt rgb24`。
- **png_seq → `compose_bgra`(BGRA)**,cv2.imwrite 需要。
- 三个函数内部都是 float[0,1] 乘 255 转 uint8(不乘会全黑)。

### 8.5 已修的坑(重要,避免重蹈覆辙)
1. **BaseWorker `_pause_event` 初始必须 `.set()`**:multiprocessing.Event() 默认未 set(阻塞),视频处理第一次 `pause_event.wait()` 就永久卡死。原 isnet 版遗留 bug,已修。
2. **RVM fgr/pha float[0,1] 转 uint8 前必须乘 255**:否则前景全黑(alpha 正常,表现为"背景扣了但人变黑")。
3. **合成字节序**:见 8.4,mov/webm 要 RGBA、mp4_bg 要 RGB、PNG 要 BGRA,搞错就红蓝反转。
4. Windows multiprocessing 不能 pickle 嵌套闭包 → worker 函数提为模块级。
5. imageio-ffmpeg 无 ffprobe → 用 `ffmpeg -i` stderr 正则解析。
6. PySide6 枚举坑:`Qt.RenderHint`/`QGraphicsView.RenderHint` 不存在,用 `QPainter.RenderHint`;`spacer.sizePolicy().Expanding` 报错,用 `QSizePolicy.Expanding`。
7. onnxruntime-directml 与 onnxruntime 互斥,不能共存。
8. 图片 isnet 多进程必须显式 CPU providers(directml 包默认会路由到 GPU)。
9. RVM 初始状态 (1,1,1,1),不要按分辨率推算。
10. ghproxy 下载 RVM(15MB)单连接极慢/中断 → 用多连接并发分片(见下)。

### 8.6 稳定性优化(2026-08-06,用户"稳定性优先"确认)
1. **错误帧恢复(video_pipeline.py)**:解码流提前结束(损坏/截断)时,若已有有效帧且未取消,用**最后有效帧补齐剩余帧**,任务照常 ok 输出,不白跑。`VideoTaskResult` 新增 `recovered_frames` 字段记录填充帧数。主循环坏帧分支 + EOF 分支都走填充。**坑**:填充分支判断取消时 `cancel_event` 可能为 None(process 参数可选),必须 `cancel_event is not None and cancel_event.is_set()` 否则 AttributeError。
2. **视频失败自动重试(video_worker.py)**:`VideoWorker` 新增 `max_retries=2`。非取消且失败时自动重试(共 3 次尝试),每次重试重置 `t0`(避免重试进度 ETA 失真),`finished` 结果带 `attempts` 字段。**坑**:重试条件必须 `attempts <= max_retries`(首次尝试算 1,循环条件少等号会只试 2 次)。
3. **图片 Pool 内存自适应(image_pipeline.py)**:`_default_workers()` 替代硬编码 4。Windows:核数//2 封顶 4;Darwin:固定 2(macOS 统一内存,每子进程独立加载 isnet ~178MB,过大易 OOM)。`ImagePipeline.__init__` 的 `n_workers=None` 走默认。

### 8.8 光流融合修复(2026-08-06,用户报"主体抠不出/背景模糊")
1. **`last_pha_blend if last_pha_blend else None` 崩溃 bug(video_pipeline.py)**:`last_pha_blend` 是 numpy 数组,`if array:` 触发 `ValueError: truth value ambiguous`,**视频第 2 帧必崩**,输出文件残缺(表现为"主体抠不出、背景模糊")。已改为 `if last_pha_blend is not None`。
2. **光流融合稀释移动主体 bug(rvm.py `warp_blend_pha`)**:原实现全图融合,移动主体 alpha 被上一帧 warp 稀释(1.0→0.7)。已改为**仅平滑边缘**:用 `edge_mask = (pha[0] > edge_lo) & (pha[0] < edge_hi)`(默认 0.05~0.95)选出过渡带,只对边缘做「当前帧 + 上一帧光流 warp」加权,主体内部/背景完全保留当前帧。
3. **恢复帧判断逻辑重写(video_pipeline.py)**:原用 `recovered == 0 or rgb is not last_rgb` 判断"是否正常帧"(依赖对象身份,脆弱)。改为显式 `is_recovery` 标志位:坏帧/EOF 填充分支置 True,正常帧置 False;恢复帧清空 `last_pha_blend`/`last_rgb_flow` 避免乱 warp。

### 8.7 实时预览 + 光流帧间传播(2026-08-06,最新)

1. **实时预览(无新增参数)**:pipeline 的 `progress_cb` 第 4 个参数为 `preview_rgba: bytes | None`(RGBA raw bytes,每 5 帧一次)。`ProgressPayload` 新增 `preview_rgba/preview_w/preview_h` 字段,worker 端 emit(Qt 跨线程安全),`video_tab._on_progress` 用 `QImage(bytes, w, h, 4*w, RGBA8888)` 零拷贝构造 → `TransparentPreview.show_pixmap` 更新。处理时预览窗实时显示每 5 帧抠像结果。**坑**:QImage 需 `.copy()` 再转 QPixmap(PySide6 生命周期),且 `_on_progress` 在主线程,信号封送 bytes 是线程安全的(规模小,每 5 帧约 1-4MB;若大分辨率需节流更保守)。
2. **光流帧间传播(边缘过渡带平滑)**:`rvm.warp_blend_pha(pha, last_pha, last_rgb, rgb, blend_weight=0.3, edge_lo=0.05, edge_hi=0.95)`。只对 alpha 处于过渡带(0.05-0.95)的像素做 Farneback 光流 warp 后加权融合,主体(alpha≈1)与背景(alpha≈0)完全取当前帧——避免移动物体 alpha 被稀释。恢复帧(内容未变)跳过光流并清掉融合参考。尺寸不匹配/last_pha=None/异常均直通回原始 pha。**实测**:边缘过渡带 mask 均值极低时跳过全图光流计算(无边缘→无意义),性能无损。

### 8.8 已砍掉的方案(勿重提)
- **任务队列(多视频并行)**:用户明确砍掉。原因:Mac 统一内存成倍占用、RVM 单进程独占 GPU、CoreML 并发线程竞争难预测、无 Mac 真机排错难。视频保持串行队列最稳。
- **任务队列(多视频并行)**:用户明确砍掉。原因:Mac 统一内存成倍占用、RVM 单进程独占 GPU、CoreML 并发线程竞争难预测、无 Mac 真机排错难。视频保持串行队列最稳。

---

## 9. 下一步开发计划

### 9.1 macOS 跨平台支持(代码已完成,Windows 验证通过)

**目标**:支持 Intel + Apple Silicon 两种 Mac,视频用 CoreML GPU 加速,图片保留 CPU。用户无 Mac,代码改动已在 Windows 完成并验证。

**关键调研结论(勿推翻)**:
- **不要用 `onnxruntime-coreml` 包**(已停更 1.13.1,仅 cp39,装不上 Python 3.12)。标准 `onnxruntime` 的 macOS wheel 已内置 `CoreMLExecutionProvider`。
- **onnxruntime 1.24+ 只发布 arm64 macOS wheel** → Intel Mac 必须锁 `onnxruntime==1.23.0`(同时提供 arm64 + x86_64 wheel)。
- CoreML EP 对 RVM 的动态 shape / ConvGRU 支持有限(可能部分算子切回 CPU),需失败降级 + Mac 真机验证加速效果。

**改动清单(全部已实施,2026-08-06)**:
1. `core/rvm.py`:
   - ✅ 抽纯函数 `_resolve_provider(platform_name, avail, prefer_gpu)` + 重构 `detect_provider`:Darwin 上 CoreML 优先,Windows 上 DML 优先,其他 CPU。
   - ✅ `video_backend()` 平台化:返回 "DirectML GPU" / "CoreML GPU" / "CPU"。
   - ✅ `build_session` 加 CoreML 失败降级:GPU provider Session 创建失败回退 CPU;成功后 log 实际 provider。
   - ✅ docstring 中性化。
2. `app.py`:
   - ✅ `freeze_support()` 无条件调用(macOS frozen .app 用 spawn 需要;非 frozen 是 no-op)。
   - ✅ `--selftest` 加 `_resolve_provider` 纯函数断言段(6 组用例覆盖 win32/darwin/linux × GPU/CPU 分支)。
3. `ui/video_tab.py`:✅ 后端 label 中性化,去掉硬编码,改为 "{backend} (GPU 自动)"。
4. `pyproject.toml` ✅ 平台标记依赖:
   ```toml
   "onnxruntime-directml; platform_system == 'Windows'",
   "onnxruntime==1.23.0; platform_system == 'Darwin'",
   ```
   (不再写裸 onnxruntime,避免 Windows 双装冲突。Linux 平台不装 onnxruntime——当前无 Linux 计划。)
5. **不改但记录**:`bgremover.spec` Mac 打包需 `upx=False`、BUNDLE/INFO.plist、代码签名;`make_zip.py` 产出名需按平台分。留给 CI 阶段。

**Windows 上已验证**:selftest 全绿(含新断言段,backend=DirectML GPU);`uv pip install -e . --dry-run` 解析成功(21 包);视频链路回归 mov_alpha + mp4_bg 双 PASS;GUI offscreen 冒烟 backend label 中性化无硬编码。

**Mac 实机验证清单**(用户有 Mac 时):install 解析;`ort.get_available_providers()` 含 CoreML;selftest backend=CoreML GPU;真实视频对比 GPU/CPU 帧耗时(若接近则 CoreML 未接管关键算子,看日志 `number of partitions supported by CoreML`);PyInstaller 打包后多进程正常。

### 9.2 P1.5 错误日志功能(已完成,2026-08-06)

**目标**:出现运行时错误时能自动生成日志文件方便查修(尤其 Mac 远程排错)。已实施并验证。

**已确认方案**:
- UI 日志入口:「打开日志目录」按钮(用 `QDesktopServices.openUrl(logs_dir())`,不弹窗)。
- 日志组织:`app.log`(全量)+ `error.log`(仅 ERROR+ 级)+ **日志头环境信息**(版本/系统/CPU)。

**改动清单(全部已实施,2026-08-06)**:
1. `core/util.py` ✅ 加 `collect_env_info()`:返回 dict(平台/系统/芯片/Python/onnxruntime+providers/是否 frozen/应用版本)。**onnxruntime 延迟 import**,缺失记 "N/A",任一字段失败不抛错。
2. `app.py` `setup_logging()` ✅:保留 app.log,额外加 `error.log`(独立 RotatingFileHandler,handler 级别 ERROR+,2MB/backup 3);handlers 配置后写日志头环境摘要(`=== 环境信息 ===` 逐行打印 `collect_env_info()` 键值)。
3. `ui/main_window.py` ✅ 工具栏加「日志」按钮(spacer 与主题按钮之间),`_open_logs()` 用 `QDesktopServices.openUrl(QUrl.fromLocalFile(logs_dir()))`;打开失败状态栏提示。image_tab/video_tab 的失败提示文案改为 `"处理失败,日志已保存到 <logs_dir>"`。
4. workers ✅ 补 `log.exception`:image_worker.py("图片处理失败")/video_worker.py("视频处理失败: {src}")/download_worker.py("模型下载失败: {purposes}")。video_pipeline.py:245 已有,不重复。

**验证(Windows 全过)**:app.log + error.log 均生成;error.log 只收 ERROR+(info 不入);日志头含完整环境摘要(platform/onnxruntime=1.24.4/providers 含 DML);触发 ImageWorker 异常确认 error.log 落 traceback;GUI offscreen 冒烟 btn_logs 存在 + _open_logs 不抛错;--selftest 全绿。

**扩展(2026-08-06,失败主动弹窗)**:用户反馈日志入口太被动,改为处理任务失败时主动弹模态错误对话框(`ui/dialogs.py::show_error_dialog`)。图片批量失败聚合为一条(列出失败文件限前 8 条,超限提示「… 等 N 条未显示」);视频失败、两个 tab 的 worker 级异常均弹。全成功不弹、模型下载失败不弹(横幅已有提示)。验证:弹窗冒烟 + 端到端接线(图片部分失败/全成功不弹/两 tab worker 异常)+ selftest 全绿。

### 9.3 P2(PRD 未做)
错误帧恢复、任务队列、GPU 自动检测(已基本被 DML/CoreML 覆盖)、光流传播、mask 编辑、代码签名。

---

## 10. 开发时需要注意的问题

> **Windows 构建/打包/排错基线见 [WINDOWS_BUILD.md](WINDOWS_BUILD.md)**(含 spec 快照、打包步骤、已踩坑排错表、Win vs Mac 差异对照)。本节为通用注意事项。

### 环境与命令
- Python 用 `.venv`(3.12),运行命令必须带 `PYTHONPATH=src`(或 `cd /d/claudework/bg-remover` 后执行)。
- **工作目录会漂移**:bash 里 cd 到别的目录后相对路径失效,一律用绝对路径 `D:\claudework\bg-remover\.venv\Scripts\python.exe`。
- 依赖用 uv:`D:\uv\uv-x86_64-pc-windows-msvc\uv.exe pip install <pkg>`。
- 本机 `github.com` 直连 403 → 下载走 `ghproxy.net` 代理。**小文件用 curl 多连接并发分片(range),单连接 15MB 会超时/中断**。
- 打包命令:`D:\claudework\bg-remover\.venv\Scripts\pyinstaller.exe --noconfirm --clean bgremover.spec`,然后 `make_zip.py`。
- 打包前先 `taskkill //F //IM "AI抠图.exe"`,且**确认没有播放器/其他进程占用 dist 里的视频文件**,否则 PermissionError 打包失败(已踩坑)。
- 本项目**不是 git 仓库**。改动前建议备份(P0 时备份到 `_backup_p0_/`)。

### 架构约束
- **`core/` 绝不能 import PySide6**(multiprocessing 子进程 import 会崩)。
- multiprocessing 的 worker 函数必须模块级,不能是闭包(Windows spawn)。
- onnxruntime Session 不可跨进程 pickle。
- **视频推理必须单进程顺序**(RVM 状态跨帧 + DML 单进程独占),图片才用 Pool。
- **图片 Session 必须显式 providers=["CPUExecutionProvider"]**(两处:matting.init_worker + model_store.ModelManager.get_session)。

### 性能基准(开发机 R5 5600 + 6750 GRE)
| 场景 | 耗时 |
|------|------|
| isnet 单帧推理(CPU 1024) | ~1.8s |
| RVM 单帧(CPU 1280×720) | ~0.1s(9.6fps) |
| RVM 单帧(DML GPU 1280×720) | ~0.07s(14.6fps, 仅 1.5x,数据拷贝+小模型开销) |
| 72 帧视频 mov_alpha 端到端 | ~4.3s |

**注**:DirectML 在开发机独显只提速 1.5x(RVM 本身已比 isnet 快 19x)。多厂商兼容 + CPU 回退是主要价值。CoreML 在 Mac 上的实际加速需真机验证。

### 验证命令
```bash
cd /d/claudework/bg-remover
PYTHONPATH=src .venv/Scripts/python.exe -c "import sys; sys.argv=['x','--selftest']; from bgremover.app import _selftest; sys.exit(_selftest())"
# 期望:selftest OK / multiprocessing OK / ffmpeg OK / probe_video OK / RVM OK(backend=DirectML GPU)
```

### 用户需求背景
- 用户要"发给别人用的桌面版",对打包分发在意;目标用户 GPU 配置多样(可能 Intel 核显或 NVIDIA 独显),故 GPU 必须多厂商兼容。
- 用户用剪映对比视频抠像速度。
- 用户无 Mac 实体机,但要把软件发给 Mac 用户 → Mac 支持靠 CI + 代码级验证 + 用户提供 Mac 时真机验证。
- 用户遇到运行时错误后要求建立日志机制防患未然(P1.5)。
