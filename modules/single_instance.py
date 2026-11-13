# -*- coding: utf-8 -*-
"""
Quản lý Single-Instance và giải phóng tiến trình / tài nguyên hệ điều hành an toàn (v1.8).
- Ngăn mở đồng thời nhiều cửa sổ ứng dụng bằng Win32 Kernel Mutex + IPC QLocalServer/QLocalSocket.
- Khi có instance thứ hai khởi chạy, đánh thức cửa sổ đang mở lên phía trước rồi thoát sạch sẽ.
- Khi đóng ứng dụng, dừng và thu hồi các tiến trình con đang gắn với tiến trình hiện tại.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from typing import Callable, Optional

from PyQt6.QtNetwork import QLocalServer, QLocalSocket

_ERROR_ALREADY_EXISTS = 183
_TH32CS_SNAPPROCESS = 0x00000002
_PROCESS_TERMINATE = 0x0001
_PROCESS_SYNCHRONIZE = 0x00100000

_TRACKED_LOCK = threading.Lock()
_TRACKED_PROCESSES: set = set()
_EXEMPT_PIDS: set[int] = set()


def exempt_child_pid(pid: Optional[int]) -> None:
    """Đánh dấu một PID con (ví dụ script tự cập nhật) được miễn trừ khi dọn tiến trình lúc thoát."""
    if pid is None:
        return
    try:
        pid_int = int(pid)
    except (TypeError, ValueError):
        return
    if pid_int <= 0:
        return
    with _TRACKED_LOCK:
        _EXEMPT_PIDS.add(pid_int)


def register_child_process(proc) -> None:
    """Đăng ký tiến trình con (subprocess.Popen / multiprocessing.Process) để giải phóng khi thoát."""
    if proc is None:
        return
    with _TRACKED_LOCK:
        _TRACKED_PROCESSES.add(proc)


def unregister_child_process(proc) -> None:
    """Gỡ đăng ký tiến trình con sau khi đã hoàn tất bình thường."""
    if proc is None:
        return
    with _TRACKED_LOCK:
        _TRACKED_PROCESSES.discard(proc)


def _terminate_tracked_processes() -> int:
    """Dừng toàn bộ tiến trình con đã đăng ký còn đang hoạt động."""
    terminated = 0
    with _TRACKED_LOCK:
        snapshot = list(_TRACKED_PROCESSES)
        _TRACKED_PROCESSES.clear()

    for proc in snapshot:
        try:
            # subprocess.Popen
            if hasattr(proc, "poll") and hasattr(proc, "terminate"):
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=0.5)
                    except Exception:
                        if hasattr(proc, "kill"):
                            proc.kill()
                    terminated += 1
            # multiprocessing.Process
            elif hasattr(proc, "is_alive") and hasattr(proc, "terminate"):
                if proc.is_alive():
                    proc.terminate()
                    proc.join(timeout=0.5)
                    if proc.is_alive() and hasattr(proc, "kill"):
                        proc.kill()
                        proc.join(timeout=0.3)
                    terminated += 1
        except Exception:
            pass
    return terminated


def _terminate_windows_child_pids(parent_pid: int) -> int:
    """Duyệt Snapshot tiến trình Windows để dọn các tiến trình con trực tiếp của parent_pid."""
    if os.name != "nt":
        return 0
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snap = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    if snap == wintypes.HANDLE(-1).value:
        return 0

    child_pids: list[tuple[int, str]] = []
    try:
        pe = PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            while True:
                if int(pe.th32ParentProcessID) == int(parent_pid) and int(pe.th32ProcessID) != int(parent_pid):
                    child_pids.append((int(pe.th32ProcessID), str(pe.szExeFile)))
                if not kernel32.Process32NextW(snap, ctypes.byref(pe)):
                    break
    finally:
        kernel32.CloseHandle(snap)

    killed = 0
    # Không đụng tới console host hệ thống hoặc tiến trình được miễn trừ (vd script cập nhật)
    ignored_names = {"conhost.exe", "csrss.exe"}
    with _TRACKED_LOCK:
        exempt_snapshot = set(_EXEMPT_PIDS)
    for pid, exe_name in child_pids:
        if pid in exempt_snapshot or exe_name.lower() in ignored_names:
            continue
        h_proc = kernel32.OpenProcess(_PROCESS_TERMINATE | _PROCESS_SYNCHRONIZE, False, pid)
        if h_proc:
            try:
                if kernel32.TerminateProcess(h_proc, 1):
                    kernel32.WaitForSingleObject(h_proc, 500)
                    killed += 1
            finally:
                kernel32.CloseHandle(h_proc)
    return killed


def terminate_child_processes(parent_pid: Optional[int] = None) -> int:
    """
    Thoát toàn bộ tiến trình con trực tiếp và các tiến trình đã đăng ký thuộc ứng dụng.
    An toàn khi không có tiến trình con nào.
    """
    count = _terminate_tracked_processes()
    pid = int(parent_pid if parent_pid is not None else os.getpid())
    if os.name == "nt":
        count += _terminate_windows_child_pids(pid)
    return count


class SingleInstanceGuard:
    """
    Bộ khóa đơn thực thể (Single Instance Guard):
    - Đảm bảo chỉ có duy nhất một cửa sổ ESP32 Manager Tool hoạt động cùng lúc.
    - Cung cấp kênh IPC QLocalServer/QLocalSocket để đưa cửa sổ đang mở lên phía trước.
    """

    def __init__(
        self,
        app_id: str = "esp32_manager_tool_single_instance_v1",
        on_activate: Optional[Callable[[], None]] = None,
    ):
        self.app_id = app_id
        self._on_activate = on_activate
        self._mutex_handle = None
        self._posix_lock_file = None
        self._server: Optional[QLocalServer] = None
        self._acquired = False

    @property
    def is_acquired(self) -> bool:
        return self._acquired

    def set_on_activate(self, callback: Optional[Callable[[], None]]) -> None:
        """Gắn callback đưa cửa sổ chính lên phía trước khi nhận yêu cầu từ instance thứ hai."""
        self._on_activate = callback

    def acquire(self) -> bool:
        """
        Thử chiếm quyền thực thể duy nhất của ứng dụng.
        Trả về True nếu đây là instance đầu tiên; False nếu đã có instance khác đang chạy.
        """
        if self._acquired:
            return True

        if os.name == "nt":
            if not self._acquire_windows_mutex():
                return False
        else:
            if not self._acquire_posix_lock():
                return False

        self._start_ipc_server()
        self._acquired = True
        return True

    def _acquire_windows_mutex(self) -> bool:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        mutex_name = f"Local\\{self.app_id}"
        handle = kernel32.CreateMutexW(None, False, mutex_name)
        err = ctypes.get_last_error()
        if not handle:
            return False
        if err == _ERROR_ALREADY_EXISTS:
            kernel32.CloseHandle(handle)
            return False
        self._mutex_handle = handle
        return True

    def _acquire_posix_lock(self) -> bool:
        import fcntl

        lock_path = os.path.join(tempfile.gettempdir(), f"{self.app_id}.lock")
        fp = open(lock_path, "w", encoding="utf-8")
        try:
            fcntl.flock(fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fp.write(str(os.getpid()))
            fp.flush()
            self._posix_lock_file = fp
            return True
        except OSError:
            fp.close()
            return False

    def _start_ipc_server(self) -> None:
        try:
            QLocalServer.removeServer(self.app_id)
            server = QLocalServer()
            if server.listen(self.app_id):
                server.newConnection.connect(self._handle_ipc_connection)
                self._server = server
            else:
                server.deleteLater()
        except Exception:
            self._server = None

    def _handle_ipc_connection(self) -> None:
        if not self._server:
            return
        while self._server.hasPendingConnections():
            sock = self._server.nextPendingConnection()
            if sock is None:
                continue
            try:
                if sock.bytesAvailable() == 0:
                    sock.waitForReadyRead(100)
                payload = bytes(sock.readAll()).decode("utf-8", errors="ignore").strip()
                if sock.state() != QLocalSocket.LocalSocketState.UnconnectedState:
                    sock.disconnectFromServer()
                sock.deleteLater()
                if (not payload or "ACTIVATE" in payload) and callable(self._on_activate):
                    self._on_activate()
            except Exception:
                try:
                    sock.deleteLater()
                except Exception:
                    pass

    def notify_existing_instance(self, timeout_ms: int = 500) -> bool:
        """Gửi tín hiệu đánh thức cửa sổ đang chạy lên phía trước."""
        sock = QLocalSocket()
        try:
            sock.connectToServer(self.app_id)
            if not sock.waitForConnected(timeout_ms):
                return False
            sock.write(b"ACTIVATE\n")
            sock.flush()
            sock.waitForBytesWritten(timeout_ms)
            sock.disconnectFromServer()
            return True
        except Exception:
            return False
        finally:
            try:
                sock.abort()
                sock.deleteLater()
            except Exception:
                pass

    def release(self) -> None:
        """Đóng server IPC và trả khóa hệ điều hành an toàn."""
        if self._server is not None:
            try:
                self._server.close()
                self._server.deleteLater()
            except Exception:
                pass
            self._server = None
            try:
                QLocalServer.removeServer(self.app_id)
            except Exception:
                pass

        if os.name == "nt" and self._mutex_handle:
            try:
                import ctypes
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel32.CloseHandle(self._mutex_handle)
            except Exception:
                pass
            self._mutex_handle = None

        if self._posix_lock_file is not None:
            try:
                import fcntl
                fcntl.flock(self._posix_lock_file.fileno(), fcntl.LOCK_UN)
                self._posix_lock_file.close()
            except Exception:
                pass
            self._posix_lock_file = None

        self._acquired = False
