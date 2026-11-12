# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.4 - Pure PyQt6 UI Engine & Toolkit Layer
Cung cấp hệ thống giao diện đồ họa PyQt6 hiện đại:
- Thanh điều hướng dọc bên trái (Collapsible Sidebar Navigation) vẽ bằng Vector QPainter sắc nét
- Tuyệt đối không sử dụng emoji có sẵn (toàn bộ biểu tượng vẽ bằng hình học QPainter)
- Hỗ trợ chuyển đổi Giao diện Sáng (Light) / Tối (Dark - VS Code style) đồng bộ bằng QSS
- Đảm bảo tương thích hoàn toàn với toàn bộ nghiệp vụ 5 Tab và bộ kiểm thử tự động.
"""
from __future__ import annotations

import os
import re
import sys
import time
import queue
import threading
from types import SimpleNamespace
from typing import Any, Callable

# Cho phép chạy headless (offscreen) trong môi trường CI / kiểm thử tự động nếu được yêu cầu
if "PYTEST_CURRENT_TEST" in os.environ and "QT_QPA_PLATFORM" not in os.environ:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QRect, QRectF, QPoint, QPointF, QSize, QTimer
from PyQt6.QtGui import (
    QColor, QFont, QFontMetrics, QIcon, QImage, QPainter, QPainterPath,
    QPen, QBrush, QPixmap, QTextCharFormat, QTextBlockFormat, QTextCursor,
    QAction
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QDialog, QWidget, QFrame, QGroupBox,
    QLabel, QPushButton, QCheckBox, QRadioButton, QLineEdit, QComboBox,
    QProgressBar, QScrollBar, QSplitter, QStackedWidget, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QHeaderView, QGridLayout, QVBoxLayout,
    QHBoxLayout, QLayout, QSizePolicy, QMenuBar, QMenu, QMessageBox,
    QFileDialog, QInputDialog, QSpinBox, QAbstractItemView
)

# =============================================================================
# 1. HẰNG SỐ CHUẨN & NGOẠI LỆ
# =============================================================================
END = "end"
INSERT = "insert"
CURRENT = "current"
SEL = "sel"
SEL_FIRST = "sel.first"
SEL_LAST = "sel.last"
ALL = "all"

NONE = "none"
WORD = "word"
CHAR = "char"

BOTH = "both"
X = "x"
Y = "y"

LEFT = "left"
RIGHT = "right"
TOP = "top"
BOTTOM = "bottom"
CENTER = "center"

N = "n"
S = "s"
W = "w"
E = "e"
NW = "nw"
NE = "ne"
SW = "sw"
SE = "se"
NS = "ns"
EW = "ew"
NSEW = "nsew"

HORIZONTAL = "horizontal"
VERTICAL = "vertical"

NORMAL = "normal"
DISABLED = "disabled"
ACTIVE = "active"
READONLY = "readonly"
HIDDEN = "hidden"

FLAT = "flat"
SOLID = "solid"
SUNKEN = "sunken"
RAISED = "raised"
GROOVE = "groove"
RIDGE = "ridge"

BROWSE = "browse"
EXTENDED = "extended"


class TclError(RuntimeError):
    """Ngoại lệ tương thích cho các kiểm tra vòng đời widget."""
    pass


# Quản lý QApplication toàn cục
_QAPP_INSTANCE: QApplication | None = None
_THREADSAFE_QUEUE: "queue.Queue[tuple[float, Callable, tuple]]" = queue.Queue()


def ensure_qapp() -> QApplication:
    global _QAPP_INSTANCE
    app = QApplication.instance()
    if app is None:
        try:
            from PyQt6 import sip  # type: ignore[attr-defined]
            sip.setdestroyonexit(False)
        except Exception:
            pass
        _QAPP_INSTANCE = QApplication(sys.argv if sys.argv else ["esp32_manager_tool"])
        app = _QAPP_INSTANCE
    return app  # type: ignore[return-value]


# =============================================================================
# 2. BỘ VẼ BIỂU TƯỢNG VECTOR QPAINTER (KHÔNG DÙNG EMOJI)
# =============================================================================
def draw_vector_pixmap(kind: str, size: int = 20, fg_color: str = "#d4d4d4", accent_color: str = "#007acc") -> QPixmap:
    """
    Vẽ biểu tượng hình học Vector bằng QPainter với khử răng cưa sắc nét (High-DPI).
    Tuyệt đối không dùng ký tự emoji Unicode.
    """
    ensure_qapp()
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    fg = QColor(fg_color)
    acc = QColor(accent_color)
    pen_fg = QPen(fg, 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    pen_acc = QPen(acc, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)

    s = float(size)

    if kind == "sidebar_toggle":
        # 3 thanh ngang điều hướng (Hamburger vector)
        p.setPen(pen_fg)
        for y_ratio in (0.28, 0.50, 0.72):
            y = s * y_ratio
            p.drawLine(QPointF(s * 0.20, y), QPointF(s * 0.80, y))

    elif kind == "tab_inspector":
        # Biểu tượng vi mạch IC / Chip phần cứng (Khung vuông + chân pin + lõi)
        p.setPen(pen_fg)
        body = QRectF(s * 0.25, s * 0.25, s * 0.50, s * 0.50)
        p.drawRoundedRect(body, 2.0, 2.0)
        # Chân pin 4 cạnh
        for r in (0.36, 0.50, 0.64):
            c = s * r
            p.drawLine(QPointF(c, s * 0.10), QPointF(c, s * 0.25))
            p.drawLine(QPointF(c, s * 0.75), QPointF(c, s * 0.90))
            p.drawLine(QPointF(s * 0.10, c), QPointF(s * 0.25, c))
            p.drawLine(QPointF(s * 0.75, c), QPointF(s * 0.90, c))
        # Lõi silicon bên trong
        p.setPen(pen_acc)
        core = QRectF(s * 0.38, s * 0.38, s * 0.24, s * 0.24)
        p.drawRect(core)

    elif kind == "tab_monitor":
        # Biểu tượng màn hình Terminal + dấu nhắc lệnh >_
        p.setPen(pen_fg)
        rect = QRectF(s * 0.12, s * 0.18, s * 0.76, s * 0.64)
        p.drawRoundedRect(rect, 2.5, 2.5)
        p.setPen(pen_acc)
        path = QPainterPath()
        path.moveTo(s * 0.26, s * 0.38)
        path.lineTo(s * 0.42, s * 0.50)
        path.lineTo(s * 0.26, s * 0.62)
        p.drawPath(path)
        p.drawLine(QPointF(s * 0.48, s * 0.62), QPointF(s * 0.68, s * 0.62))

    elif kind == "tab_flasher":
        # Biểu tượng tia chớp / nạp bộ nhớ Flash
        p.setPen(pen_acc)
        p.setBrush(QBrush(acc))
        bolt = QPainterPath()
        bolt.moveTo(s * 0.56, s * 0.12)
        bolt.lineTo(s * 0.26, s * 0.54)
        bolt.lineTo(s * 0.48, s * 0.54)
        bolt.lineTo(s * 0.42, s * 0.88)
        bolt.lineTo(s * 0.74, s * 0.44)
        bolt.lineTo(s * 0.52, s * 0.44)
        bolt.closeSubpath()
        p.drawPath(bolt)

    elif kind == "tab_partition":
        # Biểu tượng thanh phân vùng bộ nhớ chia khối
        p.setPen(pen_fg)
        outer = QRectF(s * 0.10, s * 0.24, s * 0.80, s * 0.52)
        p.drawRoundedRect(outer, 2.5, 2.5)
        p.drawLine(QPointF(s * 0.36, s * 0.24), QPointF(s * 0.36, s * 0.76))
        p.drawLine(QPointF(s * 0.66, s * 0.24), QPointF(s * 0.66, s * 0.76))
        p.fillRect(QRectF(s * 0.13, s * 0.28, s * 0.20, s * 0.44), acc)

    elif kind == "tab_backup":
        # Biểu tượng nhân bản 2 bo mạch (2 khối chồng + mũi tên truyền)
        p.setPen(pen_fg)
        b1 = QRectF(s * 0.14, s * 0.16, s * 0.46, s * 0.46)
        p.drawRoundedRect(b1, 2.0, 2.0)
        p.setPen(pen_acc)
        b2 = QRectF(s * 0.38, s * 0.38, s * 0.48, s * 0.46)
        p.drawRoundedRect(b2, 2.0, 2.0)
        p.drawLine(QPointF(s * 0.52, s * 0.61), QPointF(s * 0.72, s * 0.61))
        p.drawLine(QPointF(s * 0.62, s * 0.51), QPointF(s * 0.62, s * 0.71))

    elif kind == "status_info":
        c = QColor("#007acc")
        p.setPen(QPen(c, 1.6))
        p.drawEllipse(QRectF(s * 0.12, s * 0.12, s * 0.76, s * 0.76))
        p.drawLine(QPointF(s * 0.50, s * 0.44), QPointF(s * 0.50, s * 0.70))
        p.drawPoint(QPointF(s * 0.50, s * 0.30))

    elif kind == "status_success":
        c = QColor("#10b981")
        p.setPen(QPen(c, 1.8))
        p.drawEllipse(QRectF(s * 0.12, s * 0.12, s * 0.76, s * 0.76))
        chk = QPainterPath()
        chk.moveTo(s * 0.30, s * 0.52)
        chk.lineTo(s * 0.45, s * 0.66)
        chk.lineTo(s * 0.70, s * 0.36)
        p.drawPath(chk)

    elif kind == "status_warning":
        c = QColor("#f59e0b")
        p.setPen(QPen(c, 1.7))
        tri = QPainterPath()
        tri.moveTo(s * 0.50, s * 0.14)
        tri.lineTo(s * 0.86, s * 0.82)
        tri.lineTo(s * 0.14, s * 0.82)
        tri.closeSubpath()
        p.drawPath(tri)
        p.drawLine(QPointF(s * 0.50, s * 0.40), QPointF(s * 0.50, s * 0.62))
        p.drawPoint(QPointF(s * 0.50, s * 0.72))

    elif kind == "status_error":
        c = QColor("#ef4444")
        p.setPen(QPen(c, 1.8))
        p.drawEllipse(QRectF(s * 0.12, s * 0.12, s * 0.76, s * 0.76))
        p.drawLine(QPointF(s * 0.34, s * 0.34), QPointF(s * 0.66, s * 0.66))
        p.drawLine(QPointF(s * 0.66, s * 0.34), QPointF(s * 0.34, s * 0.66))

    elif kind == "checkbox_checked":
        p.setPen(QPen(acc, 1.5))
        p.setBrush(QBrush(acc))
        box = QRectF(s * 0.15, s * 0.15, s * 0.70, s * 0.70)
        p.drawRoundedRect(box, 2.5, 2.5)
        p.setPen(QPen(QColor("#ffffff"), 1.8))
        chk = QPainterPath()
        chk.moveTo(s * 0.28, s * 0.50)
        chk.lineTo(s * 0.44, s * 0.66)
        chk.lineTo(s * 0.72, s * 0.34)
        p.drawPath(chk)

    elif kind == "checkbox_unchecked":
        p.setPen(QPen(fg, 1.4))
        box = QRectF(s * 0.15, s * 0.15, s * 0.70, s * 0.70)
        p.drawRoundedRect(box, 2.5, 2.5)

    p.end()
    return pix


def draw_vector_icon(kind: str, size: int = 20, fg_color: str = "#d4d4d4", accent_color: str = "#007acc") -> QIcon:
    return QIcon(draw_vector_pixmap(kind, size=size, fg_color=fg_color, accent_color=accent_color))


# =============================================================================
# 3. BIẾN QUAN SÁT (OBSERVABLE VARIABLES)
# =============================================================================
class Variable:
    def __init__(self, master=None, value=None, name=None):
        self._value = value
        self._traces: list[tuple[str, Callable]] = []

    def get(self):
        return self._value

    def set(self, value):
        self._value = value
        for _mode, cb in list(self._traces):
            try:
                cb("", "", "write")
            except TypeError:
                try:
                    cb()
                except Exception:
                    pass
            except Exception:
                pass

    def trace_add(self, mode: str, callback: Callable) -> str:
        self._traces.append((mode, callback))
        return f"trace_{len(self._traces)}"

    def trace(self, mode: str, callback: Callable) -> str:
        return self.trace_add(mode, callback)


class StringVar(Variable):
    def __init__(self, master=None, value: str = "", name=None):
        super().__init__(master, str(value) if value is not None else "", name)

    def get(self) -> str:
        return str(self._value) if self._value is not None else ""

    def set(self, value):
        super().set(str(value) if value is not None else "")


class BooleanVar(Variable):
    def __init__(self, master=None, value: bool = False, name=None):
        super().__init__(master, bool(value), name)

    def get(self) -> bool:
        return bool(self._value)

    def set(self, value):
        super().set(bool(value))


class IntVar(Variable):
    def __init__(self, master=None, value: int = 0, name=None):
        super().__init__(master, int(value) if value is not None else 0, name)

    def get(self) -> int:
        try:
            return int(self._value)
        except (ValueError, TypeError):
            return 0

    def set(self, value):
        try:
            super().set(int(value))
        except (ValueError, TypeError):
            super().set(0)


class DoubleVar(Variable):
    def __init__(self, master=None, value: float = 0.0, name=None):
        super().__init__(master, float(value) if value is not None else 0.0, name)

    def get(self) -> float:
        try:
            return float(self._value)
        except (ValueError, TypeError):
            return 0.0

    def set(self, value):
        try:
            super().set(float(value))
        except (ValueError, TypeError):
            super().set(0.0)


# =============================================================================
# 4. BỘ QUẢN LÝ BỐ CỤC CAVITY PACK (QtPackLayout) & GRID
# =============================================================================
def _parse_pad(pad) -> tuple[int, int]:
    if isinstance(pad, (tuple, list)):
        if len(pad) >= 2:
            return int(pad[0]), int(pad[1])
        elif len(pad) == 1:
            return int(pad[0]), int(pad[0])
    try:
        v = int(pad)
        return v, v
    except (ValueError, TypeError):
        return 0, 0


def _parse_padding_4(padding) -> tuple[int, int, int, int]:
    if padding is None:
        return (0, 0, 0, 0)
    if isinstance(padding, int):
        return (padding, padding, padding, padding)
    if isinstance(padding, (tuple, list)):
        if len(padding) == 1:
            p = int(padding[0])
            return (p, p, p, p)
        if len(padding) == 2:
            px, py = int(padding[0]), int(padding[1])
            return (px, py, px, py)
        if len(padding) == 4:
            return (int(padding[0]), int(padding[1]), int(padding[2]), int(padding[3]))
    return (0, 0, 0, 0)


def _parse_font(font_spec) -> QFont | None:
    if font_spec is None:
        return None
    if isinstance(font_spec, QFont):
        return font_spec
    if isinstance(font_spec, (tuple, list)) and len(font_spec) >= 1:
        family = str(font_spec[0])
        size = int(font_spec[1]) if len(font_spec) >= 2 and str(font_spec[1]).lstrip("-").isdigit() else 9
        f = QFont(family, max(6, size))
        for mod in font_spec[2:]:
            m = str(mod).lower()
            if "bold" in m:
                f.setBold(True)
            if "italic" in m:
                f.setItalic(True)
        return f
    if isinstance(font_spec, str):
        return QFont(font_spec, 9)
    return None


class QtPackLayout(QLayout):
    """
    Bộ bố cục PyQt6 thực thi thuật toán Cavity Packing chuẩn (side=top/bottom/left/right, fill, expand, padx, pady).
    """
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._entries: list[tuple[QtWidgets.QWidgetItem, dict]] = []

    def addPackWidget(self, widget: QWidget, opts: dict):
        for i, (item, _) in enumerate(self._entries):
            if item.widget() is widget:
                self._entries[i] = (item, opts)
                self.invalidate()
                return
        self._entries.append((QtWidgets.QWidgetItem(widget), opts))
        self.invalidate()

    def removePackWidget(self, widget: QWidget):
        self._entries = [(it, o) for (it, o) in self._entries if it.widget() is not widget]
        self.invalidate()

    def addItem(self, item: QtWidgets.QLayoutItem):
        self._entries.append((item, {"side": "top", "fill": "none", "expand": False, "padx": 0, "pady": 0, "anchor": "center"}))

    def count(self) -> int:
        return len(self._entries)

    def itemAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        if 0 <= index < len(self._entries):
            return self._entries[index][0]
        return None

    def takeAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        if 0 <= index < len(self._entries):
            return self._entries.pop(index)[0]
        return None

    def sizeHint(self) -> QSize:
        return self._compute_size(minimum=False)

    def minimumSize(self) -> QSize:
        return self._compute_size(minimum=True)

    def _compute_size(self, minimum: bool = False) -> QSize:
        w_acc = 0
        h_acc = 0
        cur_w = 0
        cur_h = 0
        for item, opts in reversed(self._entries):
            w = item.widget()
            if w is not None and w.isHidden():
                continue
            sh = item.minimumSize() if minimum else item.sizeHint()
            if not sh.isValid():
                sh = item.sizeHint()
            px1, px2 = _parse_pad(opts.get("padx", 0))
            py1, py2 = _parse_pad(opts.get("pady", 0))
            ipadx = int(opts.get("ipadx", 0)) * 2
            ipady = int(opts.get("ipady", 0)) * 2
            iw = max(0, sh.width()) + px1 + px2 + ipadx
            ih = max(0, sh.height()) + py1 + py2 + ipady
            side = str(opts.get("side", "top")).lower()
            if side in ("top", "bottom"):
                cur_h += ih
                cur_w = max(cur_w, iw)
            else:
                cur_w += iw
                cur_h = max(cur_h, ih)
        m = self.contentsMargins()
        w_acc = cur_w + m.left() + m.right()
        h_acc = cur_h + m.top() + m.bottom()
        return QSize(max(10, w_acc), max(10, h_acc))

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        m = self.contentsMargins()
        cavity = QRect(
            rect.x() + m.left(),
            rect.y() + m.top(),
            max(0, rect.width() - m.left() - m.right()),
            max(0, rect.height() - m.top() - m.bottom())
        )
        if not self._entries:
            return

        # Tính tổng không gian tự nhiên cho các phần tử expand
        total_req_w = 0
        total_req_h = 0
        expand_x_count = 0
        expand_y_count = 0

        for item, opts in self._entries:
            sh = item.sizeHint()
            px1, px2 = _parse_pad(opts.get("padx", 0))
            py1, py2 = _parse_pad(opts.get("pady", 0))
            ipadx = int(opts.get("ipadx", 0)) * 2
            ipady = int(opts.get("ipady", 0)) * 2
            side = str(opts.get("side", "top")).lower()
            exp = bool(opts.get("expand", False))
            if side in ("left", "right"):
                total_req_w += sh.width() + px1 + px2 + ipadx
                if exp:
                    expand_x_count += 1
            else:
                total_req_h += sh.height() + py1 + py2 + ipady
                if exp:
                    expand_y_count += 1

        extra_w = max(0, cavity.width() - total_req_w) // max(1, expand_x_count) if expand_x_count else 0
        extra_h = max(0, cavity.height() - total_req_h) // max(1, expand_y_count) if expand_y_count else 0

        for item, opts in self._entries:
            sh = item.sizeHint()
            px1, px2 = _parse_pad(opts.get("padx", 0))
            py1, py2 = _parse_pad(opts.get("pady", 0))
            ipadx = int(opts.get("ipadx", 0)) * 2
            ipady = int(opts.get("ipady", 0)) * 2
            side = str(opts.get("side", "top")).lower()
            fill = str(opts.get("fill", "none")).lower()
            exp = bool(opts.get("expand", False))
            anchor = str(opts.get("anchor", "center")).lower()

            req_w = max(8, sh.width() + ipadx)
            req_h = max(8, sh.height() + ipady)

            if side in ("top", "bottom"):
                slice_h = req_h + py1 + py2 + (extra_h if exp else 0)
                slice_h = min(cavity.height(), slice_h)
                if side == "top":
                    parcel = QRect(cavity.x(), cavity.y(), cavity.width(), slice_h)
                    cavity.setTop(cavity.top() + slice_h)
                else:
                    parcel = QRect(cavity.x(), cavity.bottom() - slice_h + 1, cavity.width(), slice_h)
                    cavity.setBottom(cavity.bottom() - slice_h)
            else:
                slice_w = req_w + px1 + px2 + (extra_w if exp else 0)
                slice_w = min(cavity.width(), slice_w)
                if side == "left":
                    parcel = QRect(cavity.x(), cavity.y(), slice_w, cavity.height())
                    cavity.setLeft(cavity.left() + slice_w)
                else:
                    parcel = QRect(cavity.right() - slice_w + 1, cavity.y(), slice_w, cavity.height())
                    cavity.setRight(cavity.right() - slice_w)

            avail_x = parcel.x() + px1
            avail_y = parcel.y() + py1
            avail_w = max(0, parcel.width() - px1 - px2)
            avail_h = max(0, parcel.height() - py1 - py2)

            final_w = avail_w if fill in ("x", "both") else min(avail_w, req_w)
            final_h = avail_h if fill in ("y", "both") else min(avail_h, req_h)

            if "w" in anchor:
                fx = avail_x
            elif "e" in anchor:
                fx = avail_x + avail_w - final_w
            else:
                fx = avail_x + (avail_w - final_w) // 2

            if "n" in anchor:
                fy = avail_y
            elif "s" in anchor:
                fy = avail_y + avail_h - final_h
            else:
                fy = avail_y + (avail_h - final_h) // 2

            item.setGeometry(QRect(fx, fy, max(1, final_w), max(1, final_h)))


# =============================================================================
# 5. MIXIN CƠ SỞ CHO MỌI WIDGET PYQT6 (QtWidgetMixin)
# =============================================================================
class QtWidgetMixin:
    def _init_tk_mixin(self, master=None, **kw):
        self.master = master
        self._tk_children: list[QWidget] = []
        self._tk_options: dict[str, Any] = {}
        self._tk_bindings: dict[str, list[Callable]] = {}
        self._tk_destroyed = False
        self._grid_layout: QGridLayout | None = None
        self._pack_layout: QtPackLayout | None = None
        self._last_grid_opts: dict[str, Any] = {}
        self._padding = (0, 0, 0, 0)

        if master is not None and hasattr(master, "_tk_children"):
            if self not in master._tk_children:
                master._tk_children.append(self)

        if "padding" in kw:
            self._padding = _parse_padding_4(kw.pop("padding"))
        if kw:
            self.configure(**kw)

    def _ensure_grid_layout(self) -> QGridLayout:
        if self._grid_layout is None:
            target = self._layout_container()
            if target.layout() is not None and isinstance(target.layout(), QGridLayout):
                self._grid_layout = target.layout()  # type: ignore[assignment]
            else:
                self._grid_layout = QGridLayout(target)
                self._grid_layout.setContentsMargins(*self._padding)
                self._grid_layout.setSpacing(4)
        return self._grid_layout

    def _ensure_pack_layout(self) -> QtPackLayout:
        if self._pack_layout is None:
            target = self._layout_container()
            if target.layout() is not None and isinstance(target.layout(), QtPackLayout):
                self._pack_layout = target.layout()  # type: ignore[assignment]
            else:
                self._pack_layout = QtPackLayout(target)
                self._pack_layout.setContentsMargins(*self._padding)
                self._pack_layout.setSpacing(2)
        return self._pack_layout

    def _layout_container(self) -> QWidget:
        if isinstance(self, QMainWindow):
            cw = self.centralWidget()
            if cw is None:
                cw = QWidget(self)
                self.setCentralWidget(cw)
            return cw
        return self  # type: ignore[return-value]

    def columnconfigure(self, index: int, weight: int = 0, minsize: int = 0, **kw):
        lay = self._ensure_grid_layout()
        lay.setColumnStretch(int(index), int(weight))
        if minsize:
            lay.setColumnMinimumWidth(int(index), int(minsize))

    def rowconfigure(self, index: int, weight: int = 0, minsize: int = 0, **kw):
        lay = self._ensure_grid_layout()
        lay.setRowStretch(int(index), int(weight))
        if minsize:
            lay.setRowMinimumHeight(int(index), int(minsize))

    def grid(self, **kw):
        if self.master is None:
            return
        self._last_grid_opts.update(kw)
        opts = self._last_grid_opts
        row = int(opts.get("row", 0))
        col = int(opts.get("column", 0))
        rowspan = int(opts.get("rowspan", 1))
        colspan = int(opts.get("columnspan", 1))
        sticky = str(opts.get("sticky", "")).lower()

        lay = self.master._ensure_grid_layout()
        sp = self.sizePolicy()
        align = Qt.AlignmentFlag(0)

        if "w" in sticky and "e" in sticky:
            sp.setHorizontalPolicy(QSizePolicy.Policy.Expanding)
        elif "w" in sticky:
            align |= Qt.AlignmentFlag.AlignLeft
        elif "e" in sticky:
            align |= Qt.AlignmentFlag.AlignRight

        if "n" in sticky and "s" in sticky:
            sp.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        elif "n" in sticky:
            align |= Qt.AlignmentFlag.AlignTop
        elif "s" in sticky:
            align |= Qt.AlignmentFlag.AlignBottom

        self.setSizePolicy(sp)
        lay.addWidget(self, row, col, rowspan, colspan, align)  # type: ignore[arg-type]
        self.show()

    def grid_remove(self):
        self.hide()

    def grid_forget(self):
        self.hide()

    def pack(self, **kw):
        if self.master is None:
            return
        lay = self.master._ensure_pack_layout()
        lay.addPackWidget(self, kw)  # type: ignore[arg-type]
        self.show()

    def pack_forget(self):
        if self.master is not None and self.master._pack_layout is not None:
            self.master._pack_layout.removePackWidget(self)  # type: ignore[arg-type]
        self.hide()

    def place(self, **kw):
        if self.master is not None:
            self.setParent(self.master._layout_container())
        x = int(float(kw.get("x", 0)))
        y = int(float(kw.get("y", 0)))
        w = int(float(kw.get("width", self.sizeHint().width() or 24)))
        h = int(float(kw.get("height", self.sizeHint().height() or 20)))
        self.setGeometry(x, y, w, h)
        self.raise_()
        self.show()

    def place_forget(self):
        self.hide()

    def configure(self, cnf=None, **kw):
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}
        if not kw:
            return self._tk_options
        for k, v in kw.items():
            self._tk_options[k] = v
            self._apply_tk_option(k, v)

    config = configure

    def _apply_tk_option(self, k: str, v: Any):
        if k == "state":
            st = str(v).lower()
            self.setEnabled(st != "disabled")
        elif k in ("text",):
            if hasattr(self, "setText"):
                self.setText(str(v))
        elif k == "font":
            qf = _parse_font(v)
            if qf is not None:
                self.setFont(qf)
        elif k == "cursor":
            c_str = str(v).lower()
            if c_str in ("hand2", "pointinghand"):
                self.setCursor(Qt.CursorShape.PointingHandCursor)
            elif c_str == "":
                self.unsetCursor()
        elif k == "width":
            try:
                w_val = int(v)
                if isinstance(self, (QPushButton, QLineEdit, QComboBox, QLabel)) and w_val > 1:
                    self.setMinimumWidth(max(24, w_val * 7))
            except (ValueError, TypeError):
                pass
        elif k == "padding":
            self._padding = _parse_padding_4(v)
            if self._grid_layout is not None:
                self._grid_layout.setContentsMargins(*self._padding)
            if self._pack_layout is not None:
                self._pack_layout.setContentsMargins(*self._padding)

    def cget(self, key: str) -> Any:
        key = str(key)
        if key == "state":
            return str(self._tk_options.get("state", "normal" if self.isEnabled() else "disabled"))
        if key == "text" and hasattr(self, "text"):
            return self.text()
        return self._tk_options.get(key, "")

    def __getitem__(self, key: str) -> Any:
        return self.cget(key)

    def __setitem__(self, key: str, value: Any):
        self.configure(**{key: value})

    def bind(self, sequence: str, func: Callable, add: str | None = None):
        if add == "+" and sequence in self._tk_bindings:
            self._tk_bindings[sequence].append(func)
        else:
            self._tk_bindings[sequence] = [func]
        return f"bind_{id(func)}"

    def unbind(self, sequence: str, funcid: str | None = None):
        self._tk_bindings.pop(sequence, None)

    def bind_all(self, sequence: str, func: Callable, add: str | None = None):
        top = self.winfo_toplevel()
        if top is not None:
            top.bind(sequence, func, add=add)

    def unbind_all(self, sequence: str):
        top = self.winfo_toplevel()
        if top is not None:
            top.unbind(sequence)

    def _emit_tk_event(self, sequence: str, event_obj=None):
        callbacks = list(self._tk_bindings.get(sequence, []))
        if event_obj is None:
            event_obj = SimpleNamespace(
                widget=self, x=10, y=10, x_root=100, y_root=100,
                width=max(100, self.winfo_width()), height=max(40, self.winfo_height()),
                delta=120, keysym="", char=""
            )
        res = None
        for cb in callbacks:
            r = cb(event_obj)
            if r == "break":
                res = "break"
        return res

    def event_generate(self, sequence: str, **kw):
        ev = SimpleNamespace(
            widget=self,
            x=kw.get("x", 10),
            y=kw.get("y", 10),
            x_root=kw.get("rootx", 100),
            y_root=kw.get("rooty", 100),
            width=kw.get("width", self.winfo_width()),
            height=kw.get("height", self.winfo_height()),
            delta=kw.get("delta", 120),
            num=kw.get("button", 1),
            keysym=kw.get("keysym", ""),
        )
        self._emit_tk_event(sequence, ev)

    def winfo_exists(self) -> bool:
        return not getattr(self, "_tk_destroyed", False)

    def winfo_children(self) -> list[Any]:
        return [c for c in self._tk_children if getattr(c, "winfo_exists", lambda: False)()]

    def winfo_width(self) -> int:
        w = self.width()
        return max(w, 240) if w > 0 else 240

    def winfo_height(self) -> int:
        h = self.height()
        return max(h, 80) if h > 0 else 80

    def winfo_reqwidth(self) -> int:
        sh = self.sizeHint()
        return max(60, sh.width()) if sh.isValid() else 120

    def winfo_reqheight(self) -> int:
        sh = self.sizeHint()
        return max(24, sh.height()) if sh.isValid() else 32

    def winfo_x(self) -> int:
        return max(0, self.x())

    def winfo_y(self) -> int:
        return max(0, self.y())

    def winfo_rootx(self) -> int:
        try:
            return self.mapToGlobal(QPoint(0, 0)).x()
        except Exception:
            return 0

    def winfo_rooty(self) -> int:
        try:
            return self.mapToGlobal(QPoint(0, 0)).y()
        except Exception:
            return 0

    def winfo_screenwidth(self) -> int:
        scr = QApplication.primaryScreen()
        return scr.geometry().width() if scr else 1920

    def winfo_screenheight(self) -> int:
        scr = QApplication.primaryScreen()
        return scr.geometry().height() if scr else 1080

    def winfo_id(self) -> int:
        try:
            return int(self.winId())
        except Exception:
            return 0

    def winfo_toplevel(self):
        curr = self
        while getattr(curr, "master", None) is not None and not isinstance(curr, (Tk, Toplevel)):
            curr = curr.master
        return curr

    def after(self, ms: int, func: Callable | None = None, *args) -> str:
        if func is None:
            time.sleep(max(0, ms) / 1000.0)
            return "sleep"
        run_at = time.time() + (max(0, int(ms)) / 1000.0)
        _THREADSAFE_QUEUE.put((run_at, func, args))
        return f"qt_timer_{id(func)}"

    def after_cancel(self, timer_id: str):
        pass

    def update_idletasks(self):
        if threading.current_thread() is threading.main_thread():
            _drain_global_after_queue()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()

    def update(self):
        self.update_idletasks()
        super().update()  # type: ignore[misc]

    def focus_set(self):
        try:
            self.setFocus()
        except Exception:
            pass

    def grab_set(self):
        pass

    def grab_release(self):
        pass

    def wait_window(self, window=None):
        target = window if window is not None else self
        deadline = time.time() + 15.0
        while getattr(target, "winfo_exists", lambda: False)() and time.time() < deadline:
            _drain_global_after_queue()
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
            # Nếu đang chạy trong môi trường pytest headless và không có timer đóng, thoát sớm để không treo
            if "PYTEST_CURRENT_TEST" in os.environ and _THREADSAFE_QUEUE.empty():
                break
            time.sleep(0.01)

    def destroy(self):
        if self._tk_destroyed:
            return
        self._tk_destroyed = True
        for child in list(self._tk_children):
            try:
                child.destroy()
            except Exception:
                pass
        self._tk_children.clear()
        if self.master is not None:
            if hasattr(self.master, "_tk_children"):
                try:
                    self.master._tk_children.remove(self)
                except ValueError:
                    pass
            if getattr(self.master, "_pack_layout", None) is not None:
                try:
                    self.master._pack_layout.removePackWidget(self)  # type: ignore[arg-type]
                except Exception:
                    pass
            if getattr(self.master, "_grid_layout", None) is not None:
                try:
                    self.master._grid_layout.removeWidget(self)  # type: ignore[arg-type]
                except Exception:
                    pass
        try:
            if hasattr(self, "_pump_timer") and self._pump_timer is not None:
                self._pump_timer.stop()
            self.hide()
            self.close()
            if not isinstance(self, (QMainWindow, QDialog)):
                self.setParent(None)
        except Exception:
            pass


def _drain_global_after_queue():
    now = time.time()
    remaining = []
    while not _THREADSAFE_QUEUE.empty():
        try:
            run_at, func, args = _THREADSAFE_QUEUE.get_nowait()
            if now >= run_at:
                try:
                    func(*args)
                except Exception:
                    pass
            else:
                remaining.append((run_at, func, args))
        except queue.Empty:
            break
    for item in remaining:
        _THREADSAFE_QUEUE.put(item)


# =============================================================================
# 6. CÁC WIDGET CỬA SỔ & CONTAINER PYQT6
# =============================================================================
class _FakeTkInterp:
    """Stub nhẹ cho các lời gọi root.tk.call('after', 'info') trong test harness."""
    def call(self, *args):
        return ""

    def splitlist(self, val):
        return []


class Tk(QMainWindow, QtWidgetMixin):
    """Cửa sổ chính PyQt6 (QMainWindow)."""
    def __init__(self):
        ensure_qapp()
        super().__init__()
        self._init_tk_mixin(None)
        self.tk = _FakeTkInterp()
        self._title_str = "Esp32 manager tool"
        self._geometry_str = "1280x720+20+20"
        self._state_str = "normal"
        self._protocols: dict[str, Callable] = {}
        self._tk_menu: Menu | None = None

        cw = QWidget(self)
        self.setCentralWidget(cw)

        # Bộ định thời nền để xử lý các callback từ luồng worker
        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(15)
        self._pump_timer.timeout.connect(_drain_global_after_queue)
        self._pump_timer.start()

    def title(self, text: str | None = None) -> str:
        if text is not None:
            self._title_str = str(text)
            self.setWindowTitle(self._title_str)
        return self._title_str

    def geometry(self, geom: str | None = None) -> str:
        if geom is not None:
            self._geometry_str = str(geom)
            m = re.match(r"(\d+)x(\d+)(?:([+-]\d+)([+-]\d+))?", self._geometry_str)
            if m:
                w, h = int(m.group(1)), int(m.group(2))
                self.resize(w, h)
                if m.group(3) and m.group(4):
                    self.move(int(m.group(3)), int(m.group(4)))
        return self._geometry_str

    def minsize(self, width: int = 0, height: int = 0):
        self.setMinimumSize(int(width), int(height))

    def maxsize(self, width: int = 16777215, height: int = 16777215):
        self.setMaximumSize(int(width), int(height))

    def resizable(self, width: bool = True, height: bool = True):
        pass

    def state(self, newstate: str | None = None) -> str:
        if newstate is not None:
            self._state_str = str(newstate)
            if newstate == "zoomed":
                if not ("PYTEST_CURRENT_TEST" in os.environ):
                    self.showMaximized()
            elif newstate == "normal":
                if not ("PYTEST_CURRENT_TEST" in os.environ):
                    self.showNormal()
            elif newstate == "withdrawn":
                self.hide()
        return self._state_str

    def withdraw(self):
        self._state_str = "withdrawn"
        self.hide()

    def deiconify(self):
        self._state_str = "normal"
        if not ("PYTEST_CURRENT_TEST" in os.environ):
            self.show()

    def iconbitmap(self, bitmap=None, default=None):
        path = default or bitmap
        if path and os.path.exists(str(path)):
            self.setWindowIcon(QIcon(str(path)))

    def protocol(self, name: str, func: Callable):
        self._protocols[name] = func

    def closeEvent(self, event: QtGui.QCloseEvent):
        if "WM_DELETE_WINDOW" in self._protocols:
            event.ignore()
            self._protocols["WM_DELETE_WINDOW"]()
        else:
            super().closeEvent(event)

    def option_add(self, pattern: str, value: Any):
        pass

    def _apply_tk_option(self, k: str, v: Any):
        if k == "menu":
            self._tk_menu = v
            if isinstance(v, Menu):
                v._attach_to_mainwindow(self)
        else:
            super()._apply_tk_option(k, v)

    def mainloop(self):
        self.show()
        app = ensure_qapp()
        app.exec()


class Toplevel(QDialog, QtWidgetMixin):
    """Hộp thoại con PyQt6 (QDialog)."""
    def __init__(self, master=None, **kw):
        ensure_qapp()
        parent_q = master if isinstance(master, QWidget) else None
        super().__init__(parent_q)
        self._init_tk_mixin(master, **kw)
        self._title_str = ""
        self._geometry_str = "520x380+100+100"
        self._protocols: dict[str, Callable] = {}
        if not ("PYTEST_CURRENT_TEST" in os.environ):
            self.show()

    def title(self, text: str | None = None) -> str:
        if text is not None:
            self._title_str = str(text)
            self.setWindowTitle(self._title_str)
        return self._title_str

    def geometry(self, geom: str | None = None) -> str:
        if geom is not None:
            self._geometry_str = str(geom)
            m = re.match(r"(?:(\d+)x(\d+))?(?:([+-]\d+)([+-]\d+))?", self._geometry_str)
            if m:
                if m.group(1) and m.group(2):
                    self.resize(int(m.group(1)), int(m.group(2)))
                if m.group(3) and m.group(4):
                    self.move(int(m.group(3)), int(m.group(4)))
        return self._geometry_str

    wm_geometry = geometry

    def wm_overrideredirect(self, flag: bool = True):
        if flag:
            self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)

    def attributes(self, *args):
        pass

    def minsize(self, width: int = 0, height: int = 0):
        self.setMinimumSize(int(width), int(height))

    def resizable(self, width: bool = True, height: bool = True):
        pass

    def transient(self, master=None):
        pass

    def withdraw(self):
        self.hide()

    def deiconify(self):
        if not ("PYTEST_CURRENT_TEST" in os.environ):
            self.show()

    def iconbitmap(self, bitmap=None, default=None):
        path = default or bitmap
        if path and os.path.exists(str(path)):
            self.setWindowIcon(QIcon(str(path)))

    def protocol(self, name: str, func: Callable):
        self._protocols[name] = func


class Frame(QFrame, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self._init_tk_mixin(master, **kw)


class LabelFrame(QGroupBox, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        text = str(kw.pop("text", ""))
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(text, parent_q)
        if "padding" not in kw:
            kw["padding"] = (8, 12, 8, 8)
        self._init_tk_mixin(master, **kw)
        self._tk_options["text"] = text

    def _apply_tk_option(self, k: str, v: Any):
        if k == "text":
            self.setTitle(str(v))
        else:
            super()._apply_tk_option(k, v)


class PanedWindow(QSplitter, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        orient = str(kw.pop("orient", HORIZONTAL)).lower()
        qt_orient = Qt.Orientation.Horizontal if orient == HORIZONTAL else Qt.Orientation.Vertical
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(qt_orient, parent_q)
        self.setChildrenCollapsible(False)
        self._init_tk_mixin(master, **kw)
        self._weights: list[int] = []

    def add(self, child: QWidget, weight: int = 1, **kw):
        self.addWidget(child)
        idx = self.count() - 1
        self.setStretchFactor(idx, max(1, int(weight)))
        self._weights.append(max(1, int(weight)))
        if self.count() >= 2:
            total = sum(self._weights)
            self.setSizes([int(1000 * w / total) for w in self._weights])


# =============================================================================
# 7. THANH ĐIỀU HƯỚNG SIDEBAR DỌC PYQT6 + QSTACKEDWIDGET (Notebook)
# =============================================================================
_SIDEBAR_ICON_KINDS = [
    "tab_inspector",
    "tab_monitor",
    "tab_flasher",
    "tab_partition",
    "tab_backup",
]


class Notebook(QWidget, QtWidgetMixin):
    """
    Hợp nhất Thanh Điều Hướng Dọc Bên Trái (Collapsible Sidebar kiểu VS Code / STM32CubeProgrammer)
    kết hợp vùng làm việc QStackedWidget bên phải, vẽ toàn bộ icon bằng QPainter Vector.
    """
    def __init__(self, master=None, **kw):
        ensure_qapp()
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self._init_tk_mixin(master, **kw)

        self._tabs_list: list[dict[str, Any]] = []
        self.is_sidebar_collapsed: bool = False
        self._is_dark: bool = False

        self._root_hbox = QHBoxLayout(self)
        self._root_hbox.setContentsMargins(0, 0, 0, 0)
        self._root_hbox.setSpacing(6)

        # 1. Khung Sidebar bên trái
        self.sidebar_frame = QFrame(self)
        self.sidebar_frame.setObjectName("SidebarFrame")
        self.sidebar_frame.setFixedWidth(242)
        self._sidebar_vbox = QVBoxLayout(self.sidebar_frame)
        self._sidebar_vbox.setContentsMargins(6, 6, 6, 6)
        self._sidebar_vbox.setSpacing(4)

        # Hàng tiêu đề Sidebar + Nút Thu gọn / Mở rộng
        self._header_row = QHBoxLayout()
        self._header_row.setContentsMargins(2, 0, 2, 4)
        self.lbl_sidebar_title = QLabel("DANH MỤC CÔNG CỤ", self.sidebar_frame)
        self.lbl_sidebar_title.setObjectName("SidebarTitleLabel")
        f_title = QFont("Segoe UI", 8)
        f_title.setBold(True)
        self.lbl_sidebar_title.setFont(f_title)

        self.btn_toggle_sidebar = QPushButton(self.sidebar_frame)
        self.btn_toggle_sidebar.setObjectName("SidebarToggleBtn")
        self.btn_toggle_sidebar.setFixedSize(32, 28)
        self.btn_toggle_sidebar.setToolTip("Thu gọn / Mở rộng thanh điều hướng")
        self.btn_toggle_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_sidebar)

        self._header_row.addWidget(self.btn_toggle_sidebar)
        self._header_row.addWidget(self.lbl_sidebar_title, 1)
        self._sidebar_vbox.addLayout(self._header_row)

        # Đường kẻ phân cách dưới tiêu đề Sidebar
        self._sidebar_sep = QFrame(self.sidebar_frame)
        self._sidebar_sep.setFrameShape(QFrame.Shape.HLine)
        self._sidebar_vbox.addWidget(self._sidebar_sep)

        # Vùng chứa các nút điều hướng
        self._nav_buttons_box = QVBoxLayout()
        self._nav_buttons_box.setSpacing(4)
        self._sidebar_vbox.addLayout(self._nav_buttons_box)
        self._sidebar_vbox.addStretch(1)

        # 2. Vùng hiển thị nội dung bên phải (QStackedWidget)
        self.stack = QStackedWidget(self)
        self.stack.setObjectName("WorkspaceStack")

        # Chỉ hiển thị thanh Sidebar cho vùng điều hướng chính (nếu nằm trong hộp thoại Cài đặt 2 tab thì giữ gọn)
        self._is_main_sidebar = not isinstance(master, Toplevel)
        if self._is_main_sidebar:
            self._root_hbox.addWidget(self.sidebar_frame)
        else:
            # Hộp thoại con (ví dụ SettingsDialog): dùng thanh chuyển tab ngang phía trên
            self.sidebar_frame.setFixedWidth(185)
            self._root_hbox.addWidget(self.sidebar_frame)

        self._root_hbox.addWidget(self.stack, 1)
        self._refresh_sidebar_icons()

    def toggle_sidebar(self):
        """Thu gọn hoặc mở rộng thanh điều hướng Sidebar bên trái."""
        self.is_sidebar_collapsed = not self.is_sidebar_collapsed
        if self.is_sidebar_collapsed:
            self.sidebar_frame.setFixedWidth(52)
            self.lbl_sidebar_title.hide()
            for item in self._tabs_list:
                btn: QPushButton = item["button"]
                btn.setText("")
        else:
            self.sidebar_frame.setFixedWidth(242 if self._is_main_sidebar else 185)
            self.lbl_sidebar_title.show()
            for item in self._tabs_list:
                btn = item["button"]
                btn.setText("  " + item["text"].strip())

    def set_theme_mode(self, is_dark: bool):
        self._is_dark = is_dark
        self._refresh_sidebar_icons()

    def _refresh_sidebar_icons(self):
        fg = "#e5e7eb" if self._is_dark else "#1f2937"
        acc = "#4dabf7" if self._is_dark else "#005fb8"
        self.btn_toggle_sidebar.setIcon(draw_vector_icon("sidebar_toggle", 18, fg, acc))
        self.btn_toggle_sidebar.setIconSize(QSize(18, 18))

        curr_idx = self.stack.currentIndex()
        for idx, item in enumerate(self._tabs_list):
            btn: QPushButton = item["button"]
            icon_kind = _SIDEBAR_ICON_KINDS[idx % len(_SIDEBAR_ICON_KINDS)]
            is_sel = (idx == curr_idx)
            icon_fg = acc if is_sel else fg
            btn.setIcon(draw_vector_icon(icon_kind, 20, icon_fg, acc))
            btn.setIconSize(QSize(20, 20))
            btn.setChecked(is_sel)

    def add(self, child: QWidget, **kw):
        text = str(kw.get("text", f"Tab {len(self._tabs_list) + 1}"))
        idx = len(self._tabs_list)

        btn = QPushButton(self.sidebar_frame)
        btn.setObjectName("SidebarNavBtn")
        btn.setCheckable(True)
        btn.setMinimumHeight(38)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setToolTip(text.strip())
        if not self.is_sidebar_collapsed:
            btn.setText("  " + text.strip())
        btn.clicked.connect(lambda checked=False, i=idx: self._select_by_index(i))

        self._nav_buttons_box.addWidget(btn)
        self.stack.addWidget(child)

        self._tabs_list.append({
            "widget": child,
            "text": text,
            "button": btn,
            "id": f"tab_{idx}",
        })
        if len(self._tabs_list) == 1:
            self._select_by_index(0)
        else:
            self._refresh_sidebar_icons()

    def _select_by_index(self, idx: int):
        if 0 <= idx < len(self._tabs_list):
            self.stack.setCurrentIndex(idx)
            self._refresh_sidebar_icons()
            self._emit_tk_event("<<NotebookTabChanged>>")

    def select(self, tab_id=None):
        if tab_id is None:
            idx = self.stack.currentIndex()
            return self._tabs_list[idx]["id"] if 0 <= idx < len(self._tabs_list) else ""
        idx = self.index(tab_id)
        self._select_by_index(idx)
        return self._tabs_list[idx]["id"]

    def index(self, tab_id) -> int:
        if tab_id == "end":
            return len(self._tabs_list)
        if isinstance(tab_id, int):
            return tab_id
        for idx, item in enumerate(self._tabs_list):
            if item["widget"] is tab_id or item["id"] == tab_id:
                return idx
        return 0

    def tab(self, tab_id, option: str | None = None, **kw):
        idx = self.index(tab_id)
        if not (0 <= idx < len(self._tabs_list)):
            return {}
        item = self._tabs_list[idx]
        if "text" in kw:
            item["text"] = str(kw["text"])
            if not self.is_sidebar_collapsed:
                item["button"].setText("  " + item["text"].strip())
        if option == "text":
            return item["text"]
        return {"text": item["text"]}

    def tabs(self) -> tuple[str, ...]:
        return tuple(item["id"] for item in self._tabs_list)


# =============================================================================
# 8. CÁC WIDGET ĐIỀU KHIỂN PYQT6 (Label, Button, Entry, Combobox, Progressbar...)
# =============================================================================
class Label(QLabel, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        text = str(kw.pop("text", ""))
        self._textvariable: Variable | None = kw.pop("textvariable", None)
        if self._textvariable is not None:
            text = str(self._textvariable.get())
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(text, parent_q)
        self._init_tk_mixin(master, **kw)
        self._tk_options["text"] = text
        if self._textvariable is not None:
            self._textvariable.trace_add("write", lambda *_: self.setText(str(self._textvariable.get())))

    def _apply_tk_option(self, k: str, v: Any):
        if k == "text":
            self.setText(str(v))
        elif k == "textvariable" and isinstance(v, Variable):
            self._textvariable = v
            self.setText(str(v.get()))
            v.trace_add("write", lambda *_: self.setText(str(v.get())))
        elif k in ("fg", "foreground"):
            self._tk_options["foreground"] = v
            self._tk_options["fg"] = v
            bg = self._tk_options.get("background") or self._tk_options.get("bg")
            style_parts = [f"color: {v};"] if v else []
            if bg:
                style_parts.append(f"background-color: {bg};")
            self.setStyleSheet(" ".join(style_parts))
        elif k in ("bg", "background"):
            self._tk_options["background"] = v
            self._tk_options["bg"] = v
            fg = self._tk_options.get("foreground") or self._tk_options.get("fg")
            style_parts = [f"background-color: {v};"] if v else []
            if fg:
                style_parts.append(f"color: {fg};")
            self.setStyleSheet(" ".join(style_parts))
        elif k == "wraplength":
            self.setWordWrap(bool(v and int(v) > 0))
            if v and int(v) > 0:
                self.setMaximumWidth(int(v) + 24)
        elif k == "justify":
            j = str(v).lower()
            if j == "left":
                self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            elif j == "right":
                self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            elif j == "center":
                self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        else:
            super()._apply_tk_option(k, v)


class Button(QPushButton, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        text = str(kw.pop("text", ""))
        self._command: Callable | None = kw.pop("command", None)
        style_name = str(kw.pop("style", ""))
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(text, parent_q)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if "Accent" in style_name:
            self.setProperty("accentButton", True)
        self._init_tk_mixin(master, **kw)
        self._tk_options["text"] = text
        self._tk_options["style"] = style_name
        self.clicked.connect(self._on_qt_clicked)

    def _on_qt_clicked(self):
        if self.isEnabled() and callable(self._command):
            self._command()

    def invoke(self):
        if self.isEnabled() and callable(self._command):
            return self._command()

    def _apply_tk_option(self, k: str, v: Any):
        if k == "command":
            self._command = v
        elif k == "style":
            self.setProperty("accentButton", "Accent" in str(v))
        else:
            super()._apply_tk_option(k, v)


class Checkbutton(QCheckBox, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        text = str(kw.pop("text", ""))
        self._variable: BooleanVar | None = kw.pop("variable", None)
        self._command: Callable | None = kw.pop("command", None)
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(text, parent_q)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._updating_from_var = False
        self._init_tk_mixin(master, **kw)
        self._tk_options["text"] = text

        if self._variable is not None:
            self.setChecked(bool(self._variable.get()))
            self._variable.trace_add("write", self._sync_from_var)

        self.toggled.connect(self._on_qt_toggled)

    def _sync_from_var(self, *_):
        if self._variable is not None and not self._updating_from_var:
            self._updating_from_var = True
            try:
                self.setChecked(bool(self._variable.get()))
            finally:
                self._updating_from_var = False

    def _on_qt_toggled(self, checked: bool):
        if not self._updating_from_var:
            self._updating_from_var = True
            try:
                if self._variable is not None:
                    self._variable.set(bool(checked))
            finally:
                self._updating_from_var = False
            if callable(self._command):
                self._command()

    def invoke(self):
        if self.isEnabled():
            self.setChecked(not self.isChecked())

    def _apply_tk_option(self, k: str, v: Any):
        if k == "command":
            self._command = v
        elif k == "variable" and isinstance(v, BooleanVar):
            self._variable = v
            self.setChecked(bool(v.get()))
            v.trace_add("write", self._sync_from_var)
        else:
            super()._apply_tk_option(k, v)


class Radiobutton(QRadioButton, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        text = str(kw.pop("text", ""))
        self._variable: Variable | None = kw.pop("variable", None)
        self._value: Any = kw.pop("value", "")
        self._command: Callable | None = kw.pop("command", None)
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(text, parent_q)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_tk_mixin(master, **kw)

        if self._variable is not None:
            self.setChecked(self._variable.get() == self._value)
            self._variable.trace_add("write", self._sync_from_var)
        self.toggled.connect(self._on_qt_toggled)

    def _sync_from_var(self, *_):
        if self._variable is not None:
            self.setChecked(self._variable.get() == self._value)

    def _on_qt_toggled(self, checked: bool):
        if checked and self._variable is not None:
            if self._variable.get() != self._value:
                self._variable.set(self._value)
            if callable(self._command):
                self._command()


class Entry(QLineEdit, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        self._textvariable: Variable | None = kw.pop("textvariable", None)
        show_char = kw.pop("show", None)
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self._updating_var = False
        self._init_tk_mixin(master, **kw)
        if show_char is not None:
            self.configure(show=show_char)
        if self._textvariable is not None:
            self.setText(str(self._textvariable.get()))
            self._textvariable.trace_add("write", self._sync_from_var)
        self.textChanged.connect(self._on_text_changed)
        self.returnPressed.connect(lambda: self._emit_tk_event("<Return>"))

    def _sync_from_var(self, *_):
        if self._textvariable is not None and not self._updating_var:
            self._updating_var = True
            try:
                self.setText(str(self._textvariable.get()))
            finally:
                self._updating_var = False

    def _on_text_changed(self, text: str):
        if self._textvariable is not None and not self._updating_var:
            self._updating_var = True
            try:
                self._textvariable.set(text)
            finally:
                self._updating_var = False

    def get(self) -> str:
        return self.text()

    def insert(self, index, string: str):
        cur = self.text()
        if index == END or str(index) == "end":
            pos = len(cur)
        else:
            try:
                pos = max(0, min(len(cur), int(index)))
            except (ValueError, TypeError):
                pos = len(cur)
        self.setText(cur[:pos] + str(string) + cur[pos:])

    def delete(self, first, last=None):
        cur = self.text()
        try:
            start = 0 if first == 0 else int(first)
        except (ValueError, TypeError):
            start = 0
        if last is None:
            end = start + 1
        elif last == END or str(last) == "end":
            end = len(cur)
        else:
            try:
                end = int(last)
            except (ValueError, TypeError):
                end = len(cur)
        self.setText(cur[:start] + cur[end:])

    def select_range(self, start, end):
        self.selectAll()

    selection_range = select_range

    def icursor(self, index):
        if index == END or str(index) == "end":
            self.setCursorPosition(len(self.text()))
        else:
            try:
                self.setCursorPosition(int(index))
            except (ValueError, TypeError):
                pass

    def _apply_tk_option(self, k: str, v: Any):
        if k == "show":
            if v:
                self.setEchoMode(QLineEdit.EchoMode.Password)
            else:
                self.setEchoMode(QLineEdit.EchoMode.Normal)
        elif k == "state":
            st = str(v).lower()
            self._tk_options["state"] = st
            if st == "readonly":
                self.setReadOnly(True)
                self.setEnabled(True)
            elif st == "disabled":
                self.setEnabled(False)
            else:
                self.setReadOnly(False)
                self.setEnabled(True)
        else:
            super()._apply_tk_option(k, v)


class Combobox(QComboBox, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        self._textvariable: Variable | None = kw.pop("textvariable", None)
        values = list(kw.pop("values", []))
        self._postcommand: Callable | None = kw.pop("postcommand", None)
        state = str(kw.pop("state", "normal")).lower()
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self._updating_cb = False
        self._values_list: list[str] = [str(x) for x in values]
        self.setEditable(True)
        self.addItems(self._values_list)
        self._init_tk_mixin(master, **kw)
        self.configure(state=state, values=self._values_list)

        if self._textvariable is not None:
            self.set(str(self._textvariable.get()))
            self._textvariable.trace_add("write", self._sync_from_var)

        self.currentTextChanged.connect(self._on_text_changed)
        self.activated.connect(lambda _idx: self._emit_tk_event("<<ComboboxSelected>>"))

    def showPopup(self):
        if callable(self._postcommand):
            try:
                self._postcommand()
            except Exception:
                pass
        super().showPopup()

    def _sync_from_var(self, *_):
        if self._textvariable is not None and not self._updating_cb:
            self.set(str(self._textvariable.get()))

    def _on_text_changed(self, text: str):
        if not self._updating_cb and self._textvariable is not None:
            self._updating_cb = True
            try:
                self._textvariable.set(text)
            finally:
                self._updating_cb = False

    def get(self) -> str:
        return self.currentText()

    def set(self, value: Any):
        val_str = str(value) if value is not None else ""
        self._updating_cb = True
        try:
            idx = self.findText(val_str)
            if idx >= 0:
                self.setCurrentIndex(idx)
            self.setEditText(val_str)
            if self._textvariable is not None and self._textvariable.get() != val_str:
                self._textvariable.set(val_str)
        finally:
            self._updating_cb = False

    def current(self, newindex: int | None = None) -> int:
        if newindex is not None and 0 <= int(newindex) < self.count():
            self.setCurrentIndex(int(newindex))
        return self.currentIndex()

    def cget(self, key: str) -> Any:
        if key == "values":
            return tuple(self._values_list)
        return super().cget(key)

    def _apply_tk_option(self, k: str, v: Any):
        if k == "values":
            cur = self.get()
            self._values_list = [str(x) for x in (v or [])]
            self._updating_cb = True
            try:
                self.clear()
                self.addItems(self._values_list)
                self.setEditText(cur)
            finally:
                self._updating_cb = False
        elif k == "postcommand":
            self._postcommand = v
        elif k == "state":
            st = str(v).lower()
            self._tk_options["state"] = st
            if st == "disabled":
                self.setEnabled(False)
            elif st == "readonly":
                self.setEnabled(True)
                le = self.lineEdit()
                if le is not None:
                    le.setReadOnly(True)
            else:
                self.setEnabled(True)
                le = self.lineEdit()
                if le is not None:
                    le.setReadOnly(False)
        else:
            super()._apply_tk_option(k, v)


class Spinbox(QSpinBox, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        from_val = int(kw.pop("from_", 0))
        to_val = int(kw.pop("to", 100))
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self.setRange(from_val, to_val)
        self._init_tk_mixin(master, **kw)

    def get(self) -> str:
        return str(self.value())


class Progressbar(QProgressBar, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        length = int(kw.pop("length", 180))
        mode = str(kw.pop("mode", "determinate"))
        maximum = float(kw.pop("maximum", 100.0))
        value = float(kw.pop("value", 0.0))
        kw.pop("orient", None)
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self.setTextVisible(False)
        self.setMinimumWidth(length)
        self.setFixedHeight(14)
        self._maximum = maximum
        self._value = value
        self._mode = mode
        self._running = False
        self.setRange(0, int(maximum))
        self.setValue(int(value))
        self._init_tk_mixin(master, **kw)
        self._tk_options["mode"] = mode
        self._tk_options["value"] = value
        self._tk_options["maximum"] = maximum

    def start(self, interval: int | None = None):
        self._running = True

    def stop(self):
        self._running = False

    def step(self, amount: float = 1.0):
        self.configure(value=(self._value + float(amount)) % max(1.0, self._maximum))

    def _apply_tk_option(self, k: str, v: Any):
        if k == "mode":
            self._mode = str(v)
            self._tk_options["mode"] = self._mode
        elif k == "maximum":
            self._maximum = float(v)
            self._tk_options["maximum"] = self._maximum
            self.setRange(0, max(1, int(self._maximum)))
        elif k == "value":
            self._value = float(v)
            self._tk_options["value"] = self._value
            self.setValue(max(0, min(int(self._maximum), int(round(self._value)))))
        elif k == "length":
            self.setMinimumWidth(int(v))
        else:
            super()._apply_tk_option(k, v)


class Scrollbar(QScrollBar, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        orient = str(kw.pop("orient", VERTICAL)).lower()
        qt_orient = Qt.Orientation.Vertical if orient == VERTICAL else Qt.Orientation.Horizontal
        kw.pop("command", None)
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(qt_orient, parent_q)
        self._init_tk_mixin(master, **kw)
        # QTextEdit và QTreeWidget của PyQt6 đã tích hợp thanh cuộn mượt tự động
        self.setFixedWidth(0 if orient == VERTICAL else 0)
        self.hide()

    def set(self, first, last):
        pass


class Separator(QFrame, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        orient = str(kw.pop("orient", HORIZONTAL)).lower()
        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self.setFrameShape(QFrame.Shape.VLine if orient == VERTICAL else QFrame.Shape.HLine)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self._init_tk_mixin(master, **kw)


# =============================================================================
# 9. TRÌNH SOẠN THẢO VĂN BẢN & NHẬT KÝ PYQT6 (Text / QTextEdit)
# =============================================================================
class Text(QTextEdit, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        height_lines = kw.pop("height", None)
        width_chars = kw.pop("width", None)
        wrap_mode = str(kw.pop("wrap", WORD)).lower()
        state = str(kw.pop("state", NORMAL)).lower()
        kw.pop("relief", None)
        kw.pop("borderwidth", None)
        kw.pop("padx", None)
        kw.pop("pady", None)
        kw.pop("yscrollcommand", None)
        kw.pop("xscrollcommand", None)

        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self.setAcceptRichText(False)
        if wrap_mode == NONE:
            self.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        else:
            self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)

        if height_lines is not None:
            try:
                h_px = max(48, int(height_lines) * 19 + 12)
                if int(height_lines) <= 8:
                    self.setMaximumHeight(h_px + 20)
                self.setMinimumHeight(min(h_px, 160))
            except (ValueError, TypeError):
                pass

        self._tags_config: dict[str, dict[str, Any]] = {}
        self._init_tk_mixin(master, **kw)
        self.configure(state=state)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                if self._emit_tk_event("<Shift-Return>") == "break":
                    return
            else:
                if self._emit_tk_event("<Return>") == "break":
                    return
        super().keyPressEvent(event)

    def _pos_from_tk_index(self, idx: str) -> int:
        s = str(idx).strip().lower()
        doc = self.document()
        if s in ("end", "end-1c"):
            if doc is not None:
                return max(0, doc.characterCount() - 1)
            return len(self.toPlainText())
        if s == "1.0":
            return 0
        if s == "insert":
            return self.textCursor().position()
        m = re.match(r"(\d+)\.(\d+|end)", s)
        if m and doc is not None:
            line_no = max(1, int(m.group(1)))
            col_spec = m.group(2)
            blk = doc.findBlockByNumber(line_no - 1)
            if not blk.isValid():
                return max(0, doc.characterCount() - 1)
            offset = blk.position()
            if col_spec == "end":
                return offset + max(0, blk.length() - 1)
            return min(max(0, doc.characterCount() - 1), offset + int(col_spec))
        txt = self.toPlainText()
        return len(txt)

    def insert(self, index: str, chars: str, *tags):
        if not chars:
            return
        cursor = self.textCursor()
        s_idx = str(index).strip().lower()
        if s_idx in ("end", "end-1c"):
            cursor.movePosition(QTextCursor.MoveOperation.End)
        else:
            pos = self._pos_from_tk_index(index)
            cursor.setPosition(pos)

        tag_list: list[str] = []
        for t in tags:
            if isinstance(t, (tuple, list)):
                tag_list.extend(str(x) for x in t if x)
            elif t:
                tag_list.append(str(t))

        if not tag_list:
            cursor.insertText(str(chars))
            return

        char_fmt = QTextCharFormat()
        block_fmt = cursor.blockFormat()
        has_block_margin = False

        for t_name in tag_list:
            t_cfg = self._tags_config.get(t_name, {})
            if "foreground" in t_cfg and t_cfg["foreground"]:
                char_fmt.setForeground(QColor(str(t_cfg["foreground"])))
            if "background" in t_cfg and t_cfg["background"]:
                char_fmt.setBackground(QColor(str(t_cfg["background"])))
            if "font" in t_cfg and t_cfg["font"]:
                qf = _parse_font(t_cfg["font"])
                if qf is not None:
                    char_fmt.setFont(qf)
            if "lmargin2" in t_cfg:
                has_block_margin = True

        if has_block_margin:
            cursor.setBlockFormat(block_fmt)
        cursor.insertText(str(chars), char_fmt)

    def delete(self, index1: str, index2: str | None = None):
        s1 = str(index1).strip().lower()
        s2 = str(index2).strip().lower() if index2 is not None else None
        if s1 == "1.0" and s2 in ("end", "end-1c"):
            self.clear()
            return
        p1 = self._pos_from_tk_index(index1)
        p2 = self._pos_from_tk_index(index2) if index2 is not None else p1 + 1
        cursor = self.textCursor()
        cursor.setPosition(p1)
        cursor.setPosition(max(p1, p2), QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

    def get(self, index1: str = "1.0", index2: str | None = "end") -> str:
        txt = self.toPlainText()
        s1 = str(index1).strip().lower()
        s2 = str(index2).strip().lower() if index2 is not None else None
        if s1 == "1.0" and s2 == "end-1c":
            return txt
        if s1 == "1.0" and s2 == "end":
            return txt + "\n"
        p1 = self._pos_from_tk_index(index1)
        p2 = self._pos_from_tk_index(index2) if index2 is not None else p1 + 1
        res = txt[p1:p2]
        if s2 == "end":
            res += "\n"
        return res

    def see(self, index: str = "end"):
        sb = self.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.maximum())

    def index(self, index_spec: str) -> str:
        s = str(index_spec).strip().lower()
        doc = self.document()
        if s in ("end-1c", "end") and doc is not None:
            line_count = max(1, doc.blockCount())
            last_blk = doc.lastBlock()
            col_count = max(0, last_blk.length() - 1) if last_blk.isValid() else 0
            if s == "end":
                return f"{line_count + 1}.0"
            return f"{line_count}.{col_count}"
        txt = self.toPlainText()
        pos = self._pos_from_tk_index(index_spec)
        prefix = txt[:pos]
        lines = prefix.split("\n")
        return f"{len(lines)}.{len(lines[-1])}"

    def tag_configure(self, tagName: str, **kw):
        cfg = self._tags_config.setdefault(str(tagName), {})
        cfg.update(kw)

    tag_config = tag_configure

    def tag_cget(self, tagName: str, option: str) -> Any:
        return self._tags_config.get(str(tagName), {}).get(str(option), "")

    def yview(self, *args):
        pass

    def _apply_tk_option(self, k: str, v: Any):
        if k == "state":
            st = str(v).lower()
            self._tk_options["state"] = st
            self.setReadOnly(st == "disabled")
        elif k in ("bg", "background", "fg", "foreground", "insertbackground", "selectbackground", "selectforeground"):
            self._tk_options[k] = v
            bg = self._tk_options.get("bg") or self._tk_options.get("background")
            fg = self._tk_options.get("fg") or self._tk_options.get("foreground")
            sel_bg = self._tk_options.get("selectbackground")
            sel_fg = self._tk_options.get("selectforeground")
            parts = []
            if bg:
                parts.append(f"background-color: {bg};")
            if fg:
                parts.append(f"color: {fg};")
            if sel_bg:
                parts.append(f"selection-background-color: {sel_bg};")
            if sel_fg:
                parts.append(f"selection-color: {sel_fg};")
            if parts:
                self.setStyleSheet(f"QTextEdit {{ {' '.join(parts)} }}")
        elif k in ("yscrollcommand", "xscrollcommand"):
            pass
        else:
            super()._apply_tk_option(k, v)


# =============================================================================
# 10. BẢNG DỮ LIỆU CÂY / BẢNG PHÂN VÙNG PYQT6 (Treeview / QTreeWidget)
# =============================================================================
class Treeview(QTreeWidget, QtWidgetMixin):
    def __init__(self, master=None, **kw):
        ensure_qapp()
        columns = tuple(kw.pop("columns", ()))
        show = str(kw.pop("show", "headings"))
        selectmode = str(kw.pop("selectmode", BROWSE))
        height_rows = kw.pop("height", None)
        kw.pop("yscrollcommand", None)
        kw.pop("xscrollcommand", None)

        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self._columns = columns
        self.setColumnCount(max(1, len(columns)))
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        if selectmode == EXTENDED:
            self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        else:
            self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

        hdr = self.header()
        if hdr is not None:
            hdr.setStretchLastSection(True)
            hdr.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)

        if height_rows is not None:
            try:
                self.setMinimumHeight(max(120, int(height_rows) * 26))
            except (ValueError, TypeError):
                pass

        self._items_by_iid: dict[str, QTreeWidgetItem] = {}
        self._iid_order: list[str] = []
        self._col_configs: dict[str, dict[str, Any]] = {c: {"width": 100, "anchor": "w"} for c in columns}
        self._heading_texts: dict[str, str] = {c: c for c in columns}
        self._auto_iid_counter = 0

        self._init_tk_mixin(master, **kw)
        self._tk_options["columns"] = columns
        self._tk_options["show"] = show
        self.itemSelectionChanged.connect(lambda: self._emit_tk_event("<<TreeviewSelect>>"))

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        super().mousePressEvent(event)
        pos = event.position().toPoint()
        gpos = event.globalPosition().toPoint()
        ev = SimpleNamespace(
            widget=self, x=pos.x(), y=pos.y(),
            x_root=gpos.x(), y_root=gpos.y(),
            num=1 if event.button() == Qt.MouseButton.LeftButton else 3
        )
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_tk_event("<Button-1>", ev)
        elif event.button() == Qt.MouseButton.RightButton:
            self._emit_tk_event("<Button-3>", ev)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        super().mouseReleaseEvent(event)
        pos = event.position().toPoint()
        gpos = event.globalPosition().toPoint()
        ev = SimpleNamespace(widget=self, x=pos.x(), y=pos.y(), x_root=gpos.x(), y_root=gpos.y())
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_tk_event("<ButtonRelease-1>", ev)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        super().mouseDoubleClickEvent(event)
        pos = event.position().toPoint()
        gpos = event.globalPosition().toPoint()
        ev = SimpleNamespace(widget=self, x=pos.x(), y=pos.y(), x_root=gpos.x(), y_root=gpos.y())
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_tk_event("<Double-1>", ev)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        if event.key() == Qt.Key.Key_Space:
            self._emit_tk_event("<space>")
            return
        if event.key() == Qt.Key.Key_Delete:
            self._emit_tk_event("<Delete>")
            return
        super().keyPressEvent(event)

    def _col_index(self, col_id: str | int) -> int:
        if isinstance(col_id, int):
            return col_id
        s = str(col_id)
        if s.startswith("#") and s[1:].isdigit():
            return max(0, int(s[1:]) - 1)
        if s in self._columns:
            return self._columns.index(s)
        return 0

    def heading(self, column: str, text: str | None = None, anchor: str | None = None, command: Callable | None = None):
        idx = self._col_index(column)
        col_name = self._columns[idx] if idx < len(self._columns) else str(column)
        if text is not None:
            self._heading_texts[col_name] = str(text)
            self.setHeaderLabels([self._heading_texts.get(c, c) for c in self._columns])
        return {"text": self._heading_texts.get(col_name, "")}

    def column(self, column: str, width: int | None = None, minwidth: int | None = None, anchor: str | None = None, stretch: bool | None = None):
        idx = self._col_index(column)
        col_name = self._columns[idx] if idx < len(self._columns) else str(column)
        cfg = self._col_configs.setdefault(col_name, {"width": 100, "anchor": "w"})
        if width is not None:
            cfg["width"] = int(width)
            self.setColumnWidth(idx, int(width))
        if anchor is not None:
            cfg["anchor"] = str(anchor)
        return cfg

    def insert(self, parent: str, index: str | int, iid: str | None = None, text: str = "", values: tuple | list = (), tags: tuple | list = ()) -> str:
        if iid is None:
            self._auto_iid_counter += 1
            iid = f"I{self._auto_iid_counter:03X}"
        iid = str(iid)
        str_vals = [str(v) for v in values]
        while len(str_vals) < len(self._columns):
            str_vals.append("")

        qitem = QTreeWidgetItem(str_vals)
        qitem.setData(0, Qt.ItemDataRole.UserRole, iid)

        # Áp dụng căn lề cột & vẽ icon checkbox vector nếu là cột "checked"
        for c_idx, col_name in enumerate(self._columns):
            cfg = self._col_configs.get(col_name, {})
            anc = str(cfg.get("anchor", "w")).lower()
            if anc == "center":
                qitem.setTextAlignment(c_idx, Qt.AlignmentFlag.AlignCenter)
            elif "e" in anc:
                qitem.setTextAlignment(c_idx, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            else:
                qitem.setTextAlignment(c_idx, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            if col_name == "checked" and c_idx < len(str_vals):
                val_txt = str_vals[c_idx]
                is_chk = "[x]" in val_txt.lower() or "chọn" in val_txt.lower() or val_txt.strip() == "1"
                qitem.setIcon(c_idx, draw_vector_icon("checkbox_checked" if is_chk else "checkbox_unchecked", 16))

        if index == "end" or not isinstance(index, int) or index >= len(self._iid_order):
            self.addTopLevelItem(qitem)
            if iid in self._iid_order:
                self._iid_order.remove(iid)
            self._iid_order.append(iid)
        else:
            pos = max(0, int(index))
            self.insertTopLevelItem(pos, qitem)
            if iid in self._iid_order:
                self._iid_order.remove(iid)
            self._iid_order.insert(pos, iid)

        self._items_by_iid[iid] = qitem
        return iid

    def get_children(self, item: str | None = None) -> tuple[str, ...]:
        return tuple(self._iid_order)

    def exists(self, item: str) -> bool:
        return str(item) in self._items_by_iid

    def item(self, item: str, option: str | None = None, **kw) -> Any:
        iid = str(item)
        qitem = self._items_by_iid.get(iid)
        if qitem is None:
            return {"values": (), "text": ""}
        if "values" in kw:
            new_vals = [str(v) for v in kw["values"]]
            for i, v in enumerate(new_vals):
                if i < self.columnCount():
                    qitem.setText(i, v)
        cur_vals = tuple(qitem.text(i) for i in range(len(self._columns)))
        if option == "values":
            return cur_vals
        if option == "text":
            return qitem.text(0)
        return {"values": cur_vals, "text": qitem.text(0)}

    def set(self, item: str, column: str | None = None, value: Any = None) -> Any:
        iid = str(item)
        qitem = self._items_by_iid.get(iid)
        if qitem is None:
            return ""
        if column is None:
            return {c: qitem.text(i) for i, c in enumerate(self._columns)}
        idx = self._col_index(column)
        if value is not None:
            qitem.setText(idx, str(value))
        return qitem.text(idx)

    def delete(self, *items: str):
        for iid in items:
            s_iid = str(iid)
            qitem = self._items_by_iid.pop(s_iid, None)
            if s_iid in self._iid_order:
                self._iid_order.remove(s_iid)
            if qitem is not None:
                idx = self.indexOfTopLevelItem(qitem)
                if idx >= 0:
                    self.takeTopLevelItem(idx)

    def selection(self) -> tuple[str, ...]:
        res = []
        for qitem in self.selectedItems():
            iid = qitem.data(0, Qt.ItemDataRole.UserRole)
            if iid:
                res.append(str(iid))
        return tuple(res)

    def selection_set(self, items):
        if isinstance(items, str):
            items = (items,)
        self.clearSelection()
        for iid in items:
            qitem = self._items_by_iid.get(str(iid))
            if qitem is not None:
                qitem.setSelected(True)
                self.setCurrentItem(qitem)

    def selection_remove(self, items):
        if isinstance(items, str):
            items = (items,)
        for iid in items:
            qitem = self._items_by_iid.get(str(iid))
            if qitem is not None:
                qitem.setSelected(False)

    def focus(self, item: str | None = None) -> str:
        if item is not None:
            qitem = self._items_by_iid.get(str(item))
            if qitem is not None:
                self.setCurrentItem(qitem)
        cur = self.currentItem()
        if cur is not None:
            return str(cur.data(0, Qt.ItemDataRole.UserRole) or "")
        sel = self.selection()
        return sel[0] if sel else ""

    def see(self, item: str):
        qitem = self._items_by_iid.get(str(item))
        if qitem is not None:
            self.scrollToItem(qitem)

    def identify_row(self, y: int) -> str:
        hdr_h = self.header().height() if self.header() else 24
        qitem = self.itemAt(10, max(0, int(y) - hdr_h))
        if qitem is not None:
            iid = qitem.data(0, Qt.ItemDataRole.UserRole)
            if iid:
                return str(iid)
        # Fallback cho môi trường headless khi bảng chưa hiển thị ra màn hình
        row_idx = max(0, (int(y) - 24)) // 24
        if 0 <= row_idx < len(self._iid_order):
            return self._iid_order[row_idx]
        return self._iid_order[0] if self._iid_order else ""

    def identify_column(self, x: int) -> str:
        acc = 0
        for idx, c_name in enumerate(self._columns, 1):
            w = self._col_configs.get(c_name, {}).get("width", 100)
            acc += w
            if int(x) <= acc:
                return f"#{idx}"
        return f"#{len(self._columns)}"

    def identify_region(self, x: int, y: int) -> str:
        if int(y) < 22:
            return "heading"
        return "cell"

    def bbox(self, item: str, column: str | None = None) -> tuple[int, int, int, int]:
        iid = str(item)
        if iid not in self._items_by_iid:
            return (0, 0, 100, 24)
        row_idx = self._iid_order.index(iid) if iid in self._iid_order else 0
        col_idx = self._col_index(column) if column is not None else 0
        x_off = sum(self._col_configs.get(self._columns[i], {}).get("width", 80) for i in range(col_idx))
        w = self._col_configs.get(self._columns[col_idx], {}).get("width", 80) if col_idx < len(self._columns) else 100
        return (x_off, 24 + row_idx * 24, w, 24)

    def yview(self, *args):
        pass

    def yview_scroll(self, number: int, what: str):
        sb = self.verticalScrollBar()
        if sb is not None:
            sb.setValue(sb.value() + int(number) * 20)


# =============================================================================
# 11. KHUNG VẼ SƠ ĐỒ PHÂN VÙNG VECTOR PYQT6 (Canvas / QPainter)
# =============================================================================
class Canvas(QWidget, QtWidgetMixin):
    """
    Khung vẽ đồ họa Vector 2D dùng QPainter (phục vụ DiskMapCanvas trên Tab 4 & Tab 5).
    """
    def __init__(self, master=None, **kw):
        ensure_qapp()
        h = int(kw.pop("height", 80))
        w = kw.pop("width", None)
        kw.pop("relief", None)
        kw.pop("borderwidth", None)
        kw.pop("highlightthickness", None)
        kw.pop("highlightbackground", None)
        bg = kw.pop("background", kw.pop("bg", None))

        parent_q = master._layout_container() if hasattr(master, "_layout_container") else (master if isinstance(master, QWidget) else None)
        super().__init__(parent_q)
        self.setMinimumHeight(h)
        if h <= 120:
            self.setFixedHeight(h)
        if w is not None:
            self.setMinimumWidth(int(w))
        self.setMouseTracking(True)

        self._bg_color = str(bg) if bg else "#f0f0f0"
        self._items: list[dict[str, Any]] = []
        self._next_id = 1
        self._init_tk_mixin(master, **kw)

    def resizeEvent(self, event: QtGui.QResizeEvent):
        super().resizeEvent(event)
        ev = SimpleNamespace(widget=self, width=self.width(), height=self.height())
        self._emit_tk_event("<Configure>", ev)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        super().mouseMoveEvent(event)
        pos = event.position().toPoint()
        gpos = event.globalPosition().toPoint()
        ev = SimpleNamespace(widget=self, x=pos.x(), y=pos.y(), x_root=gpos.x(), y_root=gpos.y())
        self._emit_tk_event("<Motion>", ev)

    def leaveEvent(self, event: QtCore.QEvent):
        super().leaveEvent(event)
        ev = SimpleNamespace(widget=self, x=0, y=0, x_root=0, y_root=0)
        self._emit_tk_event("<Leave>", ev)

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        super().mousePressEvent(event)
        pos = event.position().toPoint()
        gpos = event.globalPosition().toPoint()
        ev = SimpleNamespace(widget=self, x=pos.x(), y=pos.y(), x_root=gpos.x(), y_root=gpos.y())
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_tk_event("<Button-1>", ev)
        elif event.button() == Qt.MouseButton.RightButton:
            self._emit_tk_event("<Button-3>", ev)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent):
        super().mouseDoubleClickEvent(event)
        pos = event.position().toPoint()
        gpos = event.globalPosition().toPoint()
        ev = SimpleNamespace(widget=self, x=pos.x(), y=pos.y(), x_root=gpos.x(), y_root=gpos.y())
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_tk_event("<Double-1>", ev)

    def delete(self, tagOrId: str | int):
        if str(tagOrId) == "all":
            self._items.clear()
        else:
            self._items = [it for it in self._items if it["id"] != tagOrId and tagOrId not in it.get("tags", ())]
        self.update()

    def create_rectangle(self, x1: float, y1: float, x2: float, y2: float, **kw) -> int:
        iid = self._next_id
        self._next_id += 1
        tags = kw.get("tags", ())
        if isinstance(tags, str):
            tags = (tags,)
        self._items.append({
            "id": iid,
            "type": "rect",
            "coords": (float(x1), float(y1), float(x2), float(y2)),
            "fill": kw.get("fill", ""),
            "outline": kw.get("outline", "#888888"),
            "width": float(kw.get("width", 1.0)),
            "dash": kw.get("dash", None),
            "tags": tags,
        })
        self.update()
        return iid

    def create_text(self, x: float, y: float, **kw) -> int:
        iid = self._next_id
        self._next_id += 1
        tags = kw.get("tags", ())
        if isinstance(tags, str):
            tags = (tags,)
        self._items.append({
            "id": iid,
            "type": "text",
            "coords": (float(x), float(y)),
            "text": str(kw.get("text", "")),
            "fill": kw.get("fill", "#000000"),
            "font": kw.get("font", ("Segoe UI", 8)),
            "anchor": str(kw.get("anchor", "center")).lower(),
            "tags": tags,
        })
        self.update()
        return iid

    def create_window(self, *args, window: QWidget | None = None, **kw) -> int:
        iid = self._next_id
        self._next_id += 1
        if window is not None:
            window.setParent(self)
            window.show()
        return iid

    def bbox(self, tagOrId: str = "all"):
        return (0, 0, self.winfo_width(), self.winfo_height())

    def yview(self, *args):
        pass

    def yview_scroll(self, number: int, what: str):
        pass

    def _apply_tk_option(self, k: str, v: Any):
        if k in ("bg", "background"):
            self._bg_color = str(v)
            self.update()
        elif k in ("highlightbackground", "scrollregion", "yscrollcommand"):
            pass
        else:
            super()._apply_tk_option(k, v)

    def paintEvent(self, event: QtGui.QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        p.fillRect(self.rect(), QColor(self._bg_color))

        for item in self._items:
            t = item["type"]
            if t == "rect":
                x1, y1, x2, y2 = item["coords"]
                rect = QRectF(x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))
                fill_col = item.get("fill")
                if fill_col:
                    p.fillRect(rect, QColor(str(fill_col)))
                out_col = item.get("outline")
                if out_col:
                    pen = QPen(QColor(str(out_col)), max(1.0, float(item.get("width", 1.0))))
                    if item.get("dash"):
                        pen.setStyle(Qt.PenStyle.DashLine)
                    p.setPen(pen)
                    p.drawRect(rect)
            elif t == "text":
                x, y = item["coords"]
                txt = item.get("text", "")
                if not txt:
                    continue
                qf = _parse_font(item.get("font")) or QFont("Segoe UI", 8)
                p.setFont(qf)
                p.setPen(QColor(str(item.get("fill") or "#ffffff")))
                fm = QFontMetrics(qf)
                tw = fm.horizontalAdvance(txt)
                th = fm.height()
                anc = item.get("anchor", "center")
                if "w" in anc:
                    tx = x
                elif "e" in anc:
                    tx = x - tw
                else:
                    tx = x - tw / 2.0
                ty = y + (fm.ascent() - fm.descent()) / 2.0
                p.drawText(QPointF(tx, ty), txt)

        p.end()


# =============================================================================
# 12. THANH THỰC ĐƠN (Menu / QMenuBar / QMenu), PHOTOIMAGE & STYLE QSS
# =============================================================================
class Menu:
    def __init__(self, master=None, tearoff: int = 0, **kw):
        ensure_qapp()
        self.master = master
        self._entries: list[dict[str, Any]] = []
        self._qmenu = QMenu()
        self._tk_destroyed = False

    def _attach_to_mainwindow(self, win: QMainWindow):
        mb = win.menuBar()
        if mb is None:
            return
        mb.clear()
        for entry in self._entries:
            etype = entry["type"]
            if etype == "cascade" and isinstance(entry.get("menu"), Menu):
                sub_qmenu = entry["menu"]._qmenu
                sub_qmenu.setTitle(str(entry["label"]))
                mb.addMenu(sub_qmenu)
            elif etype == "command":
                act = mb.addAction(str(entry["label"]))
                cmd = entry.get("command")
                if act is not None and callable(cmd):
                    act.triggered.connect(lambda checked=False, fn=cmd: fn())

    def add_cascade(self, label: str = "", menu: Menu | None = None, **kw):
        self._entries.append({"type": "cascade", "label": label, "menu": menu})
        if menu is not None:
            menu._qmenu.setTitle(str(label))
            self._qmenu.addMenu(menu._qmenu)

    def add_command(self, label: str = "", command: Callable | None = None, state: str = NORMAL, **kw):
        act = self._qmenu.addAction(str(label))
        if act is not None:
            act.setEnabled(str(state).lower() != "disabled")
            if callable(command):
                act.triggered.connect(lambda checked=False, fn=command: fn())
        self._entries.append({"type": "command", "label": label, "command": command, "state": state, "action": act})

    def add_separator(self):
        self._qmenu.addSeparator()
        self._entries.append({"type": "separator", "label": ""})

    def add_radiobutton(self, label: str = "", variable: Variable | None = None, value: Any = None, command: Callable | None = None, **kw):
        def _on_trig():
            if variable is not None:
                variable.set(value)
            if callable(command):
                command()
        act = self._qmenu.addAction(str(label))
        if act is not None:
            act.triggered.connect(lambda checked=False, fn=_on_trig: fn())
        self._entries.append({"type": "radiobutton", "label": label, "command": _on_trig, "variable": variable, "value": value, "action": act})

    def add_checkbutton(self, label: str = "", variable: BooleanVar | None = None, command: Callable | None = None, **kw):
        def _on_trig():
            if variable is not None:
                variable.set(not bool(variable.get()))
            if callable(command):
                command()
        act = self._qmenu.addAction(str(label))
        if act is not None:
            act.triggered.connect(lambda checked=False, fn=_on_trig: fn())
        self._entries.append({"type": "checkbutton", "label": label, "command": _on_trig, "variable": variable, "action": act})

    def configure(self, cnf=None, **kw):
        pass

    config = configure

    def type(self, index: int) -> str:
        if 0 <= int(index) < len(self._entries):
            return str(self._entries[int(index)].get("type", "command"))
        return "command"

    def nametowidget(self, name):
        if isinstance(name, Menu):
            return name
        for entry in self._entries:
            if str(entry.get("menu", "")) == str(name) or entry.get("label") == str(name):
                return entry.get("menu")
        if self._entries and isinstance(self._entries[0].get("menu"), Menu):
            return self._entries[0]["menu"]
        return self

    def index(self, pattern) -> int:
        if pattern == "end":
            return len(self._entries) - 1
        return int(pattern)

    def entrycget(self, index: int, option: str) -> Any:
        if 0 <= int(index) < len(self._entries):
            return self._entries[int(index)].get(option, "")
        return ""

    def invoke(self, index: int):
        if 0 <= int(index) < len(self._entries):
            cmd = self._entries[int(index)].get("command")
            if callable(cmd):
                return cmd()

    def tk_popup(self, x: int, y: int):
        if not ("PYTEST_CURRENT_TEST" in os.environ):
            self._qmenu.popup(QPoint(int(x), int(y)))

    post = tk_popup

    def unpost(self):
        self._qmenu.hide()

    def destroy(self):
        self._tk_destroyed = True
        self._qmenu.hide()


class PhotoImage:
    def __init__(self, width: int = 16, height: int = 16, file: str | None = None, **kw):
        ensure_qapp()
        if file and os.path.exists(str(file)):
            self._pixmap = QPixmap(str(file))
        else:
            self._pixmap = QPixmap(max(1, int(width)), max(1, int(height)))
            self._pixmap.fill(Qt.GlobalColor.transparent)

    def put(self, data, to=None):
        pass


class Style:
    """Bộ quản lý QSS Stylesheet hiện đại cho toàn bộ ứng dụng PyQt6."""
    def __init__(self, master=None):
        self.master = master
        self._theme = "clam"
        self._rules: dict[str, dict[str, Any]] = {}

    def theme_use(self, themename: str | None = None) -> str:
        if themename is not None:
            self._theme = str(themename)
        return self._theme

    def element_create(self, *args, **kw):
        pass

    def layout(self, *args, **kw):
        pass

    def configure(self, style: str, **kw):
        self._rules.setdefault(style, {}).update(kw)
        if style == ".":
            self._apply_global_qss(kw)

    def map(self, style: str, **kw):
        pass

    def _apply_global_qss(self, root_cfg: dict[str, Any]):
        app = QApplication.instance()
        if app is None:
            return
        bg = root_cfg.get("background", "#f0f0f0")
        fg = root_cfg.get("foreground", "#000000")
        text_bg = root_cfg.get("fieldbackground", "#ffffff")
        is_dark = str(bg).lower() in ("#2b2b2b", "#1e1e1e", "#18181b")

        sidebar_bg = "#202124" if is_dark else "#e5e7eb"
        sidebar_hover = "#2d2f34" if is_dark else "#d1d5db"
        sidebar_sel_bg = "#1e3a5f" if is_dark else "#dbeafe"
        accent = "#4dabf7" if is_dark else "#005fb8"
        border = "#444444" if is_dark else "#cbd5e1"
        btn_bg = "#383838" if is_dark else "#ffffff"
        btn_hover = "#484848" if is_dark else "#f1f5f9"
        dis_bg = "#323232" if is_dark else "#e2e8f0"
        dis_fg = "#888888" if is_dark else "#94a3b8"
        alt_row = "#252526" if is_dark else "#f8fafc"

        qss = f"""
        QMainWindow, QDialog, QWidget {{
            background-color: {bg};
            color: {fg};
            font-family: "Segoe UI";
            font-size: 9pt;
        }}
        QFrame#SidebarFrame {{
            background-color: {sidebar_bg};
            border: 1px solid {border};
            border-radius: 6px;
        }}
        QLabel#SidebarTitleLabel {{
            background-color: transparent;
            color: {accent};
            letter-spacing: 0.5px;
        }}
        QPushButton#SidebarToggleBtn {{
            background-color: transparent;
            border: 1px solid transparent;
            border-radius: 4px;
        }}
        QPushButton#SidebarToggleBtn:hover {{
            background-color: {sidebar_hover};
            border: 1px solid {border};
        }}
        QPushButton#SidebarNavBtn {{
            background-color: transparent;
            color: {fg};
            text-align: left;
            padding: 6px 10px;
            border: 1px solid transparent;
            border-left: 3px solid transparent;
            border-radius: 4px;
            font-weight: 500;
        }}
        QPushButton#SidebarNavBtn:hover {{
            background-color: {sidebar_hover};
        }}
        QPushButton#SidebarNavBtn:checked {{
            background-color: {sidebar_sel_bg};
            color: {accent};
            border-left: 3px solid {accent};
            font-weight: bold;
        }}
        QGroupBox {{
            border: 1px solid {border};
            border-radius: 5px;
            margin-top: 8px;
            padding-top: 6px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 10px;
            padding: 0 4px;
            color: {fg};
        }}
        QPushButton {{
            background-color: {btn_bg};
            color: {fg};
            border: 1px solid {border};
            border-radius: 4px;
            padding: 4px 10px;
        }}
        QPushButton:hover {{
            background-color: {btn_hover};
            border-color: {accent};
        }}
        QPushButton:disabled {{
            background-color: {dis_bg};
            color: {dis_fg};
            border-color: {border};
        }}
        QPushButton[accentButton="true"] {{
            color: {accent};
            border: 1px solid {accent};
            font-weight: bold;
        }}
        QLineEdit, QComboBox, QSpinBox {{
            background-color: {text_bg};
            color: {fg};
            border: 1px solid {border};
            border-radius: 4px;
            padding: 3px 6px;
        }}
        QLineEdit:disabled, QComboBox:disabled {{
            background-color: {dis_bg};
            color: {dis_fg};
        }}
        QTreeWidget {{
            background-color: {text_bg};
            alternate-background-color: {alt_row};
            color: {fg};
            border: 1px solid {border};
            border-radius: 4px;
            gridline-color: {border};
        }}
        QHeaderView::section {{
            background-color: {sidebar_bg};
            color: {fg};
            border: none;
            border-right: 1px solid {border};
            border-bottom: 1px solid {border};
            padding: 4px 6px;
            font-weight: bold;
        }}
        QProgressBar {{
            background-color: {text_bg};
            border: 1px solid {border};
            border-radius: 4px;
        }}
        QProgressBar::chunk {{
            background-color: {accent};
            border-radius: 3px;
        }}
        QMenuBar {{
            background-color: {sidebar_bg};
            color: {fg};
            border-bottom: 1px solid {border};
        }}
        QMenuBar::item:selected, QMenu::item:selected {{
            background-color: {accent};
            color: #ffffff;
        }}
        QMenu {{
            background-color: {text_bg};
            color: {fg};
            border: 1px solid {border};
        }}
        """
        if app.styleSheet() != qss:
            app.setStyleSheet(qss)


# =============================================================================
# 13. CÁC MODULE CON: font, messagebox, filedialog, simpledialog, ttk
# =============================================================================
class _FontWrapper:
    def __init__(self, font=None, **kw):
        ensure_qapp()
        self._qf = _parse_font(font) or QFont("Consolas", 10)

    def measure(self, text: str) -> int:
        fm = QFontMetrics(self._qf)
        return max(1, fm.horizontalAdvance(str(text)))


class font:
    Font = _FontWrapper


class messagebox:
    @staticmethod
    def showinfo(title: str = "", message: str = "", **kw) -> str:
        ensure_qapp()
        parent = kw.get("parent") if isinstance(kw.get("parent"), QWidget) else None
        QMessageBox.information(parent, str(title), str(message))
        return "ok"

    @staticmethod
    def showwarning(title: str = "", message: str = "", **kw) -> str:
        ensure_qapp()
        parent = kw.get("parent") if isinstance(kw.get("parent"), QWidget) else None
        QMessageBox.warning(parent, str(title), str(message))
        return "ok"

    @staticmethod
    def showerror(title: str = "", message: str = "", **kw) -> str:
        ensure_qapp()
        parent = kw.get("parent") if isinstance(kw.get("parent"), QWidget) else None
        QMessageBox.critical(parent, str(title), str(message))
        return "ok"

    @staticmethod
    def askyesno(title: str = "", message: str = "", **kw) -> bool:
        ensure_qapp()
        parent = kw.get("parent") if isinstance(kw.get("parent"), QWidget) else None
        btn = QMessageBox.question(
            parent, str(title), str(message),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        return btn == QMessageBox.StandardButton.Yes


def _convert_filetypes(filetypes) -> str:
    if not filetypes:
        return "All Files (*.*)"
    parts = []
    for label, pattern in filetypes:
        parts.append(f"{label} ({pattern})")
    return ";;".join(parts)


class filedialog:
    @staticmethod
    def askopenfilename(**kw) -> str:
        ensure_qapp()
        parent = kw.get("parent") if isinstance(kw.get("parent"), QWidget) else None
        title = str(kw.get("title", "Chọn tệp"))
        init_dir = str(kw.get("initialdir", ""))
        filt = _convert_filetypes(kw.get("filetypes"))
        path, _ = QFileDialog.getOpenFileName(parent, title, init_dir, filt)
        return path or ""

    @staticmethod
    def asksaveasfilename(**kw) -> str:
        ensure_qapp()
        parent = kw.get("parent") if isinstance(kw.get("parent"), QWidget) else None
        title = str(kw.get("title", "Lưu tệp"))
        init_dir = str(kw.get("initialdir", ""))
        init_file = str(kw.get("initialfile", ""))
        start_path = os.path.join(init_dir, init_file) if init_dir else init_file
        filt = _convert_filetypes(kw.get("filetypes"))
        path, _ = QFileDialog.getSaveFileName(parent, title, start_path, filt)
        return path or ""

    @staticmethod
    def askdirectory(**kw) -> str:
        ensure_qapp()
        parent = kw.get("parent") if isinstance(kw.get("parent"), QWidget) else None
        title = str(kw.get("title", "Chọn thư mục"))
        init_dir = str(kw.get("initialdir", ""))
        path = QFileDialog.getExistingDirectory(parent, title, init_dir)
        return path or ""


class simpledialog:
    @staticmethod
    def askstring(title: str, prompt: str, initialvalue: str = "", **kw) -> str | None:
        ensure_qapp()
        parent = kw.get("parent") if isinstance(kw.get("parent"), QWidget) else None
        text, ok = QInputDialog.getText(parent, str(title), str(prompt), QLineEdit.EchoMode.Normal, str(initialvalue))
        return text if ok else None


class ttk:
    Frame = Frame
    LabelFrame = LabelFrame
    Labelframe = LabelFrame
    PanedWindow = PanedWindow
    Notebook = Notebook
    Label = Label
    Button = Button
    Checkbutton = Checkbutton
    Radiobutton = Radiobutton
    Entry = Entry
    Combobox = Combobox
    Spinbox = Spinbox
    Progressbar = Progressbar
    Scrollbar = Scrollbar
    Separator = Separator
    Treeview = Treeview
    Style = Style
