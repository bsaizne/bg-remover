# AI 智能抠图 / 视频背景移除 — macOS 项目交接文档

> **用途**:复制到新的 Claude 对话中,让新对话无缝继续开发。
> **项目路径**:`D:\claudework\bg-remover`
> **Git 仓库**:https://github.com/bsaizne/bg-remover(已推送,含 CI)
> **更新日期**:2026-08-07

---

## 1. 项目概述

macOS 桌面应用,用 onnxruntime 推理 AI 模型自动移除图片与视频背景。**这是一个带可视化 UI 窗口的桌面软件——用户双击打开后看到 PySide6 窗口,可直接拖拽图片/视频进行抠图。** 视频推理走 CoreML GPU(Apple Silicon 原生加速),无 GPU 自动回退 CPU。

**当前全部代码在 Windows 开发机(R5 5600)上完成,通过 GitHub Actions CI 在 macos-14(arm64)上成功构建 artifact(379MB);macos-13(x86_64)排队中。Mac 真机验证待用户有 Mac 时进行。**

### 产物形态
- CI artifact(`AI抠图-mac-arm64.zip`)解压后是 `AI抠图/` 目录,Mac 上双击 `AI抠图` 即可打开 GUI 窗口
- `bgremover.spec`:`console=False`(不弹终端),GUI 启动链:`__main__.py`→`app.main()`→`QApplication.exec()`
- `--selftest` 仅 CI 无头自检用,正常启动不传此参数

### 未签名
CI 产物未签名(需 Apple Developer 证书 $99/年)。Gatekeeper 拦截时**右键→打开**即可。spec 中 `codesign_identity=None` 可按需改为证书 ID。

---

## 2. 已完成功能 ✅

### 图片处理
- 批量导入(jpg/jpeg/png/webp/bmp/tif/tiff/gif),拖拽/文件夹递归收集
- 批量抠图→透明 PNG(4 通道 RGBA),背景替换(纯色/图片)
- 棋盘格透明预览(原图/结果切换)
- 并行处理(multiprocessing.Pool,**Mac 固定 2 进程**,统一内存自适应)

### 视频处理
- 导入(mp4/mov/avi/mkv/webm/flv),元信息(分辨率/帧率/时长/大小/有无音频)
- **RVM**(RobustVideoMatting, mobilenetv3)时序循环逐帧抠图,天然连贯
- **GPU 加速**:优先 CoreMLExecutionProvider(Apple Silicon 原生),无 GPU 自动回退 CPU
- 双管道直通(ffmpeg 解码 rawvideo → RVM 推理 → ffmpeg 编码),无中间文件
- 输出:透明 MOV(ProRes 4444+Alpha)、透明 WebM(VP9+Alpha)、背景 MP4(H.264)、PNG 帧序列
- 音频:默认保留,可去除
- 双层进度(帧+总任务)+ EMA 预估剩余时间,暂停/继续/取消
- **实时背景预览**:处理时每 5 帧更新抠像结果到 TransparentPreview
- **光流帧间传播**:仅平滑边缘过渡带(alpha 0.05~0.95),减少 RVM 闪烁
- **错误帧恢复**:解码中断用最后有效帧补齐,不白跑
- **失败自动重试**:最多 2 次重试(共 3 次尝试)
- 批量视频排队串行(一个完成自动下一个)

### 通用功能
- 明暗主题切换、设置持久化(JSON,`~/Library/Application Support/bgremover/settings.json`)
- 双模型首启自动下载(isnet ~170MB + RVM ~15MB,多源断点续传)
- **日志系统**:app.log(全量) + error.log(仅 ERROR+),日志头含环境摘要
- **失败弹窗**:模态对话框(摘要+明细+「打开日志目录」「导出日志」按钮)
- **导出日志**:一键复制 app.log+error.log 到指定目录
- **工具栏**:导入/开始/暂停/取消/主题/日志/导出日志/设置
- PyInstaller 打包(onedir+zip,内置双模型+ffmpeg,开箱即用)
- `--selftest` 无头自检(isnet/multiprocessing/ffmpeg/RVM/provider 分支)

---

## 3. 未完成功能 ❌

### 待 Mac 真机/CI 验证
- macOS CoreML GPU 加速实际效果(代码已完成,`build_session` 有 session_timeout 30s 防挂)
- macOS PyInstaller 打包后的 .app 多进程是否正常
- macos-13(x86_64 Intel) CI artifact 待出

### P2(后续迭代)
- mask 边缘编辑(交互式腐蚀/膨胀/羽化)
- 代码签名(需 Apple Developer 证书 $99/年,未签名需右键打开)

### 已砍掉(勿重提)
- 任务队列(多视频并行):与 Mac 统一内存冲突,RVM 单进程独占 GPU,用户确认不做

---

## 4. 技术栈(macOS 目标)

| 组件 | 目标版本 | 说明 |
|------|---------|------|
| Python | 3.12+ | |
| GUI | PySide6 6.11+ | |
| 图像 | opencv-python-headless, numpy, Pillow | |
| 推理 | **onnxruntime==1.23.0** | Mac 目标;1.24+ 只有 arm64,Intel 须锁 1.23;内置 CoreMLExecutionProvider |
| 视频 | imageio-ffmpeg 0.6.0 | 自带 ffmpeg 7.1 |
| 打包 | PyInstaller 6.21+ | |
| 其他 | requests, psutil | |

> **开发机(Windows R5 5600)实际版本**:onnxruntime-directml 1.24.4, opencv 5.0.0.93, numpy 2.5.1, Pillow 12.3.0, psutil 7.2.2。这些是 Win 上 selftest 用的,Mac CI 走 pip install onnxruntime==1.23.0。版本差异不影响代码逻辑(API 兼容)。

### 模型
- 图片:`isnet-general-use.onnx`(178MB)
- 视频:`rvm_mobilenetv3_fp32.onnx`(15MB)
- 位置:`~/Library/Application Support/bgremover/models/`

**关键结论**:
- **不要用 `onnxruntime-coreml`**(已停更,仅 cp39)。标准 onnxruntime 的 macOS wheel 已内置 CoreMLExecutionProvider。
- CoreML 对 RVM 动态 shape / ConvGRU 支持有限(可能部分算子切 CPU),代码已做失败降级+ session_timeout 硬止损。
- Mac 打包需 `upx=False`,BUNDLE/INFO.plist,代码签名。

---

## 5. 目录结构

```
D:\claudework\bg-remover\
├─ pyproject.toml           # 平台标记:DARWIN→onnxruntime==1.23.0
├─ .python-version          # 3.12
├─ README.md                # 用户文档
├─ bgremover.spec           # PyInstaller spec(已平台化:Mac 分支 upx=False,ffmpeg 走 brew)
├─ make_zip.py              # zip 打包(产出名按平台+架构:AI抠图-mac-arm64.zip 等)
├─ _windows_backup/         # Windows 相关文件备份(WINDOWS_BUILD.md 等,Mac 项目不引用)
├─ PROJECT_HANDOFF.md       # 本交接文档
├─ .github/workflows/mac_build.yml  # CI(macos-14 arm64 ✅ + macos-13 x86_64 排队中)
├─ _backup_*/               # 历代改动备份
├─ _test_videos/            # 测试视频
├─ dist/                    # 打包输出(CI artifact)
└─ src/bgremover/
   ├─ __init__.py           # 版本号
   ├─ __main__.py           # 入口
   ├─ app.py                # 装配+freeze_support 无条件+selftest+setup_logging
   ├─ core/                 # 无 Qt 依赖(multiprocessing 子进程安全 import)
   │  ├─ config.py          # AppConfig + 跨平台数据目录(darwin→~/Library/Application Support)
   │  ├─ model_store.py     # 双模型下载/管理(断点续传)
   │  ├─ matting.py         # ISNet 图片推理(CPU,显式 CPUExecutionProvider)
   │  ├─ rvm.py             # RVM 视频推理(平台化:darwin→CoreML,失败降级CPU;warp_blend_pha 边缘光流)
   │  ├─ ffmpeg_tool.py     # ffmpeg 定位(brew 优先)/探测/命令生成
   │  ├─ video_pipeline.py  # 视频解码→推理→编码(is_recovery 错误恢复;光流;每5帧 preview_rgba)
   │  ├─ image_pipeline.py  # 批量图片调度(_default_workers:Mac 固定2)
   │  └─ util.py            # 棋盘格/ETA/collect_env_info(日志头)
   ├─ workers/              # QThread 层
   │  ├─ signals.py         # ProgressPayload(含 preview_rgba/w/h) + WorkerSignals
   │  ├─ base_worker.py     # 三态状态机(_pause_event 初始 set())
   │  ├─ image_worker.py    # 图片批处理(log.exception)
   │  ├─ video_worker.py    # 视频处理(max_retries=2;preview callback;log.exception)
   │  └─ download_worker.py # 模型下载(log.exception)
   └─ ui/                   # 界面层
      ├─ main_window.py     # 工具栏(日志+导出日志)
      ├─ image_tab.py       # 图片页(失败弹窗聚合)
      ├─ video_tab.py       # 视频页(实时预览;backend label 中性化)
      ├─ dialogs.py         # show_error_dialog(打开/导出日志) + export_logs_dialog
      ├─ preview.py         # TransparentPreview(QGraphicsView)
      ├─ settings.py        # 设置对话框
      └─ theme.py           # 明暗 QSS
```

**分层硬约束**:`core` 不 import PySide6;`workers` 只做起停与信号转发;`ui` 不碰 onnxruntime/ffmpeg。

---

## 6. 文件作用详表

| 文件 | 作用 |
|------|------|
| `pyproject.toml` | 平台标记:`onnxruntime==1.23.0; platform_system == 'Darwin'` |
| `bgremover.spec` | PyInstaller spec,Mac 分支:upx=False,ffmpeg 走 brew,不收集 DirectML DLL |
| `make_zip.py` | 压缩 onedir 为 zip,文件名按平台+架构:AI抠图-mac-arm64.zip |
| `.github/workflows/mac_build.yml` | CI:macos-14+macos-13,串行,先下载模型→selftest→打包→上传 |
| `app.py` | freeze_support 无条件调用;setup_logging(app+error.log+环境头);--selftest(含 provider 分支断言) |
| `core/config.py` | AppConfig dataclass;darwin 数据目录→~/Library/Application Support/bgremover |
| `core/model_store.py` | 双模型槽位,download 断点续传,内置模型复制 |
| `core/matting.py` | ISNet:resize 1024+/255→推理→sigmoid→合成 RGBA;init_worker 锁 CPU providers |
| `core/rvm.py` | RVM:darwin→CoreML 优先+失败降级;build_session(session_timeout);infer 状态循环;warp_blend_pha(边缘光流融合) |
| `core/ffmpeg_tool.py` | locate_ffmpeg(brew>打包内置>PATH);probe_video(ffmpeg -i 正则,无 ffprobe) |
| `core/video_pipeline.py` | 双线程解码/编码;RVM 顺序推理;is_recovery 标志位;光流(仅正常帧);每5帧 preview_rgba |
| `core/image_pipeline.py` | 并行/串行;Mac _default_workers() 固定 2 |
| `core/util.py` | collect_env_info(日志头,onnxruntime 延迟 import) |
| `workers/signals.py` | ProgressPayload(preview_rgba/preview_w/preview_h);WorkerSignals |
| `workers/base_worker.py` | _pause_event 初始 set()(修复默认暂停卡死) |
| `workers/image_worker.py` | 图片批处理,log.exception |
| `workers/video_worker.py` | probe 宽高;max_retries=2;preview callback;log.exception |
| `workers/download_worker.py` | 模型下载,log.exception |
| `ui/main_window.py` | 工具栏(日志/导出日志/主题/设置);ModelBanner |
| `ui/image_tab.py` | 失败弹窗聚合(failed 清单限8条) |
| `ui/video_tab.py` | backend label 中性化(CoreML GPU/CPU);_on_progress np.frombuffer→show_rgba 实时预览 |
| `ui/dialogs.py` | show_error_dialog(打开/导出日志+确定);export_logs_dialog(选目录→复制日志) |
| `ui/preview.py` | TransparentPreview(QGraphicsView, QPainter.RenderHint 枚举坑) |
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
    frame_step: int = 1        # 遗留,兼容旧 settings.json
    export_png_sequence: bool = False
```
持久化:`~/Library/Application Support/bgremover/settings.json`

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
    preview_rgba: bytes | None   # 实时预览 RGBA raw bytes(每5帧)
    preview_w, preview_h: int    # 预览宽高
```

### 视频元数据(probe_video)
```python
{"width", "height", "fps", "duration", "frames", "has_audio", "size_bytes"}
```

### RVM IO 约定(已踩坑确认)
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
**必须 CPU providers**:否则每子进程建 GPU session 显存爆炸。

### 8.2 视频管线(video_pipeline.py)
```
ffmpeg 解码(rawvideo,rgb24) → _Reader 线程 → 主循环:
  raw→reshape→/255→rvm.infer(session,rgb,states)→更新 states
  → 光流 warp_blend_pha(仅正常帧)
  → compose_rgba(mov/webm)/compose_rgb(mp4_bg)/compose_bgra(png)
  → 每5帧 preview_rgba→progress_cb
  → wbuf→_Writer 线程→ffmpeg 编码+mux
```
**单进程顺序**:RVM ConvGRU 须逐帧回传状态;Mac CoreML 单进程独占;Session 不可 pickle。

### 8.3 RVM 推理(rvm.py)
- 初始状态 (1,1,1,1) 全零 ×4,不按分辨率推算(否则 Expand_174 报错)
- 状态名映射:r1i→r1o(name[:-1]+"o")
- fgr 是标准 RGB 顺序
- `detect_provider()`:Darwin→CoreML 优先,失败降级 CPU;`build_session` 有 session_timeout=30s 防 Mac CoreML 图编译挂起

### 8.4 合成字节序(极易出错)
- mov/webm → **compose_rgba(RGBA)**,编码器 `-pix_fmt rgba`
- mp4_bg → **compose_rgb(RGB)**,编码器 `-pix_fmt rgb24`
- png_seq → **compose_bgra(BGRA)**,cv2.imwrite
- 内部 float[0,1]×255 转 uint8(不乘就全黑)

### 8.5 光流帧间传播(rvm.warp_blend_pha)
- 仅平滑 alpha 过渡带(0.05~0.95):主体/背景完全保留当前帧
- Farneback:灰度→calcOpticalFlowFarneback→remap warp→加权融合(当前70%+warp30%)
- 恢复帧(is_recovery=True)跳过光流;尺寸不匹配/last_pha=None/异常均直通

### 8.6 错误帧恢复(video_pipeline.py)
- `is_recovery` 标志位:坏帧/EOF 填充分支置 True
- `last_rgb` 缓存(深拷贝),恢复帧复用;恢复帧清空光流参考

### 8.7 实时预览
- pipeline 的 `progress_cb` 第 4 参数为 preview_rgba bytes(每5帧)
- ProgressPayload→worker emit→video_tab._on_progress→np.frombuffer→show_rgba

### 8.8 已踩坑(必读,避免重蹈)
1. **BaseWorker._pause_event 初始 .set()**:否则视频首次 wait 永久卡死
2. **RVM fgr/pha→uint8 必须 ×255**:否则前景全黑
3. **合成字节序**:见 8.4,RGBA/RGB/BGRA 搞错红蓝反转
4. **Win multiprocessing 不能 pickle 闭包**:worker 函数必须模块级(Mac 同样)
5. **PySide6 枚举**:用 `QPainter.RenderHint` 不用 `Qt.RenderHint`;`QSizePolicy.Expanding` 不用 `.Expanding`
6. **CoreML 算子限制**:动态 shape/ConvGRU 可能部分切 CPU,已降级+session_timeout 防挂
7. **图片 ISNet 必须 CPU providers**
8. **RVM 初始状态 (1,1,1,1)**:不按分辨率推算
9. **QImage bytes→QPixmap 需 .copy()**:PySide6 生命周期
10. **cancel_event 可能 None**:检查 `cancel_event is not None and cancel_event.is_set()`
11. **numpy 数组不能用于 if 条件**:`if array:`→`if array is not None:`
12. **实时预览用 np.frombuffer**:不能直接用 QImage(bytes,...),PySide6 下 QImage 构造后不能 hold bytes 引用

---

## 9. 下一步计划

| 优先级 | 项目 | 说明 |
|--------|------|------|
| **最高** | Mac CI x86_64 artifact | macos-13 排队中;本地有 1 个 commit(1866ac7)未推送:fail-fast:false |
| **高** | Mac 真机验证 | CoreML 实际加速效果、frozen .app 多进程是否正常;`ort.get_available_providers()` 是否含 CoreML |
| 中 | mask 边缘编辑 | 交互式腐蚀/膨胀/羽化滑块,UI 复杂度大 |
| 低 | 代码签名 | 需 Apple Developer 证书($99/年) |
| 不做 | 多视频并行 | 已砍,与 Mac 统一内存冲突 |

---

## 10. 开发注意事项(Mac 视角)

### 开发环境
- **开发机是 Windows**(R5 5600,无 Mac),所有代码改动在 Win 上做,CI 验证 Mac 构建。改动前备份到 `_backup_<feature>/`
- Python `.venv`(3.12),命令必须带 `PYTHONPATH=src`,用绝对路径:`D:\claudework\bg-remover\.venv\Scripts\python.exe`
- bash 里 cd 后相对路径失效(工作目录会漂移),一律用绝对路径
- GitHub 仓库:https://github.com/bsaizne/bg-remover(公开,含 CI Actions)
- 本机 `github.com` 直连可能失败→git push 需重试;GitHub API 不受影响
- 项目根目录 `_windows_backup/` 备份了 Windows 相关文件(WINDOWS_BUILD.md 等),Mac 项目不引用

### 架构约束
- **`core/` 绝不能 import PySide6**(子进程 import 会崩)
- multiprocessing worker 函数必须模块级(Mac spawn)
- onnxruntime Session 不可跨进程 pickle
- **视频推理必须单进程顺序**(RVM 状态跨帧),图片才用 Pool
- **图片 Session 必须显式 providers=["CPUExecutionProvider"]**

### 验证
```bash
cd /d/claudework/bg-remover
PYTHONPATH=src .venv/Scripts/python.exe -c "import sys; sys.argv=['x','--selftest']; from bgremover.app import _selftest; sys.exit(_selftest())"
# Win 开发机期望全绿,backend=DirectML GPU
# Mac CI 上 backend 可能为 CoreML GPU 或 CPU(取决于 CI runner)
```

### CI
- workflow:`.github/workflows/mac_build.yml`
- 步骤:brew ffmpeg→pip 安装→下载模型(直连 GitHub)→selftest(容错)→pyinstaller→zip→upload artifact
- 当前状态:macos-14 arm64 success(artifact 379MB);macos-13 x86_64 排队中

### 用户需求
- 用户无 Mac 实体机,但要把软件发给 Mac 用户用
- Mac 用户拿到 CI artifact(zip)→解压→双击 `AI抠图` 打开可视化窗口
- 真机验证靠用户反馈;排错靠日志(app.log + error.log) + 失败弹窗
- 用户用剪映对比视频抠像速度

---

## 11. 新对话启动提示词

复制下面内容到新 Claude 对话:

```
新 Claude 对话,请先读取项目交接文档 D:\claudework\bg-remover\PROJECT_HANDOFF.md,然后继续开发。
项目是 macOS AI 抠图/视频背景移除桌面软件(PySide6 + onnxruntime CoreML),位于 D:\claudework\bg-remover。
文档里完整记录了已完成功能/目录结构/文件作用/数据模型/业务逻辑/已修bug/下一步计划。
当前待办(文档第 9 节):
1. macos-13 x86_64 CI artifact:本地有1个commit(1866ac7)未推送,需先push
2. Mac 真机验证:待用户有 Mac 或引导下载 CI artifact 测试
3. P2:mask 边缘编辑/代码签名(需 Apple Developer 证书)
关键环境:
* 开发机是 Windows(R5 5600,无 Mac),代码在 Win 上改,CI 验证 Mac 构建
* Python .venv(3.12),命令带 PYTHONPATH=src,绝对路径 D:\claudework\bg-remover\.venv\Scripts\python.exe
* 架构硬约束:core/不import PySide6;视频单进程顺序;图片Pool Mac固定2
* --selftest 验证命令在文档第10节,可先确认代码健康
* GitHub仓库:https://github.com/bsaizne/bg-remover(已推送)
* 改动前备份到 _backup_<feature>/
```


