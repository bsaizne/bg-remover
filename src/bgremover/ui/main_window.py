"""主窗口:工具栏 + 模型横幅 + 图片/视频标签页 + 状态栏。"""
from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow, QProgressBar,
                               QPushButton, QSizePolicy, QTabWidget, QToolButton,
                               QVBoxLayout, QWidget)

from bgremover.core.config import AppConfig
from bgremover.core import model_store
from bgremover.ui.image_tab import ImageTab
from bgremover.ui.theme import THEMES
from bgremover.ui.video_tab import VideoTab
from bgremover.workers.download_worker import DownloadWorker
from bgremover.workers.signals import ProgressPayload

log = logging.getLogger(__name__)


class ModelBanner(QFrame):
    """模型缺失时的下载横幅。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("modelBanner")
        self.setVisible(False)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        self.label = QLabel("AI 模型未全部下载(图片 ~170MB + 视频 ~15MB),点击下载后即可使用(首次需要网络)")
        self.label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setFixedWidth(220)
        self.progress.setVisible(False)
        self.btn = QPushButton("下载模型")
        self.btn.setObjectName("primary")
        lay.addWidget(self.label, 1)
        lay.addWidget(self.progress)
        lay.addWidget(self.btn)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = AppConfig.load()
        self.setWindowTitle("AI 智能抠图")
        self.resize(1180, 760)

        self._build_toolbar()
        self._build_central()

        self.download_worker: DownloadWorker | None = None
        self._model_ready = all(model_store.is_model_ready(p) for p in ("image", "video"))
        self._refresh_model_state()

        self.apply_theme(self.config.theme)
        self.statusBar().showMessage("就绪")

    # ---------- UI 构建 ----------
    def _build_toolbar(self):
        tb = self.addToolBar("主工具栏")
        tb.setMovable(False)
        tb.setObjectName("mainToolbar")

        self.btn_import = QToolButton()
        self.btn_import.setText("导入文件")
        self.btn_import.clicked.connect(self._import_files)
        tb.addWidget(self.btn_import)

        self.btn_start = QToolButton()
        self.btn_start.setText("开始处理")
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._start_current_tab)
        tb.addWidget(self.btn_start)

        self.btn_pause = QToolButton()
        self.btn_pause.setText("暂停")
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._toggle_pause)
        tb.addWidget(self.btn_pause)

        self.btn_cancel = QToolButton()
        self.btn_cancel.setText("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel_all)
        tb.addWidget(self.btn_cancel)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        self.btn_logs = QToolButton()
        self.btn_logs.setText("日志")
        self.btn_logs.setToolTip("打开日志目录(app.log / error.log)")
        self.btn_logs.clicked.connect(self._open_logs)
        tb.addWidget(self.btn_logs)

        self.btn_export_logs = QToolButton()
        self.btn_export_logs.setText("导出日志")
        self.btn_export_logs.setToolTip("导出日志文件到指定位置")
        self.btn_export_logs.clicked.connect(self._export_logs)
        tb.addWidget(self.btn_export_logs)

        self.btn_theme = QToolButton()
        self.btn_theme.setText("🌓")
        self.btn_theme.setToolTip("切换主题")
        self.btn_theme.clicked.connect(self._toggle_theme)
        tb.addWidget(self.btn_theme)

        self.btn_settings = QToolButton()
        self.btn_settings.setText("设置")
        self.btn_settings.clicked.connect(self._open_settings)
        tb.addWidget(self.btn_settings)

    def _build_central(self):
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        self.banner = ModelBanner()
        self.banner.btn.clicked.connect(self._start_download)
        v.addWidget(self.banner)

        self.tabs = QTabWidget()
        self.image_tab = ImageTab(self)
        self.video_tab = VideoTab(self)
        self.tabs.addTab(self.image_tab, "图片")
        self.tabs.addTab(self.video_tab, "视频")
        v.addWidget(self.tabs, 1)

        # 底部:总进度
        bottom = QWidget()
        bh = QHBoxLayout(bottom)
        bh.setContentsMargins(4, 2, 4, 2)
        self.total_progress = QProgressBar()
        self.total_progress.setFixedHeight(18)
        self.total_progress.setRange(0, 100)
        self.total_progress.setValue(0)
        self.total_progress.setVisible(False)
        bh.addWidget(self.total_progress, 1)
        self.progress_label = QLabel("")
        self.progress_label.setMinimumWidth(120)
        bh.addWidget(self.progress_label)
        v.addWidget(bottom)

        self.setCentralWidget(central)

    # ---------- 状态刷新 ----------
    def _refresh_model_state(self):
        ready = all(model_store.is_model_ready(p) for p in ("image", "video"))
        self._model_ready = ready
        self.banner.setVisible(not ready)
        self.btn_start.setEnabled(ready)
        self.image_tab.set_model_ready(ready)
        self.video_tab.set_model_ready(ready)

    def _start_download(self):
        if not self._model_ready:
            self.banner.btn.setEnabled(False)
            self.banner.btn.setText("下载中...")
            self.banner.progress.setVisible(True)
            self.download_worker = DownloadWorker(model_store.missing_models(), self)
            self.download_worker.signals.progress.connect(self._on_download_progress)
            self.download_worker.signals.finished.connect(self._on_download_done)
            self.download_worker.signals.failed.connect(self._on_download_failed)
            self.download_worker.start()

    def _on_download_progress(self, p: ProgressPayload):
        self.banner.progress.setRange(0, max(p.total, 1))
        self.banner.progress.setValue(p.done)
        if p.total:
            mb = p.done / 1048576
            tmb = p.total / 1048576
            self.banner.label.setText(f"正在下载模型... {mb:.0f}/{tmb:.0f} MB")

    def _on_download_done(self, result):
        self.banner.progress.setValue(0)
        self.banner.progress.setVisible(False)
        self.banner.btn.setEnabled(True)
        self.banner.btn.setText("下载模型")
        if result.get("ok"):
            self.statusBar().showMessage("模型下载完成", 4000)
            self._refresh_model_state()
        else:
            self.banner.label.setText("模型下载已取消,点击重新下载")

    def _on_download_failed(self, err):
        self.banner.progress.setVisible(False)
        self.banner.btn.setEnabled(True)
        self.banner.btn.setText("下载模型")
        self.banner.label.setText(f"模型下载失败:{err.splitlines()[0] if err else ''} (请检查网络)")

    # ---------- 工具条动作 ----------
    def _start_current_tab(self):
        if self.tabs.currentIndex() == 0:
            self.image_tab.start()
        else:
            self.video_tab.start()

    def _import_files(self):
        if self.tabs.currentIndex() == 0:
            self.image_tab.import_dialog()
        else:
            self.video_tab.import_dialog()

    def _toggle_pause(self):
        tab = self.image_tab if self.tabs.currentIndex() == 0 else self.video_tab
        tab.toggle_pause()

    def _cancel_all(self):
        self.image_tab.cancel_all()
        self.video_tab.cancel_all()

    def _toggle_theme(self):
        self.config.theme = "light" if self.config.theme == "dark" else "dark"
        self.apply_theme(self.config.theme)
        self.config.save()

    def _export_logs(self):
        from bgremover.ui.dialogs import export_logs_dialog
        export_logs_dialog(self)

    def _open_logs(self):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from bgremover.core.config import logs_dir
        url = QUrl.fromLocalFile(str(logs_dir()))
        if not QDesktopServices.openUrl(url):
            self.statusBar().showMessage("无法打开日志目录", 5000)

    def apply_theme(self, theme: str):
        self.setStyleSheet(THEMES.get(theme, THEMES["dark"]))
        from bgremover.ui.settings import SettingsDialog
        SettingsDialog._current_theme = theme

    def _open_settings(self):
        from bgremover.ui.settings import SettingsDialog
        dlg = SettingsDialog(self.config, self)
        if dlg.exec():
            dlg.apply()
            self.apply_theme(self.config.theme)
            self.statusBar().showMessage("设置已保存", 3000)

    # ---------- 对外接口 ----------
    def set_start_state(self, enabled: bool):
        self.btn_start.setEnabled(enabled and self._model_ready)

    def set_running_state(self, running: bool):
        self.btn_import.setEnabled(not running)
        self.btn_pause.setEnabled(running)
        self.btn_cancel.setEnabled(running)
        self.btn_settings.setEnabled(not running)

    def show_total_progress(self, done, total, eta=0.0):
        if total > 0:
            self.total_progress.setVisible(True)
            self.total_progress.setRange(0, 1000)
            self.total_progress.setValue(int(done / total * 1000))
            from bgremover.core.util import format_duration
            if eta > 0:
                self.progress_label.setText(f"剩余 {format_duration(eta)}")
        else:
            self.total_progress.setVisible(False)
            self.progress_label.setText("")

    def log_line(self, msg: str):
        log.info("%s", msg)
