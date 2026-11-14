# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - esptool Integration & Deep Hardware Inspection Utilities
"""
import codecs
from contextlib import contextmanager, redirect_stdout, redirect_stderr
import hashlib
from importlib import metadata
import io
import re
import struct
import sys
import threading
import time

esptool = None
_esptool_load_lock = threading.Lock()
_esptool_import_attempted = False
_READ_FLASH_SUBCHUNK_BYTES = 0x200000  # 2 MB mỗi chặng đọc + kiểm tra MD5 trực tiếp từ stub


def _install_resilient_read_flash_patch(esptool_mod) -> None:
    """
    Gia cố ESPLoader.read_flash để chống nghẽn gói SLIP trên USB-Serial/JTAG (FIFO 64 byte)
    và chia các lệnh đọc lớn (như Full Flash 16 MB) thành các chặng 2 MB có tự động thử lại.
    """
    if not isinstance(getattr(esptool_mod, "__file__", None), str):
        return
    loader_mod = getattr(esptool_mod, "loader", None)
    loader_cls = getattr(loader_mod, "ESPLoader", None) if loader_mod else None
    util_mod = getattr(esptool_mod, "util", None)
    if loader_cls is None or not hasattr(loader_cls, "read_flash"):
        return

    orig_read_flash = loader_cls.read_flash
    if getattr(orig_read_flash, "_esp_mgr_resilient", False):
        return

    orig_slip_reader = getattr(loader_mod, "slip_reader", None)
    fatal_err_cls = getattr(util_mod, "FatalError", RuntimeError)
    hexify_fn = getattr(util_mod, "hexify", lambda b: b.hex())

    def _detect_panic_msg(raw_buf: bytes) -> None:
        m = re.search(
            rb"(?:G?uru Meditation Error: (?:Core \d panic'ed \(([a-zA-Z ]*)\))?|"
            rb"F?atal exception \(\d+\): (?:([a-zA-Z ]*)?.*epc)?)",
            raw_buf,
            re.DOTALL,
        )
        if m:
            cause = next((g.decode("utf-8", errors="ignore") for g in (m.group(1), m.group(2)) if g), "")
            suffix = f" ({cause})" if cause else ""
            raise fatal_err_cls(f"Guru Meditation Error detected{suffix}.")

    def _iter_resilient_slip_packets(port, trace_fn, idle_nudge_fn=None, max_nudges=32):
        """Bộ tách gói SLIP giữ nguyên trạng thái partial khi cần gửi ACK mồi giải phóng FIFO."""
        partial = None
        in_escape = False
        successful_slip = False
        nudges = 0
        while True:
            waiting = port.inWaiting()
            read_bytes = port.read(1 if waiting == 0 else waiting)
            if read_bytes == b"":
                if idle_nudge_fn is not None and nudges < max_nudges and idle_nudge_fn():
                    nudges += 1
                    continue
                if partial is None:
                    msg = (
                        "Serial data stream stopped: Possible serial noise or corruption."
                        if successful_slip
                        else "No serial data received."
                    )
                else:
                    msg = f"Packet content transfer stopped (received {len(partial)} bytes)."
                trace_fn(msg)
                raise fatal_err_cls(msg)

            nudges = 0
            for b_int in read_bytes:
                if partial is None:
                    if b_int == 0xC0:
                        partial = bytearray()
                    else:
                        rem = port.read(port.inWaiting())
                        _detect_panic_msg(read_bytes + rem)
                        raise fatal_err_cls(
                            f"Invalid head of packet (0x{b_int:02x}): Possible serial noise or corruption."
                        )
                elif in_escape:
                    in_escape = False
                    if b_int == 0xDC:
                        partial.append(0xC0)
                    elif b_int == 0xDD:
                        partial.append(0xDB)
                    else:
                        rem = port.read(port.inWaiting())
                        _detect_panic_msg(read_bytes + rem)
                        raise fatal_err_cls(f"Invalid SLIP escape (0xdb, 0x{b_int:02x}).")
                elif b_int == 0xDB:
                    in_escape = True
                elif b_int == 0xC0:
                    yield bytes(partial)
                    partial = None
                    successful_slip = True
                else:
                    partial.append(b_int)

    def _read_flash_subchunk(esp, sub_off, sub_len, total_off, total_len, base_done, progress_fn):
        port = esp._port
        sector_size = getattr(esp, "FLASH_SECTOR_SIZE", 4096) or 4096
        orig_timeout = getattr(port, "timeout", 3)
        nudge_state = {"active": False, "sent": 0}

        def _on_idle_nudge():
            if not nudge_state["active"]:
                return False
            ack_val = min(sub_len, nudge_state["sent"] + sector_size)
            esp.write(struct.pack("<I", ack_val))
            return True

        try:
            esp._slip_reader = _iter_resilient_slip_packets(
                port,
                esp.trace,
                idle_nudge_fn=_on_idle_nudge,
                max_nudges=32,
            )
            esp.check_command(
                "read flash",
                esp.ESP_CMDS["READ_FLASH"],
                struct.pack("<IIII", sub_off, sub_len, sector_size, 64),
            )
            nudge_state["active"] = True
            port.timeout = 0.15

            chunks = []
            sub_done = 0
            while sub_done < sub_len:
                p = esp.read()
                if sub_done + len(p) < sub_len and len(p) < sector_size:
                    raise fatal_err_cls(
                        f"Corrupt data, expected {sector_size:#x} bytes but received {len(p):#x} bytes."
                    )
                chunks.append(p)
                sub_done += len(p)
                nudge_state["sent"] = sub_done
                esp.write(struct.pack("<I", sub_done))
                if progress_fn and (sub_done % 1024 == 0 or sub_done == sub_len):
                    progress_fn(base_done + sub_done, total_len, total_off)

            if sub_done > sub_len:
                raise fatal_err_cls("Read more than expected.")

            port.timeout = 0.5
            digest_frame = esp.read()
            if len(digest_frame) != 16:
                raise fatal_err_cls(f"Expected digest, got: {hexify_fn(digest_frame)}")
            data = b"".join(chunks)
            expected_digest = hexify_fn(digest_frame).upper()
            digest = hashlib.md5(data).hexdigest().upper()
            if digest != expected_digest:
                raise fatal_err_cls(f"Digest mismatch: expected {expected_digest}, got {digest}")
            return data
        finally:
            try:
                port.timeout = orig_timeout
            except Exception:
                pass
            if callable(orig_slip_reader):
                try:
                    esp._slip_reader = orig_slip_reader(port, esp.trace)
                except Exception:
                    pass

    def resilient_read_flash(self, offset, length, progress_fn=None) -> bytes:
        port = getattr(self, "_port", None)
        is_real_serial = (
            getattr(self, "IS_STUB", False)
            and port is not None
            and all(callable(getattr(port, m, None)) for m in ("read", "write", "inWaiting"))
            and callable(orig_slip_reader)
            and hasattr(self, "ESP_CMDS")
            and "READ_FLASH" in getattr(self, "ESP_CMDS", {})
        )
        if not is_real_serial:
            return orig_read_flash(self, offset, length, progress_fn=progress_fn)
        if length <= 0:
            return b""

        wdt_fn = getattr(self, "disable_watchdogs", None)
        if callable(wdt_fn):
            try:
                wdt_fn()
            except Exception:
                pass

        all_chunks = []
        done = 0
        while done < length:
            sub_len = min(_READ_FLASH_SUBCHUNK_BYTES, length - done)
            sub_off = offset + done
            last_exc = None
            for attempt in range(3):
                if attempt > 0:
                    try:
                        time.sleep(0.1)
                        self.flush_input()
                        self.sync()
                    except Exception:
                        pass
                try:
                    part = _read_flash_subchunk(
                        self, sub_off, sub_len, offset, length, done, progress_fn
                    )
                    all_chunks.append(part)
                    done += len(part)
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
            if last_exc is not None:
                raise last_exc
        return b"".join(all_chunks)

    resilient_read_flash._esp_mgr_resilient = True
    loader_cls.read_flash = resilient_read_flash


def _ensure_esptool():
    """Lazy-import esptool khi cần chạy lệnh, nhưng vẫn tôn trọng object giả lập trong test."""
    global esptool, _esptool_import_attempted
    if esptool is not None:
        return esptool
    with _esptool_load_lock:
        if esptool is not None:
            return esptool
        if not _esptool_import_attempted:
            _esptool_import_attempted = True
            try:
                import esptool as _esptool_mod
                esptool = _esptool_mod
                _install_resilient_read_flash_patch(_esptool_mod)
            except ImportError:
                esptool = None
        return esptool


def preload_esptool() -> bool:
    """Nạp trước esptool ở luồng nền sau khi cửa sổ chính đã hiển thị."""
    return _ensure_esptool() is not None


def parse_esptool_progress_percent(line: str) -> float | None:
    """Trích xuất phần trăm tiến trình từ log esptool v4 '(45 %)' hoặc v5 '[...]  45.3%'."""
    if not line:
        return None
    cleaned = clean_esptool_ansi(str(line))
    for pattern in (
        r"\((\d{1,3}(?:\.\d+)?)\s*%\)",
        r"\]\s*(\d{1,3}(?:\.\d+)?)\s*%",
        r"(?:^|\s)(\d{1,3}(?:\.\d+)?)\s*%(?:\s|$)",
    ):
        match = re.search(pattern, cleaned)
        if match:
            try:
                val = float(match.group(1))
                if 0.0 <= val <= 100.0:
                    return val
            except ValueError:
                continue
    return None

from modules.config import CHIP_DATABASE
from modules.partition.partition_model import PartitionTable
from modules.stream_util import StreamInterceptor

esptool_lock = threading.Lock()
_deep_inspection_state = threading.local()
_active_esp_lock = threading.Lock()
_active_esp_instances: set = set()


def _register_active_esp(esp_obj) -> None:
    if esp_obj is None:
        return
    with _active_esp_lock:
        _active_esp_instances.add(esp_obj)


def _unregister_active_esp(esp_obj) -> None:
    if esp_obj is None:
        return
    with _active_esp_lock:
        _active_esp_instances.discard(esp_obj)


def abort_active_esptool() -> int:
    """Đóng khẩn cấp các cổng Serial đang do esptool nắm giữ để thoát tiến trình an toàn."""
    closed = 0
    with _active_esp_lock:
        snapshot = list(_active_esp_instances)
        _active_esp_instances.clear()
    for esp_obj in snapshot:
        port_obj = getattr(esp_obj, "_port", None)
        if port_obj is not None:
            for m_name in ("cancel_read", "cancel_write"):
                fn = getattr(port_obj, m_name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
            try:
                if getattr(port_obj, "is_open", True) and hasattr(port_obj, "close"):
                    port_obj.close()
                    closed += 1
            except Exception:
                pass
    return closed

_ESPTOOL_V4_ARGUMENTS = {
    "flash-id": "flash_id",
    "read-mac": "read_mac",
    "read-flash": "read_flash",
    "erase-flash": "erase_flash",
    "erase-region": "erase_region",
    "write-flash": "write_flash",
    "merge-bin": "merge_bin",
    "--pad-to-size": "--fill-flash-size",
}

_SPI_MODES = {
    0: "QIO",
    1: "QOUT",
    2: "DIO",
    3: "DOUT",
    4: "FAST_READ",
    5: "SLOW_READ",
}

_SPI_SPEEDS = {
    0x0: "40 MHz",
    0x1: "26 MHz",
    0x2: "20 MHz",
    0x5: "20 MHz",
    0xF: "80 MHz",
}

_SPI_SIZES = {
    0x0: "1 MB",
    0x1: "2 MB",
    0x2: "4 MB",
    0x3: "8 MB",
    0x4: "16 MB",
    0x5: "32 MB",
    0x6: "64 MB",
    0x7: "128 MB",
}

_IMAGE_CHIP_IDS = {
    0x0000: "ESP32",
    0x0002: "ESP32-S2",
    0x0005: "ESP32-C3",
    0x0009: "ESP32-S3",
    0x000C: "ESP32-C2",
    0x000D: "ESP32-C6",
    0x0010: "ESP32-H2",
    0x0012: "ESP32-P4",
    0x0014: "ESP32-C61",
    0x0017: "ESP32-C5",
    0x0019: "ESP32-H21",
    0x001C: "ESP32-H4",
}

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|(?:\[\d+[A-JKSTfmsu])+")


def clean_esptool_ansi(text: str) -> str:
    """Loại bỏ mã điều khiển ANSI và chuỗi xóa dòng [1A[2K của esptool v5."""
    if not text:
        return ""
    cleaned = _ANSI_ESCAPE_RE.sub("", str(text))
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    return cleaned


@contextmanager
def esptool_deep_inspection_context(capture_boot_log=True, boot_log_duration=2.2, progress_callback=None):
    """Bật chế độ thu thập chuyên sâu (Flash Header, Partition, Security, eFuse, Boot Log) trong phiên flash-id."""
    prev_enabled = getattr(_deep_inspection_state, "enabled", False)
    prev_boot = getattr(_deep_inspection_state, "capture_boot_log", True)
    prev_dur = getattr(_deep_inspection_state, "boot_log_duration", 2.2)
    prev_cb = getattr(_deep_inspection_state, "progress_callback", None)
    _deep_inspection_state.enabled = True
    _deep_inspection_state.capture_boot_log = capture_boot_log
    _deep_inspection_state.boot_log_duration = boot_log_duration
    _deep_inspection_state.progress_callback = progress_callback
    try:
        yield
    finally:
        _deep_inspection_state.enabled = prev_enabled
        _deep_inspection_state.capture_boot_log = prev_boot
        _deep_inspection_state.boot_log_duration = prev_dur
        _deep_inspection_state.progress_callback = prev_cb


def _esptool_major_version():
    """Best-effort major-version detection; unknown installs use current v5 syntax."""
    mod = _ensure_esptool()
    version_text = getattr(mod, "__version__", "") if mod is not None else ""
    if not version_text:
        try:
            version_text = metadata.version("esptool")
        except metadata.PackageNotFoundError:
            version_text = ""
    match = re.match(r"\D*(\d+)", str(version_text))
    return int(match.group(1)) if match else 5


def _normalize_esptool_args(args):
    """Translate canonical v5 CLI names when running against esptool v4."""
    normalized = [str(arg) for arg in args]
    if _esptool_major_version() < 5:
        normalized = [_ESPTOOL_V4_ARGUMENTS.get(arg, arg) for arg in normalized]
    return normalized


def esptool_command_succeeded(output):
    """Return True only when the wrapper recorded an esptool exit code of 0."""
    if not isinstance(output, str):
        return False
    match = re.search(r"\[Esptool exited with code:\s*(-?\d+)\]", output, re.IGNORECASE)
    return bool(match and int(match.group(1)) == 0 and "fatal error" not in output.lower())


def decode_flash_device_id(device_str: str) -> str:
    """Giải mã mã JEDEC Device ID (VD: 4018 -> Loại 0x40 SPI/QPI NOR, Dung lượng 0x18 = 16 MB)."""
    if not device_str:
        return "N/A"
    clean = str(device_str).strip().lower().replace("0x", "")
    if len(clean) == 4 and all(c in "0123456789abcdef" for c in clean):
        mem_type = int(clean[:2], 16)
        cap_code = int(clean[2:], 16)
        type_map = {
            0x20: "SPI NOR (3.3V)",
            0x40: "Dual/Quad SPI NOR (3.3V)",
            0x60: "Dual/Quad SPI NOR (1.8V)",
            0x70: "High-Perf Quad SPI NOR",
            0x80: "Octal/QPI NOR",
        }
        t_desc = type_map.get(mem_type, f"Type 0x{mem_type:02X}")
        if 0x10 <= cap_code <= 0x20:
            mb = (1 << cap_code) / (1024 * 1024)
            mbit = int(mb * 8)
            cap_str = f"{mb:g} MB ({mbit} Mbit)" if mb >= 1 else f"{int(mb * 1024)} KB"
            return f"0x{clean.upper()} ({t_desc}, Mã dung lượng 0x{cap_code:02X} = {cap_str})"
    return device_str


def _read_c_str(raw: bytes) -> str:
    """Trích xuất chuỗi ASCII/UTF-8 kết thúc bằng null từ mảng byte C."""
    if not raw:
        return ""
    nul_idx = raw.find(b"\x00")
    if nul_idx != -1:
        raw = raw[:nul_idx]
    if all(b == 0xFF for b in raw):
        return ""
    text = raw.decode("utf-8", errors="replace").strip()
    return text if all(32 <= ord(ch) <= 126 for ch in text) else ""


def parse_esp_image_header(data: bytes) -> dict:
    """Giải mã cấu trúc 24-byte esp_image_header_t của Bootloader hoặc Application."""
    if not data or len(data) < 24 or data[0] != 0xE9:
        return {}
    seg_count = data[1]
    spi_mode_code = data[2]
    spi_speed_code = data[3] & 0x0F
    spi_size_code = (data[3] >> 4) & 0x0F
    entry_addr = struct.unpack_from("<I", data, 4)[0]
    wp_pin = data[8]
    chip_id = struct.unpack_from("<H", data, 12)[0]
    min_rev_legacy = data[14]
    min_rev_full = struct.unpack_from("<H", data, 15)[0]
    max_rev_full = struct.unpack_from("<H", data, 17)[0]
    hash_appended = bool(data[23] == 1)

    if min_rev_full > 0 and min_rev_full != 0xFFFF:
        min_rev_str = f"v{min_rev_full // 100}.{min_rev_full % 100}"
    else:
        min_rev_str = f"v{min_rev_legacy}.0"

    if 0 < max_rev_full < 0xFFFF:
        max_rev_str = f"v{max_rev_full // 100}.{max_rev_full % 100}"
    else:
        max_rev_str = None

    return {
        "segment_count": seg_count,
        "spi_mode": _SPI_MODES.get(spi_mode_code, f"0x{spi_mode_code:02X}"),
        "spi_speed": _SPI_SPEEDS.get(spi_speed_code, f"0x{spi_speed_code:X}"),
        "spi_size_header": _SPI_SIZES.get(spi_size_code, f"0x{spi_size_code:X}"),
        "entry_addr": f"0x{entry_addr:08X}",
        "wp_pin": "Tắt (0xEE)" if wp_pin == 0xEE else f"GPIO {wp_pin}",
        "image_chip_id": f"0x{chip_id:04X} ({_IMAGE_CHIP_IDS.get(chip_id, 'Unknown')})",
        "min_chip_rev": min_rev_str,
        "max_chip_rev": max_rev_str,
        "hash_appended": hash_appended,
    }


def parse_esp_bootloader_desc(data: bytes) -> dict:
    """Giải mã cấu trúc esp_bootloader_desc_t (offset 0x20 của Bootloader ESP-IDF v5+)."""
    if not data or len(data) < 0x20 + 64:
        return {}
    base = 0x20
    if data[base] != 0x50:
        return {}
    version = data[base + 3]
    idf_ver = _read_c_str(data[base + 8 : base + 40])
    date_time = _read_c_str(data[base + 40 : base + 64])
    res = {"bootloader_version": version}
    if idf_ver:
        res["bootloader_idf_ver"] = idf_ver
    if date_time:
        res["bootloader_compile_time"] = date_time
    return res


def parse_esp_app_desc(data: bytes) -> dict:
    """Giải mã cấu trúc esp_app_desc_t (magic 0xABCD5432 tại offset 0x20 của phân vùng App)."""
    if not data or len(data) < 0x20 + 184:
        return {}
    magic = b"\x32\x54\xcd\xab"
    idx = data.find(magic)
    if idx == -1 or idx + 184 > len(data):
        return {}

    secure_version = struct.unpack_from("<I", data, idx + 4)[0]
    version = _read_c_str(data[idx + 16 : idx + 48])
    project_name = _read_c_str(data[idx + 48 : idx + 80])
    compile_time = _read_c_str(data[idx + 80 : idx + 96])
    compile_date = _read_c_str(data[idx + 96 : idx + 112])
    idf_ver = _read_c_str(data[idx + 112 : idx + 144])
    sha256_raw = data[idx + 144 : idx + 176]
    min_blk_rev = struct.unpack_from("<H", data, idx + 176)[0]
    max_blk_rev = struct.unpack_from("<H", data, idx + 178)[0]
    mmu_exp = data[idx + 180]

    res = {"secure_version": secure_version}
    if project_name:
        res["app_project_name"] = project_name
    if version:
        res["app_version"] = version
    if compile_date or compile_time:
        res["app_compile_time"] = f"{compile_date} {compile_time}".strip()
    if idf_ver:
        res["app_idf_ver"] = idf_ver
    if any(b not in (0x00, 0xFF) for b in sha256_raw):
        res["app_elf_sha256"] = sha256_raw.hex()
    if min_blk_rev > 0 and min_blk_rev != 0xFFFF:
        res["app_min_efuse_blk_rev"] = f"v{min_blk_rev // 100}.{min_blk_rev % 100}"
    if 0 < max_blk_rev < 0xFFFF:
        res["app_max_efuse_blk_rev"] = f"v{max_blk_rev // 100}.{max_blk_rev % 100}"
    if 10 <= mmu_exp <= 20:
        res["app_mmu_page_size"] = f"{(1 << mmu_exp) // 1024} KB"
    return res


def scan_drom_strings_for_metadata(data: bytes) -> dict:
    """Quét vùng .rodata (DROM) đầu phân vùng App để tìm cấu hình PSRAM, FQBN Arduino, Board và Ngoại vi."""
    if not data:
        return {}
    text = data.decode("latin-1", errors="ignore")
    meta = {}

    # 1. Tìm chuỗi Arduino FQBN đầy đủ (VD: esp32:esp32:esp32s3:...PSRAM=opi...)
    m_fqbn = re.search(r"esp32:esp32:([A-Za-z0-9_\-]+):([^\x00\r\n]{8,360})", text)
    if m_fqbn:
        fqbn_opts = m_fqbn.group(2).strip(", ")
        meta["fw_fqbn"] = f"esp32:esp32:{m_fqbn.group(1)}:{fqbn_opts}"
        opt_map = {}
        for item in fqbn_opts.split(","):
            if "=" in item:
                k, v = item.split("=", 1)
                opt_map[k.strip()] = v.strip()
        psram_opt = opt_map.get("PSRAM", "").lower()
        if psram_opt == "opi":
            meta["fw_psram_mode_cfg"] = "Octal PSRAM (8-line / X8 OPI MSPI)"
        elif psram_opt == "qspi":
            meta["fw_psram_mode_cfg"] = "Quad PSRAM (4-line / X4 QSPI)"
        elif psram_opt in ("enabled", "enable"):
            meta["fw_psram_mode_cfg"] = "SPI PSRAM (Enabled)"
        if opt_map.get("FlashMode"):
            meta["fw_flash_mode_cfg"] = opt_map["FlashMode"]
        if opt_map.get("CPUFreq"):
            meta["fw_cpu_freq_cfg"] = f"{opt_map['CPUFreq']} MHz"
        if opt_map.get("DebugLevel"):
            meta["fw_debug_level"] = opt_map["DebugLevel"]

    # 2. Nhận diện driver PSRAM từ đường dẫn/chuỗi ESP-IDF trong DROM
    if "hex_psram" in text:
        meta["fw_psram_driver"] = "Hex PSRAM (16-line / X16 MSPI)"
    elif "oct_psram" in text or "octal_psram" in text or "PSRAM=opi" in text:
        meta["fw_psram_driver"] = "Octal PSRAM (8-line / X8 OPI MSPI)"
    elif "quad_psram" in text or "PSRAM=qspi" in text:
        meta["fw_psram_driver"] = "Quad PSRAM (4-line / X4 QSPI)"
    elif "esp_psram" in text:
        meta["fw_psram_driver"] = "ESP-IDF esp_psram (Quad/SPI)"

    # 3. Nhận diện tên Board mục tiêu
    m_board = re.search(r"board=([A-Za-z0-9_\-]+)", text)
    if m_board:
        meta["fw_board_name"] = m_board.group(1)
    else:
        m_ap_board = re.search(r"(\d+\.\d+_ESP32[A-Z0-9_\-]+)", text)
        m_dev_board = re.search(r"\b(ESP32[A-Z0-9]+_[A-Z0-9_]+)\b", text)
        if m_ap_board:
            ap_name = m_ap_board.group(1).strip("_")
            meta["fw_board_name"] = f"{ap_name} ({m_dev_board.group(1)})" if m_dev_board else ap_name
        elif m_dev_board:
            meta["fw_board_name"] = m_dev_board.group(1)

    # 4. Nhận diện chuỗi Ngoại vi trong Firmware (LCD / Touch / GUI / SD / Audio)
    peripherals = []
    if re.search(r"(?:0x9341|ili9341)", text, re.IGNORECASE):
        peripherals.append("LCD TFT ILI9341 (SPI)")
    elif re.search(r"st7789", text, re.IGNORECASE):
        peripherals.append("LCD ST7789 (SPI)")
    if re.search(r"(?:touch\s+ic|ft6336|ft6236|cst816|gt911)", text, re.IGNORECASE):
        peripherals.append("Cảm ứng (Touch I2C)")
    m_lvgl = re.search(r"LVGL\s+v\d+", text)
    if m_lvgl:
        peripherals.append(f"Đồ họa {m_lvgl.group(0)}")
    if re.search(r"SD card\s+Test|SD_MMC", text, re.IGNORECASE):
        peripherals.append("Khe thẻ nhớ SD")
    if re.search(r"Microphone", text, re.IGNORECASE):
        peripherals.append("Microphone / Audio")
    if peripherals:
        meta["fw_peripherals"] = " · ".join(peripherals)

    return meta


def _probe_efuse_details(esp) -> dict:
    """Đọc thêm các thanh ghi eFuse định danh (Unique ID 128-bit, PSRAM_CAP, TEMP, PKG_VERSION, Power, USB)."""
    details = {}
    try:
        blk1 = getattr(esp, "EFUSE_BLOCK1_ADDR", None)
        rd_base = getattr(esp, "EFUSE_RD_REG_BASE", None)
        chip_name = getattr(esp, "CHIP_NAME", "")

        # Đọc USB VID/PID nếu esptool hỗ trợ (ESP32-S3 / C3 / C6 / P4...)
        usb_vid_pid_fn = getattr(esp, "get_usb_vid_pid", None)
        if callable(usb_vid_pid_fn):
            try:
                vid_pid = usb_vid_pid_fn()
                if isinstance(vid_pid, (tuple, list)) and len(vid_pid) == 2 and all(vid_pid):
                    details["usb_vid_pid"] = f"VID 0x{int(vid_pid[0]):04X} : PID 0x{int(vid_pid[1]):04X}"
            except Exception:
                pass

        # Đọc 128-bit OPTIONAL_UNIQUE_ID tại đầu BLOCK2 (BLOCK1 + 24 bytes) cho các dòng S3/C3/C6/P4/H2/C5
        if blk1 and chip_name in ("ESP32-P4", "ESP32-S3", "ESP32-C3", "ESP32-C6", "ESP32-H2", "ESP32-C5", "ESP32-C61"):
            uid_words = [esp.read_reg(blk1 + 24 + i * 4) for i in range(4)]
            uid_bytes = struct.pack("<IIII", *uid_words)
            if any(b != 0 for b in uid_bytes):
                details["unique_id_128"] = "-".join(
                    uid_bytes[i : i + 4].hex().upper() for i in range(0, 16, 4)
                )

        if chip_name == "ESP32-P4" and blk1:
            w2 = esp.read_reg(blk1 + 8)
            blk_minor = (w2 >> 8) & 0x07
            blk_major = (w2 >> 11) & 0x03
            psram_cap = (w2 >> 13) & 0x07
            temp_code = (w2 >> 16) & 0x03
            psram_vendor = (w2 >> 18) & 0x03
            pkg_ver = (w2 >> 20) & 0x07
            details["efuse_pkg_version"] = f"{pkg_ver} (QFN56 / Standard)" if pkg_ver == 0 else str(pkg_ver)
            details["efuse_blk_version"] = f"v{blk_major}.{blk_minor}"
            temp_map = {0: "Chuẩn (-40°C ~ 85°C)", 1: "Mở rộng (-40°C ~ 105°C)", 2: "Cao (-40°C ~ 125°C)"}
            details["efuse_temp_rating"] = temp_map.get(temp_code, f"Code {temp_code}")
            if psram_cap > 0:
                p_cap_map = {1: 8, 2: 2, 3: 16, 4: 4, 5: 32, 6: 64}
                details["efuse_psram_mb"] = p_cap_map.get(psram_cap, psram_cap)
                details["efuse_psram_vendor"] = f"0x{psram_vendor:02X}"
            if rd_base:
                w5 = esp.read_reg(rd_base + 20)
                pwr_sel = (w5 >> 18) & 0x01
                details["efuse_power_src"] = "DCDC" if pwr_sel == 1 else "LDO"
        elif chip_name == "ESP32-S3":
            if callable(getattr(esp, "get_pkg_version", None)):
                pkg_ver = esp.get_pkg_version()
                pkg_map = {0: "0 (QFN56)", 1: "1 (LGA56 / PICO-1)"}
                details["efuse_pkg_version"] = pkg_map.get(pkg_ver, str(pkg_ver))
            if callable(getattr(esp, "get_blk_version_major", None)) and callable(getattr(esp, "get_blk_version_minor", None)):
                details["efuse_blk_version"] = f"v{esp.get_blk_version_major()}.{esp.get_blk_version_minor()}"
            if callable(getattr(esp, "_get_efuse_flash_voltage", None)):
                try:
                    vdd = esp._get_efuse_flash_voltage()
                    if vdd:
                        details["efuse_vdd_spi"] = str(vdd)
                except Exception:
                    pass
            if callable(getattr(esp, "get_psram_cap", None)):
                p_cap = esp.get_psram_cap()
                p_cap_map = {1: 8, 2: 2, 3: 16, 4: 4}
                if p_cap in p_cap_map:
                    details["efuse_psram_mb"] = p_cap_map[p_cap]
            if callable(getattr(esp, "get_psram_vendor", None)):
                pv = esp.get_psram_vendor()
                if pv:
                    details["efuse_psram_vendor"] = str(pv)
            if callable(getattr(esp, "get_flash_vendor", None)):
                fv = esp.get_flash_vendor()
                if fv:
                    details["efuse_flash_vendor"] = str(fv)
        else:
            # Các dòng ESP32 khác (C3/C6/S2/C2/H2...) nếu có get_pkg_version / get_blk_version
            if callable(getattr(esp, "get_pkg_version", None)):
                try:
                    details["efuse_pkg_version"] = str(esp.get_pkg_version())
                except Exception:
                    pass
            if callable(getattr(esp, "get_blk_version_major", None)) and callable(getattr(esp, "get_blk_version_minor", None)):
                try:
                    details["efuse_blk_version"] = f"v{esp.get_blk_version_major()}.{esp.get_blk_version_minor()}"
                except Exception:
                    pass
    except Exception:
        pass
    return details


def _capture_boot_log_from_open_port(ser_port, max_duration=2.2) -> str:
    """Đón trực tiếp luồng Boot Log từ cổng Serial đang mở ngay thời điểm chip vừa thoát Reset."""
    if ser_port is None or not getattr(ser_port, "is_open", False):
        return ""
    orig_timeout = getattr(ser_port, "timeout", 0.1)
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    chunks = []
    start_t = time.monotonic()
    last_rx_t = start_t
    saw_app_init = False
    saw_app_main = False

    try:
        ser_port.timeout = 0.04
        while True:
            now = time.monotonic()
            elapsed = now - start_t
            if elapsed >= max_duration:
                break
            try:
                waiting = getattr(ser_port, "in_waiting", 0) or 0
                data = ser_port.read(max(256, min(4096, waiting)))
            except Exception:
                break

            if data:
                last_rx_t = time.monotonic()
                text = decoder.decode(data)
                chunks.append(text)
                joined_tail = "".join(chunks[-6:])
                if "app_init:" in joined_tail or "Pro cpu start user code" in joined_tail:
                    saw_app_init = True
                if "Calling app_main()" in joined_tail or "factory_firmware:" in joined_tail:
                    saw_app_main = True
            else:
                idle_s = time.monotonic() - last_rx_t
                # Nếu không có bất kỳ dữ liệu nào sau 0.85s thì cổng này không xuất log khởi động
                if not chunks and elapsed >= 0.85:
                    break
                # Lưu ý: Kiểm tra bộ nhớ 32MB PSRAM trên ESP32-P4 mất ~920ms im lặng trước khi in "SPI SRAM memory test OK"
                # Do đó chỉ kết thúc sớm vì idle sau khi đã qua bước app_init / app_main
                if saw_app_main and idle_s >= 0.28:
                    break
                if saw_app_init and idle_s >= 0.45:
                    break
    finally:
        try:
            ser_port.timeout = orig_timeout
        except Exception:
            pass

    tail = decoder.decode(b"", final=True)
    if tail:
        chunks.append(tail)
    return "".join(chunks)


def _probe_esp_deep_details(esp):
    """
    Thực thi chuỗi thu thập thông tin phần cứng & Flash chuyên sâu ngay trong phiên Stub đang mở:
    1. Security Info (get_security_info)
    2. Flash Status Register & JEDEC SFDP Header
    3. eFuse & Silicon Registers (Unique ID 128-bit, PKG/BLK/TEMP/Power)
    4. Bootloader Image Header & esp_bootloader_desc_t
    5. Partition Table (0x8000)
    6. Application Firmware Header, esp_app_desc_t & DROM Metadata
    7. Đón Boot Log ngay khi esp.hard_reset() nhả chân RTS
    """
    from esptool.logger import log
    import esptool.cmds as esp_cmds

    # 1. Security Information
    if not getattr(esp, "secure_download_mode", False):
        try:
            log.print("\n")
            esp_cmds.get_security_info(esp)
        except Exception:
            pass

        # 2. Flash Status & SFDP
        try:
            status_val = esp.read_status(2)
            qe_bit = (status_val >> 9) & 1
            qe_note = " (QE=1: Quad Enable)" if qe_bit else " (QE=0)"
            log.print(f"\nFlash Status & SFDP:")
            log.print("====================")
            log.print(f"Status value: {status_val:#06x}{qe_note}")
        except Exception:
            pass

        try:
            sfdp_sig = esp.read_spiflash_sfdp(0, 32)
            if sfdp_sig == 0x50444653:  # "SFDP"
                sfdp_hdr = esp.read_spiflash_sfdp(4, 32)
                minor_v = sfdp_hdr & 0xFF
                major_v = (sfdp_hdr >> 8) & 0xFF
                nph = ((sfdp_hdr >> 16) & 0xFF) + 1
                proto = (sfdp_hdr >> 24) & 0xFF
                log.print(
                    f"SFDP Header: JEDEC SFDP v{major_v}.{minor_v} "
                    f"(Signature 0x50444653, {nph} Parameter Headers, Access Protocol 0x{proto:02X})"
                )
            else:
                log.print(f"SFDP Header: Raw 0x{sfdp_sig:08X}")
        except Exception:
            pass

        # 3. eFuse & Silicon Details
        efuse_info = _probe_efuse_details(esp)
        if efuse_info:
            log.print("\neFuse & Silicon Details:")
            log.print("========================")
            for k, v in efuse_info.items():
                log.print(f"EFUSE_{k.upper()}: {v}")

        # 4. Bootloader Header & Descriptor
        boot_offset = getattr(esp, "BOOTLOADER_FLASH_OFFSET", 0x1000)
        try:
            boot_data = esp_cmds.read_flash(
                esp, boot_offset, 256, output=None, flash_size="keep", no_progress=True
            )
            if boot_data:
                boot_hdr = parse_esp_image_header(boot_data)
                boot_desc = parse_esp_bootloader_desc(boot_data)
                if boot_hdr or boot_desc:
                    log.print(f"\nBootloader Image Information (@ 0x{boot_offset:X}):")
                    log.print("===========================================")
                    if boot_hdr.get("spi_mode"):
                        log.print(f"Bootloader Flash Mode: {boot_hdr['spi_mode']}")
                    if boot_hdr.get("spi_speed"):
                        log.print(f"Bootloader Flash Speed: {boot_hdr['spi_speed']}")
                    if boot_hdr.get("spi_size_header"):
                        log.print(f"Bootloader Flash Size Header: {boot_hdr['spi_size_header']}")
                    if boot_hdr.get("min_chip_rev"):
                        log.print(f"Bootloader Min Chip Rev: {boot_hdr['min_chip_rev']}")
                    if boot_hdr.get("max_chip_rev"):
                        log.print(f"Bootloader Max Chip Rev: {boot_hdr['max_chip_rev']}")
                    if boot_desc.get("bootloader_idf_ver"):
                        log.print(f"Bootloader ESP-IDF: {boot_desc['bootloader_idf_ver']}")
                    if boot_desc.get("bootloader_compile_time"):
                        log.print(f"Bootloader Compile Time: {boot_desc['bootloader_compile_time']}")
        except Exception:
            pass

        # 5. Partition Table (@ 0x8000, fallback 0x9000 / 0xD000)
        app_offset = 0x10000
        for candidate_part_off in (0x8000, 0x9000, 0xD000):
            try:
                part_data = esp_cmds.read_flash(
                    esp, candidate_part_off, 0xC00, output=None, flash_size="keep", no_progress=True
                )
                if part_data and len(part_data) >= 32 and part_data[0:2] == b"\xaa\x50":
                    temp_table = PartitionTable()
                    temp_table.from_binary(part_data)
                    if temp_table.entries:
                        log.print(f"\nPartition Table (@ 0x{candidate_part_off:X}):")
                        log.print("===============================")
                        for entry in temp_table.entries:
                            size_kb = entry.size / 1024.0
                            size_disp = f"{size_kb / 1024.0:.2f} MB" if size_kb >= 1024 else f"{size_kb:.0f} KB"
                            log.print(
                                f"PARTITION_ENTRY: {entry.name} | {entry.type_str} | {entry.subtype_str} "
                                f"| 0x{entry.offset:X} | 0x{entry.size:X} ({size_disp})"
                            )
                            if entry.type_str == "app" and app_offset == 0x10000:
                                app_offset = entry.offset
                        break
            except Exception:
                continue

        # 6. Application Firmware Header & esp_app_desc_t
        candidate_app_offsets = [app_offset]
        for extra_off in (0x10000, 0x20000):
            if extra_off not in candidate_app_offsets:
                candidate_app_offsets.append(extra_off)

        for cand_app_off in candidate_app_offsets:
            try:
                app_data = None
                for probe_len in (65536, 16384):
                    try:
                        app_data = esp_cmds.read_flash(
                            esp, cand_app_off, probe_len, output=None, flash_size="keep", no_progress=True
                        )
                        if app_data:
                            break
                    except Exception:
                        app_data = None
                if app_data and len(app_data) >= 288 and app_data[0] == 0xE9:
                    app_hdr = parse_esp_image_header(app_data)
                    app_desc = parse_esp_app_desc(app_data)
                    drom_meta = scan_drom_strings_for_metadata(app_data)
                    log.print(f"\nApplication Firmware Information (@ 0x{cand_app_off:X}):")
                    log.print("===============================================")
                    log.print(f"App Offset: 0x{cand_app_off:X}")
                    if app_hdr.get("spi_mode"):
                        log.print(f"App Flash Mode: {app_hdr['spi_mode']}")
                    if app_hdr.get("spi_speed"):
                        log.print(f"App Flash Speed: {app_hdr['spi_speed']}")
                    if app_hdr.get("entry_addr"):
                        log.print(f"App Entry Address: {app_hdr['entry_addr']}")
                    if app_hdr.get("min_chip_rev"):
                        log.print(f"App Min Chip Rev: {app_hdr['min_chip_rev']}")
                    if app_hdr.get("max_chip_rev"):
                        log.print(f"App Max Chip Rev: {app_hdr['max_chip_rev']}")
                    if app_desc.get("app_project_name"):
                        log.print(f"App Project Name: {app_desc['app_project_name']}")
                    if app_desc.get("app_version"):
                        log.print(f"App Version: {app_desc['app_version']}")
                    if app_desc.get("app_compile_time"):
                        log.print(f"App Compile Time: {app_desc['app_compile_time']}")
                    if app_desc.get("app_idf_ver"):
                        log.print(f"App ESP-IDF: {app_desc['app_idf_ver']}")
                    if app_desc.get("app_elf_sha256"):
                        log.print(f"App ELF SHA256: {app_desc['app_elf_sha256']}")
                    if app_desc.get("app_mmu_page_size"):
                        log.print(f"App MMU Page Size: {app_desc['app_mmu_page_size']}")
                    if drom_meta.get("fw_psram_driver"):
                        log.print(f"App PSRAM Driver: {drom_meta['fw_psram_driver']}")
                    if drom_meta.get("fw_psram_mode_cfg"):
                        log.print(f"App PSRAM Config: {drom_meta['fw_psram_mode_cfg']}")
                    if drom_meta.get("fw_flash_mode_cfg"):
                        log.print(f"App Flash Config: {drom_meta['fw_flash_mode_cfg']}")
                    if drom_meta.get("fw_cpu_freq_cfg"):
                        log.print(f"App CPU Config: {drom_meta['fw_cpu_freq_cfg']}")
                    if drom_meta.get("fw_debug_level"):
                        log.print(f"App Debug Level: {drom_meta['fw_debug_level']}")
                    if drom_meta.get("fw_board_name"):
                        log.print(f"App Board Target: {drom_meta['fw_board_name']}")
                    if drom_meta.get("fw_peripherals"):
                        log.print(f"App Peripherals: {drom_meta['fw_peripherals']}")
                    if drom_meta.get("fw_fqbn"):
                        log.print(f"App Arduino FQBN: {drom_meta['fw_fqbn']}")
                    break
            except Exception:
                continue

    # 7. Hook esp.hard_reset để đón trọn vẹn Boot Log từ t=0ms ngay trước khi esptool đóng cổng
    if getattr(_deep_inspection_state, "capture_boot_log", True):
        orig_hard_reset = getattr(esp, "hard_reset", None)
        if callable(orig_hard_reset):
            boot_dur = getattr(_deep_inspection_state, "boot_log_duration", 2.2)

            def _hard_reset_and_capture_boot_log():
                ser_port = getattr(esp, "_port", None)
                try:
                    if ser_port is not None and getattr(ser_port, "is_open", False):
                        if getattr(ser_port, "baudrate", 115200) != 115200:
                            ser_port.baudrate = 115200
                        ser_port.reset_input_buffer()
                except Exception:
                    pass

                orig_hard_reset()

                try:
                    boot_log = _capture_boot_log_from_open_port(ser_port, max_duration=boot_dur)
                    if boot_log and boot_log.strip():
                        log.print("\nBoot Log Sau Khi Reset (Serial 115200 bps):")
                        log.print("===========================================")
                        log.print(boot_log.strip())
                except Exception:
                    pass

            esp.hard_reset = _hard_reset_and_capture_boot_log


def run_esptool_command(args, progress_callback=None):
    """
    Thực thi lệnh esptool an toàn với khóa luồng threading.Lock.
    Đón bắt toàn bộ stdout/stderr qua StreamInterceptor và trả về output tổng hợp.
    """
    if _ensure_esptool() is None:
        raise RuntimeError("Thư viện 'esptool' chưa được cài đặt.")

    normalized_args = _normalize_esptool_args(args)
    is_deep = getattr(_deep_inspection_state, "enabled", False) and (
        "flash-id" in normalized_args or "flash_id" in normalized_args
    )

    with esptool_lock:
        eff_cb = progress_callback or (getattr(_deep_inspection_state, "progress_callback", None) if is_deep else None)
        interceptor = StreamInterceptor(eff_cb) if eff_cb else None
        output_capture = io.StringIO() if not interceptor else None
        target = interceptor if interceptor else output_capture

        orig_esptool_flash_id = getattr(esptool, "flash_id", None)
        orig_get_dev = getattr(esptool, "get_default_connected_device", None)
        esp_cmds_mod = sys.modules.get("esptool.cmds")
        orig_cmds_flash_id = getattr(esp_cmds_mod, "flash_id", None) if esp_cmds_mod else None
        captured_esp = []

        if callable(orig_get_dev):
            def _wrapped_get_dev(*d_args, **d_kwargs):
                esp_obj = orig_get_dev(*d_args, **d_kwargs)
                if esp_obj is not None:
                    _register_active_esp(esp_obj)
                    captured_esp.append(esp_obj)
                return esp_obj

            esptool.get_default_connected_device = _wrapped_get_dev

        if is_deep and callable(orig_esptool_flash_id):
            def _wrapped_flash_id(esp_obj, *f_args, **f_kwargs):
                _register_active_esp(esp_obj)
                captured_esp.append(esp_obj)
                res_fid = orig_esptool_flash_id(esp_obj, *f_args, **f_kwargs)
                try:
                    _probe_esp_deep_details(esp_obj)
                except Exception:
                    pass
                return res_fid

            esptool.flash_id = _wrapped_flash_id
            if esp_cmds_mod and callable(orig_cmds_flash_id):
                esp_cmds_mod.flash_id = _wrapped_flash_id

        try:
            with redirect_stdout(target), redirect_stderr(target):
                esptool.main(normalized_args)
            raw_res = (target.getvalue() if target else "") + "\n[Esptool exited with code: 0]"
            return clean_esptool_ansi(raw_res) if is_deep else raw_res
        except SystemExit as e:
            code = 0 if (e.code is None or e.code == 0) else e.code
            raw_res = (target.getvalue() if target else "") + f"\n[Esptool exited with code: {code}]"
            return clean_esptool_ansi(raw_res) if is_deep else raw_res
        except Exception:
            raise
        finally:
            for e_obj in captured_esp:
                _unregister_active_esp(e_obj)
            if callable(orig_get_dev):
                esptool.get_default_connected_device = orig_get_dev
            if is_deep and callable(orig_esptool_flash_id):
                esptool.flash_id = orig_esptool_flash_id
                if esp_cmds_mod and callable(orig_cmds_flash_id):
                    esp_cmds_mod.flash_id = orig_cmds_flash_id


def parse_boot_log_output(text: str) -> dict:
    """Phân tích chuyên sâu chuỗi Boot Log ESP-IDF / ROM Bootloader (PSRAM, Heap, App, Ngoại vi)."""
    if not text:
        return {}
    info = {}

    # 1. PSRAM chi tiết (hex_psram / oct_psram / quad_psram / esp_psram)
    m = re.search(r"Found\s+(\d+)\s*MB\s+PSRAM\s+device", text, re.IGNORECASE)
    if m:
        info["psram_mb"] = int(m.group(1))

    m = re.search(r"esp_psram:\s*Speed:\s*([^\r\n]+)", text, re.IGNORECASE)
    if m:
        info["psram_speed"] = m.group(1).strip()

    if re.search(r"\bhex_psram:", text, re.IGNORECASE):
        info["psram_mode"] = "Hex PSRAM (16-line / X16 MSPI)"
    elif re.search(r"\boct(?:al)?_psram:", text, re.IGNORECASE):
        info["psram_mode"] = "Octal PSRAM (8-line OPI)"
    elif re.search(r"\bquad_psram:", text, re.IGNORECASE):
        info["psram_mode"] = "Quad PSRAM (4-line QSPI)"

    psram_fields = {
        "psram_vendor": r"psram:\s*vendor id\s*:\s*([^\r\n]+)",
        "psram_dev_id": r"psram:\s*dev id\s*:\s*([^\r\n]+)",
        "psram_density": r"psram:\s*density\s*:\s*([^\r\n]+)",
        "psram_good_die": r"psram:\s*good-die\s*:\s*([^\r\n]+)",
        "psram_srf": r"psram:\s*SRF\s*:\s*([^\r\n]+)",
        "psram_burst_type": r"psram:\s*BurstType\s*:\s*([^\r\n]+)",
        "psram_burst_len": r"psram:\s*BurstLen\s*:\s*([^\r\n]+)",
        "psram_bit_mode": r"psram:\s*BitMode\s*:\s*([^\r\n]+)",
        "psram_read_latency": r"psram:\s*Readlatency\s*:\s*([^\r\n]+)",
        "psram_drive_str": r"psram:\s*DriveStr\.\s*:\s*([^\r\n]+)",
        "psram_cs_io": r"psram CS IO is\s+([^\r\n]+)",
    }
    for key, pat in psram_fields.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            info[key] = m.group(1).strip()

    if "SPI SRAM memory test OK" in text:
        info["psram_test_status"] = "Đạt (SPI SRAM memory test OK)"
    elif re.search(r"SPI SRAM memory test\s+fail", text, re.IGNORECASE):
        info["psram_test_status"] = "Lỗi (SPI SRAM memory test FAILED)"

    m = re.search(r"Adding pool of\s+(\d+)\s*K\s+of PSRAM memory", text, re.IGNORECASE)
    if m:
        info["psram_heap_pool_kb"] = int(m.group(1))

    # 2. CPU, Console UART & Flash IO runtime
    m = re.search(r"cpu_start:\s*GPIO\s+([^\r\n]+?)\s+are used as console UART", text, re.IGNORECASE)
    if m:
        info["console_uart_pins"] = f"GPIO {m.group(1).strip()}"

    m = re.search(r"cpu_start:\s*cpu freq:\s*(\d+)\s*Hz", text, re.IGNORECASE)
    if m:
        hz = int(m.group(1))
        info["cpu_freq_runtime"] = f"{hz // 1_000_000} MHz ({hz:,} Hz)"

    m = re.search(r"spi_flash:\s*flash io:\s*([^\r\n]+)", text, re.IGNORECASE)
    if m:
        info["runtime_flash_io"] = m.group(1).strip().upper()

    # 3. Application Information từ app_init / efuse_init
    app_patterns = {
        "app_project_name": r"app_init:\s*Project name:\s*([^\r\n]+)",
        "app_version": r"app_init:\s*App version:\s*([^\r\n]+)",
        "app_compile_time": r"app_init:\s*Compile time:\s*([^\r\n]+)",
        "app_elf_sha256": r"app_init:\s*ELF file SHA256:\s*([^\r\n]+)",
        "app_idf_ver": r"app_init:\s*ESP-IDF:\s*([^\r\n]+)",
        "app_min_chip_rev": r"efuse_init:\s*Min chip rev:\s*([^\r\n]+)",
        "app_max_chip_rev": r"efuse_init:\s*Max chip rev:\s*([^\r\n]+)",
    }
    for key, pat in app_patterns.items():
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            info[key] = m.group(1).strip()

    # 4. Heap RAM Regions
    heap_regions = []
    for m in re.finditer(
        r"heap_init:\s*At\s+([0-9A-Fa-f]+)\s+len\s+([0-9A-Fa-f]+)\s+\(([^)]+)\):\s*([^\r\n]+)",
        text,
    ):
        addr, length, human_sz, reg_name = (
            m.group(1).upper(),
            m.group(2).upper(),
            m.group(3).strip(),
            m.group(4).strip(),
        )
        heap_regions.append(f"{reg_name}: {human_sz} (@ 0x{addr})")
    if heap_regions:
        info["heap_regions"] = heap_regions

    # 5. Board, USB Descriptor & Peripherals (BSP / I2C / SDMMC / DSI / CSI)
    m = re.search(r"board=([A-Za-z0-9_\-]+)(?:,\s*gpio_count=(\d+))?(?:,\s*mode=([^\r\n]+))?", text)
    if m:
        board_str = m.group(1).strip()
        if m.group(2):
            board_str += f" ({m.group(2)} GPIO" + (f", chế độ {m.group(3).strip()})" if m.group(3) else ")")
        info["board_info"] = board_str

    m_vid = re.search(r"idVendor\s*[│|:]\s*(0x[0-9A-Fa-f]+)", text)
    m_pid = re.search(r"idProduct\s*[│|:]\s*(0x[0-9A-Fa-f]+)", text)
    if m_vid and m_pid:
        info["usb_vid_pid"] = f"VID {m_vid.group(1)} : PID {m_pid.group(1)}"

    m = re.search(r"I2C scan complete\.\s*([^\r\n]+)", text)
    if m:
        info["i2c_scan_summary"] = m.group(1).strip()

    m = re.search(r"Hardware status:\s*([^\r\n]+)", text)
    if m:
        info["bsp_hardware_status"] = m.group(1).strip()

    m = re.search(r"SDMMC mount failed:\s*([^\r\n]+)", text)
    if m:
        info["sdmmc_status"] = f"Lỗi mount ({m.group(1).strip()})"

    return info


def format_chip_badge_text(chip_label: str, flash_mb=None, sram_kb=None, psram_mb=None) -> str:
    """Tạo huy hiệu thông tin thống nhất hiển thị Chip · Flash · SRAM · PSRAM cho thanh kết nối."""
    parts = [str(chip_label or "ESP")]
    if flash_mb:
        f_mb = float(flash_mb)
        f_str = f"{int(f_mb)}MB" if f_mb.is_integer() else f"{f_mb:.1f}MB"
        parts.append(f"{f_str} Flash")
    if sram_kb:
        parts.append(f"{int(sram_kb)}KB SRAM")
    if psram_mb:
        parts.append(f"{int(psram_mb)}MB PSRAM")
    else:
        parts.append("0MB PSRAM")
    return " · ".join(parts)


def parse_esptool_output(output_dict):
    """Phân tích chuỗi output từ esptool & Boot Log thành dict chứa đầy đủ thông số phần cứng, Flash, Bảo mật & Firmware."""
    raw_joined = "\n".join(output_dict.values())
    full_output = clean_esptool_ansi(raw_joined)
    info = {"raw": full_output}

    m = re.search(r"Detecting chip type\.\.\.\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info["chip_name_key"] = m.group(1).strip()

    m = re.search(r"(?:Chip is|Chip type:)\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info["chip_line"] = m.group(1).strip()
        info.setdefault("chip_name_key", info["chip_line"])

    m = re.search(r"Features:\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info["features_line"] = m.group(1).strip()

    m = re.search(r"(?:Crystal is|Crystal frequency:)\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info["crystal"] = m.group(1).strip()

    m = re.search(r"USB mode:\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info["usb_mode"] = m.group(1).strip()

    if info.get("chip_line"):
        m = re.search(r"revision\s*v?([0-9.]+)", info["chip_line"], re.IGNORECASE)
        if m:
            info["revision"] = m.group(1)

    m = re.search(r"MAC\s*[:=]\s*([0-9A-Fa-f:.]{12,17})", full_output)
    if m:
        info["mac"] = "".join(re.findall("[0-9A-Fa-f]", m.group(1).upper()))

    m = re.search(r"Manufacturer:\s*([0-9a-fA-F_xX]+)", full_output)
    if m:
        info["flash_manufacturer"] = m.group(1).lower().replace("0x", "").strip()

    m = re.search(r"Device:\s*([0-9a-fA-F_xX]+)", full_output)
    if m:
        info["flash_device"] = m.group(1).strip()

    m = re.search(r"(?:Detected|Auto-detected) flash size:\s*([0-9.]+)\s*(MB|KB)", full_output, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        unit = m.group(2).upper()
        info["flash_mb"] = val if unit == "MB" else (val / 1024.0)

    m = re.search(r"Flash type set in eFuse:\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info["flash_type_efuse"] = m.group(1).strip()

    m = re.search(r"Status value:\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info["status_value"] = m.group(1).strip()

    m = re.search(r"SFDP Header:\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info["sfdp_info"] = m.group(1).strip()

    m = re.search(r"(?:PSRAM|Embedded PSRAM)\s+(\d+)\s*MB(?:\s*\(([^)]+)\))?", info.get("features_line", ""), re.IGNORECASE)
    if m:
        info["psram_mb"] = int(m.group(1))
        info["psram_source"] = "eFuse / In-Package"
        if m.group(2):
            info.setdefault("efuse_psram_vendor", m.group(2).strip())

    # Parse Security Information
    sec_patterns = {
        "security_flags": r"Flags:\s*([^\r\n]+)",
        "security_key_purposes": r"Key Purposes:\s*([^\r\n]+)",
        "security_chip_id": r"Chip ID:\s*(\d+)",
        "security_api_version": r"API Version:\s*(\d+)",
        "secure_boot": r"Secure Boot:\s*([^\r\n]+)",
        "flash_encryption": r"Flash Encryption:\s*([^\r\n]+)",
        "spi_boot_crypt_cnt": r"(?:SPI Boot Crypt Count|Flash Crypt Count)[^:]*:\s*([^\r\n]+)",
        "jtag_security": r"JTAG:\s*([^\r\n]+)",
        "usb_security": r"USB Access:\s*([^\r\n]+)",
    }
    for key, pat in sec_patterns.items():
        m = re.search(pat, full_output, re.IGNORECASE)
        if m:
            info[key] = m.group(1).strip()

    # Parse eFuse & Silicon Details
    efuse_patterns = {
        "unique_id_128": r"EFUSE_UNIQUE_ID_128:\s*([^\r\n]+)",
        "usb_vid_pid": r"EFUSE_USB_VID_PID:\s*([^\r\n]+)",
        "efuse_pkg_version": r"EFUSE_EFUSE_PKG_VERSION:\s*([^\r\n]+)",
        "efuse_blk_version": r"EFUSE_EFUSE_BLK_VERSION:\s*([^\r\n]+)",
        "efuse_temp_rating": r"EFUSE_EFUSE_TEMP_RATING:\s*([^\r\n]+)",
        "efuse_power_src": r"EFUSE_EFUSE_POWER_SRC:\s*([^\r\n]+)",
        "efuse_vdd_spi": r"EFUSE_EFUSE_VDD_SPI:\s*([^\r\n]+)",
        "efuse_psram_vendor": r"EFUSE_EFUSE_PSRAM_VENDOR:\s*([^\r\n]+)",
        "efuse_flash_vendor": r"EFUSE_EFUSE_FLASH_VENDOR:\s*([^\r\n]+)",
    }
    for key, pat in efuse_patterns.items():
        m = re.search(pat, full_output)
        if m:
            info[key] = m.group(1).strip()

    m = re.search(r"EFUSE_EFUSE_PSRAM_MB:\s*(\d+)", full_output)
    if m and "psram_mb" not in info:
        info["psram_mb"] = int(m.group(1))
        info["psram_source"] = "eFuse"

    # Parse Bootloader & Application Firmware Info từ Flash Probe
    fw_patterns = {
        "bootloader_flash_mode": r"Bootloader Flash Mode:\s*([^\r\n]+)",
        "bootloader_flash_speed": r"Bootloader Flash Speed:\s*([^\r\n]+)",
        "bootloader_flash_size_hdr": r"Bootloader Flash Size Header:\s*([^\r\n]+)",
        "bootloader_idf_ver": r"Bootloader ESP-IDF:\s*([^\r\n]+)",
        "bootloader_compile_time": r"Bootloader Compile Time:\s*([^\r\n]+)",
        "app_offset": r"App Offset:\s*([^\r\n]+)",
        "app_flash_mode": r"App Flash Mode:\s*([^\r\n]+)",
        "app_flash_speed": r"App Flash Speed:\s*([^\r\n]+)",
        "app_entry_addr": r"App Entry Address:\s*([^\r\n]+)",
        "app_min_chip_rev": r"App Min Chip Rev:\s*([^\r\n]+)",
        "app_max_chip_rev": r"App Max Chip Rev:\s*([^\r\n]+)",
        "app_project_name": r"App Project Name:\s*([^\r\n]+)",
        "app_version": r"App Version:\s*([^\r\n]+)",
        "app_compile_time": r"App Compile Time:\s*([^\r\n]+)",
        "app_idf_ver": r"App ESP-IDF:\s*([^\r\n]+)",
        "app_elf_sha256": r"App ELF SHA256:\s*([^\r\n]+)",
        "app_mmu_page_size": r"App MMU Page Size:\s*([^\r\n]+)",
        "fw_psram_driver": r"App PSRAM Driver:\s*([^\r\n]+)",
        "fw_psram_mode_cfg": r"App PSRAM Config:\s*([^\r\n]+)",
        "fw_flash_mode_cfg": r"App Flash Config:\s*([^\r\n]+)",
        "fw_cpu_freq_cfg": r"App CPU Config:\s*([^\r\n]+)",
        "fw_debug_level": r"App Debug Level:\s*([^\r\n]+)",
        "fw_board_name": r"App Board Target:\s*([^\r\n]+)",
        "fw_peripherals": r"App Peripherals:\s*([^\r\n]+)",
        "fw_fqbn": r"App Arduino FQBN:\s*([^\r\n]+)",
    }
    for key, pat in fw_patterns.items():
        m = re.search(pat, full_output)
        if m:
            info[key] = m.group(1).strip()

    # Parse Partition Entries
    partitions = []
    for m in re.finditer(r"PARTITION_ENTRY:\s*([^\r\n]+)", full_output):
        partitions.append(m.group(1).strip())
    if partitions:
        info["partitions"] = partitions

    # Hợp nhất dữ liệu từ Boot Log (nếu có trong output)
    boot_info = parse_boot_log_output(full_output)
    for k, v in boot_info.items():
        if k == "psram_mb":
            info["psram_mb"] = v
            info["psram_source"] = "Boot Log (MSPI Probe)"
        elif k not in info or not info[k]:
            info[k] = v

    _enrich_memory_metadata(info)
    return info


def _enrich_memory_metadata(info: dict) -> None:
    """Bổ sung thông số SRAM/ROM từ CSDL và tổng hợp chi tiết PSRAM khi Boot Log bị tắt."""
    chip_data = get_chip_data(info.get("chip_name_key") or info.get("chip_line"))
    if chip_data:
        if chip_data.get("sram_kb") and not info.get("sram_kb"):
            info["sram_kb"] = int(chip_data["sram_kb"])
        if chip_data.get("rom_kb") and not info.get("rom_kb"):
            info["rom_kb"] = int(chip_data["rom_kb"])

    if "psram_mb" not in info or not info.get("psram_mb"):
        return

    psram_mb = int(info["psram_mb"])
    chip_upper = (info.get("chip_name_key") or info.get("chip_line") or "").upper()
    raw_vendor = (info.get("efuse_psram_vendor") or "").strip()

    if not info.get("psram_vendor") and raw_vendor:
        if raw_vendor == "AP_3v3":
            info["psram_vendor"] = "0x0D (AP Memory · AP_3v3 - 3.3V In-Package)"
        elif raw_vendor == "AP_1v8":
            info["psram_vendor"] = "0x0D (AP Memory · AP_1v8 - 1.8V In-Package)"
        else:
            info["psram_vendor"] = raw_vendor

    if not info.get("psram_density"):
        info["psram_density"] = f"{psram_mb * 8} Mbit ({psram_mb} MB)"

    if not info.get("psram_mode"):
        hint = " ".join(filter(None, [info.get("fw_psram_mode_cfg"), info.get("fw_psram_driver")])).lower()
        if "hex" in hint:
            info["psram_mode"] = "Hex PSRAM (16-line / X16 MSPI)"
        elif "octal" in hint or "opi" in hint:
            info["psram_mode"] = "Octal PSRAM (8-line / X8 OPI MSPI)"
        elif "quad" in hint or "qspi" in hint:
            info["psram_mode"] = "Quad PSRAM (4-line / X4 QSPI)"
        elif "ESP32-S3" in chip_upper:
            info["psram_mode"] = "Octal PSRAM (8-line / X8 OPI MSPI)" if psram_mb >= 8 else "Quad PSRAM (4-line / X4 QSPI)"
        elif "ESP32-P4" in chip_upper:
            info["psram_mode"] = "Hex PSRAM (16-line / X16 MSPI)"
        else:
            info["psram_mode"] = "Quad/SPI PSRAM"

    if not info.get("psram_bit_mode") and info.get("psram_mode"):
        mode_lower = info["psram_mode"].lower()
        if "hex" in mode_lower:
            info["psram_bit_mode"] = "X16 Mode (16-line MSPI)"
        elif "octal" in mode_lower or "opi" in mode_lower:
            info["psram_bit_mode"] = "Octal OPI (8-line / X8 MSPI)"
        else:
            info["psram_bit_mode"] = "Quad QSPI (4-line MSPI)"

    if not info.get("psram_speed"):
        spi_spd = info.get("bootloader_flash_speed") or info.get("app_flash_speed")
        if spi_spd:
            info["psram_speed"] = str(spi_spd).replace(" ", "")

    if not info.get("psram_bus_voltage"):
        if "1V8" in raw_vendor.upper() or "1.8V" in str(info.get("efuse_vdd_spi", "")).upper():
            info["psram_bus_voltage"] = "1.8V (VDD_SPI)"
        elif "3V3" in raw_vendor.upper() or "3.3V" in str(info.get("efuse_vdd_spi", "")).upper():
            info["psram_bus_voltage"] = "3.3V (VDD_SPI)"

    if not info.get("psram_test_status") and not info.get("psram_probe_note"):
        dbg_note = f" (DebugLevel={info['fw_debug_level']})" if info.get("fw_debug_level") else ""
        src_note = info.get("psram_source") or "eFuse"
        info["psram_probe_note"] = f"Vùng ánh xạ: {psram_mb * 1024:,} KB · Phát hiện từ {src_note}{dbg_note}"


def derive_mac_addresses(base_mac_hex):
    """Tính toán địa chỉ MAC Wi-Fi Station, AP và Bluetooth từ Base MAC Hex."""
    if not base_mac_hex or len(base_mac_hex) != 12:
        return {}
    try:
        b = bytes.fromhex(base_mac_hex)

        def fmt(offset):
            n = ((int.from_bytes(b, "big") + offset) % (1 << 48)).to_bytes(6, "big")
            return ":".join(f"{x:02X}" for x in n)

        return {
            "MAC Wi-Fi Station": fmt(0),
            "MAC Wi-Fi AP": fmt(1),
            "MAC Bluetooth": fmt(2),
            "MAC Ethernet / Nội bộ": fmt(3),
        }
    except Exception:
        return {}


def get_chip_data(chip_name_key):
    """Tra cứu thông số kiến trúc phần cứng chip từ CHIP_DATABASE."""
    if not chip_name_key:
        return None
    chip_name_key = str(chip_name_key).upper()
    # Espressif also markets C2/C3 variants under the ESP8684/ESP8685 names.
    chip_name_key = re.sub(r"\bESP8684\b", "ESP32-C2", chip_name_key)
    chip_name_key = re.sub(r"\bESP8685\b", "ESP32-C3", chip_name_key)
    sorted_keys = sorted(CHIP_DATABASE.keys(), key=len, reverse=True)
    for key in sorted_keys:
        if key == "ESP32":
            standard_esp32 = re.search(
                r"\bESP32(?:-?(?:D0WD(?:Q[56])?(?:-V3)?|S0WD|U4WDH|PICO(?:-D4|-V3(?:-02)?)?))?(?=$|[\s(])",
                chip_name_key,
            )
            if standard_esp32:
                return CHIP_DATABASE[key]
            continue
        if key == "ESP8266":
            if re.search(r"\bESP8266(?:EX)?(?=$|[\s(])", chip_name_key):
                return CHIP_DATABASE[key]
            continue
        if re.search(rf"{re.escape(key)}(?![A-Z0-9])", chip_name_key):
            return CHIP_DATABASE[key]
    return None
