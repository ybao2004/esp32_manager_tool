# -*- coding: utf-8 -*-
"""
Hộp thoại Thêm mới hoặc Chỉnh sửa phân vùng (PartitionEditDialog) cho PyQt6.
Tuân thủ chuẩn ESP-IDF cho dải địa chỉ App (bội số 64KB, offset >= 0x10000)
và Data (bội số 4KB).
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QGroupBox, QFrame, QWidget
)
from PyQt6.QtCore import Qt
from typing import Optional
from modules.partition.partition_model import PartitionEntry
from modules.partition.unit_formatter import (
    format_hex, format_bytes_human, sector_count, align_up, parse_size_or_offset
)
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


class PartitionEditDialog(QDialog):
    """Hộp thoại Thêm mới hoặc Chỉnh sửa một phân vùng ESP32 (PyQt6)"""

    def __init__(
        self,
        parent=None,
        entry: Optional[PartitionEntry] = None,
        suggested_offset: int = 0x10000,
        is_dark_mode: bool = True,
        default_name: str = "new_part",
    ):
        if parent is not None and not isinstance(parent, QWidget):
            parent = None
        super().__init__(parent)
        self.is_edit = (entry is not None)
        self.is_dark_mode = is_dark_mode
        self.result: Optional[PartitionEntry] = None

        if entry:
            self.entry = entry.clone()
        else:
            self.entry = PartitionEntry(
                name=default_name or "new_part",
                type_str="app",
                subtype_str="factory",
                offset=suggested_offset,
                size=1024 * 1024
            )

        self.setWindowTitle("Chỉnh Sửa Phân Vùng" if self.is_edit else "Thêm Phân Vùng Mới")
        self.setMinimumWidth(500)

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(8)
        row = 0

        # 1. Name
        lbl_name = QLabel("Tên phân vùng (Name):", self)
        lbl_name.setStyleSheet("font-weight: bold;")
        self.entry_name = QLineEdit(self.entry.name, self)
        self.entry_name.setMaxLength(16)
        hint_name = QLabel("(Tối đa 15 ký tự ASCII)", self)
        hint_name.setStyleSheet("color: gray;")
        grid.addWidget(lbl_name, row, 0)
        grid.addWidget(self.entry_name, row, 1)
        grid.addWidget(hint_name, row, 2)
        row += 1

        # 2. Type
        lbl_type = QLabel("Loại chính (Type):", self)
        lbl_type.setStyleSheet("font-weight: bold;")
        self.cb_type = QComboBox(self)
        self.cb_type.addItems(["app", "data"])
        curr_type = self.entry.type_str.lower()
        idx_type = self.cb_type.findText(curr_type)
        if idx_type >= 0:
            self.cb_type.setCurrentIndex(idx_type)
        self.cb_type.currentTextChanged.connect(self._on_type_changed)
        grid.addWidget(lbl_type, row, 0)
        grid.addWidget(self.cb_type, row, 1)
        row += 1

        # 3. Subtype
        lbl_subtype = QLabel("Phân loại phụ (SubType):", self)
        lbl_subtype.setStyleSheet("font-weight: bold;")
        self.cb_subtype = QComboBox(self)
        self.cb_subtype.setEditable(True)
        self._update_subtype_options(self.cb_type.currentText())
        curr_subtype = self.entry.subtype_str.lower()
        idx_sub = self.cb_subtype.findText(curr_subtype)
        if idx_sub >= 0:
            self.cb_subtype.setCurrentIndex(idx_sub)
        else:
            self.cb_subtype.setEditText(curr_subtype)
        grid.addWidget(lbl_subtype, row, 0)
        grid.addWidget(self.cb_subtype, row, 1)
        row += 1

        # 4. Offset
        lbl_offset = QLabel("Địa chỉ bắt đầu (Offset):", self)
        lbl_offset.setStyleSheet("font-weight: bold;")
        off_layout = QHBoxLayout()
        self.entry_offset = QLineEdit(format_hex(self.entry.offset), self)
        btn_align = QPushButton("Căn biên chuẩn", self)
        btn_align.clicked.connect(self._auto_align_offset)
        off_layout.addWidget(self.entry_offset)
        off_layout.addWidget(btn_align)
        grid.addWidget(lbl_offset, row, 0)
        grid.addLayout(off_layout, row, 1, 1, 2)
        row += 1

        # 5. Size
        lbl_size = QLabel("Dung lượng (Size):", self)
        lbl_size.setStyleSheet("font-weight: bold;")
        size_layout = QHBoxLayout()
        if self.entry.size >= 1024 * 1024 and self.entry.size % (1024 * 1024) == 0:
            init_val = str(self.entry.size // (1024 * 1024))
            init_unit = "MB"
        elif self.entry.size % 1024 == 0:
            init_val = str(self.entry.size // 1024)
            init_unit = "KB"
        else:
            init_val = str(self.entry.size)
            init_unit = "Bytes"

        self.entry_size_val = QLineEdit(init_val, self)
        self.cb_size_unit = QComboBox(self)
        self.cb_size_unit.addItems(["KB", "MB", "Bytes", "HEX"])
        idx_unit = self.cb_size_unit.findText(init_unit)
        if idx_unit >= 0:
            self.cb_size_unit.setCurrentIndex(idx_unit)
        size_layout.addWidget(self.entry_size_val)
        size_layout.addWidget(self.cb_size_unit)

        grid.addWidget(lbl_size, row, 0)
        grid.addLayout(size_layout, row, 1)
        row += 1

        # 6. Flags
        lbl_flags = QLabel("Cờ bảo mật (Flags):", self)
        lbl_flags.setStyleSheet("font-weight: bold;")
        flags_layout = QHBoxLayout()
        self.chk_enc = QCheckBox("encrypted (Mã hóa)", self)
        self.chk_enc.setChecked("encrypted" in self.entry.flags_str.lower())
        self.chk_ro = QCheckBox("readonly (Chỉ đọc)", self)
        self.chk_ro.setChecked("readonly" in self.entry.flags_str.lower())
        flags_layout.addWidget(self.chk_enc)
        flags_layout.addWidget(self.chk_ro)
        flags_layout.addStretch()
        grid.addWidget(lbl_flags, row, 0)
        grid.addLayout(flags_layout, row, 1, 1, 2)
        row += 1

        layout.addLayout(grid)

        # Preview box
        preview_group = QGroupBox("Xem trước & Kiểm tra tính hợp lệ", self)
        p_layout = QVBoxLayout(preview_group)
        self.lbl_preview = QLabel("", preview_group)
        self.lbl_preview.setWordWrap(True)
        p_layout.addWidget(self.lbl_preview)
        layout.addWidget(preview_group)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_cancel = QPushButton("Hủy bỏ", self)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_save = QPushButton("Lưu phân vùng" if self.is_edit else "Thêm phân vùng", self)
        btn_save.setProperty("accent", "true")
        btn_save.clicked.connect(self._on_save)
        btn_box.addWidget(btn_save)
        layout.addLayout(btn_box)

        # Connect change listeners
        self.entry_name.textChanged.connect(self._update_preview)
        self.entry_offset.textChanged.connect(self._update_preview)
        self.entry_size_val.textChanged.connect(self._update_preview)
        self.cb_size_unit.currentTextChanged.connect(self._update_preview)
        self.cb_subtype.currentTextChanged.connect(self._update_preview)

        self._update_preview()

    def _get_size_in_bytes(self) -> int:
        return parse_with_unit(self.entry_size_val.text(), self.cb_size_unit.currentText())

    def _on_type_changed(self, text: str):
        t = text.lower()
        self._update_subtype_options(t)
        if t == "app":
            self.cb_subtype.setEditText("factory")
        else:
            self.cb_subtype.setEditText("nvs")
        self._auto_align_offset()
        self._update_preview()

    def _update_subtype_options(self, type_str: str):
        self.cb_subtype.clear()
        if type_str.lower() == "app":
            opts = ["factory", "ota_0", "ota_1", "ota_2", "test"]
        else:
            opts = ["nvs", "phy", "ota", "spiffs", "littlefs", "fat", "coredump", "nvs_keys", "efuse"]
        self.cb_subtype.addItems(opts)

    def _auto_align_offset(self):
        try:
            curr_off = parse_size_or_offset(self.entry_offset.text())
            is_app = (self.cb_type.currentText().lower() == "app")
            pad_to = 0x10000 if is_app else 0x1000
            aligned = align_up(curr_off, pad_to)
            if is_app and aligned < 0x10000:
                aligned = 0x10000
            self.entry_offset.setText(format_hex(aligned))
        except Exception:
            self.entry_offset.setText("0x10000" if self.cb_type.currentText().lower() == "app" else "0x9000")

    def _update_preview(self):
        try:
            name = self.entry_name.text().strip()
            type_str = self.cb_type.currentText().strip()
            subtype_str = self.cb_subtype.currentText().strip()
            offset_val = parse_size_or_offset(self.entry_offset.text())
            size_val = self._get_size_in_bytes()
            end_val = offset_val + size_val

            lines = []
            lines.append(f"- Dải địa chỉ: {format_hex(offset_val)} -> {format_hex(end_val)}")
            lines.append(f"- Dung lượng: {format_bytes_human(size_val)} ({size_val:,} Bytes) | {sector_count(size_val)} Sectors (4KB)")

            warnings = []
            if len(name.encode('utf-8')) > 16:
                warnings.append("[CẢNH BÁO] Tên phân vùng dài hơn 16 bytes!")
            if size_val % 0x1000 != 0:
                warnings.append("[LỖI] Dung lượng bắt buộc phải là bội số của 4KB (0x1000)!")

            if type_str == "app":
                if offset_val % 0x10000 != 0:
                    warnings.append(f"[LỖI] Phân vùng App bắt buộc Offset phải chia hết cho 64KB (0x10000). Hiện tại: {format_hex(offset_val)}")
                if offset_val < 0x10000:
                    warnings.append("[LỖI] Phân vùng App không được đặt trong vùng cấm < 0x10000!")
            else:
                if offset_val % 0x1000 != 0:
                    warnings.append(f"[LỖI] Phân vùng Data bắt buộc Offset phải chia hết cho 4KB (0x1000). Hiện tại: {format_hex(offset_val)}")

            if not warnings:
                lines.append("[HỢP LỆ] Căn biên và thông số hoàn toàn hợp lệ theo chuẩn ESP-IDF.")
            else:
                lines.extend(warnings)

            self.lbl_preview.setText("\n".join(lines))
        except Exception as e:
            self.lbl_preview.setText(f"[CẢNH BÁO] Thông số chưa hoàn chỉnh: {e}")

    def _on_save(self):
        name = self.entry_name.text().strip()
        if not name:
            dlg.show_warning("Thiếu dữ liệu", "Vui lòng nhập tên phân vùng.", self)
            return

        if len(name.encode('utf-8')) > 16:
            dlg.show_warning("Tên quá dài", "Tên phân vùng không được vượt quá 15 ký tự ASCII.", self)
            return

        try:
            offset_val = parse_size_or_offset(self.entry_offset.text())
            size_val = self._get_size_in_bytes()
        except Exception as e:
            dlg.show_error("Sai định dạng", f"Dữ liệu Offset hoặc Size không hợp lệ: {e}", self)
            return

        if size_val <= 0 or size_val % 0x1000 != 0:
            dlg.show_error("Sai kích thước", "Dung lượng (Size) phải lớn hơn 0 và là bội số của 4KB (0x1000).", self)
            return

        type_str = self.cb_type.currentText().lower()
        if type_str == "app":
            if offset_val < 0x10000 or offset_val % 0x10000 != 0:
                offset_val = max(0x10000, align_up(offset_val, 0x10000))
                self.entry_offset.setText(format_hex(offset_val))
        else:
            if offset_val % 0x1000 != 0:
                offset_val = align_up(offset_val, 0x1000)
                self.entry_offset.setText(format_hex(offset_val))

        flags_list = []
        if self.chk_enc.isChecked():
            flags_list.append("encrypted")
        if self.chk_ro.isChecked():
            flags_list.append("readonly")
        flags_str = ", ".join(flags_list)

        self.result = PartitionEntry(
            name=name,
            type_str=type_str,
            subtype_str=self.cb_subtype.currentText().strip(),
            offset=offset_val,
            size=size_val,
            flags_str=flags_str,
            used_size=self.entry.used_size
        )
        self.accept()
