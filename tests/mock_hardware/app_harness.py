# -*- coding: utf-8 -*-
"""
HeadlessAppHarness: Test harness for headless PyQt6 lifecycle management.
Initializes MainWindow/InspectorApp in an off-screen PyQt6 environment, pumps event loops,
provides deterministic condition waiting, and ensures clean thread termination.
"""
import gc
import os
import queue
import sys
import threading
import time
from unittest.mock import patch

# Chạy PyQt6 ở chế độ offscreen headless khi chạy test
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget
from modules.ui.dispatch import UiDispatcher
from modules.app_core import InspectorApp

_global_after_queue = queue.Queue()


class _MockTk:
    def call(self, *args, **kwargs):
        return ()

    def splitlist(self, arg):
        return []


class _MockRoot(QWidget):
    def __init__(self):
        super().__init__()
        self.tk = _MockTk()

    def winfo_children(self):
        return [c for c in self.findChildren(QWidget) if hasattr(c, "winfo_exists") and c.winfo_exists()]

    def winfo_exists(self):
        return True

    def winfo_x(self):
        return self.x()

    def winfo_y(self):
        return self.y()

    def winfo_width(self):
        return self.width() if self.width() > 0 else 1024

    def winfo_height(self):
        return self.height() if self.height() > 0 else 768

    def geometry(self, geom=None):
        pass

    def minsize(self, w=0, h=0):
        pass

    def transient(self, master=None):
        pass

    def grab_set(self):
        pass

    def event_generate(self, event, **kwargs):
        pass

    def destroy(self):
        pass

    def withdraw(self):
        pass

    def update(self):
        pass

    def update_idletasks(self):
        pass

    def config(self, **kwargs):
        pass

    def after(self, ms, func=None, *args):
        if func:
            from modules.ui.dispatch import UiDispatcher
            UiDispatcher.instance().post(func, *args, delay_ms=int(ms))
        return "mock_timer"

    def after_cancel(self, t):
        pass


class HeadlessAppHarness:
    """
    Manages InspectorApp lifecycle in a headless PyQt6 test environment.
    Guarantees no visual desktop windows appear and safely tears down background threads.
    """

    _qapp = None
    _shared_root = None

    @classmethod
    def get_shared_root(cls):
        if cls._qapp is None:
            cls._qapp = QApplication.instance() or QApplication(sys.argv)
        if cls._shared_root is None:
            cls._shared_root = _MockRoot()
        return cls._shared_root

    def __init__(self):
        self.root = self.get_shared_root()
        self.app = None

    def start(self, auto_scan: bool = False) -> InspectorApp:
        """
        Instantiate InspectorApp in offscreen mode.
        Optionally triggers background tasks.
        """
        UiDispatcher.instance().drain()

        with patch('modules.app_core.set_window_icon_native'):
            self.app = InspectorApp(auto_start=auto_scan)

        self.app.saved_auto_select_new = True
        if hasattr(self.app, 'var_auto_connect_server'):
            self.app.var_auto_connect_server.set(False)

        if auto_scan:
            self.app.start_background_tasks()

        self.pump(5)
        return self.app

    def pump(self, cycles: int = 10, delay: float = 0.005, **kwargs):
        """
        Pump the PyQt6 event loop to process idle tasks and dispatcher callbacks.
        """
        if 'times' in kwargs:
            cycles = kwargs['times']
        elif 'count' in kwargs:
            cycles = kwargs['count']

        app = QApplication.instance()
        for _ in range(cycles):
            UiDispatcher.instance().drain()
            if app:
                app.processEvents()
            if delay > 0:
                time.sleep(delay)
        UiDispatcher.instance().drain()

    def wait_for(self, condition_fn, timeout: float = 4.0, poll_interval: float = 0.02):
        """
        Repeatedly pump the event loop until condition_fn() returns truthy,
        or raise TimeoutError if timeout expires.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            self.pump(2, delay=poll_interval)
            try:
                res = condition_fn()
                if res:
                    self.pump(5)
                    return res
            except Exception:
                pass
        self.pump(5)
        res = condition_fn()
        if res:
            self.pump(5)
            return res
        raise TimeoutError(f"Condition not met within {timeout} seconds: {condition_fn}")

    def close(self):
        """
        Gracefully terminate background threads and clean up app instance.
        """
        if self.app:
            try:
                self.app.stop_scan.set()
                if hasattr(self.app, 'stop_serial_thread'):
                    self.app.stop_serial_thread.set()
                if hasattr(self.app, 'is_flashing') and self.app.is_flashing.is_set():
                    self.app.is_flashing.clear()
                if hasattr(self.app, 'is_detecting') and self.app.is_detecting.is_set():
                    self.app.is_detecting.clear()
                if hasattr(self.app, '_is_partition_hw_running'):
                    self.app._is_partition_hw_running = False
                if self.app.serial_connection and getattr(self.app.serial_connection, 'is_open', False):
                    self.app.on_serial_disconnect()

                for th_name in ('flash_thread', 'detect_thread', 'partition_hw_thread', 'serial_thread', 'backup_thread', 'clone_thread'):
                    th = getattr(self.app, th_name, None)
                    if th and th.is_alive():
                        th.join(timeout=0.3)
                self.app.close()
            except Exception:
                pass

        self.pump(3, delay=0.005)
        gc.collect()
        self.app = None
