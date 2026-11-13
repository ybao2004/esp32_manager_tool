# -*- coding: utf-8 -*-
"""
Khung thẻ chứa nội dung (Card Container) chuẩn thiết kế Windows 11 Fluent.
Bo góc nhẹ, viền mảnh, hỗ trợ tiêu đề nhóm và vùng công cụ ở header.
"""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QWidget, QSizePolicy
)
from PyQt6.QtCore import Qt


class Card(QFrame):
    def __init__(self, title: str = "", icon_name: str = "", parent: QWidget = None, danger: bool = False, **kwargs):
        super().__init__(parent)
        self.setProperty("role", "card_danger" if danger else "card")

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(12, 8, 12, 8)
        self._main_layout.setSpacing(6)

        self._header_layout = None
        self._title_lbl = None

        if title or icon_name:
            self._header_layout = QHBoxLayout()
            self._header_layout.setContentsMargins(0, 0, 0, 2)
            self._header_layout.setSpacing(6)

            if icon_name:
                from modules.ui.icons import bind_themed_icon
                icon_lbl = QLabel(self)
                bind_themed_icon(icon_lbl, icon_name, size=16)
                self._header_layout.addWidget(icon_lbl)

            if title:
                self._title_lbl = QLabel(title, self)
                self._title_lbl.setProperty("role", "section")
                if danger:
                    self._title_lbl.setStyleSheet("color: #D32F2F; font-weight: bold;")
                self._header_layout.addWidget(self._title_lbl)

            self._header_layout.addStretch()
            self._main_layout.addLayout(self._header_layout)

        # Body widget / layout
        self._body_widget = QWidget(self)
        self._body_layout = QVBoxLayout(self._body_widget)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(6)
        self._main_layout.addWidget(self._body_widget, 1)

    def set_title(self, title: str):
        if self._title_lbl:
            self._title_lbl.setText(title)

    def add_header_widget(self, widget: QWidget):
        if self._header_layout:
            # Thêm trước stretch ở cuối
            count = self._header_layout.count()
            self._header_layout.insertWidget(count - 1, widget)

    @property
    def body_layout(self) -> QVBoxLayout:
        return self._body_layout

    @property
    def content_layout(self) -> QVBoxLayout:
        return self._body_layout
