# -*- coding: utf-8 -*-
"""
Bảng điều khiển thu gọn / mở rộng (CollapsiblePanel) cho PyQt6.
Thích hợp cho bảng F1-F15, Wi-Fi panel hoặc ngăn Output thô.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton, QLabel, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from modules.ui.icons import get_icon
from modules.ui.theme.tokens import ThemeTokens
from modules.ui.theme.manager import ThemeManager


class CollapsiblePanel(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, title: str = "", parent: QWidget = None, collapsed: bool = False, **kwargs):
        super().__init__(parent)
        self._is_expanded = True
        self._current_tokens: ThemeTokens = ThemeManager.instance().tokens

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header bar
        self._header = QFrame(self)
        self._header.setProperty("role", "card")
        self._header.setCursor(Qt.CursorShape.PointingHandCursor)
        h_lay = QHBoxLayout(self._header)
        h_lay.setContentsMargins(10, 6, 10, 6)
        h_lay.setSpacing(8)

        self._btn_icon = QToolButton(self._header)
        self._btn_icon.setStyleSheet("border: none; background: transparent;")
        self._btn_icon.setIcon(get_icon("chevron_down", self._current_tokens.text, 16))
        self._btn_icon.setIconSize(QSize(16, 16))
        h_lay.addWidget(self._btn_icon)

        self._title_lbl = QLabel(title, self._header)
        self._title_lbl.setStyleSheet("font-weight: 600;")
        h_lay.addWidget(self._title_lbl)
        h_lay.addStretch()

        self._header.mousePressEvent = lambda e: self.toggle()
        self._btn_icon.clicked.connect(self.toggle)
        layout.addWidget(self._header)

        # Container nội dung
        self._content_widget = QWidget(self)
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 4, 0, 0)
        self._content_layout.setSpacing(6)
        layout.addWidget(self._content_widget)

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

        if collapsed:
            self.set_expanded(False)

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def add_widget(self, widget: QWidget):
        self._content_layout.addWidget(widget)

    def add_layout(self, layout):
        self._content_layout.addLayout(layout)

    def is_expanded(self) -> bool:
        return self._is_expanded

    def set_expanded(self, expanded: bool):
        self._is_expanded = expanded
        self._content_widget.setVisible(self._is_expanded)
        ico = "chevron_down" if self._is_expanded else "chevron_right"
        self._btn_icon.setIcon(get_icon(ico, self._current_tokens.text, 16))
        self.toggled.emit(self._is_expanded)

    def toggle(self):
        self.set_expanded(not self._is_expanded)

    def _on_theme_changed(self, tokens: ThemeTokens):
        self._current_tokens = tokens
        ico = "chevron_down" if self._is_expanded else "chevron_right"
        self._btn_icon.setIcon(get_icon(ico, tokens.text, 16))
