# AI 智能抠图 / 视频背景移除

Windows/macOS桌面应用,用 onnxruntime 推理 AI 模型自动移除图片与视频背景。支持批量处理、透明导出、背景替换、实时预览与日志排错。

## 功能

- **图片**:批量导入(jpg/png/webp/bmp/tif),ISNet 模型一键抠图导出透明 PNG,或替换为纯色/图片背景;棋盘格原图/结果预览;多进程串行。
- **视频**:RobustVideoMatting(RVM)时序模型逐帧抠图,天然连贯。输出:
  - 透明 MOV(ProRes 4444 + Alpha) / 透明 WebM(VP9 + Alpha)
  - 替换背景 MP4(H.264),背景可为纯色或图片
  - PNG 帧序列(透明,BGRA)
  - **实时预览**:处理时每 5 帧更新抠像结果到视频页预览窗
  - **光流帧间传播**:帧间 matte 边缘平滑,减少 RVM 残留闪烁
- **GPU 加速(平台化)**:
  - Windows:DirectML(DmlExecutionProvider),兼容 NVIDIA/AMD/Intel
  - 无 GPU 自动回退 CPU;图片保留 CPU 并行
- 双层进度(帧 + 总任务)+ 预估剩余时间(EMA 平滑)
- 暂停/继续/取消;视频失败自动重试(最多 2 次)
- **错误帧恢复**:解码中断用相邻帧填充,不白跑
- **日志系统**:app.log(全量)+ error.log(仅 ERROR+),日志头含环境摘要(系统/芯片/onnxruntime/providers)
- **失败弹窗**:处理失败弹模态对话框(错误摘要 + 失败明细 + 「打开日志目录」「导出日志」)
- 导出日志:一键将 app.log + error.log 打包到指定目录,方便发给开发者排错
- 明暗主题切换、设置持久化、模型首启自动下载(双模型,断点续传)

## 环境要求

- Python 3.10+ / uv(.venv)
- 首次启动需联网下载 AI 模型(图片 isnet ~170MB + 视频 RVM ~15MB),之后离线可用
- FFmpeg:自动使用 `imageio-ffmpeg` 自带静态二进制(v7.1,prores_ks/vp9/x264/aac 全可用),无需系统安装

## 安装与运行

### Windows

```bash
cd bg-remover
uv venv --python 3.12
uv pip install -e .
uv run python -m bgremover
```

依赖 `onnxruntime-directml`(默认 GPU 加速)。

### macOS

```bash
cd bg-remover
uv venv --python 3.12
uv pip install -e .
uv run python -m bgremover
```

依赖 `onnxruntime==1.23.0`(内置 CoreML,支持 Intel + Apple Silicon)。macOS 图片并行固定 2 进程(统一内存自适应)。

### 打包版(Windows)

解压 `dist/AI抠图-win64.zip`,运行 `AI抠图.exe`。内置双模型 + ffmpeg,开箱即用。

## 使用

1. 启动后若模型未下载,点击顶部横幅"下载模型"(支持断点续传)。
2. 图片页:拖拽或导入图片 → 选择输出(透明 PNG / 替换背景)→ 开始抠图。
3. 视频页:导入视频(支持文件夹拖拽递归收集) → 选择输出格式、背景、音频 → 开始处理。处理时预览窗实时显示抠像结果。视频加速后端(DirectML GPU / CoreML GPU / CPU)自动检测,显示在输出设置区。
4. 工具栏「日志」按钮打开日志目录;「导出日志」将 app.log + error.log 打包到指定位置。
5. 处理失败时弹模态对话框,可直接打开日志目录或导出日志排错。

## 目录结构

```
src/bgremover/
├─ app.py               # 入口:应用装配、--selftest 无头自检、setup_logging
├─ core/                # 无 Qt 依赖(子进程可安全 import)
│  ├─ config.py         # AppConfig + 跨平台数据目录(win32/darwin/XDG)
│  ├─ model_store.py    # 双模型槽位(image/video),下载多源断点续传
│  ├─ matting.py        # ISNet 图片推理(CPU,多进程)
│  ├─ rvm.py            # RVM 视频推理(平台化 GPU + 光流融合)
│  ├─ ffmpeg_tool.py    # ffmpeg 定位/编码器自检/元数据/命令生成
│  ├─ video_pipeline.py # 视频管线(解码→RVM→编码,错误帧恢复,光流,实时预览)
│  ├─ image_pipeline.py # 批量图片调度(并行,进程数内存自适应)
│  └─ util.py           # 棋盘格/格式化/ETA/环境信息收集
├─ workers/             # QThread 层
│  ├─ signals.py        # ProgressPayload + WorkerSignals
│  ├─ base_worker.py    # QThread 三态状态机(pause/resume/cancel)
│  ├─ image_worker.py   # 图片批量(含 log.exception)
│  ├─ video_worker.py   # 视频处理(含 log.exception + 自动重试)
│  └─ download_worker.py # 模型下载(含 log.exception)
└─ ui/                  # 界面层
   ├─ main_window.py    # 主窗口/工具栏(日志+导出日志+主题+设置)
   ├─ image_tab.py      # 图片页(列表/预览/模式/失败弹窗)
   ├─ video_tab.py      # 视频页(队列/格式/实时预览/失败弹窗)
   ├─ dialogs.py        # 统一错误对话框 + 导出日志
   ├─ preview.py        # 棋盘格透明预览组件(QGraphicsView)
   ├─ settings.py       # 设置对话框
   └─ theme.py          # 明暗主题 QSS
```

## 已知限制

- 图片 CPU 推理约 1.5s/帧(ISNet 1024×1024);视频 RVM 约 0.1s/帧(CPU),DirectML GPU 约 1.5x 加速(CoreML 加速需 Mac 真机验证)
- VFR 源视频按平均帧率归一
- 透明视频需在支持 Alpha 的播放器/剪辑软件中查看(如 VLC、Premiere)
- 视频推理为单进程顺序(RVM 循环模型必须逐帧回传状态)
- Windows exe 未代码签名(SmartScreen 警告,右键"仍要运行"即可);Mac .app 未签名(Gatekeeper 拦截,需右键打开或签名)
- 光流融合仅处理边缘过渡带(alpha 0.05–0.95),主体/背景完全保留当前帧,避免移动物体 alpha 稀释

## 开发

完整构建/打包/排错基线见 [WINDOWS_BUILD.md](WINDOWS_BUILD.md)。项目交接文档见 [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md)。

源码验证:
```bash
PYTHONPATH=src .venv/Scripts/python.exe -c "import sys; sys.argv=['x','--selftest']; from bgremover.app import _selftest; sys.exit(_selftest())"
```

打包:
```bash
taskkill //F //IM "AI抠图.exe"
.venv\Scripts\pyinstaller.exe --noconfirm --clean bgremover.spec
PYTHONPATH=src .venv/Scripts/python.exe make_zip.py
```
