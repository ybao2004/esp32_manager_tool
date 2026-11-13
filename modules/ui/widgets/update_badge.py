# -*- coding: utf-8 -*-
"""
Huy hiệu dấu chấm đỏ thông báo có bản cập nhật mới (UpdateDotBadge).
Hiển thị góc trên bên phải các nút điều hướng / nút cập nhật và trên tiêu đề Tab.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QObject, QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QApplication, QWidget


_BADGE_RED = "#EF4444"
_BADGE_RING = "#FFFFFF"


def get_update_dot_icon(size: int = 10) -> QIcon:
    """Tạo QIcon hình chấm đỏ sắc nét dùng cho QTabBar."""
    app = QApplication.instance()
    dpr = app.devicePixelRatio() if app else 1.0
    pix_size = max(1, int(round(size * dpr)))

    pixmap = QPixmap(pix_size, pix_size)
    pixmap.fill(Qt.GlobalColor.transparent)
    pixmap.setDevicePixelRatio(dpr)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    margin = 1.0
    diameter = max(2.0, float(size) - margin * 2.0)
    painter.setPen(QPen(QColor(_BADGE_RING), 1.0))
    painter.setBrush(QColor(_BADGE_RED))
    painter.drawEllipse(QRectF(margin, margin, diameter, diameter))
    painter.end()

    return QIcon(pixmap)


class UpdateDotBadge(QWidget):
    """Widget dấu chấm đỏ gắn nổi ở góc trên bên phải một widget mục tiêu."""

    def __init__(
        self,
        target: QWidget,
        diameter: int = 10,
        margin_right: int = 5,
        margin_top: int = 4,
    ):
        super().__init__(target)
        self._target = target
        self._margin_right = int(margin_right)
        self._margin_top = int(margin_top)
        self._active = False

        self.setObjectName("UpdateDotBadge")
        self.setFixedSize(diameter, diameter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.hide()

        if target is not None:
            target.installEventFilter(self)
            self.reposition()

    def is_active(self) -> bool:
        return self._active

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        if self._active:
            self.reposition()
            self.show()
            self.raise_()
        else:
            self.hide()

    def reposition(self) -> None:
        if self._target is None:
            return
        w = max(self.width(), self._target.width())
        x = max(2, w - self.width() - self._margin_right)
        y = max(2, self._margin_top)
        self.move(x, y)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._target and event is not None:
            if event.type() in (
                QEvent.Type.Resize,
                QEvent.Type.Show,
                QEvent.Type.LayoutRequest,
            ):
                self.reposition()
                if self._active:
                    self.raise_()
        return super().eventFilter(watched, event)

    def paintEvent(self, event) -> None:
        if not self._active:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(1.0, 1.0, float(self.width() - 2), float(self.height() - 2))
        painter.setPen(QPen(QColor(_BADGE_RING), 1.2))
        painter.setBrush(QColor(_BADGE_RED))
        painter.drawEllipse(rect)
        painter.end()
