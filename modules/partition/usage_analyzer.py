# -*- coding: utf-8 -*-
"""
Bộ phân tích dung lượng sử dụng thực tế (Đã dùng / Còn trống) cho từng phân vùng ESP32.
Hỗ trợ:
  - Phân vùng mã thực thi (App & Bootloader) qua cấu trúc header ESP Image (0xE9).
  - Bảng phân vùng hệ thống (Partition Table 4 KB).
  - Phân vùng NVS qua bảng trạng thái Page & Bitmap ESP-IDF.
  - Các phân vùng dữ liệu khác (SPIFFS, LittleFS, FAT, Coredump, PHY, OTA Data, vùng tùy biến)
    bằng đếm trang/khối đã ghi dữ liệu (khác 0xFF).
"""
from __future__ import annotations

import struct
from typing import Callable

from modules.nvs_util import (
    ENTRY_STATE_WRITTEN,
    NVS_ENTRIES_PER_PAGE,
    NVS_PAGE_SIZE,
    PAGE_STATE_EMPTY,
    VALID_PAGE_STATES,
)
from modules.partition.partition_model import MAGIC_BYTES, MD5_PARTITION_BEGIN, PartitionTable

_ALL_FF_32 = b"\xff" * 32
_ALL_FF_256 = b"\xff" * 256


def compute_raw_non_ff_bytes(raw_bytes: bytes, subtype: str = "") -> int:
    """Đếm tổng dung lượng các khối dữ liệu đã ghi (không chứa toàn byte 0xFF)."""
    if not raw_bytes:
        return 0
    st = str(subtype or "").strip().lower()
    chunk_size = 32 if (st in ("phy", "ota") or len(raw_bytes) <= 16384) else 256
    blank = _ALL_FF_32 if chunk_size == 32 else _ALL_FF_256

    used = 0
    total = len(raw_bytes)
    full_end = (total // chunk_size) * chunk_size
    for off in range(0, full_end, chunk_size):
        if raw_bytes[off : off + chunk_size] != blank:
            used += chunk_size
    if full_end < total:
        tail = raw_bytes[full_end:]
        if any(b != 0xFF for b in tail):
            used += len(tail)
    return min(total, used)


def compute_nvs_used_bytes(raw_bytes: bytes) -> int:
    """Tính dung lượng đang sử dụng trong phân vùng NVS dựa trên header trang và bitmap entry."""
    if not raw_bytes:
        return 0
    total = len(raw_bytes)
    if total < NVS_PAGE_SIZE:
        return compute_raw_non_ff_bytes(raw_bytes, "nvs")

    page_count = total // NVS_PAGE_SIZE
    saw_valid_nvs = False
    used = 0
    for idx in range(page_count):
        base = idx * NVS_PAGE_SIZE
        page = raw_bytes[base : base + NVS_PAGE_SIZE]
        state = struct.unpack_from("<I", page, 0)[0]
        if state == PAGE_STATE_EMPTY:
            saw_valid_nvs = True
            continue
        if state in VALID_PAGE_STATES:
            saw_valid_nvs = True
            bitmap = page[32:64]
            written_slots = 0
            for slot_i in range(NVS_ENTRIES_PER_PAGE):
                bits = (bitmap[slot_i >> 2] >> ((slot_i & 3) * 2)) & 0x03
                if bits == ENTRY_STATE_WRITTEN:
                    written_slots += 1
            used += 64 + (written_slots * 32)
        else:
            used += compute_raw_non_ff_bytes(page, "nvs")

    if not saw_valid_nvs:
        return compute_raw_non_ff_bytes(raw_bytes, "nvs")
    return min(total, used)


def compute_partition_table_used_bytes(raw_pt: bytes) -> int:
    """Tính kích thước thực tế của các bản ghi đang dùng trong 4 KB bảng phân vùng."""
    if not raw_pt:
        return 0
    used = 0
    limit = min(len(raw_pt), 0xC00)
    for off in range(0, limit, 32):
        chunk = raw_pt[off : off + 32]
        if len(chunk) < 32 or chunk == _ALL_FF_32:
            break
        if chunk[:2] == MD5_PARTITION_BEGIN[:2]:
            used += 32
            break
        if chunk[:2] == MAGIC_BYTES:
            used += 32
        else:
            break
    return min(len(raw_pt), used)


def compute_esp_image_used_bytes(
    offset: int,
    max_size: int,
    read_fn: Callable[[int, int], bytes],
) -> int:
    """
    Tính kích thước chính xác (tính theo byte) của ảnh firmware / bootloader ESP32
    bằng cách đọc header 24-byte (0xE9) và duyệt chuỗi segment header mà không cần đọc toàn bộ phân vùng.
    Trả về -1 nếu vùng không trống nhưng không mang cấu trúc 0xE9 chuẩn (để fallback đọc thô).
    """
    if max_size < 24:
        return 0
    hdr = read_fn(offset, 24)
    if not hdr or len(hdr) < 24:
        return -1

    if all(b == 0xFF for b in hdr):
        probe_sz = min(256, max_size)
        first_page = hdr if probe_sz <= 24 else read_fn(offset, probe_sz)
        if first_page and all(b == 0xFF for b in first_page):
            return 0
        return -1

    if hdr[0] != 0xE9:
        return -1

    seg_count = hdr[1]
    hash_appended = hdr[23]
    if seg_count == 0 or seg_count > 32:
        return -1

    pos = offset + 24
    for _ in range(seg_count):
        if (pos - offset) + 8 > max_size:
            return -1
        seg_hdr = read_fn(pos, 8)
        if not seg_hdr or len(seg_hdr) < 8:
            return -1
        _load_addr, data_len = struct.unpack("<II", seg_hdr)
        if data_len > max_size or (pos - offset) + 8 + data_len > max_size:
            return -1
        pos += 8 + data_len

    raw_len = pos - offset
    padded_len = ((raw_len + 16) // 16) * 16
    if hash_appended == 1:
        padded_len += 32
    return min(max_size, max(0, padded_len))


def compute_data_used_bytes(raw_bytes: bytes, subtype: str = "") -> int:
    """Tính dung lượng đã dùng cho một phân vùng dữ liệu dựa trên subtype."""
    if not raw_bytes:
        return 0
    st = str(subtype or "").strip().lower()
    if st == "nvs":
        return compute_nvs_used_bytes(raw_bytes)
    return compute_raw_non_ff_bytes(raw_bytes, st)


def measure_partition_table_usage_with_reader(
    table: PartitionTable,
    read_fn: Callable[[int, int], bytes],
    *,
    raw_pt: bytes | None = None,
    progress_cb: Callable[[int, str], None] | None = None,
) -> None:
    """
    Đo và cập nhật mức sử dụng thực tế (used_size, usage_measured) cho Bootloader,
    Partition Table và toàn bộ phân vùng trong bảng qua hàm đọc Flash read_fn(offset, size).
    """
    boot_off = int(getattr(table, "bootloader_offset", 0x1000) or 0)
    pt_off = int(getattr(table, "part_table_offset", 0x8000) or 0x8000)
    boot_sz = max(0, pt_off - boot_off)

    total_steps = max(1, len(table.entries) + 2)
    step = 0

    def _notify(label: str):
        if progress_cb is not None:
            pct = min(99, max(1, int(round((step / total_steps) * 100))))
            progress_cb(pct, label)

    # 1. Bootloader
    if boot_sz > 0:
        _notify("Đang đo dung lượng Bootloader...")
        bl_used = compute_esp_image_used_bytes(boot_off, boot_sz, read_fn)
        if bl_used < 0:
            raw_bl = read_fn(boot_off, boot_sz)
            bl_used = compute_raw_non_ff_bytes(raw_bl, "bootloader")
        table.bootloader_used_size = max(0, min(boot_sz, bl_used))
        table.bootloader_usage_measured = True
    step += 1

    # 2. Partition Table
    _notify("Đang đo dung lượng Partition Table...")
    pt_blob = raw_pt if (raw_pt and len(raw_pt) >= 32) else read_fn(pt_off, 0x1000)
    table.part_table_used_size = compute_partition_table_used_bytes(pt_blob or b"")
    table.part_table_usage_measured = True
    step += 1

    # 3. Các phân vùng người dùng
    for entry in table.entries:
        _notify(f"Đang đo phân vùng '{entry.name}'...")
        if entry.size <= 0:
            entry.used_size = 0
            entry.usage_measured = True
            step += 1
            continue

        if entry.type_str.lower() == "app":
            app_used = compute_esp_image_used_bytes(entry.offset, entry.size, read_fn)
            if app_used < 0:
                raw_app = read_fn(entry.offset, entry.size)
                app_used = compute_raw_non_ff_bytes(raw_app, entry.subtype_str)
            entry.used_size = max(0, min(entry.size, app_used))
            entry.usage_measured = True
        else:
            raw_data = read_fn(entry.offset, entry.size)
            entry.used_size = max(0, min(entry.size, compute_data_used_bytes(raw_data, entry.subtype_str)))
            entry.usage_measured = True
        step += 1
