# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.1 - Local Serial Port Utilities
"""
try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None


_PHONE_USB_VIDS = frozenset({
    "04E8",  # Samsung
    "05AC",  # Apple
    "2717",  # Xiaomi
    "12D1",  # Huawei
    "22D9",  # Oppo / Realme / OnePlus
    "2A70",  # OnePlus
    "2D95",  # Vivo
    "18D1",  # Google / Android
    "05C6",  # Qualcomm Mobile
    "0E8D",  # MediaTek Preloader / VCOM
    "1782",  # Unisoc / Spreadtrum
    "1004",  # LG
    "0FCE",  # Sony Xperia
    "22B8",  # Motorola
})

_PHONE_PORT_KEYWORDS = (
    "modem",
    "samsung",
    "apple",
    "iphone",
    "ipad",
    "xiaomi",
    "redmi",
    "poco",
    "huawei",
    "honor",
    "oppo",
    "realme",
    "oneplus",
    "vivo",
    "motorola",
    "lg mobile",
    "android",
    "qualcomm",
    "hs-usb",
    "mediatek",
    "preloader",
    "spreadtrum",
    "unisoc",
    "smartphone",
    "wwan",
    "rmnet",
)


def is_bluetooth_port(p_obj) -> bool:
    """Kiểm tra xem một cổng COM có phải là kết nối Bluetooth không."""
    desc = str(getattr(p_obj, 'description', '') or '').lower()
    hwid = str(getattr(p_obj, 'hwid', '') or '').lower()
    return 'bluetooth' in desc or 'bthenum' in hwid or 'bth\\' in hwid


def is_phone_port(p_obj) -> bool:
    """Kiểm tra xem một cổng COM có phải là cổng Modem / USB của điện thoại không."""
    desc = str(getattr(p_obj, 'description', '') or '').lower()
    mfg = str(getattr(p_obj, 'manufacturer', '') or '').lower()
    hwid = str(getattr(p_obj, 'hwid', '') or '').lower()

    vid = getattr(p_obj, 'vid', None)
    if vid is not None:
        try:
            if f"{int(vid):04X}" in _PHONE_USB_VIDS:
                return True
        except (TypeError, ValueError):
            pass

    for vid_hex in _PHONE_USB_VIDS:
        v_low = vid_hex.lower()
        if f"vid_{v_low}" in hwid or f"vid:{v_low}" in hwid:
            return True

    combined = f"{desc} {mfg}"
    return any(kw in combined for kw in _PHONE_PORT_KEYWORDS)


def get_bluetooth_com_ports() -> list[str]:
    """Lấy danh sách tên các cổng COM thuộc thiết bị Bluetooth để tự động ẩn mặc định."""
    if list_ports is None:
        return []
    try:
        return [p.device for p in list_ports.comports() if is_bluetooth_port(p)]
    except Exception:
        return []


def get_phone_com_ports() -> list[str]:
    """Lấy danh sách tên các cổng COM thuộc điện thoại / Modem để tự động ẩn mặc định."""
    if list_ports is None:
        return []
    try:
        return [p.device for p in list_ports.comports() if is_phone_port(p)]
    except Exception:
        return []


def list_com_ports_local():
    """Liệt kê danh sách các cổng COM đang có trên máy."""
    if list_ports is None:
        return []
    try:
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []
