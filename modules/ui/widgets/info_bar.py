# -*- coding: utf-8 -*-
"""
Thanh thông báo nội tuyến (InfoBar) cho PyQt6 chuẩn phong cách Fluent UI.
Hiển thị thông báo trạng thái, gợi ý thao tác và cảnh báo ngay trong giao diện.
"""
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QToolButton, QWidget
from PyQt6.QtCore import Qt, QSize
from modules.ui.icons import get_icon
from modules.ui.theme.tokens import ThemeTokens
from modules.ui.theme.manager import ThemeManager


class InfoBar(QFrame):
    def __init__(self, message: str = "", level: str = "info", closable: bool = False, parent: QWidget = None):
        super().__init__(parent)
        self._level = level
        self._current_tokens: ThemeTokens = ThemeManager.instance().tokens

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        # Icon
        self._icon_lbl = QLabel(self)
        layout.addWidget(self._icon_lbl)

        # Message
        self._msg_lbl = QLabel(message, self)
        self._msg_lbl.setWordWrap(True)
        layout.addWidget(self._msg_lbl, 1)

        # Close button
        if closable:
            self._close_btn = QToolButton(self)
            self._close_btn.setStyleSheet("border: none; background: transparent;")
            self._close_btn.setIcon(get_icon("delete", self._current_tokens.text_secondary, 14))
            self._close_btn.setIconSize(QSize(14, 14))
            self._close_btn.clicked.connect(self.hide)
            layout.addWidget(self._close_btn)

        self._apply_style()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def set_message(self, text: str, level: str | None = None):
        if level:
            self._level = level
        self._msg_lbl.setText(text)
        self._apply_style()

    def _apply_style(self):
        t = self._current_tokens
        if self._level == "success":
            color = t.success
            ico = "success"
        elif self._level == "warning":
            color = t.warning
            ico = "warning"
        elif self._level == "error":
            color = t.danger
            ico = "error"
        else:
            color = t.accent
            ico = "info"

        self._icon_lbl.setPixmap(get_icon(ico, color, 18).pixmap(18, 18))
        self.setStyleSheet(f"""
            InfoBar {{
                background-color: {t.surface_alt};
                border: 1px solid {t.border};
                border-radius: {t.radius_card}px;
            }}
            QLabel {{
                color: {t.text};
                font-size: 9pt;
            }}
        """)

    def _on_theme_changed(self, tokens: ThemeTokens):
        self._current_tokens = tokens
        self._apply_style()
