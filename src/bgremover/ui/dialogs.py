"""通用 UI 对话框:统一错误提示(摘要 + 明细 + 打开/导出日志目录)。"""
from __future__ import annotations


def export_logs_dialog(parent) -> None:
    """导出日志:让用户选择目标目录,把 app.log + error.log 复制进去。

    输出目录名为 bgremover_logs_<时间戳>,方便发给开发者排错。"""
    import os
    import shutil
    from datetime import datetime

    from PySide6.QtCore import QDir
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from bgremover.core.config import logs_dir

    dest = QFileDialog.getExistingDirectory(parent, "选择日志导出目录", QDir.homePath())
    if not dest:
        return
    src_dir = logs_dir()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(dest, f"bgremover_logs_{stamp}")
    os.makedirs(out_dir, exist_ok=True)
    copied = 0
    for fname in ("app.log", "error.log"):
        src = src_dir / fname
        if src.exists():
            shutil.copy2(str(src), out_dir)
            copied += 1
    if copied:
        QMessageBox.information(parent, "导出日志", f"已导出 {copied} 个日志文件到:\n{out_dir}")
    else:
        QMessageBox.information(parent, "导出日志", "日志目录为空,没有可导出的日志文件")


def show_error_dialog(parent, title: str, summary: str, detail_lines: list[str] | None = None,
                      max_lines: int = 8):
    """模态错误对话框:错误摘要 + 失败明细(限 max_lines 行)+「打开日志目录」「导出日志」按钮。

    批量处理失败时聚合为一条提示,避免每张/每个任务都弹窗。
    """
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox

    from bgremover.core.config import logs_dir

    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setText(summary)

    lines = detail_lines or []
    shown = [ln for ln in lines if ln.strip()][:max_lines]
    if shown:
        info = "\n".join(shown)
        if len(lines) > max_lines:
            info += f"\n… 等 {len(lines) - max_lines} 条未显示"
        box.setInformativeText(info)

    btn_logs = box.addButton("打开日志目录", QMessageBox.ButtonRole.ActionRole)
    btn_export = box.addButton("导出日志", QMessageBox.ButtonRole.ActionRole)
    box.addButton("确定", QMessageBox.ButtonRole.AcceptRole)
    box.exec()
    if box.clickedButton() is btn_logs:
        url = QUrl.fromLocalFile(str(logs_dir()))
        if not QDesktopServices.openUrl(url):
            QMessageBox.warning(parent, "提示", "无法打开日志目录")
    elif box.clickedButton() is btn_export:
        export_logs_dialog(parent)
