# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.7 - Main Entry Point (PyQt6 Edition)
Ứng dụng GUI toàn diện: Kiểm tra phần cứng, Serial Monitor, Nạp Flash Firmware, Quản lý Phân vùng (Partition Wizard), Sao lưu & Nhân bản (Backup / Clone).
"""
import sys
import os
import multiprocessing

# Thêm thư mục hiện tại vào sys.path để đảm bảo import các module ổn định
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from modules.app_core import InspectorApp, main

if __name__ == '__main__':
    multiprocessing.freeze_support()

    if os.name == 'nt':
        import ctypes
        # Đặt AppUserModelID riêng để Windows gán đúng icon trên Taskbar thay vì gom nhóm icon Python
        try:
            myappid = 'ybao04.esp32managertool.1.7'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

    main()
