# -*- coding: utf-8 -*-
"""
Esp32 tool v2.1 - Tab 4: Partition Wizard (Phân vùng Bộ nhớ ESP32)
Quản lý, phân tích, tối ưu bảng phân vùng ESP-IDF với sơ đồ trực quan phong cách MiniTool.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from modules.config import (
    DARK_PALETTE, LIGHT_PALETTE, FLASH_BAUDS, FLASH_CHIP_TARGETS
)
from modules.esptool_util import run_esptool_command, esptool_command_succeeded
from modules.partition.unit_formatter import (
    DisplayMode, parse_size_or_offset, format_bytes_human, format_hex,
    format_value, align_up, sector_count
)
from modules.partition.chip_database import (
    CHIP_FAMILY_DATABASE, get_chip_info
)
from modules.partition.partition_model import (
    PartitionTable, PartitionEntry, PARTITION_TABLE_SIZE_DEFAULT
)
from modules.partition.project_scanner import scan_esp_project
from modules.dialogs.partition_dialogs import (
    PartitionEditDialog, PresetSelectorDialog
)


FLASH_SIZE_OPTIONS = [
    ("2 MB", 2 * 1024 * 1024),
    ("4 MB (Chuẩn)", 4 * 1024 * 1024),
    ("8 MB", 8 * 1024 * 1024),
    ("16 MB", 16 * 1024 * 1024),
    ("32 MB", 32 * 1024 * 1024),
]


class CanvasTooltip:
    """Tooltip nổi hiển thị thông số chi tiết khi hover chuột vào từng khối phân vùng"""
    def __init__(self, canvas: tk.Canvas):
        self.canvas = canvas
        self.tip_window: tk.Toplevel | None = None

    def show(self, text: str, x: int, y: int, is_dark: bool):
        self.hide()
        p = DARK_PALETTE if is_dark else LIGHT_PALETTE
        self.tip_window = tw = tk.Toplevel(self.canvas)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.wm_geometry(f"+{x + 12}+{y + 12}")

        frame = tk.Frame(tw, background=p["border"], padx=1, pady=1)
        frame.pack()

        lbl = tk.Label(
            frame,
            text=text,
            justify="left",
            background=p["text_bg"],
            foreground=p["text_fg"],
            font=("Segoe UI", 9),
            padx=8,
            pady=6
        )
        lbl.pack()

    def hide(self):
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None


class DiskMapCanvas(tk.Canvas):
    """
    Thanh hiển thị trực quan bản đồ bộ nhớ Flash phong cách MiniTool Partition Wizard.
    Vẽ các phân vùng và khoảng trống chưa phân bổ (Unallocated) theo tỷ lệ thực tế.
    """
    def __init__(self, parent, on_select_entry=None, on_unallocated_click=None, on_context_action=None, **kwargs):
        super().__init__(parent, height=80, relief="solid", borderwidth=1, highlightthickness=0, **kwargs)
        self.on_select_entry = on_select_entry
        self.on_unallocated_click = on_unallocated_click
        self.on_context_action = on_context_action

        self.layout_entries: list[PartitionEntry] = []
        self.flash_size: int = 4 * 1024 * 1024
        self.display_mode: DisplayMode = DisplayMode.DECIMAL
        self.selected_entry: PartitionEntry | None = None
        self.is_dark: bool = False

        self._rendered_blocks: list[tuple[float, float, float, float, PartitionEntry]] = []
        self.tooltip = CanvasTooltip(self)

        self.bind("<Configure>", lambda e: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Button-3>", self._on_right_click)

    def set_theme_mode(self, is_dark: bool):
        self.is_dark = is_dark
        p = DARK_PALETTE if is_dark else LIGHT_PALETTE
        self.configure(background=p["bg"], highlightbackground=p["border"])
        self.redraw()

    def set_data(self, layout_entries: list[PartitionEntry], flash_size: int, display_mode: DisplayMode, selected_entry: PartitionEntry | None = None):
        self.layout_entries = layout_entries
        self.flash_size = max(1024, flash_size)
        self.display_mode = display_mode
        self.selected_entry = selected_entry
        self.redraw()

    def _get_entry_color(self, entry: PartitionEntry) -> tuple[str, str]:
        """Trả về (màu nền, màu chữ) cho từng loại phân vùng"""
        if entry.is_unallocated:
            return ("#374151" if self.is_dark else "#e2e8f0", "#9ca3af" if self.is_dark else "#64748b")
        if entry.is_system:
            if entry.type_str == "bootloader":
                return ("#475569" if self.is_dark else "#94a3b8", "#ffffff")
            return ("#334155" if self.is_dark else "#64748b", "#ffffff")

        t = entry.type_str.lower()
        st = entry.subtype_str.lower()

        if t == "app":
            if st == "factory":
                return ("#2563eb" if self.is_dark else "#3b82f6", "#ffffff")
            elif st.startswith("ota_"):
                return ("#7c3aed" if self.is_dark else "#8b5cf6", "#ffffff")
            return ("#4f46e5" if self.is_dark else "#6366f1", "#ffffff")
        else:  # data
            if st == "nvs":
                return ("#d97706" if self.is_dark else "#f59e0b", "#ffffff")
            elif st == "ota":
                return ("#0d9488" if self.is_dark else "#14b8a6", "#ffffff")
            elif st in ("spiffs", "littlefs", "fat"):
                return ("#059669" if self.is_dark else "#10b981", "#ffffff")
            elif st == "phy":
                return ("#b45309" if self.is_dark else "#d97706", "#ffffff")
            elif st == "coredump":
                return ("#be185d" if self.is_dark else "#ec4899", "#ffffff")
            return ("#0891b2" if self.is_dark else "#06b6d4", "#ffffff")

    def redraw(self):
        self.delete("all")
        self._rendered_blocks.clear()

        w = self.winfo_width()
        h = self.winfo_height()
        if w < 60 or h < 30:
            return

        p = DARK_PALETTE if self.is_dark else LIGHT_PALETTE
        # Vẽ viền ngoài
        self.create_rectangle(2, 2, w - 2, h - 2, outline=p["border"], fill=p["bg"], width=1)

        if not self.layout_entries or self.flash_size <= 0:
            self.create_text(w / 2, h / 2, text="Chưa có dữ liệu phân vùng", fill=p["fg"], font=("Segoe UI", 10))
            return

        padding_x = 4.0
        padding_y = 4.0
        bar_w = w - (2 * padding_x)
        bar_h = h - (2 * padding_y)

        # Tính toán bề rộng tối thiểu 36px cho mỗi khối
        min_px = 36.0
        raw_widths = []
        for e in self.layout_entries:
            px = (e.size / self.flash_size) * bar_w
            raw_widths.append(max(px, min_px if e.size > 0 else 0))

        sum_w = sum(raw_widths)
        scale = bar_w / sum_w if sum_w > 0 else 1.0

        current_x = padding_x
        top_y = padding_y
        bot_y = padding_y + bar_h

        for idx, entry in enumerate(self.layout_entries):
            block_w = raw_widths[idx] * scale
            x1 = current_x
            x2 = current_x + block_w
            current_x = x2

            bg_color, fg_color = self._get_entry_color(entry)
            border_col = p["border"]
            border_w = 1

            is_selected = (
                self.selected_entry and not entry.is_unallocated and not entry.is_system and
                self.selected_entry.name == entry.name and self.selected_entry.offset == entry.offset
            )
            if is_selected:
                border_col = "#38bdf8" if self.is_dark else "#005fb8"
                border_w = 3

            # Vẽ khối chữ nhật phân vùng
            tag_id = f"block_{idx}"
            if entry.is_unallocated:
                self.create_rectangle(x1, top_y, x2, bot_y, fill=bg_color, outline=border_col, width=border_w, tags=tag_id, dash=(4, 2))
            else:
                self.create_rectangle(x1, top_y, x2, bot_y, fill=bg_color, outline=border_col, width=border_w, tags=tag_id)

            # Vẽ thanh % đã dùng nếu có
            if entry.used_size > 0 and entry.size > 0:
                used_ratio = min(1.0, entry.used_size / entry.size)
                used_x2 = x1 + (block_w * used_ratio)
                used_bg = "#1e40af" if self.is_dark else "#1d4ed8"
                self.create_rectangle(x1, bot_y - 8, used_x2, bot_y - 1, fill=used_bg, outline="", tags=tag_id)

            # Vẽ nhãn tên & kích thước
            mid_x = (x1 + x2) / 2
            mid_y = (top_y + bot_y) / 2

            if block_w >= 40:
                name_lbl = entry.name
                if block_w < 70 and len(name_lbl) > 8:
                    name_lbl = name_lbl[:7] + "…"
                size_lbl = format_bytes_human(entry.size, compact=True)

                self.create_text(mid_x, mid_y - 8, text=name_lbl, fill=fg_color, font=("Segoe UI", 8, "bold"), tags=tag_id)
                self.create_text(mid_x, mid_y + 8, text=size_lbl, fill=fg_color, font=("Segoe UI", 7), tags=tag_id)
            elif block_w >= 20:
                self.create_text(mid_x, mid_y, text=entry.name[:3], fill=fg_color, font=("Segoe UI", 7), tags=tag_id)

            self._rendered_blocks.append((x1, top_y, x2, bot_y, entry))

    def _find_entry_at(self, x: float, y: float) -> PartitionEntry | None:
        for x1, y1, x2, y2, entry in self._rendered_blocks:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return entry
        return None

    def _on_motion(self, event):
        entry = self._find_entry_at(event.x, event.y)
        if entry:
            self.configure(cursor="hand2")
            tip_lines = []
            if entry.is_unallocated:
                tip_lines.append(f"【 VÙNG TRỐNG (Unallocated Gap) 】")
                tip_lines.append(f"• Địa chỉ: {format_hex(entry.offset)} -> {format_hex(entry.end_offset)}")
                tip_lines.append(f"• Dung lượng trống: {format_bytes_human(entry.size)} ({entry.size:,} B)")
                tip_lines.append(f"• Số Sector: {sector_count(entry.size)} sectors")
                tip_lines.append("👉 Bấm chuột để tạo phân vùng mới trong khoảng trống này.")
            elif entry.is_system:
                tip_lines.append(f"【 Phân vùng Hệ thống: {entry.name} 】")
                tip_lines.append(f"• Offset: {format_hex(entry.offset)} | Size: {format_bytes_human(entry.size)}")
                tip_lines.append("• Phân vùng do hệ thống ESP-IDF/Bootloader quản lý cố định.")
            else:
                tip_lines.append(f"【 Phân vùng: {entry.name} 】")
                tip_lines.append(f"• Kiểu (Type): {entry.type_str} / {entry.subtype_str}")
                tip_lines.append(f"• Offset: {format_hex(entry.offset)} ({entry.offset:,} B)")
                tip_lines.append(f"• Dung lượng: {format_bytes_human(entry.size)} ({entry.size:,} B)")
                tip_lines.append(f"• Chiếm dụng: {sector_count(entry.size)} Sectors (4KB)")
                if entry.used_size > 0:
                    tip_lines.append(f"• Firmware chiếm: {format_bytes_human(entry.used_size)} ({entry.usage_percent:.1f}%)")
                    tip_lines.append(f"• Còn trống: {format_bytes_human(entry.free_size)}")
                if entry.flags_str:
                    tip_lines.append(f"• Cờ bảo mật: {entry.flags_str}")
                tip_lines.append("👉 Click để chọn | Chuột phải để mở menu thao tác.")

            root_x = self.winfo_rootx() + event.x
            root_y = self.winfo_rooty() + event.y
            self.tooltip.show("\n".join(tip_lines), root_x, root_y, self.is_dark)
        else:
            self.configure(cursor="")
            self.tooltip.hide()

    def _on_leave(self, event):
        self.configure(cursor="")
        self.tooltip.hide()

    def _on_click(self, event):
        entry = self._find_entry_at(event.x, event.y)
        if not entry:
            return
        if entry.is_unallocated:
            if self.on_unallocated_click:
                self.on_unallocated_click(entry.offset, entry.size)
        else:
            if not entry.is_system and self.on_select_entry:
                self.on_select_entry(entry)

    def _on_right_click(self, event):
        entry = self._find_entry_at(event.x, event.y)
        if not entry or entry.is_system:
            return

        menu = tk.Menu(self, tearoff=0)
        p = DARK_PALETTE if self.is_dark else LIGHT_PALETTE
        menu.configure(bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")

        if entry.is_unallocated:
            menu.add_command(
                label=f"➕ Tạo phân vùng mới tại khoảng trống {format_hex(entry.offset)}...",
                command=lambda: self.on_unallocated_click and self.on_unallocated_click(entry.offset, entry.size)
            )
        else:
            menu.add_command(
                label=f"✏️ Chỉnh sửa phân vùng '{entry.name}'...",
                command=lambda: self.on_context_action and self.on_context_action("edit", entry)
            )
            menu.add_command(
                label=f"🗑️ Xóa phân vùng '{entry.name}'",
                command=lambda: self.on_context_action and self.on_context_action("delete", entry)
            )
            menu.add_separator()
            menu.add_command(
                label=f"💾 Sao lưu phân vùng ra file .bin (Dump)...",
                command=lambda: self.on_context_action and self.on_context_action("dump", entry)
            )
            menu.add_command(
                label=f"🧹 Xóa trắng phân vùng trên chip (Erase)...",
                command=lambda: self.on_context_action and self.on_context_action("erase", entry)
            )
            menu.add_command(
                label=f"⚡ Nạp file .bin vào phân vùng '{entry.name}'...",
                command=lambda: self.on_context_action and self.on_context_action("flash_bin", entry)
            )

        menu.tk_popup(event.x_root, event.y_root)


class PartitionTabMixin:
    """
    Mixin quản lý toàn bộ giao diện và nghiệp vụ của Tab 4:
    ESP32 Partition Wizard (Phân vùng Bộ nhớ).
    """

    def create_partition_tab(self):
        """Khởi tạo toàn bộ giao diện Tab 4 bên trong self.partition_tab"""
        self.table = PartitionTable(flash_size=4 * 1024 * 1024, target_chip="esp32")
        self.display_mode = DisplayMode.DECIMAL
        self.partition_undo_stack: list[tuple[str, int, str, int]] = []
        self.partition_redo_stack: list[tuple[str, int, str, int]] = []
        self._is_populating_partition_table = False
        self._is_partition_hw_running = False

        # Nạp dữ liệu mẫu ban đầu
        default_csv = (
            "# ESP-IDF Partition Table\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1M,\n"
            "storage,  data, spiffs,  ,        2800K,\n"
        )
        self.table.from_csv(default_csv)

        # Thiết lập grid layout
        self.partition_tab.columnconfigure(0, weight=1)
        self.partition_tab.rowconfigure(2, weight=3)  # Bảng Treeview
        self.partition_tab.rowconfigure(3, weight=2)  # Khu vực sub-notebook

        # 1. Thanh điều khiển trên cùng (Header & Controls)
        header_frame = ttk.LabelFrame(self.partition_tab, text=" Cấu Hình Chip & Dung Lượng Flash ", padding=8)
        header_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(6, 4))
        self._build_partition_header(header_frame)

        # 2. Thanh nút bấm thao tác nhanh (Toolbar)
        toolbar_frame = ttk.Frame(self.partition_tab, padding=4)
        toolbar_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=2)
        self._build_partition_toolbar(toolbar_frame)

        # 3. Khung sơ đồ ổ đĩa Flash Disk Map & Bảng phân vùng
        main_paned = ttk.PanedWindow(self.partition_tab, orient="vertical")
        main_paned.grid(row=2, column=0, rowspan=2, sticky="nsew", padx=8, pady=4)

        # Nửa trên: Sơ đồ Disk Map + Bảng Treeview
        top_container = ttk.Frame(main_paned)
        top_container.columnconfigure(0, weight=1)
        top_container.rowconfigure(1, weight=1)

        # Khung Disk Map
        map_group = ttk.LabelFrame(top_container, text=" Sơ Đồ Thanh Ổ Đĩa Flash (MiniTool Partition Map) ", padding=6)
        map_group.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        map_group.columnconfigure(0, weight=1)

        self.disk_map = DiskMapCanvas(
            map_group,
            on_select_entry=self._on_disk_map_select_entry,
            on_unallocated_click=self._on_disk_map_unallocated_click,
            on_context_action=self._on_disk_map_context_action
        )
        self.disk_map.grid(row=0, column=0, sticky="ew")

        # Thống kê nhanh dung lượng
        self.lbl_flash_stats = ttk.Label(map_group, text="", font=("Segoe UI", 8, "italic"))
        self.lbl_flash_stats.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # Bảng Treeview
        table_frame = ttk.Frame(top_container)
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("name", "type", "subtype", "offset", "size", "flags", "used", "free")
        self.part_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.part_tree.heading("name", text="Tên (Name)")
        self.part_tree.heading("type", text="Kiểu (Type)")
        self.part_tree.heading("subtype", text="Phân loại (SubType)")
        self.part_tree.heading("offset", text="Offset")
        self.part_tree.heading("size", text="Dung lượng (Size)")
        self.part_tree.heading("flags", text="Cờ (Flags)")
        self.part_tree.heading("used", text="Đã dùng (%)")
        self.part_tree.heading("free", text="Còn trống")

        self.part_tree.column("name", width=120, anchor="w")
        self.part_tree.column("type", width=70, anchor="center")
        self.part_tree.column("subtype", width=95, anchor="center")
        self.part_tree.column("offset", width=140, anchor="e")
        self.part_tree.column("size", width=140, anchor="e")
        self.part_tree.column("flags", width=80, anchor="center")
        self.part_tree.column("used", width=110, anchor="center")
        self.part_tree.column("free", width=110, anchor="e")

        self.part_tree.grid(row=0, column=0, sticky="nsew")

        tree_scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self.part_tree.yview)
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        self.part_tree.configure(yscrollcommand=tree_scroll_y.set)

        self.part_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.part_tree.bind("<Double-1>", lambda e: self._action_edit_selected())
        self.part_tree.bind("<Return>", lambda e: self._action_edit_selected())
        self.part_tree.bind("<Delete>", lambda e: self._action_delete_selected())
        self.part_tree.bind("<Button-3>", self._on_tree_right_click)

        top_container.rowconfigure(1, weight=1)
        main_paned.add(top_container, weight=3)

        # Nửa dưới: Sub-notebook các tiện ích
        bottom_container = ttk.Frame(main_paned)
        self._build_partition_bottom_tabs(bottom_container)
        main_paned.add(bottom_container, weight=2)

        # Cập nhật theme và dữ liệu ban đầu
        self.disk_map.set_theme_mode(self.is_dark_mode)
        self.refresh_partition_views()

    def _build_partition_header(self, parent: ttk.LabelFrame):
        parent.columnconfigure(7, weight=1)

        # 1. Chọn Dòng Chip
        ttk.Label(parent, text="Dòng Chip:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.part_chip_var = tk.StringVar(value="ESP32 (Classic)")
        chip_names = [c.name for c in CHIP_FAMILY_DATABASE.values()]
        self.cb_part_chip = ttk.Combobox(parent, textvariable=self.part_chip_var, values=chip_names, state="readonly", width=16)
        self.cb_part_chip.grid(row=0, column=1, sticky="w", padx=(0, 16))
        self.cb_part_chip.bind("<<ComboboxSelected>>", self._on_chip_changed)

        # 2. Chọn Dung Lượng Flash
        ttk.Label(parent, text="Dung lượng Flash:").grid(row=0, column=2, sticky="w", padx=(0, 4))
        self.part_flash_var = tk.StringVar(value="4 MB (Chuẩn)")
        flash_labels = [opt[0] for opt in FLASH_SIZE_OPTIONS]
        self.cb_part_flash = ttk.Combobox(parent, textvariable=self.part_flash_var, values=flash_labels, state="readonly", width=14)
        self.cb_part_flash.grid(row=0, column=3, sticky="w", padx=(0, 16))
        self.cb_part_flash.bind("<<ComboboxSelected>>", self._on_flash_size_changed)

        # 3. Chế Độ Hiển Thị Số Liệu
        ttk.Label(parent, text="Hiển thị số liệu:").grid(row=0, column=4, sticky="w", padx=(0, 4))
        self.part_mode_var = tk.StringVar(value="Thập phân (DEC)")
        self.cb_part_mode = ttk.Combobox(
            parent,
            textvariable=self.part_mode_var,
            values=["Thập phân (DEC)", "Hệ HEX", "Song song (Dual)"],
            state="readonly",
            width=16
        )
        self.cb_part_mode.grid(row=0, column=5, sticky="w", padx=(0, 16))
        self.cb_part_mode.bind("<<ComboboxSelected>>", self._on_display_mode_changed)

    def _build_partition_toolbar(self, parent: ttk.Frame):
        # Nút thao tác phân vùng
        btn_add = ttk.Button(parent, text="➕ Thêm", command=self._action_add_partition)
        btn_add.pack(side="left", padx=2)

        btn_edit = ttk.Button(parent, text="✏️ Sửa", command=self._action_edit_selected)
        btn_edit.pack(side="left", padx=2)

        btn_del = ttk.Button(parent, text="🗑️ Xóa", command=self._action_delete_selected)
        btn_del.pack(side="left", padx=2)

        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y", padx=6, pady=2)

        btn_align = ttk.Button(parent, text="⚡ Dồn & Căn 4K/64K", command=self._action_auto_pack)
        btn_align.pack(side="left", padx=2)

        btn_preset = ttk.Button(parent, text="📋 Mẫu Chuẩn", command=self._action_presets)
        btn_preset.pack(side="left", padx=2)

        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y", padx=6, pady=2)

        btn_open = ttk.Button(parent, text="📂 Mở CSV / BIN", command=self._action_open_file)
        btn_open.pack(side="left", padx=2)

        btn_save_csv = ttk.Button(parent, text="💾 Xuất CSV", command=self._action_save_csv)
        btn_save_csv.pack(side="left", padx=2)

        btn_export_bin = ttk.Button(parent, text="📦 Xuất BIN", command=self._action_export_bin)
        btn_export_bin.pack(side="left", padx=2)

        btn_scan = ttk.Button(parent, text="🔍 Quét Dự Án", command=self._action_scan_project)
        btn_scan.pack(side="left", padx=2)

        ttk.Separator(parent, orient="vertical").pack(side="left", fill="y", padx=6, pady=2)

        self.btn_part_undo = ttk.Button(parent, text="↩️ Hoàn tác", command=self._action_undo, state="disabled")
        self.btn_part_undo.pack(side="left", padx=2)

        self.btn_part_redo = ttk.Button(parent, text="↪️ Làm lại", command=self._action_redo, state="disabled")
        self.btn_part_redo.pack(side="left", padx=2)

    def _build_partition_bottom_tabs(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        sub_notebook = ttk.Notebook(parent)
        sub_notebook.grid(row=0, column=0, sticky="nsew")

        # Tab con 1: Quy đổi nhanh & Kiểm tra hợp lệ
        tab1 = ttk.Frame(sub_notebook, padding=8)
        tab1.columnconfigure(1, weight=1)
        tab1.rowconfigure(0, weight=1)

        # Box quy đổi
        grp_conv = ttk.LabelFrame(tab1, text=" Bộ Quy Đổi Nhanh Đơn Vị ", padding=8)
        grp_conv.grid(row=0, column=0, sticky="ns", padx=(0, 8))
        grp_conv.columnconfigure(0, weight=1)

        conv_input_row = ttk.Frame(grp_conv)
        conv_input_row.pack(fill="x", pady=(0, 6))
        ttk.Label(conv_input_row, text="Nhập:").pack(side="left", padx=(0, 4))
        self.var_conv_input = tk.StringVar(value="64K")
        entry_conv = ttk.Entry(conv_input_row, textvariable=self.var_conv_input, width=18)
        entry_conv.pack(side="left", fill="x", expand=True)
        self.var_conv_input.trace_add("write", lambda *_: self._on_quick_converter_changed())

        self.lbl_conv_result = ttk.Label(grp_conv, text="", justify="left", font=("Segoe UI", 9))
        self.lbl_conv_result.pack(fill="both", expand=True)

        # Box kiểm tra lỗi ESP-IDF
        grp_val = ttk.LabelFrame(tab1, text=" Kiểm Tra Hợp Lệ Chuẩn ESP-IDF (Real-Time Rule Validator) ", padding=8)
        grp_val.grid(row=0, column=1, sticky="nsew")
        grp_val.columnconfigure(0, weight=1)
        grp_val.rowconfigure(0, weight=1)

        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        self.txt_partition_val = tk.Text(
            grp_val,
            wrap="word",
            font=("Segoe UI", 9),
            bg=p["text_bg"],
            fg=p["text_fg"],
            insertbackground=p["fg"],
            relief="solid",
            borderwidth=1
        )
        self.txt_partition_val.grid(row=0, column=0, sticky="nsew")
        val_scroll = ttk.Scrollbar(grp_val, orient="vertical", command=self.txt_partition_val.yview)
        val_scroll.grid(row=0, column=1, sticky="ns")
        self.txt_partition_val.configure(yscrollcommand=val_scroll.set)

        sub_notebook.add(tab1, text=" Quy Đổi & Kiểm Tra Lỗi ")

        # Tab con 2: Thao tác Phần cứng ESP32
        tab2 = ttk.Frame(sub_notebook, padding=8)
        tab2.columnconfigure(0, weight=1)
        tab2.rowconfigure(1, weight=1)

        hw_top = ttk.Frame(tab2)
        hw_top.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        self.lbl_hw_sync = ttk.Label(
            hw_top,
            text="Kết nối Phần cứng: Đồng bộ theo Cổng COM & Baudrate ở thanh đỉnh ứng dụng",
            font=("Segoe UI", 9, "bold")
        )
        self.lbl_hw_sync.pack(side="left", padx=(0, 10))

        btn_hw_read = ttk.Button(hw_top, text="📥 Đọc Từ Chip", command=self._hw_read_partition_table)
        btn_hw_read.pack(side="left", padx=4)

        btn_hw_flash = ttk.Button(hw_top, text="📤 Nạp Xuống Chip", command=self._hw_flash_partition_table)
        btn_hw_flash.pack(side="left", padx=4)

        btn_hw_dump = ttk.Button(hw_top, text="💾 Sao Lưu (Dump)", command=self._hw_dump_selected_partition)
        btn_hw_dump.pack(side="left", padx=4)

        btn_hw_erase = ttk.Button(hw_top, text="🧹 Xóa Trắng (Erase)", command=self._hw_erase_selected_partition)
        btn_hw_erase.pack(side="left", padx=4)

        btn_hw_write = ttk.Button(hw_top, text="⚡ Nạp File .bin Vào Phân Vùng", command=self._hw_write_selected_partition)
        btn_hw_write.pack(side="left", padx=4)

        # Log thực thi phần cứng
        log_frame = ttk.Frame(tab2)
        log_frame.grid(row=1, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.txt_partition_log = tk.Text(
            log_frame,
            wrap="word",
            font=("Consolas", 9),
            bg=p["text_bg"],
            fg=p["text_fg"],
            insertbackground=p["fg"],
            relief="solid",
            borderwidth=1
        )
        self.txt_partition_log.grid(row=0, column=0, sticky="nsew")
        hw_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.txt_partition_log.yview)
        hw_scroll.grid(row=0, column=1, sticky="ns")
        self.txt_partition_log.configure(yscrollcommand=hw_scroll.set)

        sub_notebook.add(tab2, text=" Thao Tác Phần Cứng ESP32 ")

        # Tab con 3: Sổ tay Tra cứu Phân vùng
        tab3 = ttk.Frame(sub_notebook, padding=8)
        tab3.columnconfigure(0, weight=1)
        tab3.rowconfigure(0, weight=1)

        self.txt_partition_doc = tk.Text(
            tab3,
            wrap="word",
            font=("Segoe UI", 9),
            bg=p["text_bg"],
            fg=p["text_fg"],
            insertbackground=p["fg"],
            relief="solid",
            borderwidth=1
        )
        self.txt_partition_doc.grid(row=0, column=0, sticky="nsew")
        doc_scroll = ttk.Scrollbar(tab3, orient="vertical", command=self.txt_partition_doc.yview)
        doc_scroll.grid(row=0, column=1, sticky="ns")
        self.txt_partition_doc.configure(yscrollcommand=doc_scroll.set)

        self._populate_handbook_doc()
        sub_notebook.add(tab3, text=" Sổ Tay Tra Cứu Phân Vùng ")

        self._on_quick_converter_changed()

    def _populate_handbook_doc(self):
        doc_content = (
            "SỔ TAY TRA CỨU KIẾN TRÚC PHÂN VÙNG BỘ NHỚ FLASH ESP32\n"
            "Áp dụng cho: ESP32, ESP32-S2, ESP32-S3, ESP32-C3, ESP32-C6, ESP32-P4\n"
            "--------------------------------------------------------------------------------\n\n"
            "1. BẢN ĐỒ TỔNG THỂ BỘ NHỚ FLASH ESP32 (MEMORY MAP):\n"
            "  • 0x00000 - 0x00FFF (4 KB): Vùng Header bảo lưu của ROM / Bootloader.\n"
            "  • 0x01000 - 0x07FFF (28 KB): Second-Stage Bootloader.\n"
            "  • 0x08000 - 0x08FFF (4 KB): BẢNG PHÂN VÙNG (Partition Table Sector).\n"
            "  • 0x09000 - 0x0FFFF: Dữ liệu hệ thống PHY / NVS mặc định ban đầu.\n"
            "  • 0x10000 trở đi: VÙNG CHƯƠNG TRÌNH ỨNG DỤNG (APP) - Bắt buộc căn biên 64KB (0x10000).\n"
            "  • Cuối Flash: Vùng hệ thống tệp lưu trữ (SPIFFS, LittleFS, FAT) và vùng trống (Unallocated).\n\n"
            "2. QUY TẮC CĂN CHỈNH BIÊN (ALIGNMENT RULES):\n"
            "  • Phân vùng App (factory, ota_0, ota_1...): Offset BẮT BUỘC chia hết cho 64 KB (0x10000) và >= 0x10000.\n"
            "  • Phân vùng Data (nvs, phy, spiffs, fat, littlefs...): Offset BẮT BUỘC chia hết cho 4 KB (0x1000).\n"
            "  • Dung lượng (Size): MỌI phân vùng đều phải có kích thước là bội số của sector 4 KB (0x1000).\n"
            "  • Phân vùng otadata: Bắt buộc đúng 8 KB (0x2000 = 2 sectors) để lưu trữ trạng thái boot OTA đối xứng.\n\n"
            "3. HỆ THỐNG TẬP TIN LƯU TRỮ TRÊN FLASH:\n"
            "  • LittleFS: Đề xuất hàng đầu cho hệ thống tệp nhúng, chống hỏng hóc khi mất điện đột ngột.\n"
            "  • SPIFFS: Thư viện tệp cơ bản truyền thống, phù hợp cho web tĩnh nhỏ.\n"
            "  • FATFS: Tương thích chuẩn FAT, phù hợp đọc/ghi dữ liệu lớn, log sensor hoặc chia sẻ thẻ nhớ SD.\n\n"
            "4. CÁC PHÍM TẮT THAO TÁC:\n"
            "  • Double-Click / Enter: Chỉnh sửa phân vùng đang chọn.\n"
            "  • Delete: Xóa phân vùng đang chọn.\n"
            "  • Chuột phải trên sơ đồ MiniTool: Mở menu ngữ cảnh nhanh (Sửa, Xóa, Dump, Erase, Flash .bin).\n"
            "  • Click vào khoảng trống Unallocated: Tạo phân vùng mới vừa vặn trong khe trống đó.\n"
        )
        self.txt_partition_doc.delete("1.0", "end")
        self.txt_partition_doc.insert("1.0", doc_content)
        self.txt_partition_doc.configure(state="disabled")

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

    def refresh_partition_views(self):
        """Làm mới toàn bộ giao diện: Disk Map, Bảng Treeview, Thống kê, và Kiểm tra lỗi"""
        # 1. Cập nhật Treeview
        selected_iid = self.part_tree.selection()
        selected_entry_name = None
        if selected_iid:
            selected_entry_name = self.part_tree.item(selected_iid[0], "values")[0]

        for item in self.part_tree.get_children():
            self.part_tree.delete(item)

        current_selected_entry = None
        for idx, e in enumerate(self.table.entries):
            used_str = f"{format_bytes_human(e.used_size)} ({e.usage_percent:.1f}%)" if e.used_size > 0 else "--"
            free_str = format_value(e.free_size, self.display_mode, is_size=True) if e.used_size > 0 else "--"

            iid = self.part_tree.insert("", "end", values=(
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
                self.part_tree.selection_set(iid)
                current_selected_entry = e

        # 2. Cập nhật Sơ đồ MiniTool Disk Map
        layout = self.table.get_layout_with_unallocated()
        self.disk_map.set_data(layout, self.table.flash_size, self.display_mode, current_selected_entry)

        # 3. Cập nhật Thống kê Flash
        total_allocated = sum(e.size for e in self.table.entries)
        unallocated_size = max(0, self.table.flash_size - (self.table.part_table_offset + PARTITION_TABLE_SIZE_DEFAULT) - total_allocated)
        flash_human = format_bytes_human(self.table.flash_size, compact=True)
        alloc_human = format_bytes_human(total_allocated, compact=True)
        unalloc_human = format_bytes_human(unallocated_size, compact=True)
        self.lbl_flash_stats.configure(
            text=f"Dung lượng Flash: {flash_human} | Đã phân bổ: {alloc_human} ({len(self.table.entries)} phân vùng) | Còn trống chưa cấp phát: {unalloc_human}"
        )

        # 4. Kiểm tra hợp lệ ESP-IDF
        errors = self.table.validate()
        self.txt_partition_val.configure(state="normal")
        self.txt_partition_val.delete("1.0", "end")
        if not errors:
            self.txt_partition_val.insert("1.0", "✅ BẢNG PHÂN VÙNG HOÀN TOÀN HỢP LỆ THEO CHUẨN ESP-IDF!\n\n")
            self.txt_partition_val.insert("end", "• Không có xung đột hoặc trùng lặp tên phân vùng.\n")
            self.txt_partition_val.insert("end", "• Toàn bộ Offset phân vùng App đã căn lề đúng chuẩn sector 64KB (0x10000).\n")
            self.txt_partition_val.insert("end", "• Toàn bộ Offset và Size phân vùng Data đã căn lề đúng chuẩn sector 4KB (0x1000).\n")
            self.txt_partition_val.insert("end", "• Bảng phân vùng không bị đè vào vùng cấm hệ thống hoặc vượt quá dung lượng chip Flash.\n")
        else:
            self.txt_partition_val.insert("1.0", f"⚠️ PHÁT HIỆN {len(errors)} CẢNH BÁO / LỖI BẢNG PHÂN VÙNG:\n\n")
            for err in errors:
                self.txt_partition_val.insert("end", f"  ❌ {err}\n")
            self.txt_partition_val.insert("end", "\n👉 Gợi ý: Bấm nút '⚡ Dồn & Căn 4K/64K' trên thanh công cụ để tự động sửa toàn bộ lỗi căn biên!")
        self.txt_partition_val.configure(state="disabled")

    def _on_chip_changed(self, event=None):
        name = self.part_chip_var.get()
        for cid, info in CHIP_FAMILY_DATABASE.items():
            if info.name == name:
                self._push_partition_undo_state()
                self.table.target_chip = cid
                self.table.bootloader_offset = info.bootloader_offset
                self.refresh_partition_views()
                break

    def _on_flash_size_changed(self, event=None):
        name = self.part_flash_var.get()
        for opt_label, sz in FLASH_SIZE_OPTIONS:
            if opt_label == name:
                self._push_partition_undo_state()
                self.table.flash_size = sz
                self.refresh_partition_views()
                break

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
        if not selected_iid:
            self.disk_map.selected_entry = None
            self.disk_map.redraw()
            return
        name = self.part_tree.item(selected_iid[0], "values")[0]
        for e in self.table.entries:
            if e.name == name:
                self.disk_map.selected_entry = e
                self.disk_map.redraw()
                break

    def _on_disk_map_select_entry(self, entry: PartitionEntry):
        for item in self.part_tree.get_children():
            val = self.part_tree.item(item, "values")
            if val and val[0] == entry.name:
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

    def _on_disk_map_context_action(self, action: str, entry: PartitionEntry):
        self._on_disk_map_select_entry(entry)
        if action == "edit":
            self._action_edit_selected()
        elif action == "delete":
            self._action_delete_selected()
        elif action == "dump":
            self._hw_dump_selected_partition()
        elif action == "erase":
            self._hw_erase_selected_partition()
        elif action == "flash_bin":
            self._hw_write_selected_partition()

    def _on_tree_right_click(self, event):
        row_id = self.part_tree.identify_row(event.y)
        if row_id:
            self.part_tree.selection_set(row_id)
            entry_name = self.part_tree.item(row_id, "values")[0]
            entry = next((e for e in self.table.entries if e.name == entry_name), None)
            if entry:
                self.disk_map._on_right_click(event)

    def _action_add_partition(self, suggested_offset: int | None = None):
        if suggested_offset is None:
            if self.table.entries:
                last = max(e.end_offset for e in self.table.entries)
                suggested_offset = align_up(last, 0x1000)
            else:
                suggested_offset = 0x10000

        dlg = PartitionEditDialog(self.root, entry=None, suggested_offset=suggested_offset, is_dark_mode=self.is_dark_mode)
        if dlg.result:
            self._push_partition_undo_state()
            self.table.add_entry(dlg.result)
            self.refresh_partition_views()
            self.set_status(f"Đã thêm phân vùng '{dlg.result.name}'.")

    def _action_edit_selected(self):
        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần chỉnh sửa.", parent=self.root)
            return

        name = self.part_tree.item(selected_iid[0], "values")[0]
        idx = next((i for i, e in enumerate(self.table.entries) if e.name == name), None)
        if idx is None:
            return

        entry = self.table.entries[idx]
        dlg = PartitionEditDialog(self.root, entry=entry, is_dark_mode=self.is_dark_mode)
        if dlg.result:
            self._push_partition_undo_state()
            self.table.entries[idx] = dlg.result
            self.refresh_partition_views()
            self.set_status(f"Đã cập nhật phân vùng '{dlg.result.name}'.")

    def _action_delete_selected(self):
        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần xóa.", parent=self.root)
            return

        name = self.part_tree.item(selected_iid[0], "values")[0]
        if messagebox.askyesno("Xác nhận xóa", f"Bạn có chắc chắn muốn xóa phân vùng '{name}' không?", parent=self.root):
            self._push_partition_undo_state()
            self.table.entries = [e for e in self.table.entries if e.name != name]
            self.refresh_partition_views()
            self.set_status(f"Đã xóa phân vùng '{name}'.")

    def _action_auto_pack(self):
        """Tự động dồn toàn bộ phân vùng liên tiếp và căn lề chuẩn 4K/64K"""
        if not self.table.entries:
            return
        self._push_partition_undo_state()
        self.table.auto_pack_and_align()
        self.refresh_partition_views()
        self.set_status("Đã dồn biên và căn chỉnh toàn bộ phân vùng theo chuẩn 4KB / 64KB.")
        messagebox.showinfo("Thành công", "Đã tự động tính toán lại Offset nối tiếp nhau không bị chồng lấn và căn biên chuẩn 4KB (cho Data) và 64KB (cho App)!", parent=self.root)

    def _action_presets(self):
        dlg = PresetSelectorDialog(self.root, is_dark_mode=self.is_dark_mode)
        if dlg.result:
            self._push_partition_undo_state()
            self.table.flash_size = dlg.result["flash_size"]
            self.table.target_chip = dlg.result["chip"]
            self.table.from_csv(dlg.result["csv"])

            # Cập nhật combo chip & flash
            for cid, info in CHIP_FAMILY_DATABASE.items():
                if cid == dlg.result["chip"]:
                    self.part_chip_var.set(info.name)
                    break
            for lbl, sz in FLASH_SIZE_OPTIONS:
                if sz == dlg.result["flash_size"]:
                    self.part_flash_var.set(lbl)
                    break

            self.refresh_partition_views()
            self.set_status(f"Đã nạp mẫu: {dlg.result['name']}")

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

            self.refresh_partition_views()
        except Exception as e:
            messagebox.showerror("Lỗi mở file", f"Không thể đọc file phân vùng:\n{e}", parent=self.root)

    def _action_save_csv(self):
        path = filedialog.asksaveasfilename(
            title="Lưu file CSV bảng phân vùng",
            defaultextension=".csv",
            initialfile="partitions.csv",
            filetypes=[("CSV Files (*.csv)", "*.csv"), ("All Files (*.*)", "*.*")],
            parent=self.root
        )
        if not path:
            return

        try:
            csv_content = self.table.to_csv()
            with open(path, "w", encoding="utf-8") as f:
                f.write(csv_content)
            self.set_status(f"Đã lưu thành công: {os.path.basename(path)}")
            messagebox.showinfo("Thành công", f"Đã xuất bảng phân vùng ra file CSV chuẩn ESP-IDF:\n{path}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Lỗi lưu file", f"Không thể lưu file CSV:\n{e}", parent=self.root)

    def _action_export_bin(self):
        errors = self.table.validate()
        if errors:
            ans = messagebox.askyesno(
                "Cảnh báo lỗi phân vùng",
                f"Bảng phân vùng hiện đang có {len(errors)} cảnh báo/lỗi chuẩn ESP-IDF.\nBạn có chắc chắn muốn xuất ra file nhị phân không?",
                parent=self.root
            )
            if not ans:
                return

        path = filedialog.asksaveasfilename(
            title="Xuất file BIN bảng phân vùng",
            defaultextension=".bin",
            initialfile="partition-table.bin",
            filetypes=[("Binary Files (*.bin)", "*.bin"), ("All Files (*.*)", "*.*")],
            parent=self.root
        )
        if not path:
            return

        try:
            bin_data = self.table.to_binary()
            with open(path, "wb") as f:
                f.write(bin_data)
            self.set_status(f"Đã biên dịch BIN thành công: {os.path.basename(path)} ({len(bin_data)} Bytes)")
            messagebox.showinfo("Thành công", f"Đã biên dịch bảng phân vùng sang file nhị phân 32-byte kèm MD5 Checksum:\n{path}", parent=self.root)
        except Exception as e:
            messagebox.showerror("Lỗi biên dịch BIN", f"Không thể xuất file nhị phân:\n{e}", parent=self.root)

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

        # Cập nhật giao diện
        for cid, info in CHIP_FAMILY_DATABASE.items():
            if cid == res.target_chip:
                self.part_chip_var.set(info.name)
                break
        for lbl, sz in FLASH_SIZE_OPTIONS:
            if sz == res.flash_size:
                self.part_flash_var.set(lbl)
                break

        self.refresh_partition_views()
        self.set_status(f"Đã quét thành công dự án: {res.project_name}")
        messagebox.showinfo("Quét dự án thành công", f"Đã trích xuất cấu hình phân vùng từ dự án: {res.project_name}\nTarget: {res.target_chip.upper()} | Flash: {format_bytes_human(res.flash_size, compact=True)}", parent=self.root)

    def _on_quick_converter_changed(self):
        val_str = self.var_conv_input.get().strip()
        if not val_str:
            self.lbl_conv_result.configure(text="")
            return

        try:
            val = parse_size_or_offset(val_str)
            lines = [
                f"• Bytes: {val:,} B",
                f"• Kilobytes: {val / 1024:,.2f} KB",
                f"• Megabytes: {val / (1024 * 1024):,.3f} MB",
                f"• Hệ HEX: {format_hex(val)}",
                f"• Số Sector (4KB): {sector_count(val)} sectors",
                f"• Căn lề 4KB (Data): {'ĐÚNG' if val % 0x1000 == 0 else 'SAI'}",
                f"• Căn lề 64KB (App): {'ĐÚNG' if val % 0x10000 == 0 else 'SAI'}"
            ]
            self.lbl_conv_result.configure(text="\n".join(lines))
        except Exception:
            self.lbl_conv_result.configure(text="⚠️ Vui lòng nhập đúng cú pháp (VD: 64K, 1M, 0x10000, 65536)")

    # =========================================================================
    # THAO TÁC PHẦN CỨNG ESP32 (ĐỒNG BỘ CỔNG COM VÀ ESPTOOL AN TOÀN)
    # =========================================================================

    def _log_partition_hw(self, text: str):
        self.txt_partition_log.insert("end", f"{text}\n")
        self.txt_partition_log.see("end")

    def _prepare_hardware_port(self) -> tuple[str, int, str] | None:
        """Đảm bảo cổng COM hợp lệ và tạm ngắt Serial Monitor nếu đang kết nối"""
        port = self.port_cb.get().strip()
        if not port or port == "Không có cổng COM":
            messagebox.showerror("Chưa chọn cổng COM", "Vui lòng chọn cổng COM trên thanh điều khiển trước khi thao tác phần cứng.", parent=self.root)
            return None

        baud_str = self.baud_cb.get().strip()
        baud = int(baud_str) if baud_str.isdigit() else 460800
        chip_target = self.table.target_chip

        # Ngắt Serial Monitor an toàn nếu đang mở
        if getattr(self, "serial_connection", None) and self.serial_connection.is_open:
            self.on_serial_disconnect()
            self._log_partition_hw(">> [HỆ THỐNG] Đã tự động tạm ngắt Serial Monitor để thực thi tác vụ esptool.")

        return (port, baud, chip_target)

    def _hw_read_partition_table(self):
        """Đọc 4KB tại 0x8000 từ chip ESP32"""
        if self._is_partition_hw_running:
            return
        hw_info = self._prepare_hardware_port()
        if not hw_info:
            return
        port, baud, chip = hw_info

        def worker():
            self._is_partition_hw_running = True
            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                self.root.after(0, self._log_partition_hw, f"\n=== BẮT ĐẦU ĐỌC BẢNG PHÂN VÙNG TỪ CHIP QUA {port} ===")
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['read_flash', '0x8000', '0x1000', tmp_path])

                def on_stream(line):
                    self.root.after(0, self._log_partition_hw, f"  {line}")

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res) and os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
                    with open(tmp_path, "rb") as f:
                        data = f.read()

                    def update_ui():
                        self._push_partition_undo_state()
                        self.table.from_binary(data)
                        self.refresh_partition_views()
                        self.set_status("Đã đọc và giải mã bảng phân vùng từ ESP32 thành công!", "success")
                        self._log_partition_hw(">>> ĐỌC BẢNG PHÂN VÙNG TỪ CHIP THÀNH CÔNG!")
                        messagebox.showinfo("Thành công", f"Đã đọc và nạp thành công {len(self.table.entries)} phân vùng trực tiếp từ chip ESP32!", parent=self.root)

                    self.root.after(0, update_ui)
                else:
                    self.root.after(0, lambda: self.set_status("Lỗi đọc bảng phân vùng từ chip!", "error"))
                    self.root.after(0, self._log_partition_hw, ">>> [LỖI] Không thể đọc dữ liệu phân vùng từ ESP32.")
            except Exception as ex:
                self.root.after(0, self._log_partition_hw, f">>> [NGOẠI LỆ] {ex}")
            finally:
                if os.path.isfile(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                self._is_partition_hw_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _hw_flash_partition_table(self):
        """Nạp bảng phân vùng hiện tại xuống 0x8000 của chip"""
        if self._is_partition_hw_running:
            return
        hw_info = self._prepare_hardware_port()
        if not hw_info:
            return
        port, baud, chip = hw_info

        errors = self.table.validate()
        if errors:
            ans = messagebox.askyesno(
                "Cảnh báo tính hợp lệ",
                f"Bảng phân vùng có {len(errors)} lỗi/cảnh báo. Bạn có chắc chắn muốn nạp xuống chip?",
                parent=self.root
            )
            if not ans:
                return

        def worker():
            self._is_partition_hw_running = True
            with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
                tmp_path = tmp.name

            try:
                bin_data = self.table.to_binary()
                with open(tmp_path, "wb") as f:
                    f.write(bin_data)

                self.root.after(0, self._log_partition_hw, f"\n=== NẠP BẢNG PHÂN VÙNG MỚI XUỐNG 0x8000 QUA {port} ===")
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['write_flash', '0x8000', tmp_path])

                def on_stream(line):
                    self.root.after(0, self._log_partition_hw, f"  {line}")

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res):
                    self.root.after(0, lambda: self.set_status("Đã nạp Bảng phân vùng xuống chip thành công!", "success"))
                    self.root.after(0, self._log_partition_hw, ">>> NẠP BẢNG PHÂN VÙNG XUỐNG CHIP THÀNH CÔNG!")
                    self.root.after(0, lambda: messagebox.showinfo("Thành công", "Đã nạp Bảng phân vùng mới xuống ESP32 thành công!", parent=self.root))
                else:
                    self.root.after(0, lambda: self.set_status("Lỗi nạp bảng phân vùng xuống chip!", "error"))
                    self.root.after(0, self._log_partition_hw, ">>> [LỖI] Không thể ghi bảng phân vùng xuống chip.")
            except Exception as ex:
                self.root.after(0, self._log_partition_hw, f">>> [NGOẠI LỆ] {ex}")
            finally:
                if os.path.isfile(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                self._is_partition_hw_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _hw_dump_selected_partition(self):
        """Sao lưu một phân vùng cụ thể ra file .bin trên máy tính"""
        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần sao lưu (Dump).", parent=self.root)
            return

        name = self.part_tree.item(selected_iid[0], "values")[0]
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
            try:
                self.root.after(0, self._log_partition_hw, f"\n=== SAO LƯU PHÂN VÙNG '{entry.name}' (0x{entry.offset:X}, {entry.size:,} B) VÀO {save_path} ===")
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['read_flash', format_hex(entry.offset), format_hex(entry.size), save_path])

                def on_stream(line):
                    self.root.after(0, self._log_partition_hw, f"  {line}")

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res):
                    self.root.after(0, lambda: self.set_status(f"Đã sao lưu phân vùng '{entry.name}' thành công!", "success"))
                    self.root.after(0, self._log_partition_hw, f">>> SAO LƯU THÀNH CÔNG: {save_path}")
                    self.root.after(0, lambda: messagebox.showinfo("Thành công", f"Đã sao lưu phân vùng '{entry.name}' ra file .bin thành công:\n{save_path}", parent=self.root))
                else:
                    self.root.after(0, lambda: self.set_status(f"Lỗi sao lưu phân vùng '{entry.name}'!", "error"))
                    self.root.after(0, self._log_partition_hw, f">>> [LỖI] Không thể đọc phân vùng '{entry.name}' từ chip.")
            except Exception as ex:
                self.root.after(0, self._log_partition_hw, f">>> [NGOẠI LỆ] {ex}")
            finally:
                self._is_partition_hw_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _hw_erase_selected_partition(self):
        """Xóa trắng (erase-region) một phân vùng cụ thể trên chip"""
        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần xóa trắng (Erase).", parent=self.root)
            return

        name = self.part_tree.item(selected_iid[0], "values")[0]
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
            try:
                self.root.after(0, self._log_partition_hw, f"\n=== XÓA TRẮNG VÙNG NHỚ PHÂN VÙNG '{entry.name}' (0x{entry.offset:X}, {entry.size:,} B) ===")
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['erase-region', format_hex(entry.offset), format_hex(entry.size)])

                def on_stream(line):
                    self.root.after(0, self._log_partition_hw, f"  {line}")

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res):
                    self.root.after(0, lambda: self.set_status(f"Đã xóa trắng phân vùng '{entry.name}' thành công!", "success"))
                    self.root.after(0, self._log_partition_hw, f">>> ĐÃ XÓA TRẮNG THÀNH CÔNG PHÂN VÙNG '{entry.name}'!")
                    self.root.after(0, lambda: messagebox.showinfo("Thành công", f"Đã xóa trắng vùng nhớ phân vùng '{entry.name}' thành công!", parent=self.root))
                else:
                    self.root.after(0, lambda: self.set_status(f"Lỗi xóa phân vùng '{entry.name}'!", "error"))
                    self.root.after(0, self._log_partition_hw, f">>> [LỖI] Không thể xóa phân vùng '{entry.name}'.")
            except Exception as ex:
                self.root.after(0, self._log_partition_hw, f">>> [NGOẠI LỆ] {ex}")
            finally:
                self._is_partition_hw_running = False

        threading.Thread(target=worker, daemon=True).start()

    def _hw_write_selected_partition(self):
        """Nạp file .bin vào phân vùng đang chọn"""
        selected_iid = self.part_tree.selection()
        if not selected_iid:
            messagebox.showinfo("Chưa chọn", "Vui lòng chọn phân vùng cần nạp file .bin.", parent=self.root)
            return

        name = self.part_tree.item(selected_iid[0], "values")[0]
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
            try:
                self.root.after(0, self._log_partition_hw, f"\n=== NẠP FILE {os.path.basename(bin_path)} VÀO PHÂN VÙNG '{entry.name}' TẠI 0x{entry.offset:X} ===")
                args = ['--port', port, '--baud', str(baud)]
                if chip and chip != "auto":
                    args.extend(['--chip', chip])
                args.extend(['write-flash', format_hex(entry.offset), bin_path])

                def on_stream(line):
                    self.root.after(0, self._log_partition_hw, f"  {line}")

                res = run_esptool_command(args, progress_callback=on_stream)
                if esptool_command_succeeded(res):
                    self.root.after(0, lambda: self.set_status(f"Nạp file vào phân vùng '{entry.name}' thành công!", "success"))
                    self.root.after(0, self._log_partition_hw, f">>> NẠP FILE THÀNH CÔNG VÀO PHÂN VÙNG '{entry.name}'!")
                    self.root.after(0, lambda: messagebox.showinfo("Thành công", f"Đã nạp file {os.path.basename(bin_path)} vào phân vùng '{entry.name}' thành công!", parent=self.root))
                else:
                    self.root.after(0, lambda: self.set_status(f"Lỗi nạp file vào phân vùng '{entry.name}'!", "error"))
                    self.root.after(0, self._log_partition_hw, f">>> [LỖI] Không thể nạp file vào phân vùng '{entry.name}'.")
            except Exception as ex:
                self.root.after(0, self._log_partition_hw, f">>> [NGOẠI LỆ] {ex}")
            finally:
                self._is_partition_hw_running = False

        threading.Thread(target=worker, daemon=True).start()
