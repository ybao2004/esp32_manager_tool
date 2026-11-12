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
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

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
    PartitionEditDialog, PresetSelectorDialog, SizeInputDialog
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

        frame = tk.Frame(tw, background=p["border"], padx=1, pady=1)
        frame.pack()

        lbl = tk.Label(
            frame,
            text=text,
            justify="left",
            background=p["text_bg"],
            foreground=p["text_fg"],
            font=("Segoe UI", 9),
            padx=10,
            pady=8
        )
        lbl.pack()

        tw.update_idletasks()
        req_w = tw.winfo_reqwidth()
        req_h = tw.winfo_reqheight()
        screen_w = tw.winfo_screenwidth()
        screen_h = tw.winfo_screenheight()

        pos_x = x + 14
        pos_y = y + 14
        if pos_x + req_w > screen_w - 10:
            pos_x = max(10, x - req_w - 10)
        if pos_y + req_h > screen_h - 10:
            pos_y = max(10, y - req_h - 10)

        tw.wm_geometry(f"+{pos_x}+{pos_y}")

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
        self.bind("<Double-1>", self._on_double_click)
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

    def _build_detailed_tooltip_text(self, entry: PartitionEntry) -> str:
        lines = []
        if entry.is_unallocated:
            lines.append("=" * 52)
            lines.append("【 KHOẢNG TRỐNG CHƯA PHÂN BỔ (UNALLOCATED GAP) 】")
            lines.append("=" * 52)
            lines.append(f"• Địa chỉ (Offset): {format_hex(entry.offset)} -> {format_hex(entry.end_offset)}")
            lines.append(f"• Dung lượng trống: {format_bytes_human(entry.size)} ({entry.size:,} Bytes)")
            lines.append(f"• Số Sector vật lý: {sector_count(entry.size)} sectors (mỗi sector 4KB)")
            lines.append("-" * 52)
            lines.append("📌 MỤC ĐÍCH SỬ DỤNG:")
            lines.append("Vùng nhớ Flash vật lý còn trống, chưa được cấp phát cho phân vùng nào.")
            lines.append("Có thể tận dụng để mở rộng phân vùng hoặc tạo phân vùng mới (LittleFS, SPIFFS, OTA).")
            lines.append("-" * 52)
            lines.append("💡 GỢI Ý THAO TÁC:")
            lines.append("👉 Bấm chuột trái vào khối này để tạo phân vùng mới vừa vặn.")
            return "\n".join(lines)

        if entry.is_system:
            lines.append("=" * 52)
            if entry.type_str == "bootloader":
                lines.append(f"【 PHÂN VÙNG HỆ THỐNG: {entry.name.upper()} 】")
                lines.append("=" * 52)
                lines.append(f"• Vị trí Offset: {format_hex(entry.offset)} | Kích thước: {format_bytes_human(entry.size)} ({entry.size:,} B)")
                lines.append("-" * 52)
                lines.append("📌 MỤC ĐÍCH SỬ DỤNG:")
                lines.append("Chương trình Second-Stage Bootloader do Espressif quản lý.")
                lines.append("Khởi tạo phần cứng (GPIO/PLL/Flash), đọc bảng phân vùng tại 0x8000 và nạp App.")
                lines.append("-" * 52)
                lines.append("💡 KHUYẾN NGHỊ DUNG LƯỢNG:")
                lines.append("• Mặc định: 28 KB - 32 KB (đặt tại 0x1000 trên ESP32 hoặc 0x0 trên S3/C3).")
                lines.append("• Phân vùng cố định, không được chỉnh sửa hoặc xóa.")
            else:
                lines.append(f"【 BẢNG PHÂN VÙNG HỆ THỐNG (PARTITION TABLE) 】")
                lines.append("=" * 52)
                lines.append(f"• Vị trí Offset: {format_hex(entry.offset)} | Kích thước: {format_bytes_human(entry.size)} ({entry.size:,} B)")
                lines.append("-" * 52)
                lines.append("📌 MỤC ĐÍCH SỬ DỤNG:")
                lines.append("Bản đồ lưu trữ toàn bộ các phân vùng của chip Flash.")
                lines.append("Chứa cấu trúc 32-byte định nghĩa Type, SubType, Offset, Size và MD5 Checksum.")
                lines.append("-" * 52)
                lines.append("💡 KHUYẾN NGHỊ DUNG LƯỢNG:")
                lines.append("• Chuẩn ESP-IDF: Cố định đúng 1 sector 4 KB (0x1000) tại offset 0x8000.")
            return "\n".join(lines)

        # Phân vùng người dùng
        lines.append("=" * 52)
        lines.append(f"【 PHÂN VÙNG: {entry.name} 】 (Type: {entry.type_str} | SubType: {entry.subtype_str})")
        lines.append("=" * 52)
        align_rule = "Căn biên 64 KB (0x10000)" if entry.type_str == "app" else "Căn biên 4 KB (0x1000)"
        lines.append(f"• Offset: {format_hex(entry.offset)} ({entry.offset:,} B) | {align_rule}")
        lines.append(f"• Dung lượng: {format_bytes_human(entry.size)} ({entry.size:,} B) | {sector_count(entry.size)} Sectors (4KB)")
        if entry.used_size > 0:
            lines.append(f"• Firmware chiếm: {format_bytes_human(entry.used_size)} ({entry.usage_percent:.1f}%) | Còn trống: {format_bytes_human(entry.free_size)}")
        if entry.flags_str:
            lines.append(f"• Cờ bảo mật: {entry.flags_str}")
        lines.append("-" * 52)

        t = entry.type_str.lower()
        st = entry.subtype_str.lower()

        purpose = ""
        rec_min = ""
        rec_typical = ""
        rec_max = ""

        if st == "nvs":
            purpose = (
                "Non-Volatile Storage. Lưu trữ cấu hình Wi-Fi (SSID, Password), khóa BLE,\n"
                "dữ liệu hiệu chuẩn RF (PHY calibration) và các biến Key-Value tùy biến.\n"
                "Dữ liệu được lưu vĩnh viễn, không bị mất khi reset hoặc tắt nguồn."
            )
            rec_min = "12 KB (0x3000 = 3 sectors)"
            rec_typical = "16 KB - 24 KB (0x4000 - 0x6000)"
            rec_max = "64 KB - 128 KB (nếu ứng dụng ghi nhiều tham số/biến)"
        elif st in ("ota", "otadata"):
            purpose = (
                "Lưu trữ chỉ mục và trạng thái nạp firmware qua mạng (OTA Data).\n"
                "Bootloader đọc vùng này để biết khe ota_0 hay ota_1 đang là bản mới nhất,\n"
                "hỗ trợ tự động Rollback về bản firmware cũ nếu bản mới gặp lỗi boot loop."
            )
            rec_min = "Bắt buộc cố định đúng 8 KB (0x2000 = 2 sectors) theo chuẩn ESP-IDF"
            rec_typical = "8 KB (0x2000)"
            rec_max = "8 KB (0x2000)"
        elif st == "factory":
            purpose = (
                "Bản firmware ứng dụng chính gốc xuất xưởng (Default Factory App).\n"
                "Bootloader sẽ nạp và thực thi mã tại phân vùng này khi khởi động\n"
                "(nếu cấu hình không dùng cơ chế chuyển đổi khe nạp OTA)."
            )
            rec_min = "1 MB (0x100000)"
            rec_typical = "1.5 MB - 2 MB (tùy dung lượng thư viện Wi-Fi/BLE/Web)"
            rec_max = "3 MB+ (phụ thuộc kích thước Flash)"
        elif st.startswith("ota_"):
            purpose = (
                f"Khe firmware cập nhật qua mạng ({st.upper()}).\n"
                "Hỗ trợ cơ chế nạp Over-The-Air xoay vòng hai khe (Dual-bank Ping-Pong):\n"
                "khi chip đang chạy ở khe này, firmware mới được tải vào khe kia\n"
                "và hoán đổi an toàn mà không làm gián đoạn thiết bị."
            )
            rec_min = "1 MB (0x100000)"
            rec_typical = "1.5 MB - 2 MB (các khe OTA phải có dung lượng bằng nhau)"
            rec_max = "3 MB+ (phụ thuộc kích thước Flash)"
        elif st in ("spiffs", "littlefs", "fat"):
            fs_name = st.upper()
            purpose = (
                f"Hệ thống tập tin nhúng ({fs_name}).\n"
                "Dùng lưu trữ file giao diện Web (HTML, CSS, JS), file âm thanh, ảnh,\n"
                "chứng chỉ SSL/TLS hoặc ghi nhận dữ liệu cảm biến (Data logging).\n"
                "Khuyên dùng LittleFS để chống hỏng hóc file khi mất điện đột ngột."
            )
            rec_min = "64 KB (0x10000)"
            rec_typical = "256 KB - 1.5 MB"
            rec_max = "Toàn bộ phần dung lượng còn lại của chip Flash"
        elif st == "phy":
            purpose = (
                "Chứa bảng thông số hiệu chuẩn tầng vật lý vô tuyến RF/Wi-Fi/Bluetooth,\n"
                "giúp vi điều khiển đạt công suất phát sóng và độ nhạy thu tối ưu."
            )
            rec_min = "Cố định 4 KB (0x1000 = 1 sector)"
            rec_typical = "4 KB (0x1000)"
            rec_max = "4 KB (0x1000)"
        elif st == "coredump":
            purpose = (
                "Lưu vết ngăn xếp (Stack & Registers Dump) của CPU khi hệ thống gặp lỗi\n"
                "sập chương trình (Panic crash), phục vụ phân tích gỡ lỗi sau khi khởi động lại."
            )
            rec_min = "64 KB (0x10000)"
            rec_typical = "64 KB (0x10000)"
            rec_max = "64 KB (0x10000)"
        elif st == "nvs_keys":
            purpose = (
                "Lưu khóa mã hóa dùng để giải mã phân vùng NVS khi kích hoạt tính năng\n"
                "Flash Encryption và NVS Encryption phần cứng."
            )
            rec_min = "Cố định 4 KB (0x1000 = 1 sector)"
            rec_typical = "4 KB (0x1000)"
            rec_max = "4 KB (0x1000)"
        elif st == "test":
            purpose = "Phân vùng firmware dành riêng cho kiểm thử chức năng xuất xưởng (Factory Test Mode)."
            rec_min = "512 KB (0x80000)"
            rec_typical = "1 MB (0x100000)"
            rec_max = "2 MB"
        else:
            purpose = f"Phân vùng tùy chỉnh kiểu '{t}' / subtype '{st}' do người dùng tự định nghĩa."
            rec_min = "4 KB (0x1000)"
            rec_typical = "Tùy nhu cầu sử dụng"
            rec_max = "Tùy dung lượng Flash còn lại"

        lines.append("📌 MỤC ĐÍCH SỬ DỤNG:")
        lines.append(purpose)
        lines.append("-" * 52)
        lines.append("💡 KHUYẾN NGHỊ DUNG LƯỢNG:")
        lines.append(f"• Tối thiểu: {rec_min}")
        lines.append(f"• Thông thường: {rec_typical}")
        lines.append(f"• Tối đa: {rec_max}")
        lines.append("-" * 52)
        lines.append("👉 Click chuột trái để chọn dòng | Chuột phải để chỉnh sửa nhanh")

        return "\n".join(lines)

    def _on_motion(self, event):
        entry = self._find_entry_at(event.x, event.y)
        if entry:
            self.configure(cursor="hand2")
            tip_text = self._build_detailed_tooltip_text(entry)
            root_x = self.winfo_rootx() + event.x
            root_y = self.winfo_rooty() + event.y
            self.tooltip.show(tip_text, root_x, root_y, self.is_dark)
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

    def _on_double_click(self, event):
        entry = self._find_entry_at(event.x, event.y)
        if not entry:
            return
        if entry.is_unallocated:
            if self.on_unallocated_click:
                self.on_unallocated_click(entry.offset, entry.size)
        else:
            if not entry.is_system:
                if self.on_select_entry:
                    self.on_select_entry(entry)
                if self.on_context_action:
                    self.on_context_action("edit", entry)

    def _on_right_click(self, event):
        entry = self._find_entry_at(event.x, event.y)
        if not entry or entry.is_system:
            return

        if entry.is_unallocated:
            if self.on_unallocated_click:
                self.on_unallocated_click(entry.offset, entry.size)
            return

        if self.on_select_entry:
            self.on_select_entry(entry)

        if self.on_context_action:
            self.on_context_action("full_context_menu", entry, event)


class PartitionHandbookDialog(tk.Toplevel):
    """Hộp thoại hướng dẫn & sổ tay tra cứu phân vùng ESP32"""
    def __init__(self, parent, is_dark_mode: bool = False):
        super().__init__(parent)
        self.title("Hướng Dẫn & Sổ Tay Tra Cứu Phân Vùng ESP32")
        self.geometry("800x580")
        self.minsize(620, 420)
        self.transient(parent)
        self.grab_set()

        p = DARK_PALETTE if is_dark_mode else LIGHT_PALETTE
        self.configure(bg=p["bg"])

        txt_frame = ttk.Frame(self, padding=10)
        txt_frame.pack(fill="both", expand=True)

        txt = tk.Text(
            txt_frame,
            wrap="word",
            font=("Segoe UI", 10),
            bg=p["text_bg"],
            fg=p["text_fg"],
            relief="solid",
            borderwidth=1,
            padx=12,
            pady=10
        )
        txt.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        scroll.pack(side="right", fill="y")
        txt.configure(yscrollcommand=scroll.set)

        doc_content = (
            "HƯỚNG DẪN SỬ DỤNG & TRA CỨU PHÂN VÙNG BỘ NHỚ FLASH ESP32\n"
            "Áp dụng cho: ESP32, ESP32-S2, ESP32-S3, ESP32-C2, ESP32-C3, ESP32-C6, ESP32-H2, ESP32-P4\n"
            "================================================================================\n\n"
            "1. CÁC THAO TÁC CƠ BẢN TRÊN BẢNG PHÂN VÙNG:\n"
            "  • Thêm phân vùng: Bấm nút [+] ở dòng trống cuối bảng để chèn phân vùng mới.\n"
            "  • Xóa phân vùng: Bấm nút [-] ở cột đầu tiên của dòng phân vùng muốn xóa.\n"
            "  • Chỉnh sửa nhanh: Bấm chuột phải vào bất kỳ ô nào (Tên, Kiểu, Phân loại, Offset, Dung lượng, Cờ) để chọn trực tiếp hoặc tự đặt tên/nhập tay.\n"
            "  • Mở hộp thoại chi tiết: Nhấp đúp chuột trái (Double-Click) vào dòng phân vùng.\n"
            "  • Tự động dồn căn biên: Bấm nút 'Dồn & Căn 4K/64K' trên thanh công cụ để tự động tính toán lại Offset không bị chồng lấn và đúng chuẩn căn lề.\n\n"
            "2. BẢN ĐỒ BỘ NHỚ FLASH ESP32 (MEMORY MAP):\n"
            "  • 0x00000 - 0x00FFF (4 KB): Vùng Header bảo lưu của ROM / Bootloader.\n"
            "  • 0x01000 - 0x07FFF (28 KB): Second-Stage Bootloader (0x0000 trên dòng C3/S3).\n"
            "  • 0x08000 - 0x08FFF (4 KB): BẢNG PHÂN VÙNG (Partition Table Sector cố định).\n"
            "  • 0x09000 - 0x0FFFF: Dữ liệu hệ thống NVS / PHY mặc định ban đầu.\n"
            "  • 0x10000 trở đi: VÙNG CHƯƠNG TRÌNH ỨNG DỤNG (APP) - Bắt buộc căn biên 64 KB (0x10000).\n"
            "  • Phía cuối Flash: Vùng hệ thống tệp lưu trữ (LittleFS, SPIFFS, FAT) và vùng trống (Unallocated).\n\n"
            "3. QUY TẮC CĂN CHỈNH BIÊN BẮT BUỘC (ALIGNMENT RULES):\n"
            "  • Phân vùng App (factory, ota_0, ota_1...): Offset BẮT BUỘC chia hết cho 64 KB (0x10000) và >= 0x10000 do cơ chế Flash MMU Cache của ESP32.\n"
            "  • Phân vùng Data (nvs, phy, spiffs, fat, littlefs...): Offset BẮT BUỘC chia hết cho 4 KB (0x1000) - kích thước sector SPI Flash.\n"
            "  • Dung lượng (Size): MỌI phân vùng đều phải có kích thước là bội số của sector 4 KB (0x1000).\n"
            "  • Phân vùng otadata: Bắt buộc đúng 8 KB (0x2000 = 2 sectors) để lưu trữ trạng thái boot OTA đối xứng.\n\n"
            "4. CÁC PHÂN VÙNG THÔNG DỤNG:\n"
            "  • nvs: Non-Volatile Storage (16KB - 24KB) lưu Wi-Fi, BLE và biến cấu hình.\n"
            "  • factory: Bản firmware ứng dụng chính xuất xưởng (thường từ 1.5MB - 2MB).\n"
            "  • ota_0 / ota_1: Hai khe nạp firmware từ xa xoay vòng Ping-Pong.\n"
            "  • littlefs / spiffs: Hệ thống file lưu trữ web assets, file cấu hình, log cảm biến.\n\n"
            "5. THAO TÁC PHẦN CỨNG:\n"
            "  • Đọc từ Chip: Đọc cấu trúc bảng phân vùng hiện có từ chip qua cổng COM.\n"
            "  • Nạp xuống Chip: Ghi bảng phân vùng hiện tại vào offset 0x8000 của chip.\n"
            "  • Sao Lưu: Dump nội dung nhị phân của phân vùng đang chọn ra file .bin.\n"
            "  • Xóa Trắng: Format trắng vùng nhớ của phân vùng đang chọn trên chip.\n"
            "  • Mọi nhật ký quá trình thực thi phần cứng đều được ghi trực tiếp vào Tab Serial Monitor.\n"
        )
        txt.insert("1.0", doc_content)
        txt.configure(state="disabled")

        btn_box = ttk.Frame(self, padding=(10, 0, 10, 10))
        btn_box.pack(fill="x")
        ttk.Button(btn_box, text="Đóng", command=self.destroy, width=12).pack(side="right")


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
        self.partition_undo_stack: list[tuple[str, int, str, int]] = []
        self.partition_redo_stack: list[tuple[str, int, str, int]] = []
        self._is_populating_partition_table = False
        self._is_partition_hw_running = False
        self._tree_buttons: list[ttk.Button] = []
        self.var_auto_align = tk.BooleanVar(value=True)

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
        if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
            self._cascade_auto_pack(from_idx=0)

        # Thiết lập grid layout trực tiếp cho partition_tab
        self.partition_tab.columnconfigure(0, weight=1)
        self.partition_tab.rowconfigure(0, weight=0)  # 1. Thanh công cụ
        self.partition_tab.rowconfigure(1, weight=0)  # 2. Sơ đồ Disk Map
        self.partition_tab.rowconfigure(2, weight=1)  # 3. Bảng Treeview toàn màn hình

        # 1. Thanh công cụ trên cùng (phẳng, không có viền và chữ LabelFrame)
        toolbar_frame = ttk.Frame(self.partition_tab, padding=(8, 4))
        toolbar_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(4, 2))
        self._build_partition_header(toolbar_frame)

        # 2. Khung sơ đồ ổ đĩa Flash Disk Map
        map_group = ttk.LabelFrame(self.partition_tab, text=" Sơ Đồ Thanh Ổ Đĩa Flash (MiniTool Partition Map) ", padding=6)
        map_group.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        map_group.columnconfigure(0, weight=1)

        self.disk_map = DiskMapCanvas(
            map_group,
            on_select_entry=self._on_disk_map_select_entry,
            on_unallocated_click=self._on_disk_map_unallocated_click,
            on_context_action=self._on_disk_map_context_action
        )
        self.disk_map.grid(row=0, column=0, sticky="ew")

        # Thống kê nhanh dung lượng & trạng thái kiểm tra lỗi
        self.lbl_flash_stats = ttk.Label(map_group, text="", font=("Segoe UI", 8, "italic"))
        self.lbl_flash_stats.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # 3. Bảng Treeview (Chiếm toàn bộ diện tích còn lại)
        table_frame = ttk.Frame(self.partition_tab)
        table_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        columns = ("stt", "name", "type", "subtype", "offset", "size", "flags", "used", "free")
        self.part_tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")

        self.part_tree.heading("stt", text="STT")
        self.part_tree.heading("name", text="Tên (Name)")
        self.part_tree.heading("type", text="Kiểu (Type)")
        self.part_tree.heading("subtype", text="Phân loại (SubType)")
        self.part_tree.heading("offset", text="Offset")
        self.part_tree.heading("size", text="Dung lượng (Size)")
        self.part_tree.heading("flags", text="Cờ (Flags)")
        self.part_tree.heading("used", text="Đã dùng (%)")
        self.part_tree.heading("free", text="Còn trống")

        self.part_tree.column("stt", width=55, anchor="center")
        self.part_tree.column("name", width=120, anchor="w")
        self.part_tree.column("type", width=75, anchor="center")
        self.part_tree.column("subtype", width=105, anchor="center")
        self.part_tree.column("offset", width=130, anchor="e")
        self.part_tree.column("size", width=130, anchor="e")
        self.part_tree.column("flags", width=80, anchor="center")
        self.part_tree.column("used", width=100, anchor="center")
        self.part_tree.column("free", width=100, anchor="e")

        self.part_tree.grid(row=0, column=0, sticky="nsew")

        tree_scroll_y = ttk.Scrollbar(table_frame, orient="vertical", command=self._on_tree_scroll_y)
        tree_scroll_y.grid(row=0, column=1, sticky="ns")
        self.part_tree.configure(yscrollcommand=tree_scroll_y.set)

        self.part_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.part_tree.bind("<Button-1>", self._on_tree_click)
        self.part_tree.bind("<Double-1>", self._on_tree_double_click)
        self.part_tree.bind("<Return>", lambda e: self._action_edit_selected())
        self.part_tree.bind("<Delete>", lambda e: self._action_delete_selected())
        self.part_tree.bind("<Button-3>", self._on_tree_right_click)
        self.part_tree.bind("<Configure>", lambda e: self._reposition_tree_buttons())
        self.part_tree.bind("<MouseWheel>", self._on_tree_mousewheel)
        self.part_tree.bind("<Button-4>", self._on_tree_mousewheel)
        self.part_tree.bind("<Button-5>", self._on_tree_mousewheel)

        # Cập nhật theme và dữ liệu ban đầu
        self.disk_map.set_theme_mode(self.is_dark_mode)
        self.refresh_partition_views()

    def _on_tree_scroll_y(self, *args):
        self.part_tree.yview(*args)
        self._reposition_tree_buttons()

    def _on_tree_mousewheel(self, event):
        if getattr(event, "num", None) == 4 or (hasattr(event, "delta") and event.delta > 0):
            self.part_tree.yview_scroll(-1, "units")
        elif getattr(event, "num", None) == 5 or (hasattr(event, "delta") and event.delta < 0):
            self.part_tree.yview_scroll(1, "units")
        self._reposition_tree_buttons()
        return "break"

    def _build_partition_header(self, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)

        row1 = ttk.Frame(parent)
        row1.pack(fill="x", expand=True)

        # 1. Dòng Chip (mặc định chưa chọn)
        ttk.Label(row1, text="Dòng Chip:").pack(side="left", padx=(0, 4))
        self.part_chip_var = tk.StringVar(value="(Chưa chọn)")
        chip_names = ["(Chưa chọn)"] + [c.name for c in CHIP_FAMILY_DATABASE.values()]
        self.cb_part_chip = ttk.Combobox(
            row1,
            textvariable=self.part_chip_var,
            values=chip_names,
            state="readonly",
            width=14
        )
        self.cb_part_chip.pack(side="left", padx=(0, 8))
        self.cb_part_chip.bind("<<ComboboxSelected>>", self._on_chip_changed)

        # 2. Dung lượng Flash (tùy theo dòng chip, để cao nhất, người dùng có thể chọn lại)
        ttk.Label(row1, text="Dung lượng Flash:").pack(side="left", padx=(0, 4))
        self.part_flash_var = tk.StringVar(value="32 MB")
        self.cb_part_flash = ttk.Combobox(
            row1,
            textvariable=self.part_flash_var,
            values=[opt[0] for opt in FLASH_SIZE_OPTIONS],
            state="readonly",
            width=9
        )
        self.cb_part_flash.pack(side="left", padx=(0, 8))
        self.cb_part_flash.bind("<<ComboboxSelected>>", self._on_flash_size_changed)

        self.chk_auto_align = ttk.Checkbutton(row1, text="Tự động căn chỉnh", variable=self.var_auto_align, command=self._on_toggle_auto_align)
        self.chk_auto_align.pack(side="left", padx=(0, 6))

        ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=5, pady=2)

        # 3. Đọc từ Chip & Quét dự án & Thao tác bảng phân vùng
        self.btn_part_read_hw = ttk.Button(row1, text="Đọc từ Chip", command=self._hw_read_partition_table)
        self.btn_part_read_hw.pack(side="left", padx=2)

        self.btn_part_scan = ttk.Button(row1, text="Quét Dự Án", command=self._action_scan_project)
        self.btn_part_scan.pack(side="left", padx=2)

        # 4. Sao chép cài đặt phân vùng
        self.btn_part_copy = ttk.Button(row1, text="Sao chép Cài đặt", command=self._action_copy_partition_config)
        self.btn_part_copy.pack(side="left", padx=2)

        # 5. Xóa tất cả phân vùng
        self.btn_part_clear = ttk.Button(row1, text="Xóa Tất Cả", command=self._action_clear_all_partitions)
        self.btn_part_clear.pack(side="left", padx=2)

        ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=5, pady=2)

        # 6. Hướng dẫn
        self.btn_part_help = ttk.Button(row1, text="Hướng Dẫn", command=self._open_handbook_dialog)
        self.btn_part_help.pack(side="left", padx=2)

        ttk.Separator(row1, orient="vertical").pack(side="left", fill="y", padx=5, pady=2)

        # 7. Hoàn tác
        self.btn_part_undo = ttk.Button(row1, text="Hoàn tác", command=self._action_undo, state="disabled")
        self.btn_part_undo.pack(side="left", padx=2)

        # 8. Làm lại
        self.btn_part_redo = ttk.Button(row1, text="Làm lại", command=self._action_redo, state="disabled")
        self.btn_part_redo.pack(side="left", padx=2)

    def _set_partition_ui_state(self, state):
        """Bật/tắt các điều khiển của Tab Partition khi phần cứng đang bận."""
        if isinstance(state, bool):
            state = "normal" if state else "disabled"
        for attr in (
            'btn_part_scan', 'btn_part_read_hw',
            'btn_part_copy', 'btn_part_clear', 'btn_part_help',
            'cb_part_chip', 'cb_part_flash', 'chk_auto_align'
        ):
            widget = getattr(self, attr, None)
            if widget and hasattr(widget, 'config'):
                try:
                    if isinstance(widget, ttk.Combobox):
                        widget.config(state="disabled" if state == "disabled" else "readonly")
                    else:
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
            if hasattr(self, '_update_undo_redo_buttons'):
                self._update_undo_redo_buttons()

    def _open_handbook_dialog(self):
        """Mở hộp thoại hướng dẫn & tra cứu phân vùng"""
        PartitionHandbookDialog(self.root, is_dark_mode=self.is_dark_mode)

    def _on_toggle_auto_align(self):
        """Xử lý bật/tắt checkbox tự động căn chỉnh offset"""
        if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
            self._cascade_auto_pack(from_idx=0)
            self.refresh_partition_views()
            self.set_status("Đã bật tự động căn chỉnh và dồn Offset toàn bộ phân vùng.")

    def _build_partition_toolbar(self, parent: ttk.Frame):
        pass  # Đã di chuyển các nút lên _build_partition_header

    def _build_partition_bottom_tabs(self, parent: ttk.Frame):
        pass  # Đã loại bỏ các tab phụ theo yêu cầu tối ưu diện tích

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

    def _prompt_custom_size(self, entry: PartitionEntry):
        dlg = SizeInputDialog(self.root, entry.name, entry.size, is_dark_mode=self.is_dark_mode)
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
        # 1. Cập nhật Treeview
        if selected_entry_name is None:
            selected_iid = self.part_tree.selection()
            if selected_iid:
                selected_entry_name = self._get_entry_name_from_iid(selected_iid[0])

        for item in self.part_tree.get_children():
            self.part_tree.delete(item)

        current_selected_entry = None
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
                self.part_tree.selection_set(iid)
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

        # 2. Cập nhật Sơ đồ MiniTool Disk Map
        layout = self.table.get_layout_with_unallocated()
        self.disk_map.set_data(layout, self.table.flash_size, self.display_mode, current_selected_entry)

        # 3. Cập nhật Thống kê Flash & Kiểm tra hợp lệ ESP-IDF
        total_allocated = sum(e.size for e in self.table.entries)
        unallocated_size = max(0, self.table.flash_size - (self.table.part_table_offset + PARTITION_TABLE_SIZE_DEFAULT) - total_allocated)
        flash_human = format_bytes_human(self.table.flash_size, compact=True)
        alloc_human = format_bytes_human(total_allocated, compact=True)
        unalloc_human = format_bytes_human(unallocated_size, compact=True)

        errors = self.table.validate()
        err_msg = f" | ⚠️ {len(errors)} cảnh báo/lỗi ESP-IDF" if errors else " | ✅ Chuẩn ESP-IDF"
        self.lbl_flash_stats.configure(
            text=f"Dung lượng Flash: {flash_human} | Đã phân bổ: {alloc_human} ({len(self.table.entries)} phân vùng) | Chưa cấp phát: {unalloc_human}{err_msg}"
        )

        if hasattr(self, "txt_partition_val") and self.txt_partition_val.winfo_exists():
            self.txt_partition_val.configure(state="normal")
            self.txt_partition_val.delete("1.0", "end")
            if not errors:
                self.txt_partition_val.insert("1.0", "✅ BẢNG PHÂN VÙNG HOÀN TOÀN HỢP LỆ THEO CHUẨN ESP-IDF!\n\n")
            else:
                self.txt_partition_val.insert("1.0", f"⚠️ PHÁT HIỆN {len(errors)} CẢNH BÁO / LỖI BẢNG PHÂN VÙNG:\n\n")
                for err in errors:
                    self.txt_partition_val.insert("end", f"  ❌ {err}\n")
            self.txt_partition_val.configure(state="disabled")

        # Cập nhật vị trí các nút bấm [+] và [-] trên Treeview
        if hasattr(self, "root") and self.root.winfo_exists():
            self.root.after(10, self._reposition_tree_buttons)

    def _on_chip_changed(self, event=None):
        name = self.part_chip_var.get()
        if name == "(Chưa chọn)":
            self.table.target_chip = "auto"
            self.table.bootloader_offset = 0x1000
            self.cb_part_flash["values"] = [opt[0] for opt in FLASH_SIZE_OPTIONS]
            self.part_flash_var.set(FLASH_SIZE_OPTIONS[-1][0])
            self.table.flash_size = FLASH_SIZE_OPTIONS[-1][1]
            self.refresh_partition_views()
            return

        for cid, info in CHIP_FAMILY_DATABASE.items():
            if info.name == name:
                self._push_partition_undo_state()
                self.table.target_chip = cid
                self.table.bootloader_offset = info.bootloader_offset

                # Cập nhật danh sách dung lượng flash theo dòng chip
                chip_sizes = sorted(info.supported_flash_sizes)
                size_labels = [f"{sz // (1024 * 1024)} MB" for sz in chip_sizes]
                self.cb_part_flash["values"] = size_labels

                # Mặc định để mức cao nhất của dòng chip đó
                highest_sz = chip_sizes[-1]
                highest_lbl = size_labels[-1]
                self.part_flash_var.set(highest_lbl)
                self.table.flash_size = highest_sz

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
        if not selected_iid:
            self.disk_map.selected_entry = None
            self.disk_map.redraw()
            return
        entry = self._get_entry_from_iid(selected_iid[0])
        if entry:
            self.disk_map.selected_entry = entry
            self.disk_map.redraw()

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
                    w.destroy()
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
            menu = tk.Menu(self.root, tearoff=0)
            p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
            menu.configure(bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")
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
        menu = tk.Menu(self.root, tearoff=0)
        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        menu.configure(bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")

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
        menu = tk.Menu(self.root, tearoff=0)
        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        menu.configure(bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")

        row_idx = self.table.entries.index(entry) if entry in self.table.entries else 0
        menu.add_command(label=f"PHÂN VÙNG #{row_idx + 1}: {entry.name.upper()}", state="disabled")
        menu.add_separator()

        # 1. Đổi Tên (Name)
        name_sub = tk.Menu(menu, tearoff=0, bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")
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
        type_sub = tk.Menu(menu, tearoff=0, bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")
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
        sub_menu = tk.Menu(menu, tearoff=0, bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")
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
        off_sub = tk.Menu(menu, tearoff=0, bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")
        off_sub.add_command(label="Tự động tính toán (Dồn nối tiếp)", command=lambda: self._auto_align_entry_offset(entry))
        off_sub.add_separator()
        for off in [0x9000, 0x10000, 0x20000, 0x100000, 0x200000, 0x300000]:
            off_sub.add_command(label=f"Đặt Offset: {format_hex(off)} ({format_bytes_human(off)})", command=lambda o=off: self._set_entry_field(entry, "offset", o))
        off_sub.add_separator()
        off_sub.add_command(label="Tự nhập Offset...", command=lambda: self._prompt_custom_offset(entry))
        menu.add_cascade(label=f"Đổi Offset ({format_hex(entry.offset)})", menu=off_sub)

        # 5. Đổi Dung lượng (Size)
        sz_sub = tk.Menu(menu, tearoff=0, bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")
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
        flg_sub = tk.Menu(menu, tearoff=0, bg=p["text_bg"], fg=p["text_fg"], activebackground=p["accent"], activeforeground="#ffffff")
        flg_sub.add_command(label="(Không có / Trống)", command=lambda: self._set_entry_field(entry, "flags_str", ""))
        flg_sub.add_command(label="encrypted (Mã hóa phần cứng)", command=lambda: self._set_entry_field(entry, "flags_str", "encrypted"))
        flg_sub.add_command(label="readonly (Chỉ đọc)", command=lambda: self._set_entry_field(entry, "flags_str", "readonly"))
        flg_sub.add_command(label="encrypted, readonly (Cả hai cờ: Mã hóa & Chỉ đọc)", command=lambda: self._set_entry_field(entry, "flags_str", "encrypted, readonly"))
        menu.add_cascade(label=f"Đổi Cờ ({entry.flags_str or 'Trống'})", menu=flg_sub)

        menu.add_separator()
        menu.add_command(label=f"Xóa phân vùng '{entry.name}'", command=lambda: self._action_delete_by_entry(entry))

        menu.tk_popup(event.x_root, event.y_root)

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
            if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                self._cascade_auto_pack(from_idx=0)
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
                data = self.table.to_bin()
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
                data = self.table.to_bin()
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
        if dlg.result:
            self._push_partition_undo_state()
            self.table.flash_size = dlg.result["flash_size"]
            self.table.target_chip = dlg.result["chip"]
            self.table.from_csv(dlg.result["csv"])
            if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                self._cascade_auto_pack(from_idx=0)

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
            if getattr(self, "var_auto_align", None) and self.var_auto_align.get():
                self._cascade_auto_pack(from_idx=0)

            self.current_partition_file_path = path
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

    # =========================================================================
    # THAO TÁC PHẦN CỨNG ESP32 (ĐỒNG BỘ CỔNG COM VÀ ESPTOOL AN TOÀN)
    # =========================================================================

    def _log_partition_hw(self, text: str):
        """Ghi nhật ký thao tác phần cứng phân vùng trực tiếp vào Tab Serial Monitor"""
        if hasattr(self, "append_to_monitor"):
            self.append_to_monitor(f"[PARTITION_HW] {text}")

    def _update_partition_hw_progress(self, line: str):
        """Phân tích dòng output từ esptool để cập nhật thanh tiến trình toàn cục (0% -> 100%)."""
        l_str = str(line)
        pct = None
        m_pct = re.search(r"\((\d+)\s*%\)", l_str)
        if m_pct:
            pct = max(5, min(99, int(m_pct.group(1))))
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
        if pct is not None and hasattr(self, " _update_flash_progress".strip()):
            self._update_flash_progress(pct)

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
                                    if hasattr(self, "part_chip_var"):
                                        self.part_chip_var.set(info.name)
                                        self._on_chip_changed()
                                    break
                        self.refresh_partition_views()
                        self.set_status("Đã đọc và giải mã bảng phân vùng từ ESP32 thành công!", "success", progress=100)
                        self._log_partition_hw(">>> ĐỌC BẢNG PHÂN VÙNG TỪ CHIP THÀNH CÔNG!")
                        messagebox.showinfo("Thành công", f"Đã đọc và nạp thành công {len(self.table.entries)} phân vùng trực tiếp từ chip ESP32!", parent=self.root)

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
