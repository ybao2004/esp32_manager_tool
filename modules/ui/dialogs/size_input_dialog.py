# -*- coding: utf-8 -*-
"""
Hộp thoại tự nhập dung lượng phân vùng (SizeInputDialog) cho PyQt6.
Hỗ trợ chuyển đổi đơn vị KB, MB, Bytes, HEX và kiểm tra căn lề 4KB.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QWidget, QFrame
)
from PyQt6.QtCore import Qt
from typing import Optional
from modules.partition.unit_formatter import format_hex, format_bytes_human, sector_count
from modules.ui import dialogs_service as dlg


def parse_with_unit(val_str: str, unit: str) -> int:
    val_str = val_str.strip()
    if not val_str:
        raise ValueError("Chuỗi rỗng")
    u = unit.upper()
    if u == "HEX":
        return int(val_str, 16)
    val = float(val_str)
    if u == "MB":
        return int(val * 1024 * 1024)
    elif u == "KB":
        return int(val * 1024)
    return int(val)


class SizeInputDialog(QDialog):
    def __init__(self, parent=None, partition_name: str = "", current_size_bytes: int = 0, is_dark_mode: bool = True):
        if parent is not None and not isinstance(parent, QWidget):
            parent = None
        super().__init__(parent)
        self.partition_name = partition_name
        self.current_size_bytes = current_size_bytes
        self.result: Optional[int] = None

        self.setWindowTitle(f"Nhập dung lượng - {partition_name}")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Header info
        lbl_name = QLabel(f"Phân vùng: {partition_name}", self)
        lbl_name.setStyleSheet("font-size: 10pt; font-weight: bold;")
        layout.addWidget(lbl_name)

        curr_info = f"Dung lượng hiện tại: {format_bytes_human(current_size_bytes)} ({format_hex(current_size_bytes)})"
        lbl_curr = QLabel(curr_info, self)
        lbl_curr.setStyleSheet("color: gray;")
        layout.addWidget(lbl_curr)

        # Input row
        h_box = QHBoxLayout()
        h_box.setSpacing(8)
        lbl_new = QLabel("Dung lượng mới:", self)
        h_box.addWidget(lbl_new)

        if current_size_bytes >= 1024 * 1024 and current_size_bytes % (1024 * 1024) == 0:
            init_val = str(current_size_bytes // (1024 * 1024))
            init_unit = "MB"
        elif current_size_bytes % 1024 == 0:
            init_val = str(current_size_bytes // 1024)
            init_unit = "KB"
        else:
            init_val = str(current_size_bytes)
            init_unit = "Bytes"

        self.entry_val = QLineEdit(init_val, self)
        h_box.addWidget(self.entry_val, 1)

        self.cb_unit = QComboBox(self)
        self.cb_unit.addItems(["KB", "MB", "Bytes", "HEX"])
        self.cb_unit.setCurrentText(init_unit)
        h_box.addWidget(self.cb_unit)
        layout.addLayout(h_box)

        # Thông báo tính toán
        self.lbl_info = QLabel("", self)
        self.lbl_info.setWordWrap(True)
        layout.addWidget(self.lbl_info)

        # Nút bấm Xác nhận / Hủy
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Hủy bỏ", self)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_ok = QPushButton("Xác nhận", self)
        btn_ok.setProperty("accent", "true")
        btn_ok.clicked.connect(self._on_ok)
        btn_box.addWidget(btn_ok)
        layout.addLayout(btn_box)

        self.entry_val.textChanged.connect(self._update_info)
        self.cb_unit.currentTextChanged.connect(self._update_info)

        self._update_info()

    def _get_bytes(self) -> int:
        return parse_with_unit(self.entry_val.text(), self.cb_unit.currentText())

    def _update_info(self):
        try:
            b = self._get_bytes()
            if b <= 0:
                self.lbl_info.setText("[CẢNH BÁO] Dung lượng phải lớn hơn 0.")
                return
            status = "[HỢP LỆ] Bội số 4KB" if b % 0x1000 == 0 else "[CẢNH BÁO] Chưa chia hết cho sector 4KB"
            self.lbl_info.setText(f"- {format_bytes_human(b)} ({format_hex(b)}) | {sector_count(b)} sectors | {status}")
        except Exception:
            self.lbl_info.setText("[CẢNH BÁO] Vui lòng nhập số hợp lệ.")

    def _on_ok(self):
        try:
            b = self._get_bytes()
            if b <= 0:
                dlg.show_error("Lỗi", "Dung lượng phải lớn hơn 0.", self)
                return
            if b % 0x1000 != 0:
                if not dlg.ask_yes_no("Cảnh báo", "Dung lượng không chia hết cho 4KB (1 sector SPI Flash). Bạn có muốn tiếp tục?", parent=self):
                    return
            self.result = b
            self.accept()
        except Exception as e:
            dlg.show_error("Lỗi", f"Giá trị không hợp lệ: {e}", self)
