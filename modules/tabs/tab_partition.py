# -*- coding: utf-8 -*-
"""
Esp32 tool v2.1 - Tab 4: Partition Wizard (Phân vùng Bộ nhớ ESP32)
Quản lý, phân tích, tối ưu bảng phân vùng ESP-IDF với sơ đồ trực quan phong cách MiniTool.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import threading
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout, QMenu
from PyQt6.QtCore import QPoint
from modules.ui.models import BooleanVar as _BooleanVar
from modules.ui import dialogs_service as messagebox
from modules.ui import dialogs_service as filedialog
from modules.ui import dialogs_service as simpledialog
from modules.ui.dialogs import PartitionEditDialog, PresetSelectorDialog, SizeInputDialog
from modules.config import DARK_PALETTE, LIGHT_PALETTE, FLASH_BAUDS, FLASH_CHIP_TARGETS
from modules.esptool_util import (
    run_esptool_command,
    esptool_command_succeeded,
    parse_esptool_progress_percent,
)
from modules.partition.unit_formatter import (
    DisplayMode, parse_size_or_offset, format_bytes_human, format_hex,
    format_value, align_up, sector_count
)
from modules.partition.chip_database import CHIP_FAMILY_DATABASE, get_chip_info
from modules.partition.partition_model import (
    PartitionTable, PartitionEntry, PARTITION_TABLE_SIZE_DEFAULT
)
from modules.partition.project_scanner import scan_esp_project


FLASH_SIZE_OPTIONS = [
    ("2 MB", 2 * 1024 * 1024),
    ("4 MB (Chuẩn)", 4 * 1024 * 1024),
    ("8 MB", 8 * 1024 * 1024),
    ("16 MB", 16 * 1024 * 1024),
    ("32 MB", 32 * 1024 * 1024),
]


from modules.ui.widgets.disk_map import DiskMapWidget as DiskMapCanvas


class _QMenuCompat(QMenu):
    """Lớp bọc QMenu hỗ trợ giao thức add_command / add_cascade / add_separator / tk_popup."""

    def add_command(self, label: str = "", command=None, state: str = "normal"):
        act = self.addAction(str(label))
        if state == "disabled":
            act.setEnabled(False)
        if command is not None:
            act.triggered.connect(lambda _=False, fn=command: fn())
        return act

    def add_separator(self):
        self.addSeparator()

    def add_cascade(self, label: str = "", menu: QMenu = None):
        if menu is not None:
            menu.setTitle(str(label))
            self.addMenu(menu)

    def configure(self, **kwargs):
        pass

    config = configure

    def tk_popup(self, x: int, y: int):
        self.exec(QPoint(int(x), int(y)))

    def index(self, which: str) -> int:
        acts = self.actions()
        return max(0, len(acts) - 1) if acts else 0

    def entrycget(self, idx: int, opt: str):
        acts = self.actions()
        if 0 <= idx < len(acts):
            act = acts[idx]
            if opt == "label":
                return act.text()
            if opt == "state":
                return "normal" if act.isEnabled() else "disabled"
        return ""

    def type(self, idx: int) -> str:
        acts = self.actions()
        if 0 <= idx < len(acts):
            act = acts[idx]
            if act.isSeparator():
                return "separator"
            if act.menu() is not None:
                return "cascade"
            return "command"
        return "command"


class PartitionHandbookDialog(QDialog):
    """Hộp thoại hướng dẫn và sổ tay tra cứu phân vùng ESP32 (PyQt6)"""
    def __init__(self, parent=None, is_dark_mode: bool = False):
        super().__init__(parent)
        self.setWindowTitle('Hướng Dẫn và Sổ Tay Tra Cứu Phân Vùng ESP32')
        self.resize(800, 580)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        txt = QTextEdit(self)
        txt.setReadOnly(True)
        doc_content = (
            "HƯỚNG DẪN SỬ DỤNG VÀ TRA CỨU PHÂN VÙNG BỘ NHỚ FLASH ESP32\n"
            "Áp dụng cho: ESP32, ESP32-S2, ESP32-S3, ESP32-C2, ESP32-C3, ESP32-C6, ESP32-H2, ESP32-P4\n"
            "================================================================================\n\n"
            "1. CÁC THAO TÁC CƠ BẢN TRÊN BẢNG PHÂN VÙNG:\n"
            "  - Thêm phân vùng: Bấm nút [+] ở dòng trống cuối bảng để chèn phân vùng mới.\n"
            "  - Xóa phân vùng: Bấm nút [-] ở cột đầu tiên của dòng phân vùng muốn xóa.\n"
            "  - Chỉnh sửa nhanh: Bấm chuột phải vào bất kỳ ô nào để chọn trực tiếp hoặc tự đặt tên/nhập tay.\n"
            "  - Mở hộp thoại chi tiết: Nhấp đúp chuột trái (Double-Click) vào dòng phân vùng.\n"
            "  - Tự động dồn căn biên: Bấm nút 'Dồn và Căn 4K/64K' trên thanh công cụ để tự động tính toán lại Offset không bị chồng lấn và đúng chuẩn căn lề.\n\n"
            "2. BẢN ĐỒ BỘ NHỚ FLASH ESP32 (MEMORY MAP):\n"
            "  - 0x00000 - 0x00FFF (4 KB): Vùng Header bảo lưu của ROM / Bootloader.\n"
            "  - 0x01000 - 0x07FFF (28 KB): Second-Stage Bootloader (0x0000 trên dòng C3/S3).\n"
            "  - 0x08000 - 0x08FFF (4 KB): BẢNG PHÂN VÙNG (Partition Table Sector cố định).\n"
            "  - 0x09000 - 0x0FFFF: Dữ liệu hệ thống NVS / PHY mặc định ban đầu.\n"
            "  - 0x10000 trở đi: VÙNG CHƯƠNG TRÌNH ỨNG DỤNG (APP) - Bắt buộc căn biên 64 KB (0x10000).\n"
            "  - Phía cuối Flash: Vùng hệ thống tệp lưu trữ (LittleFS, SPIFFS, FAT) và vùng trống (Unallocated).\n\n"
            "3. QUY TẮC CĂN CHỈNH BIÊN BẮT BUỘC (ALIGNMENT RULES):\n"
            "  - Phân vùng App (factory, ota_0, ota_1...): Offset BẮT BUỘC chia hết cho 64 KB (0x10000) và >= 0x10000 do cơ chế Flash MMU Cache của ESP32.\n"
            "  - Phân vùng Data (nvs, phy, spiffs, fat, littlefs...): Offset BẮT BUỘC chia hết cho 4 KB (0x1000) - kích thước sector SPI Flash.\n"
            "  - Dung lượng (Size): MỌI phân vùng đều phải có kích thước là bội số của sector 4 KB (0x1000).\n"
            "  - Phân vùng otadata: Bắt buộc đúng 8 KB (0x2000 = 2 sectors) để lưu trữ trạng thái boot OTA đối xứng.\n\n"
            "4. CÁC PHÂN VÙNG THÔNG DỤNG:\n"
            "  - nvs: Non-Volatile Storage (16KB - 24KB) lưu Wi-Fi, BLE và biến cấu hình.\n"
            "  - factory: Bản firmware ứng dụng chính xuất xưởng (thường từ 1.5MB - 2MB).\n"
            "  - ota_0 / ota_1: Hai khe nạp firmware từ xa xoay vòng Ping-Pong.\n"
            "  - littlefs / spiffs: Hệ thống file lưu trữ web assets, file cấu hình, log cảm biến.\n\n"
            "5. THAO TÁC PHẦN CỨNG:\n"
            "  - Đọc từ Chip: Đọc cấu trúc bảng phân vùng hiện có từ chip qua cổng COM.\n"
            "  - Nạp xuống Chip: Ghi bảng phân vùng hiện tại vào offset 0x8000 của chip.\n"
            "  - Sao Lưu: Dump nội dung nhị phân của phân vùng đang chọn ra file .bin.\n"
            "  - Xóa Trắng: Format trắng vùng nhớ của phân vùng đang chọn trên chip.\n"
        )
        txt.setPlainText(doc_content)
        layout.addWidget(txt, 1)

        btn_box = QHBoxLayout()
        btn_box.addStretch()
        btn_close = QPushButton('Đóng', self)
        btn_close.clicked.connect(self.accept)
        btn_box.addWidget(btn_close)
        layout.addLayout(btn_box)


class PartitionTabMixin:
    """
    Mixin quản lý toàn bộ giao diện và nghiệp vụ của Tab 4:
    ESP32 Partition Wizard (Phân vùng Bộ nhớ).
    """
    partition_hw_thread = None

    def create_partition_tab(self):
        """Khởi tạo toàn bộ giao diện Tab 4 bên trong self.partition_tab"""
        self.partition_hw_thread = None
        self.table = PartitionTable(flash_size=4 * 1024 * 1024, target_chip="esp32")
        self.display_mode = DisplayMode.DECIMAL
        self.current_partition_file_path: str | None = None
        self._syncing_chip_flash_combo = False
        self.partition_undo_stack: list[tuple[str, int, str, int]] = []
        self.partition_redo_stack: list[tuple[str, int, str, int]] = []
        self._is_populating_partition_table = False
        self._is_partition_hw_running = False
        self._tree_buttons: list = []
        if not hasattr(self, 'var_auto_align') or self.var_auto_align is None:
            self.var_auto_align = _BooleanVar(value=True)

        # Khởi tạo bảng phân vùng trống hoàn toàn cho tới khi đọc chip, nạp mẫu/CSV hoặc tự tạo
        self.refresh_partition_views()

        if hasattr(self, 'part_tree') and self.part_tree is not None:
            if hasattr(self, 'disk_map') and self.disk_map is not None:
                self.disk_map.on_select_entry = self._on_disk_map_select_entry
                self.disk_map.on_unallocated_click = self._on_disk_map_unallocated_click
                self.disk_map.on_context_action = self._on_disk_map_context_action
                self.disk_map.set_theme_mode(self.is_dark_mode)
            self.part_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
            self.part_tree.bind("<Button-1>", self._on_tree_click)
            self.part_tree.bind("<Double-1>", self._on_tree_double_click)
            self.part_tree.bind("<Button-3>", self._on_tree_right_click)
            self.refresh_partition_views()
            return

    def _set_partition_ui_state(self, state):
        """Bật/tắt các điều khiển của Tab Partition khi phần cứng đang bận."""
        if isinstance(state, bool):
            state = "normal" if state else "disabled"
        for attr in (
            'btn_part_scan', 'btn_part_read_hw', 'btn_part_flash_hw',
            'btn_part_dump_hw', 'btn_part_write_hw', 'btn_part_erase_hw',
            'btn_part_clear', 'btn_part_help',
            'cb_part_chip', 'cb_part_flash', 'cb_part_mode', 'chk_auto_align',
            'btn_add_part', 'btn_edit_part', 'btn_del_part', 'btn_autopack',
            'btn_presets', 'btn_open_csv', 'btn_save_csv'
        ):
            widget = getattr(self, attr, None)
            if widget and hasattr(widget, 'config'):
                try:
                    widget.config(state=state)
                except Exception:
                    pass
        if state == "disabled":
            for b in ('btn_part_undo', 'btn_part_redo'):
                widget = getattr(self, b, None)
                if widget and hasattr(widget, 'config'):
                    try:
                        widget.config(state="disabled")
                    except Exception:
                        pass
        else:
            if hasattr(self, '_update_partition_undo_redo_buttons'):
                self._update_partition_undo_redo_buttons()

    def _open_handbook_dialog(self):
        """Mở hộp thoại hướng dẫn & tra cứu phân vùng"""
        dlg = PartitionHandbookDialog(self.root, is_dark_mode=self.is_dark_mode)
        dlg.exec()

    def _on_toggle_auto_align(self):
        """Xử lý bật/tắt checkbox tự động căn chỉnh offset"""
        if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
            self._cascade_auto_pack(from_idx=0)
        if hasattr(self, 'part_tree') and self.part_tree is not None:
            self.refresh_partition_views()
            self.set_status("Đã cập nhật chế độ tự động căn chỉnh phân vùng.")

    def _push_partition_undo_state(self):
        state = (
            self.table.to_csv(),
            self.table.flash_size,
            self.table.target_chip,
            self.table.bootloader_offset
        )
        self.partition_undo_stack.append(state)
        if len(self.partition_undo_stack) > 50:
            self.partition_undo_stack.pop(0)
        self.partition_redo_stack.clear()
        self._update_partition_undo_redo_buttons()

    def _update_partition_undo_redo_buttons(self):
        self.btn_part_undo.configure(state="normal" if self.partition_undo_stack else "disabled")
        self.btn_part_redo.configure(state="normal" if self.partition_redo_stack else "disabled")

    def _action_undo(self):
        if self._is_partition_hw_running or (hasattr(self, 'is_device_busy') and self.is_device_busy()):
            return
        if not self.partition_undo_stack:
            return
        current = (
            self.table.to_csv(),
            self.table.flash_size,
            self.table.target_chip,
            self.table.bootloader_offset
        )
        self.partition_redo_stack.append(current)

        prev = self.partition_undo_stack.pop()
        csv_str, flash_sz, target_chip, bl_offset = prev
        self.table.flash_size = flash_sz
        self.table.target_chip = target_chip
        self.table.bootloader_offset = bl_offset
        self.table.from_csv(csv_str)

        self._update_partition_undo_redo_buttons()
        self.refresh_partition_views()
        self.set_status("Đã hoàn tác thao tác phân vùng trước (Undo).")

    def _action_redo(self):
        if self._is_partition_hw_running or (hasattr(self, 'is_device_busy') and self.is_device_busy()):
            return
        if not self.partition_redo_stack:
            return
        current = (
            self.table.to_csv(),
            self.table.flash_size,
            self.table.target_chip,
            self.table.bootloader_offset
        )
        self.partition_undo_stack.append(current)

        next_state = self.partition_redo_stack.pop()
        csv_str, flash_sz, target_chip, bl_offset = next_state
        self.table.flash_size = flash_sz
        self.table.target_chip = target_chip
        self.table.bootloader_offset = bl_offset
        self.table.from_csv(csv_str)

        self._update_partition_undo_redo_buttons()
        self.refresh_partition_views()
        self.set_status("Đã làm lại thao tác phân vùng (Redo).")

    def _get_entry_name_from_iid(self, iid: str) -> str | None:
        if not iid or iid == getattr(self, "_add_row_iid", "__add_row__"):
            return None
        vals = self.part_tree.item(iid, "values")
        if vals and len(vals) > 1:
            return str(vals[1])
        return None

    def _get_entry_from_iid(self, iid: str) -> PartitionEntry | None:
        name = self._get_entry_name_from_iid(iid)
        if not name:
            return None
        return next((e for e in self.table.entries if e.name == name), None)

    def _cascade_auto_pack(self, from_idx: int = 0):
        """Tự động căn chỉnh và dồn offset các phân vùng kế tiếp theo chuẩn ESP-IDF"""
        if not getattr(self, "var_auto_align", None) or not self.var_auto_align.get():
            return
        if not self.table.entries:
            return

        if from_idx <= 0:
            self.table.auto_pack_and_align()
        else:
            prev = self.table.entries[from_idx - 1]
            current_offset = prev.offset + prev.size
            for i in range(from_idx, len(self.table.entries)):
                e = self.table.entries[i]
                align_b = 0x10000 if e.type_str.lower() == "app" else 0x1000
                current_offset = align_up(current_offset, align_b)
                e.offset = current_offset
                current_offset += e.size

    def _set_entry_field(self, entry: PartitionEntry, field: str, value):
        self._push_partition_undo_state()
        if field == "size" and isinstance(value, int):
            if value % 0x1000 != 0:
                value = align_up(value, 0x1000)
        setattr(entry, field, value)
        idx = self.table.entries.index(entry) if entry in self.table.entries else 0
        if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
            if field == "offset":
                align_b = 0x10000 if entry.type_str.lower() == "app" else 0x1000
                entry.offset = align_up(entry.offset, align_b)
                if idx > 0:
                    prev = self.table.entries[idx - 1]
                    entry.offset = max(entry.offset, align_up(prev.end_offset, align_b))
                self._cascade_auto_pack(from_idx=idx + 1)
            elif field in ("size", "type_str", "subtype_str"):
                self._cascade_auto_pack(from_idx=idx)
        self.refresh_partition_views(selected_entry_name=entry.name)
        self.set_status(f"Đã cập nhật {field} của phân vùng '{entry.name}'.")

    def _prompt_custom_name(self, entry: PartitionEntry):
        val = simpledialog.askstring("Tự đặt tên", "Nhập tên phân vùng (tối đa 16 ký tự, không chứa dấu phẩy):", initialvalue=entry.name, parent=self.root)
        if val is not None:
            val = val.strip()
            if not val:
                messagebox.showerror("Lỗi", "Tên phân vùng không được để trống.", parent=self.root)
                return
            if "," in val:
                messagebox.showerror("Lỗi", "Tên phân vùng không được chứa dấu phẩy (,).", parent=self.root)
                return
            if len(val.encode("utf-8")) > 16:
                messagebox.showerror("Lỗi", "Tên phân vùng không được dài quá 16 bytes.", parent=self.root)
                return
            self._set_entry_field(entry, "name", val)

    def _prompt_custom_subtype(self, entry: PartitionEntry):
        val = simpledialog.askstring("Tự đặt SubType", "Nhập SubType (ví dụ: spiffs, nvs, 0x82):", initialvalue=entry.subtype_str, parent=self.root)
        if val is not None:
            self._set_entry_field(entry, "subtype_str", val.strip())

    def _prompt_custom_offset(self, entry: PartitionEntry):
        val = simpledialog.askstring("Tự nhập Offset", "Nhập địa chỉ Offset (ví dụ: 0x10000, 65536, 1M):", initialvalue=format_hex(entry.offset), parent=self.root)
        if val is not None:
            try:
                parsed = parse_size_or_offset(val.strip())
                self._set_entry_field(entry, "offset", parsed)
            except Exception as ex:
                messagebox.showerror("Lỗi", f"Địa chỉ Offset không hợp lệ: {ex}", parent=self.root)

    @staticmethod
    def _exec_dialog(dlg):
        """Hiển thị QDialog ở chế độ modal nếu result chưa được gán sẵn (hỗ trợ cả mock test)."""
        if getattr(dlg, "result", None) is None and getattr(dlg, "selected_preset", None) is None:
            import sys
            if "pytest" in sys.modules:
                return
            if hasattr(dlg, "exec") and callable(dlg.exec):
                dlg.exec()

    def _prompt_custom_size(self, entry: PartitionEntry):
        dlg = SizeInputDialog(self.root, entry.name, entry.size, is_dark_mode=self.is_dark_mode)
        self._exec_dialog(dlg)
        if dlg.result is not None:
            self._set_entry_field(entry, "size", dlg.result)

    def _auto_align_entry_offset(self, entry: PartitionEntry):
        idx = self.table.entries.index(entry) if entry in self.table.entries else -1
        if idx <= 0:
            suggested = 0x10000 if entry.type_str == "app" else 0x9000
        else:
            prev = self.table.entries[idx - 1]
            align_boundary = 0x10000 if entry.type_str == "app" else 0x1000
            suggested = align_up(prev.end_offset, align_boundary)
        self._set_entry_field(entry, "offset", suggested)

    def refresh_partition_views(self, selected_entry_name: str | None = None):
        """Làm mới toàn bộ giao diện: Disk Map, Bảng Treeview, Thống kê, và Kiểm tra lỗi"""
        # 1. Cập nhật Treeview (chặn signal để không tự động chọn dòng đầu khi bảng rỗng/làm mới)
        if selected_entry_name is None:
            selected_iid = self.part_tree.selection()
            if selected_iid:
                selected_entry_name = self._get_entry_name_from_iid(selected_iid[0])

        was_blocked = self.part_tree.blockSignals(True)
        try:
            for item in self.part_tree.get_children():
                self.part_tree.delete(item)

            current_selected_entry = None
            selected_iid_to_restore = None
            for idx, e in enumerate(self.table.entries):
                used_str = f"{format_bytes_human(e.used_size)} ({e.usage_percent:.1f}%)" if e.used_size > 0 else "--"
                free_str = format_value(e.free_size, self.display_mode, is_size=True) if e.used_size > 0 else "--"
                stt_str = f"#{idx + 1}"

                iid = self.part_tree.insert("", "end", values=(
                    stt_str,
                    e.name,
                    e.type_str,
                    e.subtype_str,
                    format_value(e.offset, self.display_mode, is_size=False),
                    format_value(e.size, self.display_mode, is_size=True),
                    e.flags_str if e.flags_str else "--",
                    used_str,
                    free_str
                ))
                if selected_entry_name and e.name == selected_entry_name:
                    selected_iid_to_restore = iid
                    current_selected_entry = e

            # Hàng trống ở cuối bảng để người dùng nhấp thêm phân vùng mới
            self._add_row_iid = "__add_row__"
            self.part_tree.insert("", "end", iid=self._add_row_iid, values=(
                "+",
                "(Nhấp vào dòng này để thêm phân vùng mới)",
                "",
                "",
                "",
                "",
                "",
                "",
                ""
            ))

            if selected_iid_to_restore:
                self.part_tree.selection_set(selected_iid_to_restore)
            else:
                self.part_tree.clearSelection()
                self.part_tree.setCurrentItem(None)
        finally:
            self.part_tree.blockSignals(was_blocked)

        # 2. Cập nhật Sơ đồ MiniTool Disk Map
        self._sync_flash_combo_to_table()
        flash_human = format_bytes_human(self.table.flash_size, compact=True)
        if not self.table.entries:
            self.disk_map.set_data([], self.table.flash_size, self.display_mode, None)
            self.lbl_flash_stats.configure(
                text=f"Dung lượng Flash: {flash_human} | Chưa có phân vùng (Chọn 'Mẫu Chuẩn...', 'Mở CSV/BIN', 'Đọc bảng từ Chip' hoặc '+ Thêm dòng')"
            )
            if hasattr(self, "txt_partition_val") and self.txt_partition_val.winfo_exists():
                self.txt_partition_val.configure(state="normal")
                self.txt_partition_val.delete("1.0", "end")
                self.txt_partition_val.insert(
                    "1.0",
                    "[TRỐNG] Chưa có phân vùng nào. Hãy nạp mẫu, mở file CSV/BIN, đọc từ chip hoặc tự thêm dòng mới.\n"
                )
                self.txt_partition_val.configure(state="disabled")
        else:
            layout = self.table.get_layout_with_unallocated()
            self.disk_map.set_data(layout, self.table.flash_size, self.display_mode, current_selected_entry)

            # 3. Cập nhật Thống kê Flash & Kiểm tra hợp lệ ESP-IDF
            total_allocated = sum(e.size for e in self.table.entries)
            unallocated_size = max(0, self.table.flash_size - (self.table.part_table_offset + PARTITION_TABLE_SIZE_DEFAULT) - total_allocated)
            alloc_human = format_bytes_human(total_allocated, compact=True)
            unalloc_human = format_bytes_human(unallocated_size, compact=True)

            errors = self.table.validate()
            err_msg = f" | [CẢNH BÁO] {len(errors)} lỗi ESP-IDF" if errors else " | [HỢP LỆ] Chuẩn ESP-IDF"
            self.lbl_flash_stats.configure(
                text=f"Dung lượng Flash: {flash_human} | Đã phân bổ: {alloc_human} ({len(self.table.entries)} phân vùng) | Chưa cấp phát: {unalloc_human}{err_msg}"
            )

            if hasattr(self, "txt_partition_val") and self.txt_partition_val.winfo_exists():
                self.txt_partition_val.configure(state="normal")
                self.txt_partition_val.delete("1.0", "end")
                if not errors:
                    self.txt_partition_val.insert("1.0", "[HỢP LỆ] BẢNG PHÂN VÙNG HOÀN TOÀN HỢP LỆ THEO CHUẨN ESP-IDF!\n\n")
                else:
                    self.txt_partition_val.insert("1.0", f"[CẢNH BÁO] PHÁT HIỆN {len(errors)} CẢNH BÁO / LỖI BẢNG PHÂN VÙNG:\n\n")
                    for err in errors:
                        self.txt_partition_val.insert("end", f"  [LỖI] {err}\n")
                self.txt_partition_val.configure(state="disabled")

        # Cập nhật vị trí các nút bấm [+] và [-] trên Treeview
        if hasattr(self, "root") and self.root.winfo_exists():
            self.root.after(10, self._reposition_tree_buttons)

    def _sync_flash_combo_to_table(self):
        """Bảo đảm combo Flash luôn hiển thị đúng dung lượng thực của bảng (tránh lệch 4 MB vs 16 MB).

        Chỉ cập nhật nhãn hiển thị (chặn signal) – không đẩy undo, không đổi dữ liệu bảng.
        """
        combo = getattr(self, "cb_part_flash", None)
        if combo is None or not hasattr(combo, "count"):
            return
        target_mb = int(self.table.flash_size // (1024 * 1024)) if self.table.flash_size else 0
        if target_mb <= 0:
            return

        def _mb_of(text: str) -> int:
            head = str(text).strip().split(" ")[0]
            return int(head) if head.isdigit() else -1

        if _mb_of(combo.currentText()) == target_mb:
            return
        was_blocked = combo.blockSignals(True)
        try:
            for i in range(combo.count()):
                if _mb_of(combo.itemText(i)) == target_mb:
                    combo.setCurrentIndex(i)
                    break
            if hasattr(combo, "_sync_fit_width"):
                combo._sync_fit_width()
        finally:
            combo.blockSignals(was_blocked)

    def _next_unique_partition_name(self, prefix: str = "part_") -> str:
        """Sinh tên phân vùng duy nhất không trùng lặp trong bảng hiện tại."""
        existing = {e.name for e in self.table.entries}
        idx = len(self.table.entries) + 1
        candidate = f"{prefix}{idx}"
        while candidate in existing:
            idx += 1
            candidate = f"{prefix}{idx}"
        return candidate

    def _sync_chip_and_flash_combos(self, chip_id: str, flash_size: int | None = None):
        """Đồng bộ combo Chip và Flash mà không kích hoạt nhân đôi undo hoặc item dư."""
        self._syncing_chip_flash_combo = True
        try:
            chip_info = None
            for cid, info in CHIP_FAMILY_DATABASE.items():
                if cid == chip_id:
                    chip_info = info
                    break
            if chip_info is not None:
                if hasattr(self, "cb_part_chip") and self.cb_part_chip is not None:
                    self.cb_part_chip.blockSignals(True)
                    self.part_chip_var.set(chip_info.name)
                    self.cb_part_chip.blockSignals(False)
                chip_sizes = sorted(chip_info.supported_flash_sizes)
                size_labels = [f"{sz // (1024 * 1024)} MB" for sz in chip_sizes]
                target_sz = flash_size if (flash_size in chip_sizes) else chip_sizes[-1]
                target_lbl = f"{target_sz // (1024 * 1024)} MB"
                if hasattr(self, "cb_part_flash") and self.cb_part_flash is not None:
                    self.cb_part_flash.blockSignals(True)
                    self.cb_part_flash["values"] = size_labels
                    self.part_flash_var.set(target_lbl)
                    self.cb_part_flash.blockSignals(False)
                self.table.flash_size = target_sz
            else:
                if hasattr(self, "cb_part_flash") and self.cb_part_flash is not None:
                    self.cb_part_flash.blockSignals(True)
                    self.cb_part_flash["values"] = [opt[0] for opt in FLASH_SIZE_OPTIONS]
                    chosen_lbl = FLASH_SIZE_OPTIONS[-1][0]
                    chosen_sz = FLASH_SIZE_OPTIONS[-1][1]
                    if flash_size is not None:
                        for lbl, sz in FLASH_SIZE_OPTIONS:
                            if sz == flash_size:
                                chosen_lbl, chosen_sz = lbl, sz
                                break
                    self.part_flash_var.set(chosen_lbl)
                    self.cb_part_flash.blockSignals(False)
                    self.table.flash_size = chosen_sz
        finally:
            self._syncing_chip_flash_combo = False

    def _on_chip_changed(self, event=None):
        if getattr(self, "_syncing_chip_flash_combo", False):
            return
        name = self.part_chip_var.get()
        if name == "(Chưa chọn)":
            self.table.target_chip = "auto"
            self.table.bootloader_offset = 0x1000
            self._sync_chip_and_flash_combos("auto", flash_size=FLASH_SIZE_OPTIONS[-1][1])
            self.refresh_partition_views()
            return

        for cid, info in CHIP_FAMILY_DATABASE.items():
            if info.name == name:
                self._push_partition_undo_state()
                self.table.target_chip = cid
                self.table.bootloader_offset = info.bootloader_offset

                # Luôn cập nhật danh sách dung lượng theo dòng chip & tự động chọn mức Flash cao nhất
                chip_sizes = sorted(info.supported_flash_sizes)
                highest_sz = chip_sizes[-1]
                self._sync_chip_and_flash_combos(cid, flash_size=highest_sz)

                self.refresh_partition_views()
                break

    def _on_flash_size_changed(self, event=None):
        name = self.part_flash_var.get().strip()
        sz_bytes = 0
        for opt_label, sz in FLASH_SIZE_OPTIONS:
            if opt_label.startswith(name) or name.startswith(opt_label):
                sz_bytes = sz
                break
        if not sz_bytes:
            parts = name.split()
            if parts and parts[0].isdigit():
                sz_bytes = int(parts[0]) * 1024 * 1024

        if sz_bytes > 0:
            self._push_partition_undo_state()
            self.table.flash_size = sz_bytes
            self.refresh_partition_views()

    def _on_display_mode_changed(self, event=None):
        mode_str = self.part_mode_var.get()
        if "HEX" in mode_str:
            self.display_mode = DisplayMode.HEX
        elif "Song song" in mode_str:
            self.display_mode = DisplayMode.DUAL
        else:
            self.display_mode = DisplayMode.DECIMAL
        self.refresh_partition_views()

    def _on_tree_select(self, event=None):
        selected_iid = self.part_tree.selection()
        if not selected_iid or selected_iid[0] == getattr(self, "_add_row_iid", "__add_row__"):
            self.disk_map.selected_entry = None
            self.disk_map.redraw()
            return
        entry = self._get_entry_from_iid(selected_iid[0])
        if entry:
            self.disk_map.selected_entry = entry
            self.disk_map.redraw()
        else:
            self.disk_map.selected_entry = None
            self.disk_map.redraw()

    def _on_tree_mousewheel(self, event):
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            self.part_tree.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
            self.part_tree.yview_scroll(1, "units")
        return "break"

    def _on_tree_click(self, event):
        row_id = self.part_tree.identify_row(event.y)
        if row_id and row_id == getattr(self, "_add_row_iid", "__add_row__"):
            self._action_add_partition()
            return "break"

    def _on_tree_double_click(self, event):
        row_id = self.part_tree.identify_row(event.y)
        if not row_id:
            return
        if row_id == getattr(self, "_add_row_iid", "__add_row__"):
            self._action_add_partition()
            return "break"
        self.part_tree.selection_set(row_id)
        self._action_edit_selected()

    def _reposition_tree_buttons(self):
        """Dọn dẹp các widget nút nổi cũ (nếu có); cột STT chỉ hiển thị số thứ tự thuần túy."""
        if getattr(self, "_repositioning_tree_buttons", False):
            return
        self._repositioning_tree_buttons = True
        try:
            for w in getattr(self, "_tree_buttons", []):
                try:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
                except Exception:
                    pass
            self._tree_buttons = []
        finally:
            self._repositioning_tree_buttons = False

    def _on_tree_motion(self, event):
        row_id = self.part_tree.identify_row(event.y)
        if row_id and row_id == getattr(self, "_add_row_iid", "__add_row__"):
            self.part_tree.configure(cursor="hand2")
            return
        self.part_tree.configure(cursor="")

    def _action_add_after_row(self, row_id: str):
        if self._is_partition_hw_running or (hasattr(self, 'is_device_busy') and self.is_device_busy()):
            return
        entry_name = self._get_entry_name_from_iid(row_id)
        idx = next((i for i, e in enumerate(self.table.entries) if e.name == entry_name), -1)
        if idx == -1:
            idx = len(self.table.entries) - 1

        current_entry = self.table.entries[idx] if 0 <= idx < len(self.table.entries) else None

        existing_names = {e.name for e in self.table.entries}
        new_name_idx = len(self.table.entries) + 1
        new_name = f"part_{new_name_idx}"
        while new_name in existing_names:
            new_name_idx += 1
            new_name = f"part_{new_name_idx}"

        if current_entry:
            suggested_offset = align_up(current_entry.end_offset, 0x1000)
        else:
            suggested_offset = 0x10000

        new_size = 0x10000  # 64 KB

        new_entry = PartitionEntry(
            name=new_name,
            type_str="data",
            subtype_str="spiffs",
            offset=suggested_offset,
            size=new_size,
            flags_str=""
        )

        self._push_partition_undo_state()
        self.table.entries.insert(idx + 1, new_entry)
        if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
            self._cascade_auto_pack(from_idx=idx + 1)
        self.refresh_partition_views(selected_entry_name=new_name)
        self.set_status(f"Đã chèn phân vùng mới '{new_name}'. Nhấp chuột phải vào từng cột để đổi giá trị.")

    def _action_delete_by_row(self, row_id: str):
        entry_name = self._get_entry_name_from_iid(row_id)
        if not entry_name:
            return
        entry = next((e for e in self.table.entries if e.name == entry_name), None)
        if entry:
            self._action_delete_by_entry(entry)

    def _action_delete_by_entry(self, entry: PartitionEntry):
        if self._is_partition_hw_running or (hasattr(self, 'is_device_busy') and self.is_device_busy()):
            return
        if messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc chắn muốn xóa phân vùng '{entry.name}' không?", parent=self.root):
            self._push_partition_undo_state()
            self.table.entries = [e for e in self.table.entries if e.name != entry.name]
            if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                self._cascade_auto_pack(from_idx=0)
            self.refresh_partition_views()
            self.set_status(f"Đã xóa phân vùng '{entry.name}'.")

    def _on_disk_map_select_entry(self, entry: PartitionEntry):
        if entry.is_system or entry.is_unallocated or self.disk_map.selected_entry is None:
            self.part_tree.clearSelection()
            self.part_tree.setCurrentItem(None)
            self.disk_map.selected_entry = None
            self.disk_map.redraw()
            return
        for item in self.part_tree.get_children():
            name = self._get_entry_name_from_iid(item)
            if name == entry.name:
                self.part_tree.selection_set(item)
                self.part_tree.see(item)
                break

    def _on_disk_map_unallocated_click(self, offset: int, size: int):
        ans = messagebox.askyesno(
            "Tạo phân vùng mới",
            f"Bạn có muốn tạo phân vùng mới trong khoảng trống tại {format_hex(offset)} (Dung lượng: {format_bytes_human(size)})?",
            parent=self.root
        )
        if ans:
            self._action_add_partition(suggested_offset=offset)

    def _on_disk_map_context_action(self, action: str, entry: PartitionEntry, event=None):
        self._on_disk_map_select_entry(entry)
        if action == "edit":
            self._action_edit_selected()
        elif action == "delete":
            self._action_delete_by_entry(entry)
        elif action == "full_context_menu" and event:
            self._show_disk_map_context_menu(event, entry)

    def _on_tree_right_click(self, event):
        row_id = self.part_tree.identify_row(event.y)
        if not row_id:
            return

        if row_id == getattr(self, "_add_row_iid", "__add_row__"):
            menu = _QMenuCompat(self.root)
            menu.add_command(label="Thêm phân vùng mới", command=self._action_add_partition)
            menu.tk_popup(event.x_root, event.y_root)
            return

        self.part_tree.selection_set(row_id)
        col_id = self.part_tree.identify_column(event.x)
        entry = self._get_entry_from_iid(row_id)
        if not entry:
            return

        self._show_column_context_menu(event, entry, col_id, row_id)

    def _show_column_context_menu(self, event, entry: PartitionEntry, col_id: str, row_id: str):
        menu = _QMenuCompat(self.root)

        row_idx = self.table.entries.index(entry) if entry in self.table.entries else 0

        # Cột #1: STT
        if col_id == "#1":
            menu.add_command(label=f"HÀNG #{row_idx + 1}: {entry.name}", state="disabled")
            menu.add_separator()
            menu.add_command(label="Chèn phân vùng mới sau dòng này", command=lambda: self._action_add_after_row(row_id))
            menu.add_command(label=f"Xóa phân vùng '{entry.name}'", command=lambda: self._action_delete_by_row(row_id))
            menu.add_separator()
            menu.add_command(label="Dồn & Căn lề toàn bộ 4K/64K", command=self._action_auto_pack)

        # Cột #2: Tên (Name)
        elif col_id == "#2":
            menu.add_command(label=f"ĐỔI TÊN PHÂN VÙNG (Hiện tại: {entry.name})", state="disabled")
            menu.add_separator()
            preset_names = (
                ["factory", "ota_0", "ota_1", "test"] if entry.type_str == "app"
                else ["nvs", "otadata", "storage", "spiffs", "littlefs", "phy_init", "coredump", "nvs_keys"]
            )
            for pname in preset_names:
                menu.add_command(label=f"Đặt tên: {pname}", command=lambda n=pname: self._set_entry_field(entry, "name", n))
            menu.add_separator()
            menu.add_command(label="Tự đặt tên...", command=lambda: self._prompt_custom_name(entry))
            menu.add_command(label="(Chưa đặt tên / Trống)", command=lambda: self._set_entry_field(entry, "name", ""))

        # Cột #3: Kiểu (Type)
        elif col_id == "#3":
            menu.add_command(label=f"ĐỔI KIỂU TYPE (Hiện tại: {entry.type_str})", state="disabled")
            menu.add_separator()

            def set_type(new_t: str):
                self._push_partition_undo_state()
                entry.type_str = new_t
                if new_t == "app":
                    if entry.subtype_str not in ("factory", "test") and not entry.subtype_str.startswith("ota_"):
                        entry.subtype_str = "factory"
                else:
                    if entry.subtype_str in ("factory", "test") or entry.subtype_str.startswith("ota_"):
                        entry.subtype_str = "spiffs"
                idx = self.table.entries.index(entry) if entry in self.table.entries else 0
                if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                    self._cascade_auto_pack(from_idx=idx)
                self.refresh_partition_views(selected_entry_name=entry.name)
                self.set_status(f"Đã đổi kiểu phân vùng '{entry.name}' sang '{new_t}'.")

            menu.add_command(label="app (0x00 - Ứng dụng thực thi)", command=lambda: set_type("app"))
            menu.add_command(label="data (0x01 - Dữ liệu hệ thống / Tệp)", command=lambda: set_type("data"))
            menu.add_separator()
            menu.add_command(label="(Chưa chọn / Trống)", command=lambda: self._set_entry_field(entry, "type_str", ""))

        # Cột #4: Phân loại (SubType)
        elif col_id == "#4":
            menu.add_command(label=f"ĐỔI PHÂN LOẠI SUBTYPE (Hiện tại: {entry.subtype_str})", state="disabled")
            menu.add_separator()
            if entry.type_str == "app":
                app_subtypes = [
                    ("factory", "factory (Firmware gốc xuất xưởng)"),
                    ("ota_0", "ota_0 (Khe firmware OTA 0)"),
                    ("ota_1", "ota_1 (Khe firmware OTA 1)"),
                    ("ota_2", "ota_2 (Khe firmware OTA 2)"),
                    ("test", "test (Bản thử nghiệm chức năng)"),
                ]
                for st_code, st_lbl in app_subtypes:
                    menu.add_command(label=st_lbl, command=lambda s=st_code: self._set_entry_field(entry, "subtype_str", s))
            else:
                data_subtypes = [
                    ("nvs", "nvs (Lưu Wi-Fi / biến Key-Value)"),
                    ("ota", "ota (otadata - Kiểm soát trạng thái OTA)"),
                    ("spiffs", "spiffs (Hệ thống tập tin SPIFFS)"),
                    ("littlefs", "littlefs (Hệ thống tập tin LittleFS khuyên dùng)"),
                    ("fat", "fat (Hệ thống tập tin FAT tương thích cao)"),
                    ("phy", "phy (Dữ liệu hiệu chuẩn vô tuyến RF)"),
                    ("coredump", "coredump (Nhật ký lỗi sập CPU crash)"),
                    ("nvs_keys", "nvs_keys (Khóa mã hóa bảo mật NVS)"),
                ]
                for st_code, st_lbl in data_subtypes:
                    menu.add_command(label=st_lbl, command=lambda s=st_code: self._set_entry_field(entry, "subtype_str", s))
            menu.add_separator()
            menu.add_command(label="Tự đặt SubType...", command=lambda: self._prompt_custom_subtype(entry))
            menu.add_command(label="(Chưa chọn / Trống)", command=lambda: self._set_entry_field(entry, "subtype_str", ""))

        # Cột #5: Offset
        elif col_id == "#5":
            menu.add_command(label=f"ĐỔI ĐỊA CHỈ OFFSET (Hiện tại: {format_hex(entry.offset)})", state="disabled")
            menu.add_separator()
            menu.add_command(label="Tự động tính toán (Dồn nối tiếp dòng trước)", command=lambda: self._auto_align_entry_offset(entry))
            menu.add_separator()
            offsets = [0x9000, 0x10000, 0x20000, 0x100000, 0x200000, 0x300000]
            for off in offsets:
                menu.add_command(label=f"Đặt Offset: {format_hex(off)} ({format_bytes_human(off)})", command=lambda o=off: self._set_entry_field(entry, "offset", o))
            menu.add_separator()
            menu.add_command(label="Tự nhập Offset...", command=lambda: self._prompt_custom_offset(entry))

        # Cột #6: Dung lượng (Size)
        elif col_id == "#6":
            menu.add_command(label=f"ĐỔI DUNG LƯỢNG SIZE (Hiện tại: {format_bytes_human(entry.size)})", state="disabled")
            menu.add_separator()
            size_presets = [
                (4 * 1024, "4 KB (1 sector)"),
                (16 * 1024, "16 KB (Chuẩn NVS)"),
                (32 * 1024, "32 KB"),
                (64 * 1024, "64 KB"),
                (128 * 1024, "128 KB"),
                (256 * 1024, "256 KB"),
                (512 * 1024, "512 KB"),
                (1024 * 1024, "1 MB"),
                (int(1.5 * 1024 * 1024), "1.5 MB"),
                (2 * 1024 * 1024, "2 MB"),
                (3 * 1024 * 1024, "3 MB"),
            ]
            for sz_val, sz_lbl in size_presets:
                menu.add_command(label=f"Đặt dung lượng: {sz_lbl}", command=lambda s=sz_val: self._set_entry_field(entry, "size", s))
            menu.add_separator()
            menu.add_command(label="Tự nhập dung lượng (chọn đơn vị)...", command=lambda: self._prompt_custom_size(entry))

        # Cột #7: Cờ (Flags)
        elif col_id == "#7":
            menu.add_command(label=f"ĐỔI CỜ BẢO MẬT (Hiện tại: {entry.flags_str or 'Trống'})", state="disabled")
            menu.add_separator()
            menu.add_command(label="(Không có / Trống)", command=lambda: self._set_entry_field(entry, "flags_str", ""))
            menu.add_command(label="encrypted (Mã hóa phần cứng)", command=lambda: self._set_entry_field(entry, "flags_str", "encrypted"))
            menu.add_command(label="readonly (Chỉ đọc)", command=lambda: self._set_entry_field(entry, "flags_str", "readonly"))
            menu.add_command(label="encrypted, readonly (Cả hai cờ: Mã hóa & Chỉ đọc)", command=lambda: self._set_entry_field(entry, "flags_str", "encrypted, readonly"))

        # Các cột #8 (used), #9 (free)
        elif col_id in ("#8", "#9"):
            menu.add_command(label=f"HÀNG #{row_idx + 1}: {entry.name}", state="disabled")

        else:
            return

        if col_id != "#1":
            menu.add_separator()
            menu.add_command(label="Chèn phân vùng mới sau dòng này", command=lambda: self._action_add_after_row(row_id))
            menu.add_command(label=f"Xóa phân vùng '{entry.name}'", command=lambda: self._action_delete_by_row(row_id))

        menu.tk_popup(event.x_root, event.y_root)

    def _show_disk_map_context_menu(self, event, entry: PartitionEntry):
        """Menu ngữ cảnh chuột phải trên Sơ đồ Flash đồng bộ đầy đủ các lựa chọn như bảng bên dưới"""
        menu = _QMenuCompat(self.root)

        row_idx = self.table.entries.index(entry) if entry in self.table.entries else 0
        menu.add_command(label=f"PHÂN VÙNG #{row_idx + 1}: {entry.name.upper()}", state="disabled")
        menu.add_separator()

        # 1. Đổi Tên (Name)
        name_sub = _QMenuCompat(menu)
        preset_names = (
            ["factory", "ota_0", "ota_1", "test"] if entry.type_str == "app"
            else ["nvs", "otadata", "storage", "spiffs", "littlefs", "phy_init", "coredump", "nvs_keys"]
        )
        for pname in preset_names:
            name_sub.add_command(label=f"Đặt tên: {pname}", command=lambda n=pname: self._set_entry_field(entry, "name", n))
        name_sub.add_separator()
        name_sub.add_command(label="Tự đặt tên...", command=lambda: self._prompt_custom_name(entry))
        name_sub.add_command(label="(Chưa đặt tên / Trống)", command=lambda: self._set_entry_field(entry, "name", ""))
        menu.add_cascade(label=f"Đổi Tên ({entry.name})", menu=name_sub)

        # 2. Đổi Kiểu (Type)
        type_sub = _QMenuCompat(menu)
        def set_type(new_t: str):
            self._push_partition_undo_state()
            entry.type_str = new_t
            if new_t == "app":
                if entry.subtype_str not in ("factory", "test") and not entry.subtype_str.startswith("ota_"):
                    entry.subtype_str = "factory"
            else:
                if entry.subtype_str in ("factory", "test") or entry.subtype_str.startswith("ota_"):
                    entry.subtype_str = "spiffs"
            if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                idx = self.table.entries.index(entry) if entry in self.table.entries else 0
                self._cascade_auto_pack(from_idx=idx)
            self.refresh_partition_views(selected_entry_name=entry.name)
            self.set_status(f"Đã đổi kiểu phân vùng '{entry.name}' sang '{new_t}'.")

        type_sub.add_command(label="app (0x00 - Ứng dụng thực thi)", command=lambda: set_type("app"))
        type_sub.add_command(label="data (0x01 - Dữ liệu hệ thống / Tệp)", command=lambda: set_type("data"))
        type_sub.add_separator()
        type_sub.add_command(label="(Chưa chọn / Trống)", command=lambda: self._set_entry_field(entry, "type_str", ""))
        menu.add_cascade(label=f"Đổi Kiểu ({entry.type_str})", menu=type_sub)

        # 3. Đổi Phân loại (SubType)
        sub_menu = _QMenuCompat(menu)
        if entry.type_str == "app":
            for st_code, st_lbl in [
                ("factory", "factory (Firmware gốc xuất xưởng)"),
                ("ota_0", "ota_0 (Khe firmware OTA 0)"),
                ("ota_1", "ota_1 (Khe firmware OTA 1)"),
                ("ota_2", "ota_2 (Khe firmware OTA 2)"),
                ("test", "test (Bản thử nghiệm chức năng)"),
            ]:
                sub_menu.add_command(label=st_lbl, command=lambda s=st_code: self._set_entry_field(entry, "subtype_str", s))
        else:
            for st_code, st_lbl in [
                ("nvs", "nvs (Lưu Wi-Fi / biến Key-Value)"),
                ("ota", "ota (otadata - Kiểm soát trạng thái OTA)"),
                ("spiffs", "spiffs (Hệ thống tập tin SPIFFS)"),
                ("littlefs", "littlefs (Hệ thống tập tin LittleFS)"),
                ("fat", "fat (Hệ thống tập tin FAT)"),
                ("phy", "phy (Dữ liệu vô tuyến RF)"),
                ("coredump", "coredump (Nhật ký sập CPU)"),
                ("nvs_keys", "nvs_keys (Khóa mã hóa NVS)"),
            ]:
                sub_menu.add_command(label=st_lbl, command=lambda s=st_code: self._set_entry_field(entry, "subtype_str", s))
        sub_menu.add_separator()
        sub_menu.add_command(label="Tự đặt SubType...", command=lambda: self._prompt_custom_subtype(entry))
        sub_menu.add_command(label="(Chưa chọn / Trống)", command=lambda: self._set_entry_field(entry, "subtype_str", ""))
        menu.add_cascade(label=f"Đổi Phân loại ({entry.subtype_str})", menu=sub_menu)

        # 4. Đổi Offset
        off_sub = _QMenuCompat(menu)
        off_sub.add_command(label="Tự động tính toán (Dồn nối tiếp)", command=lambda: self._auto_align_entry_offset(entry))
        off_sub.add_separator()
        for off in [0x9000, 0x10000, 0x20000, 0x100000, 0x200000, 0x300000]:
            off_sub.add_command(label=f"Đặt Offset: {format_hex(off)} ({format_bytes_human(off)})", command=lambda o=off: self._set_entry_field(entry, "offset", o))
        off_sub.add_separator()
        off_sub.add_command(label="Tự nhập Offset...", command=lambda: self._prompt_custom_offset(entry))
        menu.add_cascade(label=f"Đổi Offset ({format_hex(entry.offset)})", menu=off_sub)

        # 5. Đổi Dung lượng (Size)
        sz_sub = _QMenuCompat(menu)
        size_presets = [
            (4 * 1024, "4 KB (1 sector)"),
            (16 * 1024, "16 KB (Chuẩn NVS)"),
            (32 * 1024, "32 KB"),
            (64 * 1024, "64 KB"),
            (128 * 1024, "128 KB"),
            (256 * 1024, "256 KB"),
            (512 * 1024, "512 KB"),
            (1024 * 1024, "1 MB"),
            (int(1.5 * 1024 * 1024), "1.5 MB"),
            (2 * 1024 * 1024, "2 MB"),
            (3 * 1024 * 1024, "3 MB"),
        ]
        for sz_val, sz_lbl in size_presets:
            sz_sub.add_command(label=f"Đặt dung lượng: {sz_lbl}", command=lambda s=sz_val: self._set_entry_field(entry, "size", s))
        sz_sub.add_separator()
        sz_sub.add_command(label="Tự nhập dung lượng (chọn đơn vị)...", command=lambda: self._prompt_custom_size(entry))
        menu.add_cascade(label=f"Đổi Dung lượng ({format_bytes_human(entry.size)})", menu=sz_sub)

        # 6. Đổi Cờ (Flags)
        flg_sub = _QMenuCompat(menu)
        flg_sub.add_command(label="(Không có / Trống)", command=lambda: self._set_entry_field(entry, "flags_str", ""))
        flg_sub.add_command(label="encrypted (Mã hóa phần cứng)", command=lambda: self._set_entry_field(entry, "flags_str", "encrypted"))
        flg_sub.add_command(label="readonly (Chỉ đọc)", command=lambda: self._set_entry_field(entry, "flags_str", "readonly"))
        flg_sub.add_command(label="encrypted, readonly (Cả hai cờ: Mã hóa & Chỉ đọc)", command=lambda: self._set_entry_field(entry, "flags_str", "encrypted, readonly"))
        menu.add_cascade(label=f"Đổi Cờ ({entry.flags_str or 'Trống'})", menu=flg_sub)

        menu.add_separator()
        menu.add_command(label=f"Xóa phân vùng '{entry.name}'", command=lambda: self._action_delete_by_entry(entry))

        menu.tk_popup(event.x_root, event.y_root)

    def _action_add_partition(self, suggested_offset: int | None = None):
        if isinstance(suggested_offset, bool):
            suggested_offset = None

        insert_idx = len(self.table.entries)
        if suggested_offset is None:
            selected_entry = None
            selected_iid = self.part_tree.selection() if hasattr(self, "part_tree") else ()
            if selected_iid and selected_iid[0] != getattr(self, "_add_row_iid", "__add_row__"):
                selected_entry = self._get_entry_from_iid(selected_iid[0])

            if selected_entry is not None and selected_entry in self.table.entries:
                sel_idx = self.table.entries.index(selected_entry)
                insert_idx = sel_idx + 1
                suggested_offset = align_up(selected_entry.end_offset, 0x1000)
            elif self.table.entries:
                last = max(e.end_offset for e in self.table.entries)
                suggested_offset = align_up(last, 0x1000)
            else:
                suggested_offset = 0x10000

        default_name = self._next_unique_partition_name("part_")
        dlg = PartitionEditDialog(
            self.root,
            entry=None,
            suggested_offset=suggested_offset,
            is_dark_mode=self.is_dark_mode,
            default_name=default_name,
        )
        self._exec_dialog(dlg)
        if dlg.result:
            # Tránh trùng tên nếu người dùng hoặc dialog trả về tên đã tồn tại
            existing_names = {e.name for e in self.table.entries}
            if dlg.result.name in existing_names:
                dlg.result.name = self._next_unique_partition_name(f"{dlg.result.name}_")

            self._push_partition_undo_state()
            insert_idx = max(0, min(insert_idx, len(self.table.entries)))
            self.table.entries.insert(insert_idx, dlg.result)

            auto_align = bool(getattr(self, "var_auto_align", None) and self.var_auto_align.get())
            if auto_align:
                if insert_idx == 0:
                    self._cascade_auto_pack(from_idx=0)
                else:
                    prev_entry = self.table.entries[insert_idx - 1]
                    start_pack = insert_idx if dlg.result.offset < prev_entry.end_offset else insert_idx + 1
                    if start_pack < len(self.table.entries):
                        self._cascade_auto_pack(from_idx=start_pack)
            elif insert_idx + 1 < len(self.table.entries):
                # Ngay cả khi tắt auto-align, nếu chèn xen giữa làm đè lên vùng sau thì dịch vùng sau hợp lệ
                next_entry = self.table.entries[insert_idx + 1]
                if dlg.result.end_offset > next_entry.offset:
                    self._cascade_auto_pack(from_idx=insert_idx + 1)

            self.refresh_partition_views(selected_entry_name=dlg.result.name)
            self.set_status(f"Đã thêm phân vùng '{dlg.result.name}'.")

    def _action_edit_selected(self):
        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần chỉnh sửa.", parent=self.root)
            return

        name = self._get_entry_name_from_iid(selected_iid[0])
        if not name:
            return
        idx = next((i for i, e in enumerate(self.table.entries) if e.name == name), None)
        if idx is None:
            return

        entry = self.table.entries[idx]
        dlg = PartitionEditDialog(self.root, entry=entry, is_dark_mode=self.is_dark_mode)
        self._exec_dialog(dlg)
        if dlg.result:
            self._push_partition_undo_state()
            self.table.entries[idx] = dlg.result
            if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                self._cascade_auto_pack(from_idx=idx)
            self.refresh_partition_views(selected_entry_name=dlg.result.name)
            self.set_status(f"Đã cập nhật phân vùng '{dlg.result.name}'.")

    def _action_delete_selected(self):
        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần xóa.", parent=self.root)
            return

        name = self._get_entry_name_from_iid(selected_iid[0])
        if not name:
            return
        entry = next((e for e in self.table.entries if e.name == name), None)
        if entry:
            self._action_delete_by_entry(entry)

    def _action_auto_pack(self):
        """Tự động dồn toàn bộ phân vùng liên tiếp và căn lề chuẩn 4K/64K"""
        if self._is_partition_hw_running or (hasattr(self, 'is_device_busy') and self.is_device_busy()):
            return
        if not self.table.entries:
            return
        self._push_partition_undo_state()
        self.table.auto_pack_and_align()
        self.refresh_partition_views()
        self.set_status("Đã dồn biên và căn chỉnh toàn bộ phân vùng theo chuẩn 4KB / 64KB.")
        messagebox.showinfo("Thành công", "Đã tự động tính toán lại Offset nối tiếp nhau không bị chồng lấn và căn biên chuẩn 4KB (cho Data) và 64KB (cho App)!", parent=self.root)

    def _action_new_table(self):
        """Khởi tạo bảng phân vùng mới"""
        if self.table.entries:
            if not messagebox.askyesno(
                "Tạo bảng mới",
                "Bạn có muốn tạo bảng phân vùng mới không?\nCác phân vùng hiện tại sẽ được làm mới về mặc định.",
                parent=self.root
            ):
                return
        self._push_partition_undo_state()
        self.table.entries.clear()
        default_csv = (
            "# ESP-IDF Partition Table\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1M,\n"
            "storage,  data, spiffs,  ,        2800K,\n"
        )
        self.table.from_csv(default_csv)
        if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
            self._cascade_auto_pack(from_idx=0)

        if hasattr(self, 'part_tree') and self.part_tree is not None:
            if hasattr(self, 'disk_map') and self.disk_map is not None:
                self.disk_map.on_select_entry = self._on_disk_map_select_entry
                self.disk_map.on_unallocated_click = self._on_disk_map_unallocated_click
                self.disk_map.on_context_action = self._on_disk_map_context_action
            self.refresh_partition_views()
            return
        self.current_partition_file_path = None
        self.refresh_partition_views()
        self.set_status("Đã tạo bảng phân vùng mới.")

    def _action_save(self):
        """Lưu bảng phân vùng vào file hiện tại (nếu có), hoặc Lưu như nếu chưa có đường dẫn"""
        current_path = getattr(self, "current_partition_file_path", None)
        if not current_path:
            self._action_save_as()
            return

        try:
            if current_path.lower().endswith(".bin"):
                data = self.table.to_binary()
                with open(current_path, "wb") as f:
                    f.write(data)
            else:
                csv_content = self.table.to_csv()
                with open(current_path, "w", encoding="utf-8") as f:
                    f.write(csv_content)
            self.set_status(f"Đã lưu bảng phân vùng vào: {os.path.basename(current_path)}", "success")
            messagebox.showinfo("Đã lưu", f"Đã lưu bảng phân vùng thành công:\n{current_path}", parent=self.root)
        except Exception as ex:
            self.set_status("Lỗi khi lưu file!", "error")
            messagebox.showerror("Lỗi lưu file", f"Không thể lưu file:\n{ex}", parent=self.root)

    def _action_save_as(self):
        """Lưu bảng phân vùng ra file CSV hoặc BIN với tên mới"""
        filepath = filedialog.asksaveasfilename(
            title="Lưu như bảng phân vùng",
            defaultextension=".csv",
            filetypes=[
                ("ESP-IDF Partition CSV (*.csv)", "*.csv"),
                ("Binary Partition Table (*.bin)", "*.bin"),
                ("All Files (*.*)", "*.*")
            ],
            parent=self.root
        )
        if not filepath:
            return

        try:
            if filepath.lower().endswith(".bin"):
                data = self.table.to_binary()
                with open(filepath, "wb") as f:
                    f.write(data)
            else:
                csv_content = self.table.to_csv()
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(csv_content)
            self.current_partition_file_path = filepath
            self.set_status(f"Đã lưu thành công vào: {os.path.basename(filepath)}", "success")
            messagebox.showinfo("Đã lưu", f"Đã lưu bảng phân vùng thành công:\n{filepath}", parent=self.root)
        except Exception as ex:
            self.set_status("Lỗi khi lưu file!", "error")
            messagebox.showerror("Lỗi lưu file", f"Không thể lưu file:\n{ex}", parent=self.root)

    def _action_copy_partition_config(self):
        """Sao chép cấu hình phân vùng (dưới dạng CSV) vào Clipboard"""
        csv_content = self.table.to_csv()
        self.root.clipboard_clear()
        self.root.clipboard_append(csv_content)
        self.set_status("Đã sao chép cấu hình phân vùng vào Clipboard!", "success")
        messagebox.showinfo(
            "Đã sao chép",
            "Đã sao chép toàn bộ bảng phân vùng (định dạng CSV ESP-IDF) vào Clipboard!\nBạn có thể dán (Ctrl+V) vào partitions.csv hoặc tài liệu.",
            parent=self.root
        )

    def _action_clear_all_partitions(self):
        """Xóa toàn bộ các phân vùng trong bảng"""
        if not self.table.entries:
            messagebox.showinfo("Thông báo", "Bảng phân vùng hiện đang trống.", parent=self.root)
            return
        if messagebox.askyesno(
            "Xác nhận xóa tất cả",
            "Bạn có chắc chắn muốn xóa TOÀN BỘ các phân vùng trong bảng không?\n(Bạn có thể nhấn Hoàn tác để khôi phục lại)",
            parent=self.root
        ):
            self._push_partition_undo_state()
            self.table.entries.clear()
            self.refresh_partition_views()
            self.set_status("Đã xóa toàn bộ phân vùng trong bảng.")

    def _action_presets(self):
        dlg = PresetSelectorDialog(self.root, is_dark_mode=self.is_dark_mode)
        self._exec_dialog(dlg)
        preset = getattr(dlg, "result", None) or getattr(dlg, "selected_preset", None)
        if preset:
            self._push_partition_undo_state()
            self.table.flash_size = preset["flash_size"]
            self.table.target_chip = preset["chip"]
            self.table.from_csv(preset["csv"])
            if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                self._cascade_auto_pack(from_idx=0)

            # Cập nhật combo chip & flash đồng bộ
            self._sync_chip_and_flash_combos(preset["chip"], flash_size=preset["flash_size"])

            self.refresh_partition_views()
            self.set_status(f"Đã nạp mẫu: {preset['name']}")

    def _action_open_file(self):
        path = filedialog.askopenfilename(
            title="Mở file bảng phân vùng",
            filetypes=[
                ("ESP32 Partition Files (*.csv;*.bin)", "*.csv;*.bin"),
                ("CSV Files (*.csv)", "*.csv"),
                ("Binary Files (*.bin)", "*.bin"),
                ("All Files (*.*)", "*.*")
            ],
            parent=self.root
        )
        if not path:
            return

        try:
            self._push_partition_undo_state()
            if path.lower().endswith(".bin"):
                with open(path, "rb") as f:
                    data = f.read()
                self.table.from_binary(data)
                self.set_status(f"Đã nạp bảng phân vùng từ file BIN: {os.path.basename(path)}")
            else:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    csv_text = f.read()
                self.table.from_csv(csv_text)
                self.set_status(f"Đã nạp bảng phân vùng từ file CSV: {os.path.basename(path)}")
            if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                self._cascade_auto_pack(from_idx=0)

            self.current_partition_file_path = path
            self.refresh_partition_views()
        except Exception as e:
            messagebox.showerror("Lỗi mở file", f"Không thể đọc file phân vùng:\n{e}", parent=self.root)

    def _action_save_csv(self):
        """Lưu toàn bộ bảng phân vùng hiện tại ra tệp .csv (lưu đè nếu đã gắn tệp CSV, hoặc mở hộp thoại chọn nơi lưu)."""
        target_path = getattr(self, "current_partition_file_path", None)
        if not target_path or not str(target_path).lower().endswith(".csv"):
            target_path = filedialog.asksaveasfilename(
                title="Lưu file CSV bảng phân vùng",
                defaultextension=".csv",
                initialfile="partitions.csv",
                filetypes=[("CSV Files (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")],
                parent=self.root
            )
        if not target_path:
            return

        try:
            csv_content = self.table.to_csv()
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(csv_content)
            self.current_partition_file_path = target_path
            self.set_status(f"Đã lưu toàn bộ bảng phân vùng: {os.path.basename(target_path)}", "success")
            messagebox.showinfo("Thành công", f"Đã lưu toàn bộ bảng phân vùng ra file CSV chuẩn ESP-IDF:\n{target_path}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Lỗi lưu file", f"Không thể lưu file CSV:\n{e}", parent=self.root)

    def _action_scan_project(self):
        dir_path = filedialog.askdirectory(title="Chọn thư mục dự án ESP-IDF / PlatformIO", parent=self.root)
        if not dir_path:
            return

        res = scan_esp_project(dir_path)
        if not res or not res.partition_table:
            messagebox.showwarning(
                "Không tìm thấy cấu hình",
                f"Không tìm thấy file partitions.csv hoặc build/partition_table/partition-table.bin trong thư mục:\n{dir_path}",
                parent=self.root
            )
            return

        self._push_partition_undo_state()
        self.table = res.partition_table
        self.table.flash_size = res.flash_size
        self.table.target_chip = res.target_chip

        # Cập nhật giao diện đồng bộ
        self._sync_chip_and_flash_combos(res.target_chip, flash_size=res.flash_size)

        self.refresh_partition_views()
        self.set_status(f"Đã quét thành công dự án: {res.project_name}")
        messagebox.showinfo("Quét dự án thành công", f"Đã trích xuất cấu hình phân vùng từ dự án: {res.project_name}\nTarget: {res.target_chip.upper()} | Flash: {format_bytes_human(res.flash_size, compact=True)}", parent=self.root)

    # =========================================================================
    # THAO TÁC PHẦN CỨNG ESP32 (ĐỒNG BỘ CỔNG COM VÀ ESPTOOL AN TOÀN)
    # =========================================================================

    def _log_partition_hw(self, text: str):
        """Ghi nhật ký thao tác phần cứng phân vùng trực tiếp vào Tab Serial Monitor"""
        if hasattr(self, "append_to_monitor"):
            self.append_to_monitor(f"[PARTITION_HW] {text}")

    def _update_partition_hw_progress(self, line: str, task_label: str | None = None):
        """Phân tích dòng output từ esptool để cập nhật thanh tiến trình toàn cục (0% -> 100%)."""
        l_str = str(line)
        pct = None
        parsed_pct = parse_esptool_progress_percent(l_str)
        if parsed_pct is not None:
            pct = max(5, min(99, int(round(parsed_pct))))
        elif "Connecting" in l_str:
            pct = 15
        elif "Chip is" in l_str or "Chip type:" in l_str or "Connected to" in l_str:
            pct = 25
        elif "Stub flasher running" in l_str or "Running stub" in l_str:
            pct = 40
        elif "Configuring flash size" in l_str or "Erasing region" in l_str:
            pct = 60
        elif "Read " in l_str or "Wrote " in l_str or "Hash of data verified" in l_str or "Erase completed" in l_str:
            pct = 92
        if pct is not None and hasattr(self, "_update_flash_progress"):
            self._update_flash_progress(pct, task_label=task_label)

    def _prepare_hardware_port(self) -> tuple[str, int, str] | None:
        """Đảm bảo cổng COM hợp lệ và tạm ngắt Serial Monitor nếu đang kết nối"""
        port = self.port_cb.get().strip()
        if not port or port == "Không có cổng COM":
            messagebox.showerror("Chưa chọn cổng COM", "Vui lòng chọn cổng COM trên thanh điều khiển trước khi thao tác phần cứng.", parent=self.root)
            return None

        baud_str = self.baud_cb.get().strip()
        baud = int(baud_str) if baud_str.isdigit() else 460800
        chip_target = self.table.target_chip
        if chip_target == "auto" or not chip_target or (hasattr(self, "part_chip_var") and self.part_chip_var.get() == "(Chưa chọn)"):
            chip_target = "auto"

        # Ngắt Serial Monitor an toàn nếu đang mở
        if getattr(self, "serial_connection", None) and self.serial_connection.is_open:
            self.on_serial_disconnect()
            self._log_partition_hw(">> [HỆ THỐNG] Đã tự động tạm ngắt Serial Monitor để thực thi tác vụ esptool.")

        return (port, baud, chip_target)

    def _hw_read_partition_table(self):
        """Đọc 4KB bảng phân vùng từ chip ESP32"""
        if self._is_partition_hw_running:
            return
        if hasattr(self, "is_device_busy") and self.is_device_busy():
            messagebox.showwarning("Thiết bị đang bận", "Thiết bị đang bận xử lý tác vụ khác!")
            return
        hw_info = self._prepare_hardware_port()
        if not hw_info:
            return
        port, baud, chip = hw_info
        part_offset = hex(getattr(self.table, "part_table_offset", 0x8000) or 0x8000)

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_partition_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, "đọc bảng phân vùng từ chip"))
            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                safe_after(lambda: self._log_partition_hw(f"\n=== BẮT ĐẦU ĐỌC BẢNG PHÂN VÙNG TỪ CHIP QUA {port} ==="))
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['read_flash', part_offset, '0x1000', tmp_path])

                detected_chip = None
                def on_stream(line):
                    nonlocal detected_chip
                    safe_after(lambda: self._log_partition_hw(f"  {line}"))
                    safe_after(lambda l=line: self._update_partition_hw_progress(l))
                    m = re.search(r"(?:Detecting chip type\.\.\.|Chip is)\s+([A-Za-z0-9\-]+)", line, re.IGNORECASE)
                    if m:
                        detected_chip = m.group(1).strip()

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res) and os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
                    with open(tmp_path, "rb") as f:
                        data = f.read()

                    def update_ui():
                        self._push_partition_undo_state()
                        self.table.from_binary(data)
                        if detected_chip:
                            clean_det = detected_chip.lower().replace("-", "")
                            for cid, info in CHIP_FAMILY_DATABASE.items():
                                if cid.lower() == clean_det or clean_det in cid.lower() or cid.lower() in clean_det:
                                    self.table.target_chip = cid
                                    self.table.bootloader_offset = info.bootloader_offset
                                    highest_sz = max(info.supported_flash_sizes)
                                    self._sync_chip_and_flash_combos(cid, flash_size=highest_sz)
                                    break
                        self.refresh_partition_views()
                        part_count = len(self.table.entries)
                        self.set_status(
                            f"Đã đọc và giải mã bảng phân vùng ({part_count} phân vùng) từ ESP32 thành công!",
                            "success",
                            progress=100,
                        )
                        self._log_partition_hw(
                            f">>> ĐỌC VÀ NẠP THÀNH CÔNG {part_count} PHÂN VÙNG TỪ CHIP!"
                        )

                    safe_after(update_ui)
                else:
                    safe_after(lambda: self.set_status("Lỗi đọc bảng phân vùng từ chip!", "error", progress=0))
                    safe_after(lambda: self._log_partition_hw(">>> [LỖI] Không thể đọc dữ liệu phân vùng từ ESP32."))
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda: self.set_status("Lỗi đọc bảng phân vùng từ chip!", "error", progress=0))
                safe_after(lambda msg=err_msg: self._log_partition_hw(f">>> [NGOẠI LỆ] {msg}"))
            finally:
                if os.path.isfile(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                self._is_partition_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))

        self.partition_hw_thread = threading.Thread(target=worker, daemon=True)
        self.partition_hw_thread.start()

    def _hw_flash_partition_table(self):
        """Nạp bảng phân vùng hiện tại xuống chip"""
        if self._is_partition_hw_running:
            return
        if hasattr(self, "is_device_busy") and self.is_device_busy():
            messagebox.showwarning("Thiết bị đang bận", "Thiết bị đang bận xử lý tác vụ khác!")
            return
        hw_info = self._prepare_hardware_port()
        if not hw_info:
            return
        port, baud, chip = hw_info
        part_offset = hex(getattr(self.table, "part_table_offset", 0x8000) or 0x8000)

        errors = self.table.validate()
        if errors:
            ans = messagebox.askyesno(
                "Cảnh báo tính hợp lệ",
                f"Bảng phân vùng có {len(errors)} lỗi/cảnh báo. Bạn có chắc chắn muốn nạp xuống chip?",
                parent=self.root
            )
            if not ans:
                return

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_partition_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, "nạp bảng phân vùng xuống chip"))
            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                bin_data = self.table.to_binary()
                with open(tmp_path, "wb") as f:
                    f.write(bin_data)

                safe_after(lambda: self._log_partition_hw(f"\n=== NẠP BẢNG PHÂN VÙNG MỚI XUỐNG {part_offset} QUA {port} ==="))
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['write_flash', part_offset, tmp_path])

                def on_stream(line):
                    safe_after(lambda: self._log_partition_hw(f"  {line}"))
                    safe_after(lambda l=line: self._update_partition_hw_progress(l))

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res):
                    safe_after(lambda: self.set_status("Đã nạp Bảng phân vùng xuống chip thành công!", "success", progress=100))
                    safe_after(lambda: self._log_partition_hw(">>> NẠP BẢNG PHÂN VÙNG XUỐNG CHIP THÀNH CÔNG!"))
                    safe_after(lambda: messagebox.showinfo("Thành công", "Đã nạp Bảng phân vùng mới xuống ESP32 thành công!", parent=self.root))
                else:
                    safe_after(lambda: self.set_status("Lỗi nạp bảng phân vùng xuống chip!", "error", progress=0))
                    safe_after(lambda: self._log_partition_hw(">>> [LỖI] Không thể ghi bảng phân vùng xuống chip."))
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda: self.set_status("Lỗi nạp bảng phân vùng xuống chip!", "error", progress=0))
                safe_after(lambda msg=err_msg: self._log_partition_hw(f">>> [NGOẠI LỆ] {msg}"))
            finally:
                if os.path.isfile(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                self._is_partition_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))

        self.partition_hw_thread = threading.Thread(target=worker, daemon=True)
        self.partition_hw_thread.start()

    def _hw_dump_selected_partition(self):
        """Sao lưu một phân vùng cụ thể ra file .bin trên máy tính"""
        if self._is_partition_hw_running:
            return
        if hasattr(self, "is_device_busy") and self.is_device_busy():
            messagebox.showwarning("Thiết bị đang bận", "Thiết bị đang bận xử lý tác vụ khác!")
            return

        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần sao lưu (Dump).", parent=self.root)
            return

        name = self._get_entry_name_from_iid(selected_iid[0])
        entry = next((e for e in self.table.entries if e.name == name), None)
        if not entry:
            return

        save_path = filedialog.asksaveasfilename(
            title=f"Lưu file sao lưu phân vùng '{entry.name}'",
            defaultextension=".bin",
            initialfile=f"{entry.name}_{format_hex(entry.offset)}.bin",
            filetypes=[("Binary Files (*.bin)", "*.bin"), ("All Files (*.*)", "*.*")],
            parent=self.root
        )
        if not save_path:
            return

        hw_info = self._prepare_hardware_port()
        if not hw_info:
            return
        port, baud, chip = hw_info

        def worker():
            self._is_partition_hw_running = True
            if hasattr(self, 'set_global_busy_state'):
                self.root.after(0, lambda: self.set_global_busy_state(True, f"sao lưu phân vùng '{entry.name}'"))
            try:
                self.root.after(0, self._log_partition_hw, f"\n=== SAO LƯU PHÂN VÙNG '{entry.name}' (0x{entry.offset:X}, {entry.size:,} B) VÀO {save_path} ===")
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['read_flash', format_hex(entry.offset), format_hex(entry.size), save_path])

                def on_stream(line):
                    self.root.after(0, self._log_partition_hw, f"  {line}")
                    self.root.after(0, self._update_partition_hw_progress, line)

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res):
                    self.root.after(0, lambda: self.set_status(f"Đã sao lưu phân vùng '{entry.name}' thành công!", "success", progress=100))
                    self.root.after(0, self._log_partition_hw, f">>> SAO LƯU THÀNH CÔNG: {save_path}")
                    self.root.after(0, lambda: messagebox.showinfo("Thành công", f"Đã sao lưu phân vùng '{entry.name}' ra file .bin thành công:\n{save_path}", parent=self.root))
                else:
                    self.root.after(0, lambda: self.set_status(f"Lỗi sao lưu phân vùng '{entry.name}'!", "error", progress=0))
                    self.root.after(0, self._log_partition_hw, f">>> [LỖI] Không thể đọc phân vùng '{entry.name}' từ chip.")
            except Exception as ex:
                self.root.after(0, lambda: self.set_status(f"Lỗi sao lưu phân vùng '{entry.name}'!", "error", progress=0))
                self.root.after(0, self._log_partition_hw, f">>> [NGOẠI LỆ] {ex}")
            finally:
                self._is_partition_hw_running = False
                if hasattr(self, 'set_global_busy_state'):
                    self.root.after(0, lambda: self.set_global_busy_state(False))

        self.partition_hw_thread = threading.Thread(target=worker, daemon=True)
        self.partition_hw_thread.start()

    def _hw_erase_selected_partition(self):
        """Xóa trắng (erase-region) một phân vùng cụ thể trên chip"""
        if self._is_partition_hw_running:
            return
        if hasattr(self, "is_device_busy") and self.is_device_busy():
            messagebox.showwarning("Thiết bị đang bận", "Thiết bị đang bận xử lý tác vụ khác!")
            return

        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần xóa trắng (Erase).", parent=self.root)
            return

        name = self._get_entry_name_from_iid(selected_iid[0])
        entry = next((e for e in self.table.entries if e.name == name), None)
        if not entry:
            return

        ans = messagebox.askyesno(
            "Xác nhận xóa trắng",
            f"Bạn có chắc chắn muốn XÓA TRẮNG (Erase Region) phân vùng '{entry.name}' tại {format_hex(entry.offset)} ({format_bytes_human(entry.size)}) trên chip không?\nThao tác này sẽ xóa sạch dữ liệu trong phân vùng đó!",
            parent=self.root
        )
        if not ans:
            return

        hw_info = self._prepare_hardware_port()
        if not hw_info:
            return
        port, baud, chip = hw_info

        def worker():
            self._is_partition_hw_running = True
            if hasattr(self, 'set_global_busy_state'):
                self.root.after(0, lambda: self.set_global_busy_state(True, f"xóa vùng phân vùng '{entry.name}'"))
            try:
                self.root.after(0, self._log_partition_hw, f"\n=== XÓA TRẮNG VÙNG NHỚ PHÂN VÙNG '{entry.name}' (0x{entry.offset:X}, {entry.size:,} B) ===")
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['erase-region', format_hex(entry.offset), format_hex(entry.size)])

                def on_stream(line):
                    self.root.after(0, self._log_partition_hw, f"  {line}")
                    self.root.after(0, self._update_partition_hw_progress, line)

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res):
                    self.root.after(0, lambda: self.set_status(f"Đã xóa trắng phân vùng '{entry.name}' thành công!", "success", progress=100))
                    self.root.after(0, self._log_partition_hw, f">>> ĐÃ XÓA TRẮNG THÀNH CÔNG PHÂN VÙNG '{entry.name}'!")
                    self.root.after(0, lambda: messagebox.showinfo("Thành công", f"Đã xóa trắng vùng nhớ phân vùng '{entry.name}' thành công!", parent=self.root))
                else:
                    self.root.after(0, lambda: self.set_status(f"Lỗi xóa phân vùng '{entry.name}'!", "error", progress=0))
                    self.root.after(0, self._log_partition_hw, f">>> [LỖI] Không thể xóa phân vùng '{entry.name}'.")
            except Exception as ex:
                self.root.after(0, lambda: self.set_status(f"Lỗi xóa phân vùng '{entry.name}'!", "error", progress=0))
                self.root.after(0, self._log_partition_hw, f">>> [NGOẠI LỆ] {ex}")
            finally:
                self._is_partition_hw_running = False
                if hasattr(self, 'set_global_busy_state'):
                    self.root.after(0, lambda: self.set_global_busy_state(False))

        self.partition_hw_thread = threading.Thread(target=worker, daemon=True)
        self.partition_hw_thread.start()

    def _hw_write_selected_partition(self):
        """Nạp file .bin vào phân vùng đang chọn"""
        if self._is_partition_hw_running:
            return
        if hasattr(self, "is_device_busy") and self.is_device_busy():
            messagebox.showwarning("Thiết bị đang bận", "Thiết bị đang bận xử lý tác vụ khác!")
            return

        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần nạp file .bin.", parent=self.root)
            return

        name = self._get_entry_name_from_iid(selected_iid[0])
        entry = next((e for e in self.table.entries if e.name == name), None)
        if not entry:
            return

        bin_path = filedialog.askopenfilename(
            title=f"Chọn file .bin nạp vào phân vùng '{entry.name}'",
            filetypes=[("Binary Files (*.bin)", "*.bin"), ("All Files (*.*)", "*.*")],
            parent=self.root
        )
        if not bin_path:
            return

        file_sz = os.path.getsize(bin_path)
        if file_sz > entry.size:
            messagebox.showerror(
                "File quá lớn",
                f"File {os.path.basename(bin_path)} có dung lượng {file_sz:,} Bytes, vượt quá kích thước cho phép của phân vùng '{entry.name}' ({entry.size:,} Bytes)!",
                parent=self.root
            )
            return

        hw_info = self._prepare_hardware_port()
        if not hw_info:
            return
        port, baud, chip = hw_info

        def worker():
            self._is_partition_hw_running = True
            if hasattr(self, 'set_global_busy_state'):
                self.root.after(0, lambda: self.set_global_busy_state(True, f"nạp file vào phân vùng '{entry.name}'"))
            try:
                self.root.after(0, self._log_partition_hw, f"\n=== NẠP FILE {os.path.basename(bin_path)} VÀO PHÂN VÙNG '{entry.name}' TẠI 0x{entry.offset:X} ===")
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['write_flash', format_hex(entry.offset), bin_path])

                def on_stream(line):
                    self.root.after(0, self._log_partition_hw, f"  {line}")
                    self.root.after(0, self._update_partition_hw_progress, line)

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res):
                    self.root.after(0, lambda: self.set_status(f"Nạp file vào phân vùng '{entry.name}' thành công!", "success", progress=100))
                    self.root.after(0, self._log_partition_hw, f">>> NẠP FILE THÀNH CÔNG VÀO PHÂN VÙNG '{entry.name}'!")
                    self.root.after(0, lambda: messagebox.showinfo("Thành công", f"Đã nạp file {os.path.basename(bin_path)} vào phân vùng '{entry.name}' thành công!", parent=self.root))
                else:
                    self.root.after(0, lambda: self.set_status(f"Lỗi nạp file vào phân vùng '{entry.name}'!", "error", progress=0))
                    self.root.after(0, self._log_partition_hw, f">>> [LỖI] Không thể nạp file vào phân vùng '{entry.name}'.")
            except Exception as ex:
                self.root.after(0, lambda: self.set_status(f"Lỗi nạp file vào phân vùng '{entry.name}'!", "error", progress=0))
                self.root.after(0, self._log_partition_hw, f">>> [NGOẠI LỆ] {ex}")
            finally:
                self._is_partition_hw_running = False
                if hasattr(self, 'set_global_busy_state'):
                    self.root.after(0, lambda: self.set_global_busy_state(False))

        self.partition_hw_thread = threading.Thread(target=worker, daemon=True)
        self.partition_hw_thread.start()
