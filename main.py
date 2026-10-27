# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.0 - Main Entry Point
Ứng dụng GUI toàn diện: Kiểm tra phần cứng, Serial Monitor, Nạp Flash Firmware, Quản lý Phân vùng (Partition Wizard) và Tự động Cập nhật.
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
            myappid = 'mytool.esp32managertool.1.0'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass

        try:
            # Per-Monitor V2 keeps icons and controls crisp when moving the app
            # between displays with different Windows scaling factors.
            if not ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                raise OSError("Per-Monitor V2 DPI awareness was not applied")
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
                
    main()
