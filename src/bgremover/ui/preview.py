"""棋盘格透明预览组件(QGraphicsView)。"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QImage, QPixmap, QBrush, QColor, QPainter
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsPixmapItem

from bgremover.core.util import checkerboard_bgr


class TransparentPreview(QGraphicsView):
    """显示 RGBA 图像,以棋盘格衬托透明区域。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._item = QGraphicsPixmapItem()
        self._scene.addItem(self._item)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setBackgroundBrush(QBrush(QColor("#1b1b1b")))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._pixmap = QPixmap()

    def show_bgr(self, img_bgr, w, h):
        """显示 BGR ndarray。"""
        rgb = img_bgr.tobytes()
        qi = QImage(rgb, w, h, 3 * w, QImage.Format.Format_BGR888).copy()
        self._set_pixmap(QPixmap.fromImage(qi))

    def show_rgba(self, rgba):
        """显示 RGBA ndarray(H,W,4)。"""
        h, w = rgba.shape[:2]
        qi = QImage(rgba.tobytes(), w, h, 4 * w, QImage.Format.Format_RGBA8888).copy()
        self._set_pixmap(QPixmap.fromImage(qi))

    def show_checkerboard_bg(self, w, h):
        cb = checkerboard_bgr(w, h)
        qi = QImage(cb.tobytes(), w, h, 3 * w, QImage.Format.Format_BGR888).copy()
        self._set_pixmap(QPixmap.fromImage(qi))

    def show_pixmap(self, pm: QPixmap):
        self._set_pixmap(pm)

    def clear_image(self):
        self._pixmap = QPixmap()
        self._item.setPixmap(QPixmap())
        self._scene.setSceneRect(QRectF())

    def _set_pixmap(self, pm: QPixmap):
        self._pixmap = pm
        self._item.setPixmap(pm)
        self._scene.setSceneRect(QRectF(pm.rect()))
        self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
