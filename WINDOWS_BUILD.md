# Windows 构建 / 打包 / 排错基线

> 本文件是 **Windows 专用**的构建与分发基线,防止未来 Mac/CI 改动破坏 Windows 打包时无法修复。
> 项目不是 git 仓库,无版本历史可回退,此文档 + `bgremover.spec` 顶部注释快照为唯一参照。
> 主交接文档见 [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md)(本文件与其信息互补,不重复)。
> 最近更新:2026-08-06(基线建立,含全部已实现功能)

---

## 1. 环境与路径

| 项 | 值 |
|----|-----|
| 项目根 | `D:\claudework\bg-remover` |
| Python | 3.12.13,虚拟环境 `.venv/` |
| 解释器绝对路径 | `D:\claudework\bg-remover\.venv\Scripts\python.exe` |
| PyInstaller | `D:\claudework\bg-remover\.venv\Scripts\pyinstaller.exe` |
| uv | `D:\uv\uv-x86_64-pc-windows-msvc\uv.exe` |
| 源码运行需 | 带 `PYTHONPATH=src`(或先 `cd /d/claudework/bg-remover`) |
| 用户数据目录 | `%LOCALAPPDATA%\bgremover\`(模型/日志/设置) |
| 模型下载 | 本机 `github.com` 直连 403 → 走 `ghproxy.net` 代理;小文件用 curl 多连接并发分片(range),单连接 15MB 会超时/中断 |

**注意**:bash 里 cd 到别的目录后相对路径失效,一律用绝对路径。

---

## 2. 依赖基线(Windows 专属)

| 组件 | 版本 | 说明 |
|------|------|------|
| Python | 3.12.13 | uv 管理,`.venv/` |
| GUI | PySide6 6.11.1 | |
| 图像 | opencv-python-headless 5.0.0.93、numpy 2.5.1、Pillow 12.3.0 | |
| 推理 | **onnxruntime-directml 1.24.4** | **与 onnxruntime 包互斥,不能共存**,模块名同为 `onnxruntime` |
| 视频 | imageio-ffmpeg 0.6.0 | 自带 ffmpeg 7.1 静态二进制(prores_ks/vp9/x264/aac/opus 全可用),无系统 ffmpeg/ffprobe |
| 打包 | PyInstaller 6.21.0 | |
| 其他 | requests 2.34.2、psutil 7.2.2 | |

### pyproject.toml 依赖标记(勿手改)
```toml
"onnxruntime-directml; platform_system == 'Windows'",
"onnxruntime==1.23.0; platform_system == 'Darwin'",
```
Windows 上绝不能再装裸 `onnxruntime`,否则与 directml 冲突(双装后 import 混乱)。

---

## 3. 打包步骤(完整命令)

```bash
cd /d/claudework/bg-remover

# 0) 前置检查:双模型必须已下载(spec 缺失时会直接退出报错)
ls "$LOCALAPPDATA/bgremover/models/"

# 1) 清理残留 AI抠图.exe 进程(否则打包/覆盖失败)
taskkill //F //IM "AI抠图.exe"

# 2) 确认没有播放器/其他进程占用 dist/AI抠图 里的视频文件
#    (否则 PyInstaller 写 dist 时报 PermissionError,已踩坑)
#    关闭 VLC/剪映/资源管理器预览等

# 3) 打包(onedir,输出到 dist/AI抠图)
D:\claudework\bg-remover\.venv\Scripts\pyinstaller.exe --noconfirm --clean bgremover.spec

# 4) 压缩为分发 zip
PYTHONPATH=src D:\claudework\bg-remover\.venv\Scripts\python.exe make_zip.py
# 产出 dist/AI抠图-win64.zip
```

**产物布局**(onedir,验证标准):
```
dist/AI抠图/
├─ AI抠图.exe
└─ _internal/
   ├─ models/isnet-general-use.onnx + rvm_mobilenetv3_fp32.onnx
   ├─ ffmpeg/ffmpeg.exe
   └─ onnxruntime/onnxruntime.dll + DirectML.dll
```

---

## 4. bgremover.spec 关键配置快照(防覆盖)

`bgremover.spec` 顶部已有一段只读注释快照(勿删)。核心事实:

- `console=False`(GUI,不弹控制台);`upx=True`
- `datas`:双模型 → `_internal/models/`;ffmpeg → `_internal/ffmpeg/`
- `binaries`:**onnxruntime 原生 DLL 目录** → `_internal/onnxruntime/`
  ```python
  import onnxruntime as _ort
  _ort_dir = os.path.dirname(_ort.__file__)
  binaries.append((_ort_dir, "onnxruntime"))
  ```
- `hiddenimports = ["onnxruntime", "opencv", "PIL._tkinter_finder", "imageio_ffmpeg"]`
- 入口 `src/bgremover/__main__.py`,`pathex` 含 `src`
- 模型在 spec 内定位(导入 `bgremover.core.config.models_dir`),**打包前模型必须先存在**

**Mac 打包差异(将来 CI 做,勿用于 Windows)**:
- `upx=False`
- 需 BUNDLE(Info.plist)+ 代码签名
- `console=True`(py2app 惯例,看实际)
- 依赖是 `onnxruntime==1.23.0`,不是 directml

---

## 5. 验证命令

### 5.1 源码验证(开发机,含 GPU)
```bash
cd /d/claudework/bg-remover
PYTHONPATH=src .venv/Scripts/python.exe -c "import sys; sys.argv=['x','--selftest']; from bgremover.app import _selftest; sys.exit(_selftest())"
# 期望全绿,最后一行 backend=DirectML GPU
```
selftest 覆盖:isnet 推理 / multiprocessing / ffmpeg 探测与编码器 / RVM 推理 / provider 4 平台分支。

### 5.2 打包产物验证
`--selftest` 在 frozen 下 exit code 可用(console=False 无 stdout,但退出码有效):
```bash
D:\claudework\bg-remover\dist\AI抠图\AI抠图.exe --selftest
echo $?   # 0 = 全链路 OK
```
GUI 手动验证:启动后视频页后端 label 显示 "视频加速: DirectML GPU (GPU 自动)"。

---

## 6. 已踩坑排错表(Windows)

| 症状 | 原因 | 解决 |
|------|------|------|
| `PermissionError: [WinError 32]` 打包失败 | 残留 AI抠图.exe 或播放器占用 dist 内视频 | `taskkill //F //IM "AI抠图.exe"`,关播放器,重跑打包 |
| `图片模型未找到 / 视频模型未找到` spec 退出 | 模型未下载 | 先跑一次 `python -m bgremover` 完成模型下载 |
| import onnxruntime 后 provider 异常 | directml 与 onnxruntime 双装冲突 | 只装 onnxruntime-directml,卸载裸 onnxruntime |
| 图片批量子进程显存爆炸/走 GPU | isnet 多进程 Pool 未锁 CPU | 图片 Session 必须 `providers=["CPUExecutionProvider"]`(matting.init_worker + model_store.get_session) |
| 打包后 multiprocessing 子进程无法启动 | 缺 freeze_support | app.main() 无条件调用 `multiprocessing.freeze_support()` |
| ghproxy 下载大文件超时中断 | 单连接慢 | curl 多连接并发分片(range) |
| RVM 视频全黑/前景黑 | fgr/pha 未乘 255 或字节序错 | mov/webm→RGBA, mp4_bg→RGB, PNG→BGRA;float[0,1]×255 转 uint8 |

---

## 7. Windows vs Mac 差异对照

| 维度 | Windows | macOS |
|------|---------|-------|
| onnxruntime | directml(含 DmlExecutionProvider) | `onnxruntime==1.23.0`(内置 CoreMLExecutionProvider,arm64+x86_64) |
| 视频 GPU | DirectML(多厂商统一) | CoreML(动态 shape 支持有限,可能部分算子切 CPU) |
| 图片 Pool 进程数 | 核数//2,封顶 4 | **固定 2**(统一内存,防 OOM) |
| 数据目录 | `%LOCALAPPDATA%\bgremover\` | `~/Library/Application Support/bgremover/` |
| spec `upx` | `True` | `False` |
| 打包 | onedir + zip(exe 未签名,SmartScreen 警告) | BUNDLE/INFO.plist + 签名(Gatekeeper 拦截未签名) |
| 日志目录 | `%LOCALAPPDATA%\bgremover\logs\` | `~/Library/Application Support/bgremover/logs/` |

**Mac 实机验证清单**(用户有 Mac 时):install 解析;`ort.get_available_providers()` 含 CoreML;selftest backend=CoreML GPU;真实视频对比 GPU/CPU 帧耗时(接近则 CoreML 未接管关键算子,看日志 `number of partitions supported by CoreML`);PyInstaller 打包后多进程正常。
