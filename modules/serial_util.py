# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.1 - Local Serial Port Utilities
"""
try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None


def is_bluetooth_port(p_obj) -> bool:
    """Kiểm tra xem một cổng COM có phải là kết nối Bluetooth không."""
    desc = str(getattr(p_obj, 'description', '') or '').lower()
    hwid = str(getattr(p_obj, 'hwid', '') or '').lower()
    return 'bluetooth' in desc or 'bthenum' in hwid or 'bth\\' in hwid


def get_bluetooth_com_ports() -> list[str]:
    """Lấy danh sách tên các cổng COM thuộc thiết bị Bluetooth để tự động ẩn mặc định."""
    if list_ports is None:
        return []
    try:
        return [p.device for p in list_ports.comports() if is_bluetooth_port(p)]
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
