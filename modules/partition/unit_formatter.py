# -*- coding: utf-8 -*-
"""
ESP32 Partition Engine - Unit Formatter & Converter
Hỗ trợ 3 chế độ hiển thị: DECIMAL (Thập phân trực quan), HEX, và DUAL (Song song).
"""
import re
from enum import Enum


class DisplayMode(Enum):
    DECIMAL = "decimal"  # Mặc định: KB/MB kèm số byte có dấu phẩy
    HEX = "hex"          # Hệ Thập lục phân: 0x...
    DUAL = "dual"        # Song song: Thập phân [HEX]


def parse_size_or_offset(input_str: str) -> int:
    """
    Phân tích chuỗi nhập vào bất kỳ thành số Byte nguyên (integer):
    Hỗ trợ:
      - '0x10000', '0x1000' (HEX)
      - '65536', '65,536' (Bytes)
      - '64K', '64KB', '64 kb' (KiloBytes)
      - '1M', '1MB', '1.5M', '1.5MB' (MegaBytes)
      - '4B', '4 B' (Bytes)
    """
    if input_str is None:
        raise ValueError("Giá trị không được rỗng.")

    text = str(input_str).strip().replace(",", "").replace(" ", "").upper()
    if not text:
        raise ValueError("Giá trị đang để trống.")

    # 1. Định dạng HEX
    if text.startswith("0X"):
        return int(text, 16)

    # 2. Đơn vị MegaBytes (M / MB)
    m_match = re.match(r"^([0-9.]+)(?:MB|M)$", text)
    if m_match:
        val = float(m_match.group(1))
        return int(round(val * 1024 * 1024))

    # 3. Đơn vị KiloBytes (K / KB)
    k_match = re.match(r"^([0-9.]+)(?:KB|K)$", text)
    if k_match:
        val = float(k_match.group(1))
        return int(round(val * 1024))

    # 4. Đơn vị Bytes (B)
    b_match = re.match(r"^([0-9]+)(?:B)?$", text)
    if b_match:
        return int(b_match.group(1))

    # 5. Thử parse trực tiếp số nguyên
    return int(text, 10)


def format_bytes_human(byte_count: int, compact: bool = False) -> str:
    """Định dạng byte thành đơn vị thân thiện: KB, MB, Bytes"""
    if byte_count < 0:
        return "0 B"
    if byte_count >= 1024 * 1024:
        mb = byte_count / (1024 * 1024)
        if mb.is_integer():
            return f"{int(mb)} MB" if compact else f"{int(mb)} MB ({byte_count:,} B)"
        return f"{mb:.2f} MB" if compact else f"{mb:.2f} MB ({byte_count:,} B)"
    elif byte_count >= 1024:
        kb = byte_count / 1024
        if kb.is_integer():
            return f"{int(kb)} KB" if compact else f"{int(kb)} KB ({byte_count:,} B)"
        return f"{kb:.1f} KB" if compact else f"{kb:.1f} KB ({byte_count:,} B)"
    return f"{byte_count:,} B"


def format_hex(value: int, min_digits: int = 5) -> str:
    """Định dạng số nguyên sang chuỗi Hex chuẩn ESP-IDF (ví dụ: 0x10000)"""
    if value < 0:
        return "0x0"
    hex_str = f"{value:X}"
    if len(hex_str) < min_digits:
        hex_str = hex_str.zfill(min_digits)
    return f"0x{hex_str}"


def format_value(value: int, mode: DisplayMode = DisplayMode.DECIMAL, is_size: bool = True) -> str:
    """
    Định dạng giá trị theo DisplayMode được chọn.
    """
    if value is None:
        return "--"

    hex_str = format_hex(value, min_digits=5 if (is_size and value >= 0x10000) else 4)

    if mode == DisplayMode.HEX:
        return hex_str
    elif mode == DisplayMode.DECIMAL:
        if is_size:
            return format_bytes_human(value, compact=False)
        else:
            if value == 0:
                return "0 B"
            kb = value / 1024
            if kb.is_integer():
                return f"{int(kb)} KB ({value:,} B)"
            return f"{value:,} B"
    else:  # DUAL
        if is_size:
            human = format_bytes_human(value, compact=True)
            return f"{human} [{hex_str}]"
        else:
            if value >= 1024 and (value % 1024 == 0):
                return f"{value // 1024} KB [{hex_str}]"
            return f"{value:,} B [{hex_str}]"


def align_up(value: int, alignment: int) -> int:
    """Làm tròn lên bội số của alignment"""
    remainder = value % alignment
    if remainder == 0:
        return value
    return value + (alignment - remainder)


def sector_count(size_bytes: int) -> int:
    """Số lượng sector 4KB mà vùng nhớ chiếm dụng"""
    if size_bytes <= 0:
        return 0
    return (size_bytes + 4095) // 4096
