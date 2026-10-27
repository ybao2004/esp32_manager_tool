# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Win32 High-DPI Icon Utility
"""
import sys
import os
import tkinter as tk

def set_window_icon_native(window, base_dir=None):
    """
    Thiết lập Icon cửa sổ và Taskbar cực kỳ sắc nét trên Windows.
    Sử dụng trực tiếp Win32 API (LoadImageW + WM_SETICON) cho đúng kích cỡ thực tế của hệ thống
    (tránh việc Tkinter iconphoto phóng to icon 16x16 lên Taskbar làm mờ nhòe).
    """
    if base_dir is None:
        # Nếu đang chạy exe đóng gói PyInstaller
        base_dir = getattr(sys, '_MEIPASS', None)
        if not base_dir:
            # Nếu chạy script nguồn, tìm tại thư mục gốc của project
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            if not any(
                os.path.exists(os.path.join(base_dir, folder, filename))
                for folder in ("icons", "")
                for filename in ("esp_icon_v3.ico", "esp_icon_v2.ico", "esp_icon.ico")
            ):
                base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Ưu tiên tìm trong thư mục icons/, fallback về base_dir
    icon_dir = os.path.join(base_dir, "icons") if os.path.isdir(os.path.join(base_dir, "icons")) else base_dir
    icon_path = ""
    for filename in ("esp_icon_v3.ico", "esp_icon_v2.ico", "esp_icon.ico"):
        for folder in (icon_dir, base_dir):
            candidate = os.path.join(folder, filename)
            if os.path.exists(candidate):
                icon_path = candidate
                break
        if icon_path:
            break
    has_set_native = False

    # 1. Thiết lập iconbitmap chuẩn
    if os.path.exists(icon_path):
        try:
            window.iconbitmap(default=icon_path)
        except Exception:
            try:
                window.iconbitmap(icon_path)
            except Exception:
                pass

    # 2. Trên Windows: Sử dụng Win32 API để gán icon với đúng kích thước DPI thực tế
    if os.name == 'nt' and os.path.exists(icon_path):
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            # ctypes defaults to 32-bit int; HWND/HICON are pointer-sized on Win64.
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            user32.LoadImageW.restype = wintypes.HANDLE
            user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, ctypes.c_size_t, ctypes.c_ssize_t]
            user32.SendMessageW.restype = ctypes.c_ssize_t
            if hasattr(user32, "GetDpiForWindow"):
                user32.GetDpiForWindow.argtypes = [wintypes.HWND]
                user32.GetDpiForWindow.restype = wintypes.UINT
            window.update_idletasks()
            hwnd = user32.GetParent(window.winfo_id())
            if not hwnd:
                hwnd = window.winfo_id()

            SM_CXSMICON = 49  # Chiều rộng icon nhỏ (title bar)
            SM_CYSMICON = 50  # Chiều cao icon nhỏ
            SM_CXICON = 11    # Chiều rộng icon lớn (taskbar / Alt+Tab)
            SM_CYICON = 12    # Chiều cao icon lớn

            dpi = user32.GetDpiForWindow(hwnd) if hasattr(user32, "GetDpiForWindow") else 96
            if hasattr(user32, "GetSystemMetricsForDpi"):
                sm_w = user32.GetSystemMetricsForDpi(SM_CXSMICON, dpi) or 16
                sm_h = user32.GetSystemMetricsForDpi(SM_CYSMICON, dpi) or 16
                big_w = user32.GetSystemMetricsForDpi(SM_CXICON, dpi) or 32
                big_h = user32.GetSystemMetricsForDpi(SM_CYICON, dpi) or 32
            else:
                sm_w = user32.GetSystemMetrics(SM_CXSMICON) or 16
                sm_h = user32.GetSystemMetrics(SM_CYSMICON) or 16
                big_w = user32.GetSystemMetrics(SM_CXICON) or 32
                big_h = user32.GetSystemMetrics(SM_CYICON) or 32

            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010

            h_icon_sm = user32.LoadImageW(None, os.path.abspath(icon_path), IMAGE_ICON, sm_w, sm_h, LR_LOADFROMFILE)
            h_icon_big = user32.LoadImageW(None, os.path.abspath(icon_path), IMAGE_ICON, big_w, big_h, LR_LOADFROMFILE)

            WM_SETICON = 0x0080
            ICON_SMALL = 0
            ICON_BIG = 1

            if h_icon_sm:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, h_icon_sm)
            if h_icon_big:
                user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, h_icon_big)
            if h_icon_sm or h_icon_big:
                # Keep native handles alive for the lifetime of this Tk window.
                window._native_icon_handles = (h_icon_sm, h_icon_big)
                has_set_native = True
        except Exception:
            pass

    # 3. Phương án dự phòng qua Tkinter iconphoto (nếu không phải Windows hoặc Win32 API lỗi)
    # LƯU Ý: Thứ tự phải từ LỚN ĐẾN NHỎ để Tkinter lấy ảnh lớn làm mặc định, KHÔNG bị vỡ hạt
    if not has_set_native:
        app_icons = []
        for icon_file in [
            "esp_icon_v3.png", "esp_icon_v3_128.png", "esp_icon_v3_64.png",
            "esp_icon_v3_48.png", "esp_icon_v3_32.png", "esp_icon_v3_24.png",
            "esp_icon_v3_20.png", "esp_icon_v3_16.png",
            "esp_icon_v2.png", "esp_icon_v2_128.png", "esp_icon_v2_64.png",
            "esp_icon_v2_48.png", "esp_icon_v2_32.png", "esp_icon_v2_24.png",
            "esp_icon_v2_20.png", "esp_icon_v2_16.png", "esp_icon.png",
        ]:
            p = os.path.join(icon_dir, icon_file)
            if not os.path.exists(p):
                p = os.path.join(base_dir, icon_file)
            if os.path.exists(p):
                try:
                    app_icons.append(tk.PhotoImage(file=p))
                except Exception:
                    pass
        if app_icons:
            try:
                window.iconphoto(True, *app_icons)
            except Exception:
                pass
