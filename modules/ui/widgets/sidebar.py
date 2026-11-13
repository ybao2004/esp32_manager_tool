# -*- coding: utf-8 -*-
"""
Thanh điều hướng bên trái (Collapsible Sidebar Navigation) cho PyQt6.
Hỗ trợ chuyển đổi chế độ mở rộng / thu gọn (icon-only), hoạt họa mượt mà và cập nhật màu vector theo theme.
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QToolButton, QButtonGroup,
    QSpacerItem, QSizePolicy, QWidget
)
from PyQt6.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve, QSize
from modules.ui.icons import get_icon
from modules.ui.text import qt_text
from modules.ui.theme.tokens import ThemeTokens
from modules.ui.theme.manager import ThemeManager
from modules.ui.widgets.update_badge import UpdateDotBadge


class Sidebar(QFrame):
    page_selected = pyqtSignal(int)

    NAV_ITEMS = [
        ("inspector", "Kiểm tra Chip", "inspector"),
        ("monitor", "Serial Monitor & Log", "monitor"),
        ("flasher", "Nạp Firmware", "flash"),
        ("partition", "Phân vùng", "partition"),
        ("backup", "Sao lưu & Chép", "backup"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self._is_collapsed = False
        self._buttons: list[QToolButton] = []
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        self._current_tokens: ThemeTokens = ThemeManager.instance().tokens

        self._build_ui()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 8, 6, 8)
        layout.setSpacing(4)

        # 1. Nút Thu gọn / Mở rộng ở trên cùng
        self.btn_toggle_sidebar = QToolButton(self)
        self.btn_toggle_sidebar.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_sidebar.setToolTip("Thu gọn / Mở rộng thanh bên (Ctrl+B)")
        self.btn_toggle_sidebar.setIcon(get_icon("menu", self._current_tokens.sidebar_text, 20))
        self.btn_toggle_sidebar.setIconSize(QSize(20, 20))
        self.btn_toggle_sidebar.setText("  " + qt_text("DANH MỤC"))
        self.btn_toggle_sidebar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_toggle_sidebar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_toggle_sidebar.clicked.connect(self.toggle_collapse)
        layout.addWidget(self.btn_toggle_sidebar)

        # 2. Danh sách 5 nút điều hướng chính
        for idx, (key, label, icon_name) in enumerate(self.NAV_ITEMS):
            btn = QToolButton(self)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setText("  " + qt_text(label))
            btn.setToolTip(label)
            btn.setIcon(get_icon(icon_name, self._current_tokens.sidebar_text, 20))
            btn.setIconSize(QSize(20, 20))
            btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setProperty("nav_key", key)
            btn.setProperty("nav_icon", icon_name)

            btn.clicked.connect(lambda checked=False, i=idx: self.page_selected.emit(i))
            self._btn_group.addButton(btn, idx)
            self._buttons.append(btn)
            layout.addWidget(btn)

        # Đẩy nút Cài đặt xuống đáy
        layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # 3. Nút Cài đặt ở dưới cùng
        self.btn_settings = QToolButton(self)
        self.btn_settings.setCheckable(True)
        self.btn_settings.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_settings.setText("  " + qt_text("Cài đặt"))
        self.btn_settings.setToolTip("Cài đặt hệ thống")
        self.btn_settings.setIcon(get_icon("settings", self._current_tokens.sidebar_text, 20))
        self.btn_settings.setIconSize(QSize(20, 20))
        self.btn_settings.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.btn_settings.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_settings.setProperty("nav_key", "settings")
        self.btn_settings.setProperty("nav_icon", "settings")
        self.btn_settings.clicked.connect(lambda checked=False: self.page_selected.emit(5))
        self._btn_group.addButton(self.btn_settings, 5)
        self._buttons.append(self.btn_settings)
        self._settings_badge = UpdateDotBadge(self.btn_settings, margin_right=6, margin_top=5)
        layout.addWidget(self.btn_settings)

        # Thiết lập độ rộng mặc định
        w = self._current_tokens.sidebar_width_expanded
        self.setFixedWidth(w)

        # Mặc định chọn mục đầu tiên (Kiểm tra phần cứng)
        if self._buttons:
            self._buttons[0].setChecked(True)
        self._btn_group.buttonToggled.connect(lambda _b, _c: self._sync_icons())
        self._sync_icons()

    def _sync_icons(self):
        tokens = self._current_tokens
        self.btn_toggle_sidebar.setIcon(get_icon("menu", tokens.sidebar_text, 20))
        for b in self._buttons:
            ico_name = b.property("nav_icon")
            if ico_name:
                ico_col = "#FFFFFF" if b.isChecked() else tokens.sidebar_text
                b.setIcon(get_icon(str(ico_name), ico_col, 20))

    @property
    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def set_collapsed(self, collapsed: bool):
        if self._is_collapsed == collapsed:
            return
        self._is_collapsed = collapsed
        target_w = self._current_tokens.sidebar_width_collapsed if self._is_collapsed else self._current_tokens.sidebar_width_expanded

        # Đổi kiểu hiển thị nút
        style = Qt.ToolButtonStyle.ToolButtonIconOnly if self._is_collapsed else Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        self.btn_toggle_sidebar.setToolButtonStyle(style)
        for b in self._buttons:
            b.setToolButtonStyle(style)

        self.setFixedWidth(target_w)
        if hasattr(self, "_settings_badge"):
            self._settings_badge.reposition()

    def set_settings_badge(self, active: bool):
        """Hiển thị hoặc ẩn dấu chấm đỏ hướng dẫn trên nút Cài đặt."""
        if hasattr(self, "_settings_badge"):
            self._settings_badge.set_active(bool(active))

    def has_settings_badge(self) -> bool:
        return hasattr(self, "_settings_badge") and self._settings_badge.is_active()

    def toggle_collapse(self):
        self.set_collapsed(not self._is_collapsed)

    def select(self, index: int):
        if 0 <= index < len(self._buttons):
            self._buttons[index].setChecked(True)
            self.page_selected.emit(index)

    def _on_theme_changed(self, tokens: ThemeTokens):
        self._current_tokens = tokens
        # Cập nhật lại màu các icon trên sidebar theo trạng thái chọn & theme
        self._sync_icons()

        # Cập nhật kích thước nếu preset thay đổi
        if self._is_collapsed:
            self.setFixedWidth(tokens.sidebar_width_collapsed)
        else:
            self.setFixedWidth(tokens.sidebar_width_expanded)
