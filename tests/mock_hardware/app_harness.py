# -*- coding: utf-8 -*-
"""
HeadlessAppHarness: Test harness for headless PyQt6 lifecycle management.
Initializes InspectorApp in an off-screen withdrawn PyQt6 QMainWindow root, pumps event loops,
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

from modules import qt_toolkit as tk
from modules.app_core import InspectorApp

# Hàng đợi after() an toàn đa luồng dùng chung với qt_toolkit
_global_after_queue = tk._THREADSAFE_QUEUE


class HeadlessAppHarness:
    """
    Manages InspectorApp lifecycle in a headless PyQt6 test environment.
    Guarantees no visual desktop windows appear and safely tears down background threads.
    """

    _shared_root = None

    @classmethod
    def get_shared_root(cls):
        if cls._shared_root is None or not cls._shared_root.winfo_exists():
            try:
                cls._shared_root = tk.Tk()
                cls._shared_root.withdraw()
            except Exception as exc:
                raise RuntimeError(f"PyQt6 display environment unavailable: {exc}")
        return cls._shared_root

    def __init__(self):
        self.root = self.get_shared_root()
        self.app = None

    def _drain_after_queue(self):
        """Execute all queued worker callbacks whose scheduled time has arrived."""
        tk._drain_global_after_queue()

    def start(self, auto_scan=False) -> InspectorApp:
        """
        Instantiate InspectorApp with native window icon calls safely mocked out.
        Optionally triggers background tasks.
        """
        while not _global_after_queue.empty():
            try:
                _global_after_queue.get_nowait()
            except queue.Empty:
                break

        for child in list(self.root.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        try:
            if self.root.winfo_exists():
                self.root.update_idletasks()
                self.root.update()
        except Exception:
            pass

        with patch('modules.app_core.set_window_icon_native'), \
             patch('modules.dialogs.settings_dialog.set_window_icon_native'):
            self.app = InspectorApp(self.root)

        self.app.saved_auto_select_new = True
        if hasattr(self.app, 'var_auto_connect_server'):
            self.app.var_auto_connect_server.set(False)

        if auto_scan:
            self.app.start_background_tasks()

        self.pump(5)
        return self.app

    def pump(self, cycles=10, delay=0.005, **kwargs):
        """
        Pump the PyQt6 event loop to process idle tasks and after() callbacks.
        """
        if 'times' in kwargs:
            cycles = kwargs['times']
        elif 'count' in kwargs:
            cycles = kwargs['count']
        for _ in range(cycles):
            self._drain_after_queue()
            try:
                if self.root.winfo_exists():
                    self.root.update_idletasks()
                    self.root.update()
            except Exception:
                break
            if delay > 0:
                time.sleep(delay)
        self._drain_after_queue()

    def wait_for(self, condition_fn, timeout=4.0, poll_interval=0.02):
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
                    return res
            except Exception:
                pass
        self.pump(2)
        res = condition_fn()
        if res:
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
                if hasattr(self.app, 'is_backing_up') and self.app.is_backing_up.is_set():
                    self.app.is_backing_up.clear()
                if self.app.serial_connection and getattr(self.app.serial_connection, 'is_open', False):
                    self.app.on_serial_disconnect()

                for th_name in ('flash_thread', 'detect_thread', 'partition_hw_thread', 'serial_thread', 'backup_thread', 'clone_thread'):
                    th = getattr(self.app, th_name, None)
                    if th and th.is_alive():
                        th.join(timeout=0.3)
            except Exception:
                pass

        self.pump(3, delay=0.005)

        while not _global_after_queue.empty():
            try:
                _global_after_queue.get_nowait()
            except queue.Empty:
                break

        try:
            self.root.config(menu="")
        except Exception:
            pass

        for child in list(self.root.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        while not _global_after_queue.empty():
            try:
                _global_after_queue.get_nowait()
            except queue.Empty:
                break

        gc.collect()

        try:
            if self.root.winfo_exists():
                self.root.update_idletasks()
                self.root.update()
        except Exception:
            pass

        self.app = None
