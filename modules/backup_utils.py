# -*- coding: utf-8 -*-
"""
Các hàm tiện ích sao lưu, mã băm và suy đoán địa chỉ bộ nhớ cho ESP32 (v1.5).
"""
import hashlib
import re
from datetime import datetime
from modules.config import APP_NAME, APP_VERSION
from modules.partition.unit_formatter import align_up, format_hex, format_bytes_human

SENSITIVE_DATA_SUBTYPES = frozenset({"otadata", "ota", "phy", "nvs_keys", "efuse"})


def sanitize_filename_token(text: str | None, default: str = "UNKNOWN") -> str:
    """Làm sạch chuỗi tên chip/phân vùng để dùng an toàn trong tên tệp Windows."""
    raw = str(text or "").strip()
    if not raw or raw.lower() in ("n/a", "chưa xác định", "chưa rõ", "unknown", "none"):
        return default
    cleaned = re.sub(r'[<>:"/\\|?*\s]+', "_", raw)
    cleaned = re.sub(r"_+", "_", cleaned).strip("._ ")
    return cleaned or default


def normalize_mac_filename_token(mac: str | None) -> str:
    """Chuẩn hóa địa chỉ MAC bỏ dấu ':' thành chuỗi HEX viết hoa 12 ký tự (fallback NOMAC)."""
    raw = str(mac or "").strip()
    if not raw or raw.lower() in ("n/a", "chưa xác định", "chưa rõ", "unknown", "none"):
        return "NOMAC"
    hex_only = re.sub(r"[^0-9A-Fa-f]", "", raw).upper()
    if len(hex_only) != 12:
        return "NOMAC"
    return hex_only


def format_full_flash_filename(
    chip_name: str | None,
    mac: str | None,
    ts_tag: str | None = None,
) -> str:
    """Định dạng tên file sao lưu Full Flash: <tên chip gốc>_<MAC gốc>_Full - <yyyymmdd_hhmmss>.bin."""
    chip_tok = sanitize_filename_token(chip_name, default="ESP32")
    mac_tok = normalize_mac_filename_token(mac)
    ts = ts_tag or datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{chip_tok}_{mac_tok}_Full - {ts}.bin"


def format_partition_backup_filename(
    chip_name: str | None,
    mac: str | None,
    part_name: str | None,
    offset: int,
    ts_tag: str | None = None,
) -> str:
    """Định dạng tên file sao lưu phân vùng: <tên chip gốc>_<MAC gốc>_<tên phân vùng>_<offset> - <yyyymmdd_hhmmss>.bin."""
    chip_tok = sanitize_filename_token(chip_name, default="ESP32")
    mac_tok = normalize_mac_filename_token(mac)
    part_tok = sanitize_filename_token(part_name, default="region")
    off_tok = f"0x{int(offset):X}"
    ts = ts_tag or datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{chip_tok}_{mac_tok}_{part_tok}_{off_tok} - {ts}.bin"


def is_non_firmware_data_region(region: dict | None) -> tuple[bool, str]:
    """
    Kiểm tra xem vùng phân vùng trên Tab 5 có phải dữ liệu (không phải firmware/hệ thống) hay không.
    Trả về (allowed, level):
      - (False, "blocked") cho Bootloader, Partition Table và mọi phân vùng app (factory/ota_*/test).
      - (True, "sensitive") cho phân vùng data nhạy cảm (otadata/ota/phy/nvs_keys/efuse).
      - (True, "normal") cho các phân vùng data thông thường (nvs/spiffs/littlefs/fat/coredump/...).
    """
    if not region:
        return False, "empty"
    r_type = str(region.get("type") or "").strip().lower()
    r_sub = str(region.get("subtype") or "").strip().lower()
    r_key = str(region.get("key") or "")
    if r_type != "data" or r_key in ("__bootloader__", "__part_table__"):
        return False, "blocked"
    if r_sub in SENSITIVE_DATA_SUBTYPES:
        return True, "sensitive"
    return True, "normal"


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
        f"HỒ SƠ SAO LƯU PHẦN CỨNG & FIRMWARE - {APP_NAME.upper()} v{APP_VERSION}",
        "",
        "THÔNG TIN PHẦN CỨNG & MẠNG BOARD GỐC:",
        f"  Thời gian sao lưu     : {manifest.get('timestamp', 'N/A')}",
        f"  Cổng COM sao lưu      : {manifest.get('source_port', 'N/A')} (@ {manifest.get('baudrate', 'N/A')} bps)",
        f"  Dòng Chip gốc         : {manifest.get('source_chip', 'N/A')}",
        f"  Phiên bản Silicon     : {manifest.get('source_revision', 'N/A')}",
        f"  Tần số thạch anh      : {manifest.get('source_crystal', 'N/A')}",
        f"  Địa chỉ MAC gốc       : {manifest.get('source_mac', 'N/A')}",
        f"  Kích thước Flash chip : {manifest.get('flash_size_human', 'N/A')} ({manifest.get('flash_size_bytes', 0):,} Bytes)",
        f"  Chế độ cắt trống 0xFF : {'Bật (Smart Trim 4KB)' if manifest.get('smart_trim') else 'Tắt (Giữ nguyên kích thước vùng)'}",
        "",
        "DANH SÁCH CÁC PHÂN VÙNG / TỆP NHỊ PHÂN ĐÃ SAO LƯU:",
    ]

    regions = manifest.get("regions", [])
    for idx, reg in enumerate(regions, 1):
        lines.extend([
            "",
            f"[{idx:02d}] Phân vùng: {reg.get('name', 'unknown')} "
            f"(Type: {reg.get('type', 'N/A')} | SubType: {reg.get('subtype', 'N/A')})",
            f"     • Tên file .bin         : {reg.get('filename', 'N/A')}",
            f"     • Địa chỉ bắt đầu       : {reg.get('offset_hex', '0x0')} ({reg.get('offset', 0):,} Bytes)",
            f"     • Dung lượng phân vùng  : {reg.get('partition_size_human', 'N/A')} ({reg.get('partition_size', 0):,} Bytes)",
            f"     • Dung lượng file lưu   : {reg.get('saved_size_human', 'N/A')} ({reg.get('saved_size', 0):,} Bytes)",
            f"     • Mã băm MD5            : {reg.get('md5', 'N/A')}",
            f"     • Mã băm SHA-256        : {reg.get('sha256', 'N/A')}",
        ])

    if regions:
        pair_args = " ".join(f"{r.get('offset_hex', '0x0')} \"{r.get('filename', '')}\"" for r in regions)
        lines.extend([
            "",
            "LỆNH ESPTOOL KHÔI PHỤC / NHÂN BẢN MẪU:",
            f"  esptool --port <COM_ĐÍCH> --baud 460800 write-flash -z {pair_args}",
        ])

    return "\n".join(lines) + "\n"
