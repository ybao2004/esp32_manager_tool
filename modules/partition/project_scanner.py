# -*- coding: utf-8 -*-
"""
ESP32 Partition Engine - Smart ESP-IDF Project Scanner
Quét và đối chiếu kích thước file .bin thực tế với dung lượng từng phân vùng.
"""
from __future__ import annotations

import os
import json
import re
from typing import Optional, Dict, Any, Tuple

from modules.partition.partition_model import PartitionTable, PartitionEntry
from modules.partition.unit_formatter import parse_size_or_offset


FLASH_SIZE_MAP = {
    "1MB": 1 * 1024 * 1024,
    "2MB": 2 * 1024 * 1024,
    "4MB": 4 * 1024 * 1024,
    "8MB": 8 * 1024 * 1024,
    "16MB": 16 * 1024 * 1024,
    "32MB": 32 * 1024 * 1024,
}


class ProjectScanResult:
    def __init__(self):
        self.project_name: str = ""
        self.project_dir: str = ""
        self.target_chip: str = "esp32"
        self.flash_size: int = 4 * 1024 * 1024
        self.part_table_offset: int = 0x8000
        self.partition_csv_path: Optional[str] = None
        self.partition_bin_path: Optional[str] = None
        self.flasher_args_path: Optional[str] = None
        self.partition_table: Optional[PartitionTable] = None
        self.bin_files_info: Dict[int, Dict[str, Any]] = {}  # offset -> {path, size, name}


def scan_esp_project(project_dir: str) -> Optional[ProjectScanResult]:
    """
    Quét tự động thư mục dự án ESP-IDF / PlatformIO để trích xuất cấu hình phân vùng
    và kích thước file thực tế.
    """
    if not os.path.isdir(project_dir):
        return None

    res = ProjectScanResult()
    res.project_dir = os.path.abspath(project_dir)
    res.project_name = os.path.basename(res.project_dir)

    # 1. Đọc sdkconfig nếu có
    sdkconfig_path = os.path.join(res.project_dir, "sdkconfig")
    if os.path.isfile(sdkconfig_path):
        try:
            with open(sdkconfig_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                # Chip target
                m_chip = re.search(r'CONFIG_IDF_TARGET="([^"]+)"', content)
                if m_chip:
                    res.target_chip = m_chip.group(1)

                # Flash size
                m_size = re.search(r'CONFIG_ESPTOOLPY_FLASHSIZE(?:_(\d+MB))?="?([^"\r\n]+)"?', content)
                if m_size:
                    size_key = m_size.group(1) or m_size.group(2)
                    size_key = size_key.upper().strip()
                    if size_key in FLASH_SIZE_MAP:
                        res.flash_size = FLASH_SIZE_MAP[size_key]

                # Partition table offset
                m_off = re.search(r'CONFIG_PARTITION_TABLE_OFFSET=(0x[0-9a-fA-F]+|\d+)', content)
                if m_off:
                    res.part_table_offset = int(m_off.group(1), 0)
        except Exception:
            pass

    # 2. Tìm file CSV phân vùng
    csv_candidates = ["partitions.csv", "partitions_two_ota.csv", "partitions_singleapp.csv"]
    for c in csv_candidates:
        p = os.path.join(res.project_dir, c)
        if os.path.isfile(p):
            res.partition_csv_path = p
            break

    # 3. Tìm file nhị phân partition-table.bin trong build
    build_dir = os.path.join(res.project_dir, "build")
    if os.path.isdir(build_dir):
        bin_p = os.path.join(build_dir, "partition_table", "partition-table.bin")
        if os.path.isfile(bin_p):
            res.partition_bin_path = bin_p

        # 4. Tìm flasher_args.json trong build để biết file .bin nào nạp vào đâu
        flash_args_p = os.path.join(build_dir, "flasher_args.json")
        if os.path.isfile(flash_args_p):
            res.flasher_args_path = flash_args_p
            try:
                with open(flash_args_p, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)
                    flash_files = data.get("flash_files", {})
                    for off_str, rel_path in flash_files.items():
                        off_val = parse_size_or_offset(off_str)
                        full_bin_path = os.path.normpath(os.path.join(build_dir, rel_path))
                        if os.path.isfile(full_bin_path):
                            sz = os.path.getsize(full_bin_path)
                            res.bin_files_info[off_val] = {
                                "path": full_bin_path,
                                "name": os.path.basename(full_bin_path),
                                "size": sz
                            }
            except Exception:
                pass

    # 5. Khởi tạo PartitionTable từ CSV hoặc Binary
    table = PartitionTable(flash_size=res.flash_size, part_table_offset=res.part_table_offset)
    loaded = False

    if res.partition_csv_path:
        try:
            with open(res.partition_csv_path, "r", encoding="utf-8", errors="ignore") as f:
                table.from_csv(f.read())
                loaded = True
        except Exception:
            pass

    if not loaded and res.partition_bin_path:
        try:
            with open(res.partition_bin_path, "rb") as f:
                table.from_binary(f.read())
                loaded = True
        except Exception:
            pass

    # 6. Gán used_size từ các file .bin đã build vào từng phân vùng
    if loaded and res.bin_files_info:
        for entry in table.entries:
            if entry.offset in res.bin_files_info:
                entry.used_size = res.bin_files_info[entry.offset]["size"]

    res.partition_table = table if loaded else None
    return res
