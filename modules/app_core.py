# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v1.2 - Core Application Controller (PyQt6 Edition)
Đơn giản hóa kiến trúc, khởi động mượt với StartupSplash thuần QWidget trên Taskbar,
hỗ trợ đầy đủ icon Windows Taskbar ở cả source & .exe, khóa đơn thực thể (Single-Instance)
và giải phóng tiến trình / tài nguyên an toàn khi thoát.
"""
import os
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from modules.config import CONFIG_FILE
from modules.serial_util import list_com_ports_local, get_bluetooth_com_ports
from modules.ui import dialogs_service as messagebox
from modules.ui import dialogs_service as filedialog


def _build_inspector_app_class():
    """Khởi tạo lớp InspectorApp theo kiểu lazy để giảm độ trễ import trước khi hiện Splash."""
    from modules.ui.main_window import MainWindow

    class _InspectorApp(MainWindow):
        """Điểm vào tương thích cho InspectorApp kế thừa MainWindow thuần PyQt6."""

        def __init__(self, root=None, auto_start: bool = True, parent=None, progress_callback=None):
            super().__init__(
                root=root,
                auto_start=auto_start,
                parent=parent,
                progress_callback=progress_callback,
            )

    _InspectorApp.__name__ = "InspectorApp"
    _InspectorApp.__qualname__ = "InspectorApp"
    return _InspectorApp


def __getattr__(name: str):
    if name == "InspectorApp":
        cls = _build_inspector_app_class()
        globals()["InspectorApp"] = cls
        return cls
    if name == "MainWindow":
        from modules.ui.main_window import MainWindow
        globals()["MainWindow"] = MainWindow
        return MainWindow
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def resolve_app_icon_path(base_dir=None) -> str:
    """Tìm đường dẫn file esp_icon_v3.ico chuẩn cho cả chế độ source và PyInstaller One-File EXE."""
    candidates = []
    if base_dir:
        candidates.append(os.path.join(str(base_dir), "icons", "esp_icon_v3.ico"))
    if hasattr(sys, "_MEIPASS"):
        candidates.append(os.path.join(getattr(sys, "_MEIPASS"), "icons", "esp_icon_v3.ico"))
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    candidates.append(os.path.join(repo_root, "icons", "esp_icon_v3.ico"))
    for p in candidates:
        if os.path.isfile(p):
            return p
    return ""


def destroy_window_icons_native(window) -> None:
    """Giải phóng các handle icon Win32 (DestroyIcon) đã nạp cho cửa sổ khi thoát ứng dụng."""
    if os.name != "nt" or window is None:
        return
    hicons = getattr(window, "_native_hicons", None)
    if not hicons:
        return
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        DestroyIcon = user32.DestroyIcon
        DestroyIcon.argtypes = [wintypes.HANDLE]
        DestroyIcon.restype = wintypes.BOOL
        for h in list(hicons):
            if h:
                try:
                    DestroyIcon(h)
                except Exception:
                    pass
    except Exception:
        pass
    try:
        window._native_hicons = []
    except Exception:
        pass


def set_window_icon_native(window, base_dir=None):
    """Thiết lập biểu tượng ứng dụng cho cả Qt và Win32 Taskbar (WM_SETICON ICON_BIG/ICON_SMALL)."""
    if isinstance(base_dir, str) and os.path.isfile(base_dir):
        icon_path = base_dir
    else:
        icon_path = resolve_app_icon_path(base_dir)
    if not icon_path:
        return

    app = QApplication.instance()
    q_icon = QIcon(icon_path)
    if app is not None:
        app.setWindowIcon(q_icon)
    if window is not None and not isinstance(window, int) and hasattr(window, "setWindowIcon"):
        try:
            window.setWindowIcon(q_icon)
        except Exception:
            pass

    if os.name != "nt" or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
        return
    if window is None:
        return

    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(window) if isinstance(window, int) else (int(window.winId()) if hasattr(window, "winId") else 0)
        if not hwnd:
            return

        user32 = ctypes.windll.user32
        LoadImageW = user32.LoadImageW
        LoadImageW.argtypes = [
            wintypes.HINSTANCE,
            wintypes.LPCWSTR,
            wintypes.UINT,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]
        LoadImageW.restype = wintypes.HANDLE

        SendMessageW = user32.SendMessageW
        SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        SendMessageW.restype = wintypes.LPARAM

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x00000010
        WM_SETICON = 0x0080
        ICON_SMALL = 0
        ICON_BIG = 1

        if not isinstance(window, int):
            destroy_window_icons_native(window)

        hicon_big = LoadImageW(None, icon_path, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        hicon_small = LoadImageW(None, icon_path, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        if not hicon_big:
            hicon_big = LoadImageW(None, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE)

        tracked = []
        if hicon_big:
            SendMessageW(hwnd, WM_SETICON, ICON_BIG, hicon_big)
            tracked.append(hicon_big)
        if hicon_small:
            SendMessageW(hwnd, WM_SETICON, ICON_SMALL, hicon_small)
            tracked.append(hicon_small)
        if not isinstance(window, int):
            window._native_hicons = tracked
    except Exception:
        pass


def main():
    from modules.single_instance import SingleInstanceGuard, terminate_child_processes
    from modules.ui.splash import StartupSplash

    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)

    guard = SingleInstanceGuard(app_id="esp32_manager_tool_single_instance_v1")
    if not guard.acquire():
        guard.notify_existing_instance()
        sys.exit(0)

    icon_path = resolve_app_icon_path()
    if icon_path:
        app.setWindowIcon(QIcon(icon_path))

    splash = None
    if os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
        splash = StartupSplash()
        if icon_path:
            splash.setWindowIcon(QIcon(icon_path))
        splash.show()
        set_window_icon_native(splash)
        splash.raise_()
        splash.activateWindow()
        splash.set_stage(12, "Đang khởi tạo lõi ứng dụng PyQt6...")

    def _report_stage(pct: int, msg: str):
        if splash is not None:
            splash.set_stage(pct, msg)

    window = None
    cleaned_up = False

    def _finalize_shutdown():
        nonlocal cleaned_up
        if cleaned_up:
            return
        cleaned_up = True
        if window is not None:
            try:
                if hasattr(window, "cleanup_resources"):
                    window.cleanup_resources(force=True)
            except Exception:
                pass
            destroy_window_icons_native(window)
        try:
            guard.release()
        except Exception:
            pass
        try:
            terminate_child_processes()
        except Exception:
            pass

    app.aboutToQuit.connect(_finalize_shutdown)

    try:
        _report_stage(24, "Đang nạp giao diện & các module công cụ...")
        MainWindowCls = __getattr__("MainWindow")
        window = MainWindowCls(progress_callback=_report_stage)
        guard.set_on_activate(window.bring_to_front)
        _report_stage(94, "Đang hiển thị cửa sổ làm việc chính...")
        window.showMaximized()
        set_window_icon_native(window)
        window.raise_()
        window.activateWindow()
        if splash is not None:
            _report_stage(100, "Sẵn sàng!")
            splash.finish(window)
            destroy_window_icons_native(splash)
        exit_code = app.exec()
    finally:
        if splash is not None:
            try:
                splash.close()
            except Exception:
                pass
            destroy_window_icons_native(splash)
        _finalize_shutdown()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
