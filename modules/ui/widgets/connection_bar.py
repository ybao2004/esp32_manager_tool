# -*- coding: utf-8 -*-
"""
Thanh kết nối phần cứng chung (Global Connection Bar) cho PyQt6.
Chứa lựa chọn cổng COM, Baudrate, nút Kết nối/Ngắt kết nối và huy hiệu chip ESP32.
"""
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QComboBox, QPushButton, QToolButton,
    QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, QSize
from modules.config import COMMON_BAUDS
from modules.ui.icons import get_icon
from modules.ui.theme.tokens import ThemeTokens
from modules.ui.theme.manager import ThemeManager


class _ComboCompat(QComboBox):
    def get(self) -> str:
        return self.currentText()

    def set(self, val: str):
        val_str = str(val)
        idx = self.findText(val_str)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.addItem(val_str)
            self.setCurrentIndex(self.count() - 1)

    def bind(self, event: str, callback):
        self.currentTextChanged.connect(lambda _: callback(None))

    def cget(self, prop: str):
        if prop == "state":
            return "readonly" if self.isEnabled() else "disabled"
        return ""

    def config(self, **kwargs):
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")

    def configure(self, **kwargs):
        self.config(**kwargs)

    def winfo_exists(self) -> bool:
        return True

    def __setitem__(self, key, value):
        if key == "values":
            curr = self.currentText()
            self.blockSignals(True)
            self.clear()
            self.addItems([str(v) for v in value])
            self.setCurrentText(curr)
            self.blockSignals(False)
        elif key == "state":
            self.setEnabled(value != "disabled")

    def __getitem__(self, key):
        if key == "values":
            return [self.itemText(i) for i in range(self.count())]
        elif key == "state":
            return "readonly" if self.isEnabled() else "disabled"
        return ""


class _ButtonCompat(QPushButton):
    def cget(self, prop: str):
        if prop == "text":
            return self.text()
        elif prop == "state":
            return "normal" if self.isEnabled() else "disabled"
        return ""

    def config(self, **kwargs):
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")

    configure = config

    def winfo_exists(self) -> bool:
        return True

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        if key == "text":
            self.setText(str(value))
        elif key == "state":
            self.setEnabled(value != "disabled")


class ConnectionBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setProperty("role", "card")
        self._current_tokens: ThemeTokens = ThemeManager.instance().tokens

        self._build_ui()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # Label Cổng COM
        lbl_port = QLabel("Cổng COM:", self)
        lbl_port.setStyleSheet("font-weight: 500;")
        layout.addWidget(lbl_port)

        # Dropdown Cổng COM
        self.port_cb = _ComboCompat(self)
        self.port_cb.setMinimumWidth(220)
        self.port_cb.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        layout.addWidget(self.port_cb)

        # Nút Làm mới cổng COM
        self.refresh_btn = QToolButton(self)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setToolTip("Quét lại danh sách cổng COM")
        self.refresh_btn.setFixedSize(32, 32)
        self.refresh_btn.setIcon(get_icon("refresh", self._current_tokens.text, 18))
        self.refresh_btn.setIconSize(QSize(18, 18))
        self._update_refresh_btn_style(self._current_tokens)
        layout.addWidget(self.refresh_btn)

        # Phân cách nhẹ
        layout.addSpacing(6)

        # Label Baudrate
        lbl_baud = QLabel("Baudrate:", self)
        lbl_baud.setStyleSheet("font-weight: 500;")
        layout.addWidget(lbl_baud)

        # Dropdown Baudrate
        self.baud_cb = _ComboCompat(self)
        self.baud_cb.setEditable(True)
        self.baud_cb.addItems(COMMON_BAUDS)
        self.baud_cb.setCurrentText("115200")
        self.baud_cb.setMinimumWidth(110)
        layout.addWidget(self.baud_cb)

        # Phân cách
        layout.addSpacing(6)

        # Nút Kết nối Serial
        self.serial_toggle_btn = _ButtonCompat("Kết nối", self)
        self.serial_toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.serial_toggle_btn.setProperty("accent", "true")
        self.serial_toggle_btn.setIcon(get_icon("plug_disconnected", self._current_tokens.on_accent, 16))
        self.serial_toggle_btn.setIconSize(QSize(16, 16))
        layout.addWidget(self.serial_toggle_btn)

        # Giãn cách linh hoạt
        layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))

        # Chip Badge (Huy hiệu thông tin chip rút gọn)
        self.chip_badge = QLabel("Chưa kết nối chip", self)
        self.chip_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {self._current_tokens.surface_alt};
                color: {self._current_tokens.text_secondary};
                border: 1px solid {self._current_tokens.border};
                border-radius: 12px;
                padding: 3px 10px;
                font-size: 8.5pt;
                font-weight: 500;
            }}
        """)
        layout.addWidget(self.chip_badge)

    def set_chip_badge_info(self, text: str, is_active: bool = False):
        color = self._current_tokens.success if is_active else self._current_tokens.text_secondary
        self.chip_badge.setText(text)
        self.chip_badge.setStyleSheet(f"""
            QLabel {{
                background-color: {self._current_tokens.surface_alt};
                color: {color};
                border: 1px solid {self._current_tokens.border};
                border-radius: 12px;
                padding: 3px 10px;
                font-size: 8.5pt;
                font-weight: 500;
            }}
        """)

    def _update_refresh_btn_style(self, tokens: ThemeTokens):
        self.refresh_btn.setStyleSheet(f"""
            QToolButton {{
                background-color: {tokens.surface};
                border: 1px solid {tokens.border};
                border-radius: {tokens.radius_control}px;
                padding: 0px;
            }}
            QToolButton:hover {{
                background-color: {tokens.surface_alt};
                border-color: {tokens.accent};
            }}
            QToolButton:pressed {{
                background-color: {tokens.selection};
            }}
        """)

    def _on_theme_changed(self, tokens: ThemeTokens):
        self._current_tokens = tokens
        self.refresh_btn.setIcon(get_icon("refresh", tokens.text, 18))
        self._update_refresh_btn_style(tokens)
        # Nút serial accent icon theo on_accent
        is_conn = (self.serial_toggle_btn.text() == "Ngắt kết nối")
        ico_name = "plug_connected" if is_conn else "plug_disconnected"
        self.serial_toggle_btn.setIcon(get_icon(ico_name, tokens.on_accent, 16))
        self.set_chip_badge_info(self.chip_badge.text(), "Chưa" not in self.chip_badge.text())
