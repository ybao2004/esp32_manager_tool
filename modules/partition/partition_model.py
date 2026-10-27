# -*- coding: utf-8 -*-
"""
ESP32 Partition Engine - Partition Model & Binary Parser
Tuân thủ 100% chuẩn kỹ thuật của ESP-IDF (gen_esp32part.py).
"""
from __future__ import annotations

import binascii
import hashlib
import struct
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any

from modules.partition.unit_formatter import parse_size_or_offset, align_up, format_hex


MAGIC_BYTES = b'\xaa\x50'
MD5_PARTITION_BEGIN = b'\xeb\xeb' + b'\xff' * 14
PARTITION_TABLE_OFFSET_DEFAULT = 0x8000
PARTITION_TABLE_SIZE_DEFAULT = 0x1000
MAX_PARTITION_TABLE_DATA_LEN = 0xC00  # 3K (96 entries), để dành 1K cho chữ ký bảo mật

# Các loại Type
TYPE_APP = 0x00
TYPE_DATA = 0x01
TYPE_BOOTLOADER = 0x02
TYPE_PARTITION_TABLE = 0x03

TYPE_NAME_TO_INT = {
    'app': TYPE_APP,
    'data': TYPE_DATA,
    'bootloader': TYPE_BOOTLOADER,
    'partition_table': TYPE_PARTITION_TABLE,
}
TYPE_INT_TO_NAME = {v: k for k, v in TYPE_NAME_TO_INT.items()}

# Các loại SubType
SUBTYPE_APP_FACTORY = 0x00
SUBTYPE_APP_TEST = 0x20
SUBTYPE_APP_OTA_MIN = 0x10
SUBTYPE_APP_OTA_MAX = 0x1F

SUBTYPES_MAP = {
    TYPE_APP: {
        'factory': 0x00,
        'test': 0x20,
    },
    TYPE_DATA: {
        'ota': 0x00,
        'phy': 0x01,
        'nvs': 0x02,
        'coredump': 0x03,
        'nvs_keys': 0x04,
        'efuse': 0x05,
        'fat': 0x81,
        'spiffs': 0x82,
        'littlefs': 0x83,
    }
}
# Bổ sung ota_0 đến ota_15
for slot in range(16):
    SUBTYPES_MAP[TYPE_APP][f'ota_{slot}'] = SUBTYPE_APP_OTA_MIN + slot

# Cờ Flags
FLAG_ENCRYPTED = (1 << 0)
FLAG_READONLY = (1 << 1)


@dataclass
class PartitionEntry:
    name: str
    type_str: str          # 'app' hoặc 'data'
    subtype_str: str       # 'factory', 'nvs', 'spiffs', etc.
    offset: int = 0
    size: int = 0
    flags_str: str = ""    # 'encrypted', 'readonly', hoặc ''
    
    # Các thuộc tính theo dõi hiển thị
    used_size: int = 0     # Dung lượng thực tế file .bin chiếm dụng (nếu quét từ dự án)
    is_system: bool = False       # Đánh dấu phân vùng hệ thống (Bootloader, Partition Table)
    is_unallocated: bool = False  # Đánh dấu vùng trống chưa phân bổ

    @property
    def end_offset(self) -> int:
        return self.offset + self.size

    @property
    def free_size(self) -> int:
        if self.used_size > 0:
            return max(0, self.size - self.used_size)
        return self.size

    @property
    def usage_percent(self) -> float:
        if self.size <= 0:
            return 0.0
        if self.used_size <= 0:
            return 0.0
        return min(100.0, (self.used_size / self.size) * 100.0)

    @property
    def type_int(self) -> int:
        return TYPE_NAME_TO_INT.get(self.type_str.lower(), TYPE_DATA)

    @property
    def subtype_int(self) -> int:
        sub_map = SUBTYPES_MAP.get(self.type_int, {})
        val = sub_map.get(self.subtype_str.lower(), None)
        if val is not None:
            return val
        try:
            return int(self.subtype_str, 0)
        except (ValueError, TypeError):
            return 0

    @property
    def flags_int(self) -> int:
        flag = 0
        f_lower = self.flags_str.lower()
        if 'encrypted' in f_lower:
            flag |= FLAG_ENCRYPTED
        if 'readonly' in f_lower:
            flag |= FLAG_READONLY
        return flag

    def to_csv_line(self) -> str:
        f_str = self.flags_str if self.flags_str else ""
        return f"{self.name}, {self.type_str}, {self.subtype_str}, {format_hex(self.offset)}, {format_hex(self.size)}, {f_str}"

    def clone(self) -> PartitionEntry:
        return PartitionEntry(
            name=self.name,
            type_str=self.type_str,
            subtype_str=self.subtype_str,
            offset=self.offset,
            size=self.size,
            flags_str=self.flags_str,
            used_size=self.used_size,
            is_system=self.is_system,
            is_unallocated=self.is_unallocated
        )


class PartitionTable:
    def __init__(self, flash_size: int = 4 * 1024 * 1024, part_table_offset: int = 0x8000, bootloader_offset: int = 0x1000, target_chip: str = "esp32"):
        self.flash_size: int = flash_size
        self.part_table_offset: int = part_table_offset
        self.bootloader_offset: int = bootloader_offset
        self.target_chip: str = target_chip
        self.entries: List[PartitionEntry] = []

    def clear(self):
        self.entries.clear()

    def add_entry(self, entry: PartitionEntry):
        self.entries.append(entry)

    def remove_entry_at(self, index: int):
        if 0 <= index < len(self.entries):
            del self.entries[index]

    def move_entry(self, from_idx: int, to_idx: int):
        if 0 <= from_idx < len(self.entries) and 0 <= to_idx < len(self.entries):
            item = self.entries.pop(from_idx)
            self.entries.insert(to_idx, item)

    def sort_by_offset(self):
        self.entries.sort(key=lambda x: x.offset)

    def auto_pack_and_align(self):
        """
        Tự động tính toán lại toàn bộ Offset nối tiếp nhau từ sau Partition Table,
        đảm bảo chuẩn 4KB cho Data và chuẩn 64KB cho App mà không bị chồng lấn hay lãng phí.
        """
        current_offset = self.part_table_offset + PARTITION_TABLE_SIZE_DEFAULT
        for entry in self.entries:
            if entry.type_str.lower() == 'app':
                current_offset = align_up(current_offset, 0x10000)  # 64 KB
            else:
                current_offset = align_up(current_offset, 0x1000)   # 4 KB
            entry.offset = current_offset
            current_offset += entry.size

    def validate(self) -> List[str]:
        """
        Kiểm tra toàn diện tính hợp lệ của bảng phân vùng theo chuẩn ESP-IDF.
        Trả về danh sách các cảnh báo / lỗi (nếu có).
        """
        errors = []
        if not self.entries:
            return ["Bảng phân vùng đang rỗng."]

        # 1. Trùng tên
        names = [e.name for e in self.entries]
        dup_names = set(n for n in names if names.count(n) > 1)
        for d in dup_names:
            errors.append(f"Tên phân vùng '{d}' bị trùng lặp.")

        # 2. Vùng cấm và chồng lấn Partition Table
        pt_start = self.part_table_offset
        pt_end = pt_start + PARTITION_TABLE_SIZE_DEFAULT

        sorted_entries = sorted(self.entries, key=lambda x: x.offset)
        last_end = 0

        has_ota_app = False
        has_otadata = False

        for entry in sorted_entries:
            # Tên dài quá 16 byte
            if len(entry.name.encode('utf-8')) > 16:
                errors.append(f"Tên phân vùng '{entry.name}' dài hơn 16 bytes (tối đa 15 ký tự ASCII).")

            # Dung lượng phải là bội số của 4KB
            if entry.size % 0x1000 != 0:
                errors.append(f"Phân vùng '{entry.name}' có Size {entry.size} không chia hết cho 4 KB (0x1000).")

            # Căn chỉnh Offset
            if entry.type_str.lower() == 'app':
                has_ota_app = has_ota_app or entry.subtype_str.lower().startswith('ota_')
                if entry.offset % 0x10000 != 0:
                    errors.append(f"Phân vùng App '{entry.name}' có Offset {format_hex(entry.offset)} không chia hết cho 64 KB (0x10000).")
                if entry.offset < 0x10000:
                    errors.append(f"Phân vùng App '{entry.name}' có Offset {format_hex(entry.offset)} nằm trong vùng cấm < 0x10000.")
            else:
                if entry.offset % 0x1000 != 0:
                    errors.append(f"Phân vùng Data '{entry.name}' có Offset {format_hex(entry.offset)} không chia hết cho 4 KB (0x1000).")
                if entry.subtype_str.lower() == 'ota':
                    has_otadata = True
                    if entry.size != 0x2000:
                        errors.append(f"Phân vùng otadata '{entry.name}' bắt buộc phải có dung lượng đúng 8 KB (0x2000).")

            # Chồng lấn Partition Table
            if not (entry.end_offset <= pt_start or entry.offset >= pt_end):
                errors.append(f"Phân vùng '{entry.name}' ({format_hex(entry.offset)}-{format_hex(entry.end_offset)}) bị đè vào Bảng phân vùng ({format_hex(pt_start)}-{format_hex(pt_end)}).")

            # Chồng lấn giữa các phân vùng
            if entry.offset < last_end:
                errors.append(f"Phân vùng '{entry.name}' tại {format_hex(entry.offset)} bị chồng lấn vào phân vùng trước (kết thúc tại {format_hex(last_end)}).")

            last_end = max(last_end, entry.end_offset)

        # Kiểm tra otadata khi có ota app
        if has_ota_app and not has_otadata:
            errors.append("Bảng phân vùng có khe ota_X nhưng thiếu phân vùng 'otadata' (Type: data, SubType: ota, Size: 8K).")

        # Kiểm tra vượt quá Flash size
        if last_end > self.flash_size:
            errors.append(f"Tổng dung lượng phân vùng (chiếm đến {format_hex(last_end)}) vượt quá dung lượng chip Flash đã chọn ({format_hex(self.flash_size)}).")

        return errors

    def get_layout_with_unallocated(self) -> List[PartitionEntry]:
        """
        Tạo danh sách layout đầy đủ cho sơ đồ MiniTool:
        Gồm: Bootloader -> Partition Table -> Các phân vùng -> Các khoảng Unallocated xen kẽ hoặc cuối Flash.
        """
        layout: List[PartitionEntry] = []

        # 1. Bootloader
        boot_off = self.bootloader_offset
        pt_off = self.part_table_offset
        if pt_off > boot_off:
            layout.append(PartitionEntry(
                name="Bootloader",
                type_str="bootloader",
                subtype_str="primary",
                offset=boot_off,
                size=pt_off - boot_off,
                is_system=True
            ))

        # 2. Partition Table (0x8000 - 0x9000)
        layout.append(PartitionEntry(
            name="Partition Table",
            type_str="partition_table",
            subtype_str="primary",
            offset=pt_off,
            size=PARTITION_TABLE_SIZE_DEFAULT,
            is_system=True
        ))

        # 3. Duyệt các phân vùng người dùng và chèn Unallocated
        sorted_entries = sorted(self.entries, key=lambda x: x.offset)
        current_cursor = pt_off + PARTITION_TABLE_SIZE_DEFAULT

        for entry in sorted_entries:
            if entry.offset > current_cursor:
                # Có khoảng trống chưa phân bổ
                gap = entry.offset - current_cursor
                layout.append(PartitionEntry(
                    name="Unallocated",
                    type_str="free",
                    subtype_str="free",
                    offset=current_cursor,
                    size=gap,
                    is_unallocated=True
                ))
            layout.append(entry)
            current_cursor = max(current_cursor, entry.end_offset)

        # 4. Khoảng trống cuối Flash
        if current_cursor < self.flash_size:
            layout.append(PartitionEntry(
                name="Unallocated",
                type_str="free",
                subtype_str="free",
                offset=current_cursor,
                size=self.flash_size - current_cursor,
                is_unallocated=True
            ))

        return layout

    def to_csv(self) -> str:
        """Xuất bảng phân vùng ra nội dung file partitions.csv chuẩn ESP-IDF"""
        lines = [
            "# ESP-IDF Partition Table",
            "# Name,   Type, SubType, Offset,  Size, Flags"
        ]
        for e in self.entries:
            lines.append(e.to_csv_line())
        return "\n".join(lines) + "\n"

    def from_csv(self, csv_text: str):
        """Đọc và nạp dữ liệu từ chuỗi CSV của ESP-IDF"""
        self.clear()
        lines = csv_text.strip().splitlines()

        raw_records = []
        for line_no, raw_line in enumerate(lines, start=1):
            line = raw_line.strip()
            if not line or line.startswith('#'):
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) < 5:
                continue

            name = parts[0]
            type_str = parts[1]
            subtype_str = parts[2]
            raw_offset = parts[3]
            raw_size = parts[4]
            flags_str = parts[5] if len(parts) > 5 else ""

            size_val = parse_size_or_offset(raw_size)
            offset_val = parse_size_or_offset(raw_offset) if raw_offset else None

            raw_records.append((name, type_str, subtype_str, offset_val, size_val, flags_str))

        # Phục hồi các offset để trống (, ,)
        last_end = self.part_table_offset + PARTITION_TABLE_SIZE_DEFAULT
        for name, type_str, subtype_str, offset_val, size_val, flags_str in raw_records:
            if offset_val is None:
                pad_to = 0x10000 if type_str.lower() == 'app' else 0x1000
                offset_val = align_up(last_end, pad_to)
            
            entry = PartitionEntry(
                name=name,
                type_str=type_str,
                subtype_str=subtype_str,
                offset=offset_val,
                size=size_val,
                flags_str=flags_str
            )
            self.add_entry(entry)
            last_end = entry.end_offset

    def to_binary(self) -> bytes:
        """
        Biên dịch bảng phân vùng sang file nhị phân 32-byte struct kèm MD5 Checksum
        tương đương công cụ gen_esp32part.py
        """
        records = bytearray()
        md5 = hashlib.md5()

        for e in self.entries:
            # 32 bytes struct:
            # 2B magic (0xAA50) | 1B type | 1B subtype | 4B offset | 4B size | 16B name | 4B flags
            magic = MAGIC_BYTES
            t = e.type_int
            st = e.subtype_int
            off = e.offset
            sz = e.size
            name_bytes = e.name.encode('utf-8')[:16].ljust(16, b'\x00')
            flags = e.flags_int

            rec = struct.pack('<2sBBLL16sL', magic, t, st, off, sz, name_bytes, flags)
            records.extend(rec)
            md5.update(rec)

        # Ghi MD5 checksum entry (32 bytes)
        # [0..1]: 0xEB 0xEB, [2..15]: 0xFF, [16..31]: 16 bytes MD5 digest
        md5_record = bytearray(MD5_PARTITION_BEGIN) + md5.digest()
        records.extend(md5_record)

        # Padding 0xFF cho đủ kích thước sector (0x1000 = 4096 bytes)
        if len(records) < PARTITION_TABLE_SIZE_DEFAULT:
            records.extend(b'\xff' * (PARTITION_TABLE_SIZE_DEFAULT - len(records)))

        return bytes(records)

    def from_binary(self, data: bytes):
        """Đọc và giải mã trực tiếp từ file nhị phân partition-table.bin hoặc 4KB đọc từ ESP32"""
        self.clear()
        if len(data) < 32:
            raise ValueError("Dữ liệu nhị phân quá ngắn (nhỏ hơn 32 bytes).")

        md5 = hashlib.md5()
        for i in range(0, len(data), 32):
            chunk = data[i:i + 32]
            if len(chunk) < 32:
                break
            if chunk == b'\xff' * 32:
                break  # Gặp vùng kết thúc bảng phân vùng

            # Kiểm tra dòng MD5
            if chunk[:2] == MD5_PARTITION_BEGIN[:2]:
                # Đây là dòng MD5 checksum, kết thúc đọc các partition entries
                break

            magic, t, st, off, sz, name_bytes, flags = struct.unpack('<2sBBLL16sL', chunk)
            if magic != MAGIC_BYTES:
                continue

            md5.update(chunk)
            name = name_bytes.split(b'\x00')[0].decode('utf-8', errors='replace')
            type_str = TYPE_INT_TO_NAME.get(t, f'0x{t:02x}')

            # Tìm tên SubType
            sub_map = SUBTYPES_MAP.get(t, {})
            subtype_str = None
            for s_name, s_val in sub_map.items():
                if s_val == st:
                    subtype_str = s_name
                    break
            if subtype_str is None:
                subtype_str = f'0x{st:02x}'

            flags_list = []
            if flags & FLAG_ENCRYPTED:
                flags_list.append('encrypted')
            if flags & FLAG_READONLY:
                flags_list.append('readonly')
            flags_str = ", ".join(flags_list)

            entry = PartitionEntry(
                name=name,
                type_str=type_str,
                subtype_str=subtype_str,
                offset=off,
                size=sz,
                flags_str=flags_str
            )
            self.add_entry(entry)
