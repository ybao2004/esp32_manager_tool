# -*- coding: utf-8 -*-
"""
ESP32 Partition Engine Package
Cung cấp mô hình dữ liệu bảng phân vùng, bộ phân tích nhị phân, định dạng đơn vị và quét dự án.
"""
from modules.partition.unit_formatter import (
    DisplayMode, parse_size_or_offset, format_bytes_human, format_hex,
    format_value, align_up, sector_count
)
from modules.partition.chip_database import (
    ChipInfo, CHIP_FAMILY_DATABASE, get_chip_info
)
from modules.partition.partition_model import (
    PartitionEntry, PartitionTable,
    TYPE_APP, TYPE_DATA, TYPE_BOOTLOADER, TYPE_PARTITION_TABLE,
    SUBTYPES_MAP, FLAG_ENCRYPTED, FLAG_READONLY
)
from modules.partition.project_scanner import (
    ProjectScanResult, scan_esp_project
)

__all__ = [
    'DisplayMode', 'parse_size_or_offset', 'format_bytes_human', 'format_hex',
    'format_value', 'align_up', 'sector_count',
    'ChipInfo', 'CHIP_FAMILY_DATABASE', 'get_chip_info',
    'PartitionEntry', 'PartitionTable',
    'TYPE_APP', 'TYPE_DATA', 'TYPE_BOOTLOADER', 'TYPE_PARTITION_TABLE',
    'SUBTYPES_MAP', 'FLAG_ENCRYPTED', 'FLAG_READONLY',
    'ProjectScanResult', 'scan_esp_project',
]
