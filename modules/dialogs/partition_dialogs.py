# -*- coding: utf-8 -*-
"""
ESP32 Partition Engine - Dialogs for Partition Management & Presets
Hộp thoại thêm/sửa phân vùng và chọn mẫu bảng phân vùng chuẩn ESP-IDF.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Tuple, Dict, Any, List

from modules.config import DARK_PALETTE, LIGHT_PALETTE
from modules.dialogs.layout_util import fit_dialog
from modules.win32_util import set_window_icon_native
from modules.partition.partition_model import (
    PartitionEntry, SUBTYPES_MAP, TYPE_APP, TYPE_DATA
)
from modules.partition.unit_formatter import (
    parse_size_or_offset, format_hex, format_bytes_human,
    align_up, sector_count
)


PRESET_CONFIGS = [
    {
        "name": "1. Chuẩn mặc định ESP-IDF (Factory 1MB + SPIFFS) - Flash 4MB",
        "flash_size": 4 * 1024 * 1024,
        "chip": "esp32",
        "csv": (
            "# ESP-IDF Partition Table - Default SPIFFS\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1M,\n"
            "storage,  data, spiffs,  ,        2800K,\n"
        )
    },
    {
        "name": "2. Cập nhật OTA kép (Factory + OTA_0 + OTA_1) - Flash 4MB",
        "flash_size": 4 * 1024 * 1024,
        "chip": "esp32",
        "csv": (
            "# ESP-IDF Partition Table - Two OTA\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x4000,\n"
            "otadata,  data, ota,     0xd000,  0x2000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1M,\n"
            "ota_0,    app,  ota_0,   ,        1M,\n"
            "ota_1,    app,  ota_1,   ,        1M,\n"
            "storage,  data, spiffs,  ,        800K,\n"
        )
    },
    {
        "name": "3. Ứng dụng lớn không OTA (Single Large App 3MB) - Flash 4MB",
        "flash_size": 4 * 1024 * 1024,
        "chip": "esp32",
        "csv": (
            "# ESP-IDF Partition Table - Large App 3MB (No OTA)\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 3M,\n"
            "storage,  data, spiffs,  ,        896K,\n"
        )
    },
    {
        "name": "4. Đa hệ thống tệp (LittleFS + FATFS) - Flash 4MB",
        "flash_size": 4 * 1024 * 1024,
        "chip": "esp32",
        "csv": (
            "# ESP-IDF Partition Table - Multi Storage\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1536K,\n"
            "web_fs,   data, littlefs, ,       1280K,\n"
            "data_log, data, fat,      ,       1M,\n"
        )
    },
    {
        "name": "5. Flash lớn 8MB có OTA kép (OTA_0 2.5MB + OTA_1 2.5MB) - Flash 8MB",
        "flash_size": 8 * 1024 * 1024,
        "chip": "esp32s3",
        "csv": (
            "# ESP-IDF Partition Table - 8MB Two OTA\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x4000,\n"
            "otadata,  data, ota,     0xd000,  0x2000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 2M,\n"
            "ota_0,    app,  ota_0,   ,        2560K,\n"
            "ota_1,    app,  ota_1,   ,        2560K,\n"
            "storage,  data, spiffs,  ,        600K,\n"
        )
    },
    {
        "name": "6. Flash cực lớn 16MB có OTA kép (OTA_0 4.5MB + OTA_1 4.5MB + FS 6MB) - Flash 16MB",
        "flash_size": 16 * 1024 * 1024,
        "chip": "esp32s3",
        "csv": (
            "# ESP-IDF Partition Table - 16MB Two OTA\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "otadata,  data, ota,     0xf000,  0x2000,\n"
            "phy_init, data, phy,     0x11000, 0x1000,\n"
            "factory,  app,  factory, 0x20000, 2M,\n"
            "ota_0,    app,  ota_0,   ,        4608K,\n"
            "ota_1,    app,  ota_1,   ,        4608K,\n"
            "storage,  data, spiffs,  ,        4M,\n"
        )
    },
    {
        "name": "7. Rút gọn tối giản (Minimal SPIFFS) - Flash 2MB",
        "flash_size": 2 * 1024 * 1024,
        "chip": "esp32c3",
        "csv": (
            "# ESP-IDF Partition Table - Minimal 2MB\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x4000,\n"
            "phy_init, data, phy,     0xd000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1280K,\n"
            "storage,  data, spiffs,  ,        600K,\n"
        )
    }
]


class PartitionEditDialog:
    """Hộp thoại Thêm mới hoặc Chỉnh sửa một phân vùng"""

    def __init__(self, parent, entry: Optional[PartitionEntry] = None, suggested_offset: int = 0x10000, is_dark_mode: bool = True):
        self.parent = parent
        self.is_edit = (entry is not None)
        self.is_dark_mode = is_dark_mode
        self.result: Optional[PartitionEntry] = None

        if entry:
            self.entry = entry.clone()
        else:
            self.entry = PartitionEntry(
                name="new_part",
                type_str="app",
                subtype_str="factory",
                offset=suggested_offset,
                size=1024 * 1024
            )

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Chỉnh Sửa Phân Vùng" if self.is_edit else "Thêm Phân Vùng Mới")
        set_window_icon_native(self.dialog)

        self.palette = DARK_PALETTE if is_dark_mode else LIGHT_PALETTE
        self.dialog.configure(bg=self.palette["bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._build_ui()
        fit_dialog(self.dialog, parent, minimum_width=520, minimum_height=420)
        self.dialog.wait_window()

    def _build_ui(self):
        container = ttk.Frame(self.dialog, padding=14)
        container.pack(fill="both", expand=True)

        # Form layout
        row = 0

        # 1. Tên phân vùng
        ttk.Label(container, text="Tên phân vùng (Name):", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=6
        )
        self.var_name = tk.StringVar(value=self.entry.name)
        self.entry_name = ttk.Entry(container, textvariable=self.var_name, width=28)
        self.entry_name.grid(row=row, column=1, sticky="w", pady=6)
        ttk.Label(container, text="(Tối đa 15 ký tự ASCII)", foreground=self.palette["disabled_fg"]).grid(
            row=row, column=2, sticky="w", padx=6
        )
        row += 1

        # 2. Loại chính (Type)
        ttk.Label(container, text="Loại chính (Type):", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=6
        )
        self.var_type = tk.StringVar(value=self.entry.type_str.lower())
        self.cb_type = ttk.Combobox(container, textvariable=self.var_type, values=["app", "data"], state="readonly", width=25)
        self.cb_type.grid(row=row, column=1, sticky="w", pady=6)
        self.cb_type.bind("<<ComboboxSelected>>", self._on_type_changed)
        row += 1

        # 3. Phân loại phụ (SubType)
        ttk.Label(container, text="Phân loại phụ (SubType):", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=6
        )
        self.var_subtype = tk.StringVar(value=self.entry.subtype_str.lower())
        self.cb_subtype = ttk.Combobox(container, textvariable=self.var_subtype, width=25)
        self.cb_subtype.grid(row=row, column=1, sticky="w", pady=6)
        self._update_subtype_options(self.var_type.get())
        row += 1

        # 4. Offset
        ttk.Label(container, text="Địa chỉ bắt đầu (Offset):", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=6
        )
        off_frame = ttk.Frame(container)
        off_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=6)

        self.var_offset = tk.StringVar(value=format_hex(self.entry.offset))
        self.entry_offset = ttk.Entry(off_frame, textvariable=self.var_offset, width=16)
        self.entry_offset.pack(side="left", padx=(0, 6))

        self.btn_align = ttk.Button(off_frame, text="⚡ Căn biên chuẩn", command=self._auto_align_offset)
        self.btn_align.pack(side="left")
        row += 1

        # 5. Size
        ttk.Label(container, text="Dung lượng (Size):", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=6
        )
        self.var_size = tk.StringVar(value=format_hex(self.entry.size))
        self.entry_size = ttk.Entry(container, textvariable=self.var_size, width=28)
        self.entry_size.grid(row=row, column=1, sticky="w", pady=6)
        ttk.Label(container, text="(Ví dụ: 64K, 1M, 0x10000)", foreground=self.palette["disabled_fg"]).grid(
            row=row, column=2, sticky="w", padx=6
        )
        row += 1

        # 6. Flags
        ttk.Label(container, text="Cờ bảo mật (Flags):", font=("Segoe UI", 9, "bold")).grid(
            row=row, column=0, sticky="w", pady=6
        )
        flags_frame = ttk.Frame(container)
        flags_frame.grid(row=row, column=1, columnspan=2, sticky="w", pady=6)

        self.var_encrypted = tk.BooleanVar(value=("encrypted" in self.entry.flags_str.lower()))
        self.chk_enc = ttk.Checkbutton(flags_frame, text="encrypted (Mã hóa)", variable=self.var_encrypted)
        self.chk_enc.pack(side="left", padx=(0, 14))

        self.var_readonly = tk.BooleanVar(value=("readonly" in self.entry.flags_str.lower()))
        self.chk_ro = ttk.Checkbutton(flags_frame, text="readonly (Chỉ đọc)", variable=self.var_readonly)
        self.chk_ro.pack(side="left")
        row += 1

        # Khung preview trực quan
        preview_box = ttk.LabelFrame(container, text=" Xem trước & Kiểm tra tính hợp lệ ", padding=10)
        preview_box.grid(row=row, column=0, columnspan=3, sticky="nsew", pady=(12, 12))
        container.rowconfigure(row, weight=1)
        container.columnconfigure(1, weight=1)

        self.lbl_preview = ttk.Label(preview_box, text="", justify="left", font=("Segoe UI", 9))
        self.lbl_preview.pack(fill="both", expand=True)
        row += 1

        # Bottom Buttons
        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=row, column=0, columnspan=3, sticky="e", pady=(6, 0))

        btn_cancel = ttk.Button(btn_frame, text="Hủy bỏ", command=self.dialog.destroy)
        btn_cancel.pack(side="right", padx=(8, 0))

        btn_save = ttk.Button(btn_frame, text="Lưu phân vùng" if self.is_edit else "Thêm phân vùng", command=self._on_save)
        btn_save.pack(side="right")

        # Gán sự kiện cập nhật preview
        self.var_name.trace_add("write", lambda *_: self._update_preview())
        self.var_offset.trace_add("write", lambda *_: self._update_preview())
        self.var_size.trace_add("write", lambda *_: self._update_preview())
        self.var_type.trace_add("write", lambda *_: self._update_preview())
        self.var_subtype.trace_add("write", lambda *_: self._update_preview())

        self._update_preview()

    def _on_type_changed(self, event=None):
        t = self.var_type.get().lower()
        self._update_subtype_options(t)
        if t == "app":
            self.var_subtype.set("factory")
        else:
            self.var_subtype.set("nvs")
        self._update_preview()

    def _update_subtype_options(self, type_str: str):
        if type_str == "app":
            opts = ["factory", "ota_0", "ota_1", "ota_2", "test"]
        else:
            opts = ["nvs", "phy", "ota", "spiffs", "littlefs", "fat", "coredump", "nvs_keys", "efuse"]
        self.cb_subtype["values"] = opts

    def _auto_align_offset(self):
        try:
            curr_off = parse_size_or_offset(self.var_offset.get())
            is_app = (self.var_type.get().lower() == "app")
            pad_to = 0x10000 if is_app else 0x1000
            aligned = align_up(curr_off, pad_to)
            self.var_offset.set(format_hex(aligned))
        except Exception:
            self.var_offset.set("0x10000" if self.var_type.get().lower() == "app" else "0x9000")

    def _update_preview(self):
        try:
            name = self.var_name.get().strip()
            type_str = self.var_type.get().strip()
            subtype_str = self.var_subtype.get().strip()
            offset_val = parse_size_or_offset(self.var_offset.get())
            size_val = parse_size_or_offset(self.var_size.get())
            end_val = offset_val + size_val

            lines = []
            lines.append(f"• Dải địa chỉ: {format_hex(offset_val)} -> {format_hex(end_val)}")
            lines.append(f"• Dung lượng: {format_bytes_human(size_val)} ({size_val:,} Bytes) | {sector_count(size_val)} Sectors (4KB)")

            # Kiểm tra quy tắc
            warnings = []
            if len(name.encode('utf-8')) > 16:
                warnings.append("⚠️ Tên phân vùng dài hơn 16 bytes!")
            if size_val % 0x1000 != 0:
                warnings.append("❌ Dung lượng bắt buộc phải là bội số của 4KB (0x1000)!")

            if type_str == "app":
                if offset_val % 0x10000 != 0:
                    warnings.append(f"❌ Phân vùng App bắt buộc Offset phải chia hết cho 64KB (0x10000). Hiện tại: {format_hex(offset_val)}")
                if offset_val < 0x10000:
                    warnings.append("❌ Phân vùng App không được đặt trong vùng cấm < 0x10000!")
            else:
                if offset_val % 0x1000 != 0:
                    warnings.append(f"❌ Phân vùng Data bắt buộc Offset phải chia hết cho 4KB (0x1000). Hiện tại: {format_hex(offset_val)}")

            if not warnings:
                lines.append("✅ Căn biên và thông số hoàn toàn hợp lệ theo chuẩn ESP-IDF.")
            else:
                lines.extend(warnings)

            self.lbl_preview.config(text="\n".join(lines))
        except Exception as e:
            self.lbl_preview.config(text=f"⚠️ Thông số chưa hoàn chỉnh: {e}")

    def _on_save(self):
        name = self.var_name.get().strip()
        if not name:
            messagebox.showwarning("Thiếu dữ liệu", "Vui lòng nhập tên phân vùng.", parent=self.dialog)
            return

        if len(name.encode('utf-8')) > 16:
            messagebox.showwarning("Tên quá dài", "Tên phân vùng không được vượt quá 15 ký tự ASCII.", parent=self.dialog)
            return

        try:
            offset_val = parse_size_or_offset(self.var_offset.get())
            size_val = parse_size_or_offset(self.var_size.get())
        except Exception as e:
            messagebox.showerror("Sai định dạng", f"Dữ liệu Offset hoặc Size không hợp lệ: {e}", parent=self.dialog)
            return

        if size_val <= 0 or size_val % 0x1000 != 0:
            messagebox.showerror("Sai kích thước", "Dung lượng (Size) phải lớn hơn 0 và là bội số của 4KB (0x1000).", parent=self.dialog)
            return

        type_str = self.var_type.get().lower()
        if type_str == "app":
            if offset_val % 0x10000 != 0 or offset_val < 0x10000:
                messagebox.showerror("Lỗi Căn Biên App", "Phân vùng App bắt buộc Offset phải chia hết cho 64KB (0x10000) và >= 0x10000.", parent=self.dialog)
                return
        else:
            if offset_val % 0x1000 != 0:
                messagebox.showerror("Lỗi Căn Biên Data", "Phân vùng Data bắt buộc Offset phải chia hết cho 4KB (0x1000).", parent=self.dialog)
                return

        flags_list = []
        if self.var_encrypted.get():
            flags_list.append("encrypted")
        if self.var_readonly.get():
            flags_list.append("readonly")
        flags_str = ", ".join(flags_list)

        self.result = PartitionEntry(
            name=name,
            type_str=type_str,
            subtype_str=self.var_subtype.get().strip(),
            offset=offset_val,
            size=size_val,
            flags_str=flags_str,
            used_size=self.entry.used_size
        )
        self.dialog.destroy()


class PresetSelectorDialog:
    """Hộp thoại chọn bảng phân vùng mẫu chuẩn ESP-IDF"""

    def __init__(self, parent, is_dark_mode: bool = True):
        self.parent = parent
        self.is_dark_mode = is_dark_mode
        self.result: Optional[Dict[str, Any]] = None

        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Chọn Mẫu Phân Vùng Chuẩn (Presets)")
        set_window_icon_native(self.dialog)

        self.palette = DARK_PALETTE if is_dark_mode else LIGHT_PALETTE
        self.dialog.configure(bg=self.palette["bg"])
        self.dialog.transient(parent)
        self.dialog.grab_set()

        self._build_ui()
        fit_dialog(self.dialog, parent, minimum_width=640, minimum_height=460)
        self.dialog.wait_window()

    def _build_ui(self):
        container = ttk.Frame(self.dialog, padding=12)
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Danh Sách Mẫu Thiết Kế Sẵn Chuẩn ESP-IDF:", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        # Combobox chọn mẫu
        self.var_choice = tk.StringVar(value=PRESET_CONFIGS[0]["name"])
        names = [p["name"] for p in PRESET_CONFIGS]
        self.cb_presets = ttk.Combobox(container, textvariable=self.var_choice, values=names, state="readonly", width=55)
        self.cb_presets.pack(fill="x", pady=(0, 10))
        self.cb_presets.bind("<<ComboboxSelected>>", self._on_preset_selected)

        # Khung text preview CSV
        ttk.Label(container, text="Nội dung partitions.csv tương ứng:").pack(anchor="w", pady=(0, 4))
        
        preview_frame = ttk.Frame(container)
        preview_frame.pack(fill="both", expand=True, pady=(0, 10))

        self.txt_preview = tk.Text(
            preview_frame,
            wrap="none",
            font=("Consolas", 10),
            bg=self.palette["text_bg"],
            fg=self.palette["text_fg"],
            insertbackground=self.palette["fg"],
            relief="solid",
            borderwidth=1
        )
        self.txt_preview.pack(side="left", fill="both", expand=True)

        scroll_y = ttk.Scrollbar(preview_frame, orient="vertical", command=self.txt_preview.yview)
        scroll_y.pack(side="right", fill="y")
        self.txt_preview.config(yscrollcommand=scroll_y.set)

        # Buttons
        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x")

        btn_cancel = ttk.Button(btn_frame, text="Hủy bỏ", command=self.dialog.destroy)
        btn_cancel.pack(side="right", padx=(8, 0))

        btn_apply = ttk.Button(btn_frame, text="Áp Dụng Mẫu Này", command=self._on_apply)
        btn_apply.pack(side="right")

        self._on_preset_selected()

    def _on_preset_selected(self, event=None):
        name = self.var_choice.get()
        for p in PRESET_CONFIGS:
            if p["name"] == name:
                self.txt_preview.delete("1.0", "end")
                self.txt_preview.insert("1.0", p["csv"])
                break

    def _on_apply(self):
        name = self.var_choice.get()
        for p in PRESET_CONFIGS:
            if p["name"] == name:
                self.result = p
                break
        self.dialog.destroy()
