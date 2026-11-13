# -*- coding: utf-8 -*-
"""
Hộp thoại xóa vùng nhớ Flash tùy chỉnh (EraseRegionDialog) cho PyQt6.
Cho phép xóa phân vùng theo địa chỉ Offset và Size tùy chọn, bắt buộc căn lề 4KB.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget
)
from PyQt6.QtCore import Qt
from typing import Optional, Tuple
from modules.partition.unit_formatter import parse_size_or_offset, format_hex, format_bytes_human
from modules.ui import dialogs_service as dlg


class EraseRegionDialog(QDialog):
    def __init__(self, parent=None, default_offset="0x10000", default_size="0x10000"):
        if parent is not None and not isinstance(parent, QWidget):
            parent = None
        super().__init__(parent)
        self.setWindowTitle("Xóa vùng nhớ Flash (Erase Region)")
        self.setMinimumWidth(380)
        self.port_label: Optional[str] = None
        # Nếu tham số thứ 2 được truyền là tên cổng (vd 'COM3') thì dùng mặc định vùng NVS
        try:
            parse_size_or_offset(str(default_offset))
        except Exception:
            self.port_label = str(default_offset)
            default_offset = "0x9000"
            default_size = "0x6000"
        self.offset: Optional[int] = None
        self.size: Optional[int] = None
        self.result: Optional[Tuple[int, int]] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        warn_lbl = QLabel("Cảnh báo: Hành động này sẽ xóa trắng dữ liệu Flash trong phạm vi chọn!", self)
        warn_lbl.setStyleSheet("color: #D32F2F; font-weight: bold;")
        warn_lbl.setWordWrap(True)
        layout.addWidget(warn_lbl)

        # Offset input
        h_off = QHBoxLayout()
        h_off.addWidget(QLabel("Địa chỉ bắt đầu (Offset):", self))
        self.entry_offset = QLineEdit(default_offset, self)
        h_off.addWidget(self.entry_offset)
        layout.addLayout(h_off)

        # Size input
        h_sz = QHBoxLayout()
        h_sz.addWidget(QLabel("Kích thước vùng xóa (Size):", self))
        self.entry_size = QLineEdit(default_size, self)
        h_sz.addWidget(self.entry_size)
        layout.addLayout(h_sz)

        self.info_lbl = QLabel("", self)
        self.info_lbl.setWordWrap(True)
        layout.addWidget(self.info_lbl)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Hủy bỏ", self)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_erase = QPushButton("Thực hiện Xóa", self)
        btn_erase.setProperty("danger", "true")
        btn_erase.clicked.connect(self._on_erase)
        btn_box.addWidget(btn_erase)
        layout.addLayout(btn_box)

        self.entry_offset.textChanged.connect(self._validate)
        self.entry_size.textChanged.connect(self._validate)
        self._validate()

    def _validate(self):
        try:
            off = parse_size_or_offset(self.entry_offset.text())
            sz = parse_size_or_offset(self.entry_size.text())
            if sz <= 0:
                self.info_lbl.setText("[LỖI] Kích thước phải lớn hơn 0.")
                return
            if off % 4096 != 0 or sz % 4096 != 0:
                self.info_lbl.setText("[CẢNH BÁO] Offset và Size bắt buộc phải căn lề 4KB (0x1000).")
                return
            self.info_lbl.setText(f"[HỢP LỆ] Phạm vi: {format_hex(off)} -> {format_hex(off + sz)} ({format_bytes_human(sz)})")
        except Exception:
            self.info_lbl.setText("[CẢNH BÁO] Vui lòng nhập định dạng Hex (0x...) hoặc dung lượng hợp lệ.")

    def _on_erase(self):
        try:
            off = parse_size_or_offset(self.entry_offset.text())
            sz = parse_size_or_offset(self.entry_size.text())
            if off % 4096 != 0 or sz % 4096 != 0:
                dlg.show_error("Lỗi", "Địa chỉ và kích thước bắt buộc phải là bội số của 4KB (sector SPI Flash).", self)
                return
            if not dlg.ask_yes_no("Xác nhận xóa Flash", f"Bạn có chắc chắn muốn xóa {format_bytes_human(sz)} từ {format_hex(off)}?", danger=True, parent=self):
                return
            self.offset = off
            self.size = sz
            self.result = (off, sz)
            self.accept()
        except Exception as e:
            dlg.show_error("Lỗi", f"Giá trị không hợp lệ: {e}", self)
