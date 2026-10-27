# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - esptool Integration Utilities
"""
import io
import threading
import re
from importlib import metadata
from contextlib import redirect_stdout, redirect_stderr

try:
    import esptool
except ImportError:
    esptool = None

from modules.config import CHIP_DATABASE
from modules.stream_util import StreamInterceptor

esptool_lock = threading.Lock()

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


def _esptool_major_version():
    """Best-effort major-version detection; unknown installs use current v5 syntax."""
    version_text = getattr(esptool, "__version__", "") if esptool is not None else ""
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

def run_esptool_command(args, progress_callback=None):
    """
    Thực thi lệnh esptool an toàn với khóa luồng threading.Lock.
    Đón bắt toàn bộ stdout/stderr qua StreamInterceptor và trả về output tổng hợp.
    """
    if esptool is None:
        raise RuntimeError("Thư viện 'esptool' chưa được cài đặt.")

    with esptool_lock:
        interceptor = StreamInterceptor(progress_callback) if progress_callback else None
        output_capture = io.StringIO() if not interceptor else None
        target = interceptor if interceptor else output_capture
        try:
            with redirect_stdout(target), redirect_stderr(target): 
                # Both esptool v4 and v5 officially accept the CLI argument
                # list directly. Avoid mutating process-wide sys.argv while a
                # GUI application has other background threads running.
                esptool.main(_normalize_esptool_args(args))
            return (target.getvalue() if target else "") + "\n[Esptool exited with code: 0]"
        except SystemExit as e:
            code = 0 if (e.code is None or e.code == 0) else e.code
            res = (target.getvalue() if target else "") + f"\n[Esptool exited with code: {code}]"
            return res
        except Exception:
            raise

def parse_esptool_output(output_dict):
    """Phân tích chuỗi output từ esptool thành dict chứa thông số phần cứng chip & flash."""
    full_output = "\n".join(output_dict.values())
    info = {'raw': full_output}
    
    m = re.search(r"Detecting chip type...\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m: info['chip_name_key'] = m.group(1).strip()
    
    m = re.search(r"(?:Chip is|Chip type:)\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m:
        info['chip_line'] = m.group(1).strip()
        # esptool v5 no longer prints the old "Detecting chip type..."
        # line, so use the richer Chip type line as the lookup source.
        info.setdefault('chip_name_key', info['chip_line'])
    
    m = re.search(r"Features:\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m: info['features_line'] = m.group(1).strip()
    
    m = re.search(r"(?:Crystal is|Crystal frequency:)\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m: info['crystal'] = m.group(1).strip()
    
    if info.get('chip_line'):
        m = re.search(r"revision\s*v?([0-9.]+)", info['chip_line'], re.IGNORECASE)
        if m: info['revision'] = m.group(1)
        
    m = re.search(r"MAC\s*[:=]\s*([0-9A-Fa-f:.]{12,17})", full_output)
    if m: info['mac'] = "".join(re.findall("[0-9A-Fa-f]", m.group(1).upper()))
    
    m = re.search(r"Manufacturer:\s*([0-9a-fA-F_xX]+)", full_output)
    if m: info["flash_manufacturer"] = m.group(1).lower().replace("0x", "").strip()
    
    m = re.search(r"Device:\s*([0-9a-fA-F_xX]+)", full_output)
    if m: info["flash_device"] = m.group(1).strip()
    
    m = re.search(r"Detected flash size:\s*([0-9.]+)\s*(MB|KB)", full_output, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        unit = m.group(2).upper()
        info['flash_mb'] = val if unit == 'MB' else (val / 1024.0)
    
    m = re.search(r"Status value:\s*([^\r\n]+)", full_output, re.IGNORECASE)
    if m: info['status_value'] = m.group(1).strip()
    
    m = re.search(r"(?:PSRAM|Embedded PSRAM)\s+(\d+)MB", info.get('features_line', ''), re.IGNORECASE)
    if m: info['psram_mb'] = int(m.group(1))
    
    return info

def derive_mac_addresses(base_mac_hex):
    """Tính toán địa chỉ MAC Wi-Fi Station, AP và Bluetooth từ Base MAC Hex."""
    if not base_mac_hex or len(base_mac_hex) != 12: return {}
    try:
        b = bytes.fromhex(base_mac_hex)
        def fmt(offset):
            n = ((int.from_bytes(b, 'big') + offset) % (1 << 48)).to_bytes(6, 'big')
            return ":".join(f"{x:02X}" for x in n)
        return {"MAC Wi-Fi Station": fmt(0), "MAC Wi-Fi AP": fmt(1), "MAC Bluetooth": fmt(2)}
    except Exception: return {}

def get_chip_data(chip_name_key):
    """Tra cứu thông số kiến trúc phần cứng chip từ CHIP_DATABASE."""
    if not chip_name_key: return None
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
