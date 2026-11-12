# -*- coding: utf-8 -*-
"""
HeadlessAppHarness: Test harness for headless Tkinter lifecycle management.
Initializes InspectorApp in an off-screen withdrawn Tk root, pumps event loops,
provides deterministic condition waiting, and ensures clean thread termination.
"""
import gc
import os
import queue
import sys
import threading
import time
import tkinter as tk
from unittest.mock import patch

from modules.app_core import InspectorApp

# Ensure TCL_LIBRARY and TK_LIBRARY are properly set for Windows environments
if "TCL_LIBRARY" not in os.environ:
    tcl_dir = os.path.join(sys.base_prefix, "tcl", "tcl8.6")
    if os.path.exists(tcl_dir):
        os.environ["TCL_LIBRARY"] = tcl_dir
if "TK_LIBRARY" not in os.environ:
    tk_dir = os.path.join(sys.base_prefix, "tcl", "tk8.6")
    if os.path.exists(tk_dir):
        os.environ["TK_LIBRARY"] = tk_dir

# Thread-safe after() queue for background thread dispatching
_global_after_queue = queue.Queue()
_original_misc_after = tk.Misc.after


def _threadsafe_misc_after(self, ms, func=None, *args):
    if func is None:
        return _original_misc_after(self, ms)
    if threading.current_thread() is threading.main_thread():
        try:
            return _original_misc_after(self, ms, func, *args)
        except RuntimeError as e:
            if "main thread is not in main loop" not in str(e):
                raise
    # Worker thread (or main thread fallback): enqueue to run in main thread
    run_at = time.time() + (ms / 1000.0)
    _global_after_queue.put((run_at, func, args))
    return f"mock_timer_{id(func)}"


tk.Misc.after = _threadsafe_misc_after

_original_misc_winfo_exists = tk.Misc.winfo_exists


def _threadsafe_misc_winfo_exists(self):
    if threading.current_thread() is threading.main_thread():
        return _original_misc_winfo_exists(self)
    # Non-main thread: safely check if window still exists without calling Tcl cross-thread
    return getattr(self, '_w', None) is not None


tk.Misc.winfo_exists = _threadsafe_misc_winfo_exists

_orig_var_del = tk.Variable.__del__
def _safe_var_del(self):
    try:
        _orig_var_del(self)
    except (tk.TclError, RuntimeError):
        pass
tk.Variable.__del__ = _safe_var_del

_orig_img_del = tk.Image.__del__
def _safe_img_del(self):
    try:
        _orig_img_del(self)
    except (tk.TclError, RuntimeError):
        pass
tk.Image.__del__ = _safe_img_del


class HeadlessAppHarness:
    """
    Manages InspectorApp lifecycle in a headless test environment.
    Guarantees no visual desktop windows appear and safely tears down background threads.
    Reuses a persistent withdrawn Tk root to avoid Tcl re-init corruption on Windows.
    """

    _shared_root = None

    @classmethod
    def get_shared_root(cls):
        if cls._shared_root is None or not cls._shared_root.winfo_exists():
            try:
                cls._shared_root = tk.Tk()
                cls._shared_root.withdraw()
            except tk.TclError as exc:
                raise RuntimeError(f"Tcl/Tk display environment unavailable: {exc}")
        return cls._shared_root

    def __init__(self):
        self.root = self.get_shared_root()
        self.app = None

    def _drain_after_queue(self):
        """Execute all queued worker callbacks whose scheduled time has arrived."""
        now = time.time()
        remaining = []
        while not _global_after_queue.empty():
            try:
                run_at, func, args = _global_after_queue.get_nowait()
                if now >= run_at:
                    try:
                        func(*args)
                    except Exception as err:
                        import traceback
                        traceback.print_exc()
                else:
                    remaining.append((run_at, func, args))
            except queue.Empty:
                break
        for item in remaining:
            _global_after_queue.put(item)

    def start(self, auto_scan=False) -> InspectorApp:
        """
        Instantiate InspectorApp with native window icon calls safely mocked out.
        Optionally triggers background tasks.
        """
        # Drain any leftover callbacks from prior tests
        while not _global_after_queue.empty():
            try:
                _global_after_queue.get_nowait()
            except queue.Empty:
                break

        # Clear any leftover widgets from prior tests
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

        # Set default test geometry to avoid layout recalculation lags
        self.app.saved_auto_select_new = True
        if hasattr(self.app, 'var_auto_connect_server'):
            self.app.var_auto_connect_server.set(False)

        if auto_scan:
            self.app.start_background_tasks()

        self.pump(5)
        return self.app

    def pump(self, cycles=10, delay=0.005, **kwargs):
        """
        Pump the Tkinter event loop to process idle tasks and after() callbacks.
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
            except (tk.TclError, Exception):
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
        # Final attempt
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
                if self.app.serial_connection and getattr(self.app.serial_connection, 'is_open', False):
                    self.app.on_serial_disconnect()

                # Gracefully join background hardware threads with short timeout
                for th_name in ('flash_thread', 'detect_thread', 'partition_hw_thread', 'serial_thread'):
                    th = getattr(self.app, th_name, None)
                    if th and th.is_alive():
                        th.join(timeout=0.3)
            except Exception:
                pass

        self.pump(3, delay=0.005)

        # Cancel all pending native Tcl timers
        try:
            if self.root.winfo_exists():
                timers = self.root.tk.call('after', 'info')
                for t in self.root.tk.splitlist(timers):
                    try:
                        self.root.after_cancel(t)
                    except Exception:
                        pass
        except Exception:
            pass

        # Drain thread-safe queue
        while not _global_after_queue.empty():
            try:
                _global_after_queue.get_nowait()
            except queue.Empty:
                break

        # Clear menu bar
        try:
            self.root.config(menu="")
        except Exception:
            pass

        # Clear widgets but keep root alive for next test
        for child in list(self.root.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass

        # Drain thread-safe queue again
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
