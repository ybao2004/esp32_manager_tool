# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.3 - Tab 5: Backup & Direct Multi-Board Clone Mixin
Sao lưu phân vùng / toàn bộ Flash từ chip kèm hồ sơ băm (MD5, SHA-256, MAC gốc, tên chip, thời gian, địa chỉ, dung lượng)
và Sao chép trực tiếp (Direct Clone) từ 1 Board gốc sang 1 hoặc nhiều Board đích cùng lúc.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
from datetime import datetime
from modules import qt_toolkit as tk
from modules.qt_toolkit import ttk, messagebox, filedialog

from modules.config import (
    DARK_PALETTE, LIGHT_PALETTE, FLASH_BAUDS, REPORT_FONT_SIZE,
    APP_NAME, APP_VERSION
)
from modules.esptool_util import (
    run_esptool_command, esptool_command_succeeded, parse_esptool_output
)
from modules.serial_util import list_com_ports_local
from modules.partition.unit_formatter import (
    DisplayMode, format_bytes_human, format_hex, align_up
)
from modules.partition.chip_database import (
    CHIP_FAMILY_DATABASE, get_chip_info
)
from modules.partition.partition_model import (
    PartitionTable, PartitionEntry
)
from modules.tabs.tab_partition import DiskMapCanvas


def compute_bytes_hashes(data: bytes) -> dict[str, str]:
    """Tính toán đồng thời mã băm MD5 và SHA-256 cho khối dữ liệu nhị phân."""
    return {
        "md5": hashlib.md5(data).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def smart_trim_trailing_ff(
    data: bytes,
    min_size: int = 4096,
    align_bytes: int = 4096,
    min_keep_bytes: int | None = None
) -> bytes:
    """
    Cắt bỏ chuỗi byte trống (0xFF) dư thừa ở cuối phân vùng để tối ưu dung lượng file .bin
    và tăng tốc độ nạp khi nhân bản sang các mạch đích, vẫn đảm bảo căn biên sector 4KB.
    """
    if min_keep_bytes is not None:
        min_size = min_keep_bytes
    if not data:
        return data
    stripped = data.rstrip(b"\xff")
    if not stripped:
        # Toàn bộ phân vùng đang trống (toàn 0xFF), giữ tối thiểu 1 sector (4KB)
        return data[:min(len(data), max(1, min_size))]
    aligned_len = align_up(len(stripped), align_bytes) if align_bytes > 1 else len(stripped)
    final_len = min(len(data), max(min_size, aligned_len))
    return data[:final_len]


def infer_bootloader_offset_for_chip(chip_name: str) -> int:
    """Xác định địa chỉ Offset chuẩn của Second-Stage Bootloader theo từng dòng chip ESP."""
    norm = (chip_name or "").upper().replace("-", "").replace("_", "")
    if any(k in norm for k in ("ESP32P4", "ESP32C5")):
        return 0x2000
    if any(k in norm for k in ("ESP32S3", "ESP32C2", "ESP32C3", "ESP32C6", "ESP32H2", "ESP8266")):
        return 0x0000
    return 0x1000


def build_backup_metadata_report(
    manifest: dict | None = None,
    *,
    chip_info: dict | None = None,
    saved_items: list[dict] | None = None,
    backup_dir: str = "",
    timestamp_str: str = "",
) -> str:
    """Tạo nội dung file báo cáo thông tin sao lưu (backup_info.txt) đầy đủ, rõ ràng."""
    if manifest is None:
        manifest = {
            "timestamp": timestamp_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_port": (chip_info or {}).get("source_port", "N/A"),
            "baudrate": (chip_info or {}).get("baudrate", "460800"),
            "source_chip": (chip_info or {}).get("chip_name", "ESP32"),
            "source_revision": (chip_info or {}).get("revision", "N/A"),
            "source_crystal": (chip_info or {}).get("crystal", "N/A"),
            "source_mac": (chip_info or {}).get("mac", "N/A"),
            "flash_size_human": (chip_info or {}).get("flash_size", "N/A"),
            "flash_size_bytes": (chip_info or {}).get("flash_size_bytes", 0),
            "smart_trim": True,
            "regions": [
                {
                    "name": it.get("name", "unknown"),
                    "type": it.get("type", it.get("type_str", "N/A")),
                    "subtype": it.get("subtype", it.get("subtype_str", "N/A")),
                    "filename": it.get("filename", "N/A"),
                    "offset": it.get("offset", 0),
                    "offset_hex": it.get("offset_hex") or format_hex(int(it.get("offset", 0))),
                    "partition_size": it.get("partition_size", it.get("original_size", 0)),
                    "partition_size_human": it.get("partition_size_human") or format_bytes_human(int(it.get("partition_size", it.get("original_size", 0)))),
                    "saved_size": it.get("saved_size", 0),
                    "saved_size_human": it.get("saved_size_human") or format_bytes_human(int(it.get("saved_size", 0))),
                    "md5": it.get("md5", "N/A"),
                    "sha256": it.get("sha256", "N/A"),
                }
                for it in (saved_items or [])
            ],
        }
    lines = [
        "=" * 82,
        f"HỒ SƠ SAO LƯU PHẦN CỨNG & FIRMWARE - {APP_NAME.upper()} v{APP_VERSION}",
        "=" * 82,
        f"Thời gian sao lưu     : {manifest.get('timestamp', 'N/A')}",
        f"Cổng COM sao lưu      : {manifest.get('source_port', 'N/A')} (@ {manifest.get('baudrate', 'N/A')} bps)",
        f"Dòng Chip gốc         : {manifest.get('source_chip', 'N/A')}",
        f"Phiên bản Silicon     : {manifest.get('source_revision', 'N/A')}",
        f"Tần số thạch anh      : {manifest.get('source_crystal', 'N/A')}",
        f"Địa chỉ MAC gốc       : {manifest.get('source_mac', 'N/A')}",
        f"Kích thước Flash chip : {manifest.get('flash_size_human', 'N/A')} ({manifest.get('flash_size_bytes', 0):,} Bytes)",
        f"Chế độ cắt trống 0xFF : {'Bật (Smart Trim 4KB)' if manifest.get('smart_trim') else 'Tắt (Giữ nguyên kích thước vùng)'}",
        "-" * 82,
        "DANH SÁCH CÁC PHÂN VÙNG / TỆP NHỊ PHÂN ĐÃ SAO LƯU:",
        "-" * 82,
    ]

    regions = manifest.get("regions", [])
    for idx, reg in enumerate(regions, 1):
        lines.extend([
            f"[{idx:02d}] Phân vùng: {reg.get('name', 'unknown')} "
            f"(Type: {reg.get('type', 'N/A')} | SubType: {reg.get('subtype', 'N/A')})",
            f"     • Tên file .bin         : {reg.get('filename', 'N/A')}",
            f"     • Địa chỉ bắt đầu       : {reg.get('offset_hex', '0x0')} ({reg.get('offset', 0):,} Bytes)",
            f"     • Dung lượng phân vùng  : {reg.get('partition_size_human', 'N/A')} ({reg.get('partition_size', 0):,} Bytes)",
            f"     • Dung lượng file lưu   : {reg.get('saved_size_human', 'N/A')} ({reg.get('saved_size', 0):,} Bytes)",
            f"     • Mã băm MD5            : {reg.get('md5', 'N/A')}",
            f"     • Mã băm SHA-256        : {reg.get('sha256', 'N/A')}",
            "-" * 82,
        ])

    if regions:
        pair_args = " ".join(f"{r.get('offset_hex', '0x0')} \"{r.get('filename', '')}\"" for r in regions)
        lines.extend([
            "LỆNH ESPTOOL KHÔI PHỤC / NHÂN BẢN MẪU:",
            f"  esptool --port <COM_ĐÍCH> --baud 460800 write-flash -z {pair_args}",
            "=" * 82,
        ])

    return "\n".join(lines) + "\n"


class BackupCloneTabMixin:
    """
    Mixin quản lý Tab 5: Sao lưu & Nhân bản Trực tiếp (Backup & Direct Multi-Board Clone).
    """
    backup_hw_thread = None

    def create_backup_tab(self):
        """Khởi tạo giao diện Tab 5 bên trong self.backup_tab."""
        self.backup_hw_thread = None
        self._is_backup_hw_running = False
        self.backup_source_info = {
            "chip_name": "ESP32",
            "chip_line": "Chưa đọc từ chip (Đang hiển thị bố cục mặc định)",
            "revision": "N/A",
            "crystal": "N/A",
            "mac": "Chưa xác định",
            "flash_size": 4 * 1024 * 1024,
            "bootloader_offset": 0x1000,
            "part_table_offset": 0x8000,
        }
        self.backup_last_saved_dir = ""
        self.backup_last_manifest: dict | None = None

        self.var_backup_smart_trim = tk.BooleanVar(value=True)
        self.var_clone_erase_first = tk.BooleanVar(value=False)
        self.var_clone_source_mode = tk.StringVar(value="live_board")
        self.backup_selected_keys: set[str] = set()
        self.backup_region_hashes: dict[str, str] = {}
        self.clone_target_vars: dict[str, tk.BooleanVar] = {}

        # Khởi tạo bảng phân vùng mẫu cho sơ đồ DiskMapCanvas của Tab 5
        self.backup_table = PartitionTable(flash_size=4 * 1024 * 1024, target_chip="esp32")
        default_csv = (
            "# ESP-IDF Partition Table\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1M,\n"
            "storage,  data, spiffs,  0x110000, 1M,\n"
        )
        self.backup_table.from_csv(default_csv)

        self.backup_tab.columnconfigure(0, weight=1)
        self.backup_tab.rowconfigure(0, weight=0)  # 1. Thanh điều khiển Board gốc
        self.backup_tab.rowconfigure(1, weight=0)  # 2. Thanh sơ đồ phân vùng DiskMapCanvas
        self.backup_tab.rowconfigure(2, weight=1)  # 3. Khung chia đôi: Danh sách vùng sao lưu & Nhân bản đa mạch

        # 1. Thanh điều khiển Board gốc trên cùng
        top_bar = ttk.Frame(self.backup_tab, padding=(8, 4))
        top_bar.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        self._build_backup_top_bar(top_bar)

        # 2. Thanh sơ đồ phân vùng trực quan (giống Tab 4)
        map_group = ttk.LabelFrame(
            self.backup_tab,
            text=" Sơ Đồ Phân Vùng Trên Chip Gốc (Click vào từng khối để Chọn / Bỏ chọn Sao lưu) ",
            padding=6
        )
        map_group.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        map_group.columnconfigure(0, weight=1)

        self.backup_disk_map = DiskMapCanvas(
            map_group,
            on_select_entry=self._on_backup_map_click_entry,
            on_unallocated_click=None,
            on_context_action=None
        )
        self.backup_disk_map.grid(row=0, column=0, sticky="ew")

        self.lbl_backup_chip_summary = ttk.Label(
            map_group,
            text="",
            font=("Segoe UI", 8, "italic")
        )
        self.lbl_backup_chip_summary.grid(row=1, column=0, sticky="w", pady=(4, 0))

        # 3. Khung chính: Trái (Bảng tích chọn phân vùng) - Phải (Sao lưu & Sao chép trực tiếp sang nhiều Board)
        body_frame = ttk.Frame(self.backup_tab)
        body_frame.grid(row=2, column=0, sticky="nsew", padx=8, pady=(0, 6))
        body_frame.columnconfigure(0, weight=5)
        body_frame.columnconfigure(1, weight=4)
        body_frame.rowconfigure(0, weight=1)

        self._build_backup_regions_panel(body_frame)
        self._build_backup_actions_and_clone_panel(body_frame)

        # Chọn mặc định toàn bộ các phân vùng (bao gồm Bootloader & Partition Table)
        for reg in self._get_all_backup_regions():
            self.backup_selected_keys.add(reg["key"])

        self.backup_disk_map.set_theme_mode(getattr(self, "is_dark_mode", False))
        self.refresh_backup_views()

    def _build_backup_top_bar(self, parent: ttk.Frame):
        row = ttk.Frame(parent)
        row.pack(fill="x", expand=True)

        ttk.Label(row, text="Board Gốc (COM):", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 4))
        self.backup_src_port_var = tk.StringVar(value="")
        self.cb_backup_src_port = ttk.Combobox(
            row,
            textvariable=self.backup_src_port_var,
            values=[],
            state="readonly",
            width=10,
            postcommand=self._refresh_backup_ports
        )
        self.cb_backup_src_port.pack(side="left", padx=(0, 4))
        self.cb_backup_src_port.bind("<<ComboboxSelected>>", lambda e: self._refresh_clone_target_checkboxes())

        self.btn_backup_refresh_com = ttk.Button(
            row, text="Làm mới COM", width=12, command=self._refresh_backup_ports
        )
        self.btn_backup_refresh_com.pack(side="left", padx=(0, 8))

        ttk.Label(row, text="Baudrate:").pack(side="left", padx=(0, 4))
        self.backup_baud_var = tk.StringVar(value="460800")
        self.cb_backup_baud = ttk.Combobox(
            row,
            textvariable=self.backup_baud_var,
            values=FLASH_BAUDS,
            state="readonly",
            width=9
        )
        self.cb_backup_baud.pack(side="left", padx=(0, 8))

        self.btn_backup_read_chip = ttk.Button(
            row,
            text="ĐỌC CẤU TRÚC & MAC TỪ CHIP GỐC",
            style="Accent.TButton",
            command=self._hw_probe_source_chip_for_backup
        )
        self.btn_backup_read_chip.pack(side="left", padx=(0, 8))

        ttk.Separator(row, orient="vertical").pack(side="left", fill="y", padx=5, pady=2)

        self.btn_backup_sel_all = ttk.Button(
            row, text="Chọn Tất Cả", command=lambda: self._backup_select_all(True)
        )
        self.btn_backup_sel_all.pack(side="left", padx=2)

        self.btn_backup_unsel_all = ttk.Button(
            row, text="Bỏ Chọn", command=lambda: self._backup_select_all(False)
        )
        self.btn_backup_unsel_all.pack(side="left", padx=2)

        self.btn_backup_sel_fw = ttk.Button(
            row, text="Chỉ Chọn Firmware & Boot", command=self._backup_select_firmware_only
        )
        self.btn_backup_sel_fw.pack(side="left", padx=2)

        self.chk_backup_trim = ttk.Checkbutton(
            row,
            text="Cắt trống 0xFF (Smart Trim)",
            variable=self.var_backup_smart_trim
        )
        self.chk_backup_trim.pack(side="left", padx=(6, 0))

    def _build_backup_regions_panel(self, parent: ttk.Frame):
        left_group = ttk.LabelFrame(
            parent,
            text=" Danh Sách Phân Vùng & Dữ Liệu Cần Sao Lưu (Click dòng để Chọn [x] / Bỏ chọn [ ]) ",
            padding=6
        )
        left_group.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        left_group.columnconfigure(0, weight=1)
        left_group.rowconfigure(0, weight=1)

        cols = ("checked", "stt", "name", "type", "subtype", "offset", "size", "hash")
        self.backup_tree = ttk.Treeview(left_group, columns=cols, show="headings", selectmode="browse")

        self.backup_tree.heading("checked", text="Chọn")
        self.backup_tree.heading("stt", text="STT")
        self.backup_tree.heading("name", text="Tên Vùng")
        self.backup_tree.heading("type", text="Kiểu")
        self.backup_tree.heading("subtype", text="Phân loại")
        self.backup_tree.heading("offset", text="Địa chỉ (Offset)")
        self.backup_tree.heading("size", text="Dung lượng")
        self.backup_tree.heading("hash", text="Mã băm SHA-256 / Trạng thái")

        self.backup_tree.column("checked", width=48, anchor="center")
        self.backup_tree.column("stt", width=42, anchor="center")
        self.backup_tree.column("name", width=110, anchor="w")
        self.backup_tree.column("type", width=70, anchor="center")
        self.backup_tree.column("subtype", width=85, anchor="center")
        self.backup_tree.column("offset", width=95, anchor="e")
        self.backup_tree.column("size", width=95, anchor="e")
        self.backup_tree.column("hash", width=165, anchor="w")

        self.backup_tree.grid(row=0, column=0, sticky="nsew")
        vsb = ttk.Scrollbar(left_group, orient="vertical", command=self.backup_tree.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.backup_tree.configure(yscrollcommand=vsb.set)

        self.backup_tree.bind("<ButtonRelease-1>", self._on_backup_tree_click)
        self.backup_tree.bind("<space>", self._on_backup_tree_space)

        # Thanh nút phụ dưới bảng phân vùng
        bottom_left = ttk.Frame(left_group)
        bottom_left.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        self.btn_backup_to_folder = ttk.Button(
            bottom_left,
            text="SAO LƯU VÙNG ĐÃ CHỌN RA THƯ MỤC (KÈM SHA256/MAC)",
            style="Accent.TButton",
            command=self._hw_backup_selected_to_folder
        )
        self.btn_backup_to_folder.pack(side="left", padx=(0, 6))

        self.btn_backup_full_chip = ttk.Button(
            bottom_left,
            text="Sao Lưu Toàn Bộ Flash (1 File .bin)",
            command=self._hw_backup_full_flash_single_file
        )
        self.btn_backup_full_chip.pack(side="left", padx=(0, 6))

        self.btn_backup_to_flasher = ttk.Button(
            bottom_left,
            text="Đẩy sang Tab Nạp Flash",
            command=self._action_send_backup_to_flasher_tab
        )
        self.btn_backup_to_flasher.pack(side="left")

    def _build_backup_actions_and_clone_panel(self, parent: ttk.Frame):
        right_container = ttk.Frame(parent)
        right_container.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        right_container.columnconfigure(0, weight=1)
        right_container.rowconfigure(0, weight=0)
        right_container.rowconfigure(1, weight=1)

        # Khung trên: Sao chép trực tiếp từ Board gốc sang 1 hoặc nhiều Board đích
        clone_group = ttk.LabelFrame(
            right_container,
            text=" Sao Chép Trực Tiếp (Direct Clone: 1 Board Gốc -> Nhiều Board Đích) ",
            padding=8
        )
        clone_group.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        clone_group.columnconfigure(0, weight=1)

        mode_row = ttk.Frame(clone_group)
        mode_row.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(mode_row, text="Nguồn dữ liệu:", font=("Segoe UI", 9, "bold")).pack(side="left", padx=(0, 6))
        ttk.Radiobutton(
            mode_row,
            text="Đọc trực tiếp từ Board Gốc",
            variable=self.var_clone_source_mode,
            value="live_board"
        ).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(
            mode_row,
            text="Từ Thư mục Sao lưu đã lưu",
            variable=self.var_clone_source_mode,
            value="saved_folder"
        ).pack(side="left")

        target_hdr = ttk.Frame(clone_group)
        target_hdr.grid(row=1, column=0, sticky="ew", pady=(2, 2))
        ttk.Label(
            target_hdr,
            text="Tích chọn các cổng COM Đích (Board nhận sao chép):",
            font=("Segoe UI", 9, "bold")
        ).pack(side="left")
        ttk.Button(
            target_hdr,
            text="Chọn hết cổng đích",
            command=lambda: self._select_all_clone_targets(True)
        ).pack(side="right", padx=(4, 0))

        self.clone_target_ports_frame = ttk.Frame(clone_group)
        self.clone_target_ports_frame.grid(row=2, column=0, sticky="ew", pady=2)

        clone_ctrl = ttk.Frame(clone_group)
        clone_ctrl.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        self.chk_clone_erase = ttk.Checkbutton(
            clone_ctrl,
            text="Xóa sạch Flash board đích trước khi chép (--erase-all)",
            variable=self.var_clone_erase_first
        )
        self.chk_clone_erase.pack(side="left")

        clone_btn_bar = ttk.Frame(clone_group)
        clone_btn_bar.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        self.btn_direct_clone = ttk.Button(
            clone_btn_bar,
            text="SAO CHÉP TRỰC TIẾP SANG CÁC BOARD ĐÍCH",
            style="Accent.TButton",
            command=self._hw_start_direct_multi_board_clone
        )
        self.btn_direct_clone.pack(side="left", fill="x", expand=True)

        # Khung dưới: Nhật ký Sao lưu & Nhân bản
        log_group = ttk.LabelFrame(
            right_container,
            text=" Nhật Ký Sao Lưu, Mã Băm (MD5/SHA256) & Tiến Trình Nhân Bản ",
            padding=6
        )
        log_group.grid(row=1, column=0, sticky="nsew")
        log_group.columnconfigure(0, weight=1)
        log_group.rowconfigure(0, weight=1)

        self.backup_log_txt = tk.Text(
            log_group,
            height=10,
            wrap="word",
            font=("Consolas", REPORT_FONT_SIZE),
            relief="flat",
            borderwidth=1,
            state="disabled"
        )
        self.backup_log_txt.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        vsb_log = ttk.Scrollbar(log_group, orient="vertical", command=self.backup_log_txt.yview)
        vsb_log.grid(row=0, column=1, sticky="ns")
        self.backup_log_txt.configure(yscrollcommand=vsb_log.set)

        btn_clear_log = ttk.Button(
            log_group,
            text="Xóa Nhật Ký",
            command=lambda: self.on_clear(self.backup_log_txt, clear_status=False)
        )
        btn_clear_log.grid(row=1, column=0, columnspan=2, sticky="e", pady=(4, 0))

    def log_backup(self, text: str, tag: str | None = None):
        """Ghi nhật ký vào khung log của Tab 5."""
        try:
            if hasattr(self, "backup_log_txt") and self.backup_log_txt.winfo_exists():
                self.backup_log_txt.config(state="normal")
                self.backup_log_txt.insert("end", text + "\n", tag)
                self.backup_log_txt.see("end")
                self.backup_log_txt.config(state="disabled")
        except Exception:
            pass

    def _get_all_backup_regions(self) -> list[dict]:
        """
        Trả về danh sách toàn bộ các phân vùng có thể sao lưu trên chip gốc:
        Bao gồm Bootloader, Partition Table và tất cả các phân vùng trong self.backup_table.entries.
        """
        boot_off = int(self.backup_source_info.get("bootloader_offset", 0x1000))
        part_off = int(self.backup_source_info.get("part_table_offset", 0x8000))
        boot_size = max(0x1000, part_off - boot_off) if part_off > boot_off else 0x7000

        regions = [
            {
                "key": f"sys_bootloader_{boot_off:X}",
                "name": "bootloader",
                "type": "system",
                "subtype": "bootloader",
                "offset": boot_off,
                "size": boot_size,
                "is_system": True,
            },
            {
                "key": f"sys_parttable_{part_off:X}",
                "name": "partition_table",
                "type": "system",
                "subtype": "part_table",
                "offset": part_off,
                "size": 0x1000,
                "is_system": True,
            },
        ]

        for entry in sorted(self.backup_table.entries, key=lambda e: e.offset):
            regions.append({
                "key": f"part_{entry.name}_{entry.offset:X}",
                "name": entry.name,
                "type": entry.type_str,
                "subtype": entry.subtype_str,
                "offset": entry.offset,
                "size": entry.size,
                "is_system": False,
            })
        return regions

    def _refresh_backup_ports(self):
        """Đồng bộ danh sách cổng COM cho Board Gốc và danh sách checkbox Board Đích."""
        raw_ports = list_com_ports_local()
        filtered = self.filter_ignored_ports(raw_ports) if hasattr(self, "filter_ignored_ports") else raw_ports

        if hasattr(self, "cb_backup_src_port") and self.cb_backup_src_port.winfo_exists():
            self.cb_backup_src_port["values"] = filtered
            curr_src = self.backup_src_port_var.get().strip()
            top_port = self.port_cb.get().strip() if hasattr(self, "port_cb") else ""
            if curr_src and curr_src in filtered:
                self.backup_src_port_var.set(curr_src)
            elif top_port and top_port in filtered:
                self.backup_src_port_var.set(top_port)
            elif filtered:
                self.backup_src_port_var.set(filtered[0])
            else:
                self.backup_src_port_var.set("")

        self._refresh_clone_target_checkboxes(filtered)

    def _refresh_clone_target_checkboxes(self, available_ports: list[str] | None = None):
        """Hiển thị danh sách các cổng COM Đích (loại trừ cổng COM đang làm Board Gốc)."""
        if not hasattr(self, "clone_target_ports_frame") or not self.clone_target_ports_frame.winfo_exists():
            return

        if available_ports is None:
            raw_ports = list_com_ports_local()
            available_ports = self.filter_ignored_ports(raw_ports) if hasattr(self, "filter_ignored_ports") else raw_ports

        src_port = self.backup_src_port_var.get().strip().upper()
        prev_states = {k: v.get() for k, v in self.clone_target_vars.items()}

        for w in self.clone_target_ports_frame.winfo_children():
            w.destroy()
        self.clone_target_vars.clear()

        target_candidates = [p for p in available_ports if p.strip().upper() != src_port]
        if not target_candidates:
            ttk.Label(
                self.clone_target_ports_frame,
                text="(Chưa phát hiện thêm cổng COM đích nào khác ngoài cổng Board gốc. Hãy cắm thêm mạch đích và bấm 'Làm mới COM')",
                font=("Segoe UI", 8, "italic")
            ).pack(anchor="w", padx=4, pady=2)
            return

        for idx, p_name in enumerate(target_candidates):
            var = tk.BooleanVar(value=prev_states.get(p_name, True))
            self.clone_target_vars[p_name] = var
            cb = ttk.Checkbutton(
                self.clone_target_ports_frame,
                text=f"Board Đích: {p_name}",
                variable=var
            )
            cb.grid(row=idx // 3, column=idx % 3, sticky="w", padx=8, pady=2)

    def _select_all_clone_targets(self, select: bool = True):
        for var in self.clone_target_vars.values():
            var.set(select)

    def refresh_backup_views(self):
        """Cập nhật thanh sơ đồ phân vùng DiskMapCanvas và bảng Treeview của Tab 5."""
        if not hasattr(self, "backup_tree") or not self.backup_tree.winfo_exists():
            return

        self._refresh_backup_ports()

        # Cập nhật thanh sơ đồ phân vùng
        layout_entries = self.backup_table.get_layout_with_unallocated()
        selected_entry = None
        for e in layout_entries:
            if not e.is_unallocated:
                k = f"part_{e.name}_{e.offset:X}"
                if k in self.backup_selected_keys:
                    selected_entry = e
                    break
        self.backup_disk_map.set_data(
            layout_entries=layout_entries,
            flash_size=self.backup_table.flash_size,
            display_mode=DisplayMode.DECIMAL,
            selected_entry=selected_entry
        )

        # Cập nhật bảng Treeview
        for item in self.backup_tree.get_children():
            self.backup_tree.delete(item)

        regions = self._get_all_backup_regions()
        for r in regions:
            r["selected"] = r["key"] in self.backup_selected_keys
        self.backup_regions = regions
        selected_count = 0
        selected_bytes = 0

        for idx, reg in enumerate(regions, 1):
            key = reg["key"]
            is_checked = key in self.backup_selected_keys
            if is_checked:
                selected_count += 1
                selected_bytes += reg["size"]

            chk_symbol = "[x]" if is_checked else "[ ]"
            hash_info = self.backup_region_hashes.get(key, "Sẵn sàng sao lưu" if is_checked else "Bỏ qua")
            self.backup_tree.insert(
                "",
                "end",
                iid=key,
                values=(
                    chk_symbol,
                    idx,
                    reg["name"],
                    reg["type"],
                    reg["subtype"],
                    format_hex(reg["offset"]),
                    format_bytes_human(reg["size"]),
                    hash_info,
                )
            )

        chip_lbl = self.backup_source_info.get("chip_line", "Chưa đọc từ chip")
        mac_lbl = self.backup_source_info.get("mac", "N/A")
        flash_lbl = format_bytes_human(self.backup_table.flash_size)
        self.lbl_backup_chip_summary.config(
            text=(
                f"Chip gốc: {chip_lbl}  |  MAC gốc: {mac_lbl}  |  Flash: {flash_lbl}  |  "
                f"Đang chọn: {selected_count}/{len(regions)} phân vùng ({format_bytes_human(selected_bytes)})"
            )
        )

    def _on_backup_map_click_entry(self, entry: PartitionEntry):
        """Khi click vào một khối phân vùng trên thanh sơ đồ DiskMapCanvas -> Đảo chọn phân vùng đó."""
        if entry.is_unallocated:
            return
        key = f"part_{entry.name}_{entry.offset:X}"
        if key in self.backup_selected_keys:
            self.backup_selected_keys.remove(key)
        else:
            self.backup_selected_keys.add(key)
        self.refresh_backup_views()
        if self.backup_tree.exists(key):
            self.backup_tree.selection_set(key)
            self.backup_tree.see(key)

    def _on_backup_tree_click(self, event):
        iid = self.backup_tree.identify_row(event.y)
        if not iid:
            return
        if iid in self.backup_selected_keys:
            self.backup_selected_keys.remove(iid)
        else:
            self.backup_selected_keys.add(iid)
        self.refresh_backup_views()
        if self.backup_tree.exists(iid):
            self.backup_tree.selection_set(iid)

    def _on_backup_tree_space(self, event):
        sel = self.backup_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid in self.backup_selected_keys:
            self.backup_selected_keys.remove(iid)
        else:
            self.backup_selected_keys.add(iid)
        self.refresh_backup_views()
        if self.backup_tree.exists(iid):
            self.backup_tree.selection_set(iid)

    def _backup_select_all(self, select: bool = True):
        self.backup_selected_keys.clear()
        if select:
            for reg in self._get_all_backup_regions():
                self.backup_selected_keys.add(reg["key"])
        self.refresh_backup_views()

    def _action_backup_select_all(self, select: bool = True):
        self._backup_select_all(select)

    def _backup_select_firmware_only(self):
        """Chỉ tích chọn Bootloader, Partition Table và các phân vùng Firmware (app / otadata)."""
        self.backup_selected_keys.clear()
        for reg in self._get_all_backup_regions():
            if reg["is_system"] or reg["type"] == "app" or reg["subtype"] in ("ota", "otadata", "phy"):
                self.backup_selected_keys.add(reg["key"])
        self.refresh_backup_views()

    def _action_backup_select_firmware_only(self):
        self._backup_select_firmware_only()

    def _set_backup_ui_state(self, state):
        if isinstance(state, bool):
            state = "normal" if state else "disabled"
        for attr in (
            "cb_backup_src_port", "btn_backup_refresh_com", "cb_backup_baud",
            "btn_backup_read_chip", "btn_backup_sel_all", "btn_backup_unsel_all",
            "btn_backup_sel_fw", "chk_backup_trim", "btn_backup_to_folder",
            "btn_backup_full_chip", "btn_backup_to_flasher", "btn_direct_clone",
            "chk_clone_erase"
        ):
            w = getattr(self, attr, None)
            if w and hasattr(w, "config"):
                try:
                    if isinstance(w, ttk.Combobox):
                        w.config(state="disabled" if state == "disabled" else "readonly")
                    else:
                        w.config(state=state)
                except Exception:
                    pass

    def _prepare_backup_source_port(self) -> tuple[str, int] | None:
        port = self.backup_src_port_var.get().strip()
        if not port and hasattr(self, "port_cb"):
            port = self.port_cb.get().strip()
            if port:
                self.backup_src_port_var.set(port)
        if not port:
            messagebox.showwarning("Thiếu Cổng COM", "Vui lòng chọn cổng COM của Board Gốc trước khi thao tác!", parent=self.root)
            return None

        baud_str = self.backup_baud_var.get().strip()
        baud = int(baud_str) if baud_str.isdigit() else 460800

        if getattr(self, "serial_connection", None) and getattr(self.serial_connection, "is_open", False):
            self.on_serial_disconnect()
            self.log_backup(">> [HỆ THỐNG] Đã tự động tạm ngắt Serial Monitor để thực thi tác vụ Sao lưu / Nhân bản.")
        return port, baud

    def _probe_chip_and_partition_sync(self, port: str, baud: int, safe_after) -> bool:
        """
        Đọc thông tin định danh chip (Tên chip, Revision, Crystal, MAC gốc, Dung lượng Flash)
        và đọc bảng phân vùng 0x8000 từ Board Gốc.
        """
        safe_after(lambda: self.log_backup(f"\n=== ĐỌC THÔNG TIN CHIP & BẢNG PHÂN VÙNG TỪ BOARD GỐC ({port}) ===", "header"))
        safe_after(lambda: self.set_status(f"Đang nhận diện chip và đọc MAC gốc trên {port}...", "info", progress=15))

        fid_out = run_esptool_command(["--port", port, "--baud", str(baud), "flash-id"])
        if not esptool_command_succeeded(fid_out):
            safe_after(lambda: self.log_backup(">>> [LỖI] Không thể kết nối với chip trên cổng " + port, "red"))
            return False

        parsed = parse_esptool_output({"flash_id": fid_out})
        chip_key = parsed.get("chip_name_key") or "ESP32"
        chip_line = parsed.get("chip_line") or chip_key
        rev = parsed.get("revision") or "N/A"
        crystal = parsed.get("crystal") or "N/A"
        mac_hex = parsed.get("mac")
        mac_fmt = ":".join(mac_hex[i:i+2] for i in range(0, 12, 2)).upper() if mac_hex and len(mac_hex) == 12 else "N/A"
        flash_mb = parsed.get("flash_mb") or 4.0
        flash_bytes = int(flash_mb * 1024 * 1024)
        boot_off = infer_bootloader_offset_for_chip(chip_key)

        self.backup_source_info.update({
            "chip_name": chip_key,
            "chip_line": chip_line,
            "revision": rev,
            "crystal": crystal,
            "mac": mac_fmt,
            "flash_size": flash_bytes,
            "bootloader_offset": boot_off,
            "part_table_offset": 0x8000,
        })

        safe_after(lambda: self.log_backup(
            f"  + Chip gốc: {chip_line} | MAC gốc: {mac_fmt} | Flash: {flash_mb:.1f} MB | Bootloader @ 0x{boot_off:X}"
        ))
        safe_after(lambda: self.set_status(f"Đang đọc bảng phân vùng (0x8000) từ {chip_key}...", "info", progress=45))

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            read_out = run_esptool_command(["--port", port, "--baud", str(baud), "read-flash", "0x8000", "0x1000", tmp_path])
            if esptool_command_succeeded(read_out) and os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, "rb") as f:
                    pt_bytes = f.read()
                new_table = PartitionTable(flash_size=flash_bytes, target_chip=chip_key.lower().replace("-", ""))
                new_table.bootloader_offset = boot_off
                new_table.from_binary(pt_bytes)
                if new_table.entries:
                    self.backup_table = new_table
                    safe_after(lambda n=len(new_table.entries): self.log_backup(
                        f"  + Đã giải mã thành công {n} phân vùng từ bảng phân vùng trên chip.", "green"
                    ))
                else:
                    self.backup_table.flash_size = flash_bytes
                    self.backup_table.bootloader_offset = boot_off
                    safe_after(lambda: self.log_backup(
                        "  ! Không tìm thấy cấu trúc phân vùng chuẩn tại 0x8000, giữ danh sách phân vùng hiện tại."
                    ))
            else:
                return False
        finally:
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        return True

    def _hw_probe_source_chip_for_backup(self):
        """Sự kiện bấm nút 'ĐỌC CẤU TRÚC & MAC TỪ CHIP GỐC'."""
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            messagebox.showwarning("Thiết bị đang bận", "Vui lòng đợi tác vụ phần cứng hiện tại hoàn tất!", parent=self.root)
            return

        prep = self._prepare_backup_source_port()
        if not prep:
            return
        port, baud = prep

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_backup_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, "đọc cấu trúc phân vùng & MAC từ chip gốc"))
            else:
                safe_after(lambda: self._set_backup_ui_state("disabled"))

            ok = False
            try:
                ok = self._probe_chip_and_partition_sync(port, baud, safe_after)
                if ok:
                    def _on_ok():
                        self.backup_selected_keys = {r["key"] for r in self._get_all_backup_regions()}
                        self.backup_region_hashes.clear()
                        self.refresh_backup_views()
                        self.set_status("Đã đọc thông tin chip, địa chỉ MAC và bảng phân vùng thành công!", "success", progress=100)
                    safe_after(_on_ok)
                else:
                    safe_after(lambda: self.set_status("Không thể đọc cấu trúc từ chip gốc!", "error", progress=0))
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda m=err_msg: self.log_backup(f">>> [NGOẠI LỆ] {m}", "red"))
                safe_after(lambda: self.set_status("Lỗi khi đọc chip gốc!", "error", progress=0))
            finally:
                self._is_backup_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))
                else:
                    safe_after(lambda: self._set_backup_ui_state("normal"))

        self.backup_hw_thread = threading.Thread(target=worker, daemon=True)
        self.backup_hw_thread.start()

    def _dump_selected_regions_to_dir_sync(
        self, port: str, baud: int, out_dir: str, regions: list[dict], smart_trim: bool, safe_after,
        progress_start: float = 15.0, progress_end: float = 95.0
    ) -> dict | None:
        """
        Thực thi đọc tuần tự các phân vùng đã chọn từ cổng `port` ra thư mục `out_dir`,
        tính toán mã băm MD5 & SHA-256, xuất `partitions.csv`, `backup_manifest.json` và `backup_info.txt`.
        """
        os.makedirs(out_dir, exist_ok=True)
        total_bytes = max(1, sum(r["size"] for r in regions))
        completed_bytes = 0
        saved_regions_meta = []

        for idx, reg in enumerate(regions, 1):
            r_name = reg["name"]
            r_off = reg["offset"]
            r_size = reg["size"]
            safe_filename = f"{idx:02d}_{r_name}_{format_hex(r_off)}.bin"
            dest_path = os.path.join(out_dir, safe_filename)

            safe_after(lambda n=r_name, o=r_off, s=r_size, i=idx, tot=len(regions): self.log_backup(
                f"  [{i}/{tot}] Đang sao lưu '{n}' tại {format_hex(o)} ({format_bytes_human(s)})..."
            ))

            def on_stream(line, base_done=completed_bytes, cur_sz=r_size):
                m = re.search(r"\((\d+)\s*%\)", str(line))
                if m:
                    pct = int(m.group(1))
                    cur_done = base_done + (pct / 100.0) * cur_sz
                    overall = progress_start + ((cur_done / total_bytes) * (progress_end - progress_start))
                    safe_after(lambda p=overall, n=r_name, pc=pct: self.set_status(
                        f"Đang sao lưu '{n}' ({pc}%)...", "warning", progress=p
                    ))

            args = ["--port", port, "--baud", str(baud), "read-flash", format_hex(r_off), format_hex(r_size), dest_path]
            res = run_esptool_command(args, progress_callback=on_stream)
            if not esptool_command_succeeded(res) or not os.path.isfile(dest_path):
                safe_after(lambda n=r_name: self.log_backup(f">>> [LỖI] Sao lưu phân vùng '{n}' thất bại!", "red"))
                return None

            with open(dest_path, "rb") as f:
                raw_data = f.read()

            if smart_trim and not reg.get("is_system", False):
                final_data = smart_trim_trailing_ff(raw_data, min_size=4096, align_bytes=4096)
                if len(final_data) != len(raw_data):
                    with open(dest_path, "wb") as f:
                        f.write(final_data)
            else:
                final_data = raw_data

            hashes = compute_bytes_hashes(final_data)
            short_sha = f"SHA256: {hashes['sha256'][:16]}..."
            reg_key = reg["key"]
            self.backup_region_hashes[reg_key] = short_sha

            saved_regions_meta.append({
                "key": reg_key,
                "name": r_name,
                "type": reg["type"],
                "subtype": reg["subtype"],
                "offset": r_off,
                "offset_hex": format_hex(r_off),
                "partition_size": r_size,
                "partition_size_human": format_bytes_human(r_size),
                "saved_size": len(final_data),
                "saved_size_human": format_bytes_human(len(final_data)),
                "filename": safe_filename,
                "filepath": dest_path,
                "md5": hashes["md5"],
                "sha256": hashes["sha256"],
            })

            safe_after(
                lambda n=r_name, sz=len(final_data), md5=hashes["md5"], sha=hashes["sha256"]: self.log_backup(
                    f"      -> Đã lưu: {format_bytes_human(sz)} | MD5: {md5} | SHA256: {sha[:24]}...", "green"
                )
            )
            completed_bytes += r_size

        # Xuất thêm file partitions.csv chuẩn ESP-IDF
        try:
            csv_path = os.path.join(out_dir, "partitions.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write(self.backup_table.to_csv())
        except Exception:
            pass

        manifest = {
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_port": port,
            "baudrate": baud,
            "source_chip": self.backup_source_info.get("chip_line", "ESP32"),
            "source_chip_key": self.backup_source_info.get("chip_name", "ESP32"),
            "source_revision": self.backup_source_info.get("revision", "N/A"),
            "source_crystal": self.backup_source_info.get("crystal", "N/A"),
            "source_mac": self.backup_source_info.get("mac", "N/A"),
            "flash_size_bytes": self.backup_table.flash_size,
            "flash_size_human": format_bytes_human(self.backup_table.flash_size),
            "smart_trim": smart_trim,
            "regions": saved_regions_meta,
        }

        manifest_json_path = os.path.join(out_dir, "backup_manifest.json")
        with open(manifest_json_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        info_txt_path = os.path.join(out_dir, "backup_info.txt")
        report_txt = build_backup_metadata_report(manifest)
        with open(info_txt_path, "w", encoding="utf-8") as f:
            f.write(report_txt)

        safe_after(lambda p=info_txt_path: self.log_backup(f"  + Đã ghi hồ sơ băm & thông tin gốc: {p}", "blue"))
        return manifest

    def _hw_backup_selected_to_folder(self):
        """Sao lưu các phân vùng đang được tích chọn ra thư mục trên máy tính kèm file backup_info.txt."""
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            messagebox.showwarning("Thiết bị đang bận", "Vui lòng đợi tác vụ hiện tại hoàn tất!", parent=self.root)
            return

        selected_regions = [r for r in self._get_all_backup_regions() if r["key"] in self.backup_selected_keys]
        if not selected_regions:
            messagebox.showwarning("Chưa chọn phân vùng", "Vui lòng tích chọn ít nhất 1 phân vùng trong danh sách để sao lưu!", parent=self.root)
            return

        prep = self._prepare_backup_source_port()
        if not prep:
            return
        port, baud = prep

        parent_dir = filedialog.askdirectory(
            title="Chọn thư mục chứa bản sao lưu Firmware & Phân vùng",
            parent=self.root
        )
        if not parent_dir:
            return

        chip_tag = (self.backup_source_info.get("chip_name") or "ESP").replace(" ", "_")
        ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(parent_dir, f"Backup_{chip_tag}_{ts_tag}")
        smart_trim = bool(self.var_backup_smart_trim.get())

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_backup_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, "sao lưu phân vùng từ chip ra máy tính"))
            else:
                safe_after(lambda: self._set_backup_ui_state("disabled"))

            try:
                # Nếu chưa đọc thông tin MAC/chip thực tế từ cổng này, tự động đọc trước khi sao lưu
                if self.backup_source_info.get("mac") in (None, "Chưa xác định", "N/A"):
                    self._probe_chip_and_partition_sync(port, baud, safe_after)

                manifest = self._dump_selected_regions_to_dir_sync(
                    port, baud, out_dir, selected_regions, smart_trim, safe_after,
                    progress_start=20.0, progress_end=98.0
                )
                if manifest:
                    self.backup_last_saved_dir = out_dir
                    self.backup_last_manifest = manifest
                    safe_after(self.refresh_backup_views)
                    safe_after(lambda: self.set_status("Đã sao lưu thành công kèm hồ sơ SHA-256 & MAC gốc!", "success", progress=100))
                    safe_after(lambda: self.log_backup(f"\n>>> HOÀN TẤT SAO LƯU VÀO THƯ MỤC:\n    {out_dir}", "green"))
                    safe_after(lambda: messagebox.showinfo(
                        "Sao lưu thành công",
                        f"Đã sao lưu {len(selected_regions)} phân vùng kèm hồ sơ mã băm (MD5/SHA-256), địa chỉ MAC gốc và thông tin chip tại:\n\n{out_dir}",
                        parent=self.root
                    ))
                else:
                    safe_after(lambda: self.set_status("Sao lưu phân vùng thất bại!", "error", progress=0))
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda m=err_msg: self.log_backup(f">>> [NGOẠI LỆ] {m}", "red"))
                safe_after(lambda: self.set_status("Lỗi trong quá trình sao lưu!", "error", progress=0))
            finally:
                self._is_backup_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))
                else:
                    safe_after(lambda: self._set_backup_ui_state("normal"))

        self.backup_hw_thread = threading.Thread(target=worker, daemon=True)
        self.backup_hw_thread.start()

    def _hw_backup_full_flash_single_file(self):
        """Sao lưu toàn bộ bộ nhớ Flash từ 0x0 đến hết dung lượng Flash ra 1 file .bin duy nhất kèm file .txt thông tin."""
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            messagebox.showwarning("Thiết bị đang bận", "Vui lòng đợi tác vụ hiện tại hoàn tất!", parent=self.root)
            return

        prep = self._prepare_backup_source_port()
        if not prep:
            return
        port, baud = prep

        chip_tag = (self.backup_source_info.get("chip_name") or "ESP32").replace(" ", "_")
        ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = filedialog.asksaveasfilename(
            title="Lưu bản sao lưu Toàn Bộ Flash (0x0 -> Hết Flash)",
            defaultextension=".bin",
            initialfile=f"FullFlash_{chip_tag}_{ts_tag}.bin",
            filetypes=[("Binary Flash Dump (*.bin)", "*.bin"), ("All Files (*.*)", "*.*")],
            parent=self.root
        )
        if not save_path:
            return

        smart_trim = bool(self.var_backup_smart_trim.get())

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_backup_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, "sao lưu toàn bộ Flash (0x0)"))
            else:
                safe_after(lambda: self._set_backup_ui_state("disabled"))

            try:
                if self.backup_source_info.get("mac") in (None, "Chưa xác định", "N/A"):
                    self._probe_chip_and_partition_sync(port, baud, safe_after)

                flash_sz = int(self.backup_table.flash_size)
                safe_after(lambda: self.log_backup(
                    f"\n=== BẮT ĐẦU SAO LƯU TOÀN BỘ FLASH (0x0 -> {format_hex(flash_sz)}, {format_bytes_human(flash_sz)}) ===",
                    "header"
                ))

                def on_stream(line):
                    m = re.search(r"\((\d+)\s*%\)", str(line))
                    if m:
                        pct = int(m.group(1))
                        prog = 15 + int(pct * 0.8)
                        safe_after(lambda p=prog, pc=pct: self.set_status(
                            f"Đang đọc toàn bộ Flash ({pc}%)...", "warning", progress=p
                        ))

                res = run_esptool_command(
                    ["--port", port, "--baud", str(baud), "read-flash", "0x0", format_hex(flash_sz), save_path],
                    progress_callback=on_stream
                )
                if esptool_command_succeeded(res) and os.path.isfile(save_path):
                    with open(save_path, "rb") as f:
                        raw_data = f.read()
                    if smart_trim:
                        final_data = smart_trim_trailing_ff(raw_data, min_size=65536, align_bytes=4096)
                        if len(final_data) != len(raw_data):
                            with open(save_path, "wb") as f:
                                f.write(final_data)
                    else:
                        final_data = raw_data

                    hashes = compute_bytes_hashes(final_data)
                    manifest = {
                        "app_name": APP_NAME,
                        "app_version": APP_VERSION,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source_port": port,
                        "baudrate": baud,
                        "source_chip": self.backup_source_info.get("chip_line", "ESP32"),
                        "source_revision": self.backup_source_info.get("revision", "N/A"),
                        "source_crystal": self.backup_source_info.get("crystal", "N/A"),
                        "source_mac": self.backup_source_info.get("mac", "N/A"),
                        "flash_size_bytes": flash_sz,
                        "flash_size_human": format_bytes_human(flash_sz),
                        "smart_trim": smart_trim,
                        "regions": [{
                            "name": "full_flash",
                            "type": "image",
                            "subtype": "full_dump",
                            "offset": 0,
                            "offset_hex": "0x0",
                            "partition_size": flash_sz,
                            "partition_size_human": format_bytes_human(flash_sz),
                            "saved_size": len(final_data),
                            "saved_size_human": format_bytes_human(len(final_data)),
                            "filename": os.path.basename(save_path),
                            "filepath": save_path,
                            "md5": hashes["md5"],
                            "sha256": hashes["sha256"],
                        }],
                    }
                    info_path = os.path.splitext(save_path)[0] + "_backup_info.txt"
                    with open(info_path, "w", encoding="utf-8") as f:
                        f.write(build_backup_metadata_report(manifest))

                    self.backup_last_manifest = manifest
                    safe_after(lambda: self.set_status("Đã sao lưu toàn bộ Flash kèm file thông tin thành công!", "success", progress=100))
                    safe_after(lambda: self.log_backup(
                        f">>> ĐÃ LƯU FULL FLASH: {save_path}\n"
                        f"    Dung lượng lưu: {format_bytes_human(len(final_data))} | MD5: {hashes['md5']}\n"
                        f"    SHA-256: {hashes['sha256']}\n"
                        f"    File thông tin: {info_path}",
                        "green"
                    ))
                    safe_after(lambda: messagebox.showinfo(
                        "Sao lưu Toàn bộ Flash thành công",
                        f"Đã lưu ảnh nhị phân toàn bộ Flash tại:\n{save_path}\n\n"
                        f"Kèm hồ sơ mã băm SHA-256 & MAC gốc tại:\n{info_path}",
                        parent=self.root
                    ))
                else:
                    safe_after(lambda: self.set_status("Sao lưu toàn bộ Flash thất bại!", "error", progress=0))
                    safe_after(lambda: self.log_backup(">>> [LỖI] Không thể đọc toàn bộ Flash từ chip!", "red"))
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda m=err_msg: self.log_backup(f">>> [NGOẠI LỆ] {m}", "red"))
                safe_after(lambda: self.set_status("Lỗi khi sao lưu toàn bộ Flash!", "error", progress=0))
            finally:
                self._is_backup_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))
                else:
                    safe_after(lambda: self._set_backup_ui_state("normal"))

        self.backup_hw_thread = threading.Thread(target=worker, daemon=True)
        self.backup_hw_thread.start()

    def _action_send_backup_to_flasher_tab(self):
        """Đẩy tự động các file .bin và địa chỉ Offset từ bản sao lưu gần nhất sang 4 hàng của Tab 3 (Nạp Flash)."""
        if not self.backup_last_manifest or not self.backup_last_manifest.get("regions"):
            messagebox.showinfo(
                "Chưa có bản sao lưu",
                "Hãy thực hiện Sao lưu ra thư mục (hoặc Sao lưu Toàn bộ Flash) trước khi đẩy sang Tab Nạp Flash!",
                parent=self.root
            )
            return

        regions = self.backup_last_manifest["regions"][:4]
        if hasattr(self, "flash_file_rows"):
            for idx, row in enumerate(self.flash_file_rows):
                if idx < len(regions):
                    reg = regions[idx]
                    row["var_enable"].set(True)
                    row["path_entry"].delete(0, tk.END)
                    row["path_entry"].insert(0, reg["filepath"])
                    row["offset_entry"].delete(0, tk.END)
                    row["offset_entry"].insert(0, reg["offset_hex"])
                    if hasattr(self, "_update_file_size_display"):
                        self._update_file_size_display(idx)
                else:
                    row["var_enable"].set(False)

        if hasattr(self, "notebook") and hasattr(self, "flasher_tab"):
            self.notebook.select(self.flasher_tab)
        self.set_status(f"Đã nạp {len(regions)} file từ bản sao lưu sang Tab Nạp Flash!", "success")

    def _hw_start_direct_multi_board_clone(self):
        """
        Sao chép trực tiếp từ 1 Board Gốc (hoặc thư mục sao lưu) sang 1 hoặc nhiều Board Đích đang cắm trên máy tính.
        """
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            messagebox.showwarning("Thiết bị đang bận", "Vui lòng đợi tác vụ hiện tại hoàn tất!", parent=self.root)
            return

        target_ports = [p for p, var in self.clone_target_vars.items() if var.get()]
        if not target_ports:
            messagebox.showwarning(
                "Chưa chọn Board Đích",
                "Vui lòng cắm thêm ít nhất 1 mạch ESP đích vào máy tính, bấm 'Làm mới COM' và tích chọn các cổng COM Đích cần nhận sao chép!",
                parent=self.root
            )
            return

        source_mode = self.var_clone_source_mode.get()
        baud_str = self.backup_baud_var.get().strip()
        baud = int(baud_str) if baud_str.isdigit() else 460800
        erase_first = bool(self.var_clone_erase_first.get())
        smart_trim = bool(self.var_backup_smart_trim.get())

        selected_regions = [r for r in self._get_all_backup_regions() if r["key"] in self.backup_selected_keys]
        src_port = ""
        saved_folder_dir = ""

        if source_mode == "live_board":
            if not selected_regions:
                messagebox.showwarning("Chưa chọn phân vùng", "Vui lòng tích chọn các phân vùng cần sao chép ở bảng bên trái!", parent=self.root)
                return
            prep = self._prepare_backup_source_port()
            if not prep:
                return
            src_port, baud = prep
            if src_port.upper() in [t.upper() for t in target_ports]:
                messagebox.showerror("Trùng cổng COM", "Cổng COM Nguồn không được nằm trong danh sách Cổng COM Đích!", parent=self.root)
                return
        else:
            init_dir = self.backup_last_saved_dir if (self.backup_last_saved_dir and os.path.isdir(self.backup_last_saved_dir)) else "."
            saved_folder_dir = filedialog.askdirectory(
                initialdir=init_dir,
                title="Chọn thư mục chứa bản sao lưu (có file backup_manifest.json)",
                parent=self.root
            )
            if not saved_folder_dir:
                return
            manifest_file = os.path.join(saved_folder_dir, "backup_manifest.json")
            if not os.path.isfile(manifest_file):
                messagebox.showerror(
                    "Thiếu hồ sơ sao lưu",
                    f"Không tìm thấy file 'backup_manifest.json' trong thư mục:\n{saved_folder_dir}",
                    parent=self.root
                )
                return

        targets_str = ", ".join(target_ports)
        src_desc = f"Board Gốc ({src_port})" if source_mode == "live_board" else f"Thư mục ({os.path.basename(saved_folder_dir)})"
        if not messagebox.askyesno(
            "Xác nhận Sao chép Trực tiếp (Direct Clone)",
            f"Nguồn sao chép: {src_desc}\n"
            f"Các Board Đích nhận dữ liệu ({len(target_ports)} mạch): {targets_str}\n"
            f"Tốc độ Baud: {baud} bps\n\n"
            f"Bạn có chắc chắn muốn bắt đầu sao chép đồng loạt sang {len(target_ports)} mạch đích không?",
            parent=self.root
        ):
            return

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_backup_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, f"nhân bản sang {len(target_ports)} board đích"))
            else:
                safe_after(lambda: self._set_backup_ui_state("disabled"))

            temp_clone_dir = None
            try:
                if source_mode == "live_board":
                    temp_clone_dir = tempfile.mkdtemp(prefix="esp32_direct_clone_")
                    safe_after(lambda: self.log_backup(
                        f"\n=== BƯỚC 1/2: HÚT DỮ LIỆU TỪ BOARD GỐC ({src_port}) ===", "header"
                    ))
                    if self.backup_source_info.get("mac") in (None, "Chưa xác định", "N/A"):
                        self._probe_chip_and_partition_sync(src_port, baud, safe_after)

                    manifest = self._dump_selected_regions_to_dir_sync(
                        src_port, baud, temp_clone_dir, selected_regions, smart_trim, safe_after,
                        progress_start=10.0, progress_end=50.0
                    )
                    if not manifest or not manifest.get("regions"):
                        safe_after(lambda: self.set_status("Lỗi khi đọc dữ liệu từ Board Gốc! Đã dừng sao chép.", "error", progress=0))
                        return
                else:
                    manifest_file = os.path.join(saved_folder_dir, "backup_manifest.json")
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    for reg in manifest.get("regions", []):
                        reg["filepath"] = os.path.join(saved_folder_dir, reg["filename"])

                write_pairs = []
                for reg in manifest.get("regions", []):
                    fpath = reg.get("filepath")
                    off_hex = reg.get("offset_hex")
                    if fpath and os.path.isfile(fpath) and off_hex:
                        write_pairs.append((off_hex, fpath))

                if not write_pairs:
                    safe_after(lambda: self.set_status("Không có dữ liệu phân vùng hợp lệ để ghi!", "error", progress=0))
                    return

                safe_after(lambda: self.log_backup(
                    f"\n=== BƯỚC 2/2: SAO CHÉP SANG {len(target_ports)} BOARD ĐÍCH ({targets_str}) ===", "header"
                ))

                success_ports = []
                failed_ports = []
                total_targets = len(target_ports)

                for t_idx, t_port in enumerate(target_ports, 1):
                    base_prog = 50.0 + ((t_idx - 1) / total_targets) * 48.0
                    span_prog = 48.0 / total_targets

                    safe_after(lambda tp=t_port, ti=t_idx, tt=total_targets: self.log_backup(
                        f"\n  >>> [{ti}/{tt}] Đang nạp nhân bản vào Board Đích: {tp}..."
                    ))
                    safe_after(lambda tp=t_port, ti=t_idx, tt=total_targets, bp=base_prog: self.set_status(
                        f"Đang chép sang Board Đích {tp} ({ti}/{tt})...", "warning", progress=bp
                    ))

                    args = ["--port", t_port, "--baud", str(baud), "write-flash", "-z"]
                    if erase_first:
                        args.append("--erase-all")
                    for off_hex, fpath in write_pairs:
                        args.extend([off_hex, fpath])

                    def on_target_stream(line, bp=base_prog, sp=span_prog, tp=t_port, ti=t_idx, tt=total_targets):
                        m = re.search(r"\((\d+)\s*%\)", str(line))
                        if m:
                            pct = int(m.group(1))
                            cur_p = bp + (pct / 100.0) * sp
                            safe_after(lambda p=cur_p, port_lbl=tp, pc=pct, i=ti, tot=tt: self.set_status(
                                f"Đang chép sang {port_lbl} [{i}/{tot}] ({pc}%)...", "warning", progress=p
                            ))

                    res = run_esptool_command(args, progress_callback=on_target_stream)
                    if esptool_command_succeeded(res):
                        success_ports.append(t_port)
                        safe_after(lambda tp=t_port: self.log_backup(
                            f"      [THÀNH CÔNG] Board {tp} đã nhận đầy đủ Firmware & Phân vùng!", "green"
                        ))
                    else:
                        failed_ports.append(t_port)
                        safe_after(lambda tp=t_port: self.log_backup(
                            f"      [THẤT BẠI] Không thể ghi dữ liệu vào Board {tp}!", "red"
                        ))

                summary_msg = (
                    f"Hoàn tất nhân bản: Thành công {len(success_ports)}/{total_targets} board"
                    + (f" ({', '.join(success_ports)})" if success_ports else "")
                    + (f" | Lỗi: {', '.join(failed_ports)}" if failed_ports else "")
                )
                final_level = "success" if not failed_ports else ("warning" if success_ports else "error")
                final_prog = 100 if success_ports else 0
                safe_after(lambda m=summary_msg, lv=final_level, p=final_prog: self.set_status(m, lv, progress=p))
                safe_after(lambda m=summary_msg: self.log_backup(f"\n=== KẾT QUẢ NHÂN BẢN ĐA MẠCH: {m} ===", "header"))
                safe_after(lambda m=summary_msg: messagebox.showinfo("Kết quả Sao chép Trực tiếp", m, parent=self.root))
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda m=err_msg: self.log_backup(f">>> [NGOẠI LỆ] {m}", "red"))
                safe_after(lambda: self.set_status("Lỗi trong quá trình sao chép trực tiếp!", "error", progress=0))
            finally:
                if temp_clone_dir and os.path.isdir(temp_clone_dir):
                    try:
                        import shutil
                        shutil.rmtree(temp_clone_dir, ignore_errors=True)
                    except Exception:
                        pass
                self._is_backup_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))
                else:
                    safe_after(lambda: self._set_backup_ui_state("normal"))

        self.backup_hw_thread = threading.Thread(target=worker, daemon=True)
        self.backup_hw_thread.start()
