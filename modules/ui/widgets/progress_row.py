# -*- coding: utf-8 -*-
"""
Dòng tiến trình nhân bản board đích (ProgressRow) cho Tab 5.
Mỗi board đích có checkbox chọn, nhãn cổng COM, thanh tiến trình riêng và trạng thái chi tiết.
"""
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QCheckBox, QLabel, QProgressBar, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal
from modules.ui.theme.tokens import ThemeTokens
from modules.ui.theme.manager import ThemeManager


class ProgressRow(QWidget):
    toggled = pyqtSignal(bool)

    def __init__(self, port: str, description: str = "", checked: bool = True, parent=None):
        super().__init__(parent)
        self.port = port
        self._current_tokens: ThemeTokens = ThemeManager.instance().tokens

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(10)

        # Checkbox chọn
        self.checkbox = QCheckBox(self)
        self.checkbox.setChecked(checked)
        self.checkbox.toggled.connect(self.toggled.emit)
        layout.addWidget(self.checkbox)

        # Label tên cổng
        display_name = f"{port} ({description})" if description else port
        self.port_lbl = QLabel(display_name, self)
        self.port_lbl.setMinimumWidth(160)
        self.port_lbl.setStyleSheet("font-weight: 500;")
        layout.addWidget(self.port_lbl)

        # Thanh tiến trình
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setMinimumWidth(180)
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.progress_bar)

        # Nhãn trạng thái
        self.status_lbl = QLabel("Sẵn sàng", self)
        self.status_lbl.setMinimumWidth(120)
        self.status_lbl.setStyleSheet(f"color: {self._current_tokens.text_secondary};")
        layout.addWidget(self.status_lbl)

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def is_checked(self) -> bool:
        return self.checkbox.isChecked()

    def set_checked(self, checked: bool):
        self.checkbox.setChecked(checked)

    def set_progress(self, percent: int, status_text: str = "", is_error: bool = False, is_success: bool = False):
        self.progress_bar.setValue(max(0, min(100, int(percent))))
        if status_text:
            self.status_lbl.setText(status_text)
        t = self._current_tokens
        if is_error:
            self.status_lbl.setStyleSheet(f"color: {t.danger}; font-weight: bold;")
        elif is_success:
            self.status_lbl.setStyleSheet(f"color: {t.success}; font-weight: bold;")
        else:
            self.status_lbl.setStyleSheet(f"color: {t.text};")

    def reset_state(self):
        self.progress_bar.setValue(0)
        self.status_lbl.setText("Sẵn sàng")
        self.status_lbl.setStyleSheet(f"color: {self._current_tokens.text_secondary};")

    def _on_theme_changed(self, tokens: ThemeTokens):
        self._current_tokens = tokens
