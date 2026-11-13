# -*- coding: utf-8 -*-
"""
Trình quản lý biểu tượng vector Fluent UI System Icons (Microsoft, MIT License).
Tô màu động theo ThemeTokens và kết xuất sắc nét High-DPI qua QSvgRenderer.
"""
import os
import sys
import re
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtCore import QByteArray, QObject, QRectF, QSize, Qt
from PyQt6.QtWidgets import QApplication, QAbstractButton, QLabel

_ICON_CACHE: dict[tuple[str, str, int, float], QIcon] = {}

_ICON_ALIASES: dict[str, str] = {
    "chip": "inspector",
    "trash": "delete",
    "folder": "open",
    "window_console": "monitor",
    "checkmark": "success",
    "router": "server",
    "dismiss": "close",
}


def _get_icons_dir() -> str:
    """Xác định đường dẫn thư mục icons/fluent kể cả khi đóng gói PyInstaller One-File EXE."""
    if hasattr(sys, "_MEIPASS"):
        base_dir = getattr(sys, "_MEIPASS")
    else:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base_dir, "icons", "fluent")


def get_icon(name: str, color: str = "#212121", size: int = 20) -> QIcon:
    """
    Trả về QIcon được kết xuất từ file SVG Fluent UI tương ứng,
    tô màu theo mã HEX 'color' và kích thước 'size'.
    """
    # Ánh xạ các tên biểu tượng alias sang file SVG tương ứng trong icons/fluent
    base_name = name[:-4] if name.endswith(".svg") else name
    resolved_name = _ICON_ALIASES.get(base_name, base_name)
    clean_name = f"{resolved_name}.svg"

    app = QApplication.instance()
    dpr = app.devicePixelRatio() if app else 1.0
    cache_key = (clean_name, color.lower(), size, dpr)
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]

    icons_dir = _get_icons_dir()
    svg_path = os.path.join(icons_dir, clean_name)

    if not os.path.isfile(svg_path):
        # Trả về icon rỗng an toàn nếu file không tồn tại
        empty_icon = QIcon()
        _ICON_CACHE[cache_key] = empty_icon
        return empty_icon

    try:
        with open(svg_path, "r", encoding="utf-8") as f:
            svg_content = f.read()

        # Thay thế màu fill và stroke sang mã màu theo yêu cầu
        # Xử lý các pattern fill="currentColor", fill="#212121", fill="none"
        def _replace_fill(m):
            val = m.group(1).strip()
            if val.lower() == "none":
                return 'fill="none"'
            return f'fill="{color}"'

        modified_svg = re.sub(r'fill="([^"]+)"', _replace_fill, svg_content)
        # Nếu thẻ path không có fill mà có stroke thì đổi stroke
        modified_svg = re.sub(r'stroke="(?!none)[^"]+"', f'stroke="{color}"', modified_svg)
        # Nếu trong SVG chưa có thuộc tính fill ở các path đơn giản
        if 'fill="' not in modified_svg and '<path' in modified_svg:
            modified_svg = modified_svg.replace('<path', f'<path fill="{color}"')

        # Màu cho trạng thái disabled (mờ 35%)
        c_obj = QColor(color)
        dis_color = f"rgba({c_obj.red()}, {c_obj.green()}, {c_obj.blue()}, 0.35)"
        disabled_svg = re.sub(r'fill="([^"]+)"', lambda m: 'fill="none"' if m.group(1).lower() == "none" else f'fill="{dis_color}"', svg_content)

        # Render Active/Normal Pixmap
        renderer = QSvgRenderer(QByteArray(modified_svg.encode("utf-8")))
        pix_w = int(size * dpr)
        pix_h = int(size * dpr)

        pixmap = QPixmap(pix_w, pix_h)
        pixmap.fill(Qt.GlobalColor.transparent)
        pixmap.setDevicePixelRatio(dpr)

        target_rect = QRectF(1.0, 1.0, float(max(1, size - 2)), float(max(1, size - 2)))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer.render(painter, target_rect)
        painter.end()

        # Render Disabled Pixmap
        renderer_dis = QSvgRenderer(QByteArray(disabled_svg.encode("utf-8")))
        pixmap_dis = QPixmap(pix_w, pix_h)
        pixmap_dis.fill(Qt.GlobalColor.transparent)
        pixmap_dis.setDevicePixelRatio(dpr)

        painter_dis = QPainter(pixmap_dis)
        painter_dis.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter_dis.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        renderer_dis.render(painter_dis, target_rect)
        painter_dis.end()

        icon = QIcon()
        icon.addPixmap(pixmap, QIcon.Mode.Normal, QIcon.State.Off)
        icon.addPixmap(pixmap, QIcon.Mode.Active, QIcon.State.Off)
        icon.addPixmap(pixmap_dis, QIcon.Mode.Disabled, QIcon.State.Off)

        _ICON_CACHE[cache_key] = icon
        return icon

    except Exception:
        fallback = QIcon()
        _ICON_CACHE[cache_key] = fallback
        return fallback


class _IconThemeBinder(QObject):
    """Tự động cập nhật QIcon/QPixmap của widget mỗi khi ThemeManager đổi Light/Dark."""

    def __init__(self, target, icon_name: str, size: int = 20, role: str = "text"):
        super().__init__(target)
        self._target = target
        self._icon_name = icon_name
        self._size = size
        self._role = role

    def apply(self, tokens) -> None:
        if self._target is None or tokens is None:
            return
        if self._role == "on_accent":
            color = tokens.on_accent
        elif self._role == "muted":
            color = tokens.text_secondary
        elif self._role == "danger":
            color = tokens.danger
        else:
            color = tokens.text
        ic = get_icon(self._icon_name, color=color, size=self._size)
        try:
            if isinstance(self._target, QAbstractButton):
                self._target.setIcon(ic)
            elif isinstance(self._target, QLabel):
                if not ic.isNull():
                    self._target.setPixmap(ic.pixmap(self._size, self._size))
        except RuntimeError:
            pass


def bind_themed_icon(target, name: str, size: int = 20, role: str = "text"):
    """Gắn icon vector theo ThemeTokens hiện tại và tự tô lại khi đổi chế độ Sáng/Tối."""
    from modules.ui.theme.manager import ThemeManager

    tm = ThemeManager.instance()
    binder = _IconThemeBinder(target, name, size=size, role=role)
    # Giữ tham chiếu Python cùng vòng đời widget để WeakMethod hoạt động ổn định
    setattr(target, "_icon_theme_binder", binder)
    binder.apply(tm.tokens)
    tm.theme_changed.connect(binder.apply)
    return binder
