# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Local Serial Port Utilities
"""
try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None

def list_com_ports_local():
    """Liệt kê danh sách các cổng COM đang có trên máy."""
    if list_ports is None:
        return []
    try:
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []
