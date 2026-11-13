# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.11 - Update Checker & Downloader Utility
Kiểm tra phiên bản mới từ GitHub Releases API và tải trực tiếp file cập nhật.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from typing import Callable, Dict, Any, Tuple
from modules.config import APP_VERSION


DEFAULT_REPO = "ybao2004/esp32_manager_tool"


def is_running_frozen() -> bool:
    """Trả về True nếu ứng dụng đang chạy từ file đóng gói (.exe PyInstaller)."""
    return bool(getattr(sys, "frozen", False)) and bool(getattr(sys, "executable", ""))


def get_running_executable_path() -> str:
    """Trả về đường dẫn tuyệt đối của file .exe đang chạy (hoặc chuỗi rỗng nếu chạy từ source)."""
    if not is_running_frozen():
        return ""
    return os.path.abspath(sys.executable)


def is_same_target_as_running_exe(dest_path: str) -> bool:
    """Kiểm tra dest_path có trỏ đúng tới file .exe đang chạy hay không."""
    if not dest_path:
        return False
    running_exe = get_running_executable_path()
    if not running_exe:
        return False
    try:
        norm_dest = os.path.normcase(os.path.realpath(os.path.abspath(dest_path)))
        norm_running = os.path.normcase(os.path.realpath(running_exe))
        return norm_dest == norm_running
    except OSError:
        return os.path.normcase(os.path.abspath(dest_path)) == os.path.normcase(running_exe)


def get_staged_update_path(asset_name: str = "Esp32_manager_tool_update.exe") -> str:
    """Tạo đường dẫn file tạm an toàn trong %TEMP% để tải bản cập nhật trước khi thay thế."""
    base_name = os.path.basename(asset_name or "Esp32_manager_tool_update.exe").strip()
    if not base_name:
        base_name = "Esp32_manager_tool_update.exe"
    return os.path.join(tempfile.gettempdir(), f"esp32_manager_update_{os.getpid()}_{base_name}")


def parse_version_tuple(ver_str: str) -> Tuple[int, ...]:
    """Chuyển chuỗi phiên bản (e.g. 'v1.0', '1.2.3', 'v2.1-beta') thành tuple số nguyên để so sánh"""
    if not ver_str:
        return (0,)
    # Tìm các cụm số nguyên liên tiếp
    nums = re.findall(r"\d+", str(ver_str))
    if not nums:
        return (0,)
    return tuple(int(n) for n in nums)


def is_newer_version(latest_tag: str, current_version: str) -> bool:
    """So sánh xem latest_tag có lớn hơn current_version không"""
    t_latest = parse_version_tuple(latest_tag)
    t_current = parse_version_tuple(current_version)

    # Đệm số 0 cho bằng độ dài nếu cần
    max_len = max(len(t_latest), len(t_current))
    t_latest_pad = t_latest + (0,) * (max_len - len(t_latest))
    t_current_pad = t_current + (0,) * (max_len - len(t_current))

    return t_latest_pad > t_current_pad


def check_for_updates(current_version: str = "1.0", repo: str = DEFAULT_REPO) -> Dict[str, Any]:
    """
    Kiểm tra phiên bản phát hành mới nhất từ GitHub API.
    Không làm sập ứng dụng khi offline hoặc khi repo chưa có release nào.
    """
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {
        "User-Agent": f"Esp32ManagerTool/{current_version}",
        "Accept": "application/vnd.github.v3+json"
    }
    req = urllib.request.Request(api_url, headers=headers)

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                tag_name = data.get("tag_name", "").strip()
                release_name = data.get("name", tag_name)
                release_notes = data.get("body", "").strip()
                published_at = data.get("published_at", "")[:10]
                html_url = data.get("html_url", f"https://github.com/{repo}/releases")

                assets = data.get("assets", [])
                download_url = ""
                asset_name = ""
                asset_size = 0

                # Ưu tiên tìm file .exe hoặc .zip
                for asset in assets:
                    name = asset.get("name", "").lower()
                    if name.endswith(".exe") or name.endswith(".zip") or name.endswith(".rar"):
                        download_url = asset.get("browser_download_url", "")
                        asset_name = asset.get("name", "")
                        asset_size = asset.get("size", 0)
                        break

                # Nếu không có asset đóng gói riêng, lấy zipball source
                if not download_url and data.get("zipball_url"):
                    download_url = data.get("zipball_url", "")
                    asset_name = f"{tag_name}.zip"

                has_update = is_newer_version(tag_name, current_version)

                return {
                    "status": "success",
                    "has_update": has_update,
                    "latest_version": tag_name,
                    "release_name": release_name,
                    "release_notes": release_notes,
                    "published_at": published_at,
                    "html_url": html_url,
                    "download_url": download_url,
                    "asset_name": asset_name,
                    "asset_size": asset_size,
                    "message": "Đã kiểm tra thành công."
                }
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {
                "status": "no_releases",
                "has_update": False,
                "latest_version": current_version,
                "release_name": "",
                "release_notes": "",
                "published_at": "",
                "html_url": f"https://github.com/{repo}",
                "download_url": "",
                "asset_name": "",
                "asset_size": 0,
                "message": f"Chưa có bản phát hành chính thức nào trên GitHub repository:\nhttps://github.com/{repo}\nBạn đang sử dụng phiên bản gốc (v{current_version})."
            }
        return {
            "status": "error",
            "has_update": False,
            "latest_version": current_version,
            "message": f"Lỗi máy chủ GitHub HTTP {e.code}: {e.reason}"
        }
    except urllib.error.URLError as e:
        return {
            "status": "error",
            "has_update": False,
            "latest_version": current_version,
            "message": f"Không thể kết nối Internet hoặc GitHub API:\n{e.reason}"
        }
    except Exception as e:
        return {
            "status": "error",
            "has_update": False,
            "latest_version": current_version,
            "message": f"Ngoại lệ khi kiểm tra cập nhật:\n{str(e)}"
        }


def download_update_asset(
    download_url: str,
    dest_path: str,
    progress_callback: Callable[[float, int, int], None] | None = None,
    cancel_event: threading.Event | None = None
) -> Tuple[bool, str]:
    """
    Tải file cập nhật trực tiếp về máy tính kèm theo callback cập nhật tiến trình.
    """
    if not download_url:
        return False, "Không có đường dẫn tải file cập nhật."
    if not dest_path:
        return False, "Đường dẫn lưu file cập nhật không hợp lệ."
    if is_same_target_as_running_exe(dest_path):
        return (
            False,
            "Không thể ghi đè trực tiếp lên file đang chạy. Vui lòng dùng chế độ tự cập nhật để tải tạm và thay thế khi đóng ứng dụng.",
        )

    headers = {
        "User-Agent": f"Esp32ManagerTool/{APP_VERSION}"
    }
    req = urllib.request.Request(download_url, headers=headers)
    parent_dir = os.path.dirname(os.path.abspath(dest_path))
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    temp_dest = f"{dest_path}.{os.getpid()}.downloading"

    try:
        with urllib.request.urlopen(req, timeout=30) as response, open(temp_dest, "wb") as out_file:
            total_size = int(response.headers.get("content-length", 0))
            downloaded = 0
            chunk_size = 16384  # 16 KB

            while True:
                if cancel_event and cancel_event.is_set():
                    out_file.close()
                    if os.path.exists(temp_dest):
                        try:
                            os.remove(temp_dest)
                        except OSError:
                            pass
                    return False, "Người dùng đã hủy quá trình tải."

                chunk = response.read(chunk_size)
                if not chunk:
                    break

                out_file.write(chunk)
                downloaded += len(chunk)

                if progress_callback:
                    percent = (downloaded / total_size * 100.0) if total_size > 0 else 0.0
                    progress_callback(percent, downloaded, total_size)

        # Thay thế nguyên tử file đích (tránh WinError 183 khi file đích đã tồn tại)
        try:
            os.replace(temp_dest, dest_path)
        except OSError as replace_err:
            if os.path.exists(temp_dest):
                try:
                    os.remove(temp_dest)
                except OSError:
                    pass
            return (
                False,
                f"Không thể ghi vào '{dest_path}' (file có thể đang được chương trình khác sử dụng): {replace_err}",
            )
        return True, dest_path

    except Exception as e:
        if os.path.exists(temp_dest):
            try:
                os.remove(temp_dest)
            except OSError:
                pass
        return False, f"Lỗi khi tải file: {str(e)}"


def build_windows_self_update_script(
    staged_exe_path: str,
    target_exe_path: str,
    current_pid: int,
    relaunch: bool = True,
) -> str:
    """Sinh nội dung script .cmd đợi tiến trình hiện tại thoát, ghi đè .exe và khởi động lại."""
    src = os.path.abspath(staged_exe_path).replace('"', "")
    dst = os.path.abspath(target_exe_path).replace('"', "")
    pid = int(current_pid)
    relaunch_block = f'start "" "{dst}"\r\n' if relaunch else ""
    return (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        f"set \"TARGET_PID={pid}\"\r\n"
        f"set \"SRC_EXE={src}\"\r\n"
        f"set \"DST_EXE={dst}\"\r\n"
        "set /a WAIT_COUNT=0\r\n"
        ":WAIT_EXIT\r\n"
        "tasklist /FI \"PID eq %TARGET_PID%\" /FO CSV /NH 2>nul | findstr /C:\",\\\"%TARGET_PID%\\\",\" >nul\r\n"
        "if errorlevel 1 goto REPLACE_FILE\r\n"
        "set /a WAIT_COUNT+=1\r\n"
        "if %WAIT_COUNT% GEQ 60 goto REPLACE_FILE\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        "goto WAIT_EXIT\r\n"
        ":REPLACE_FILE\r\n"
        "set /a RETRY=0\r\n"
        ":RETRY_MOVE\r\n"
        "move /Y \"%SRC_EXE%\" \"%DST_EXE%\" >nul 2>nul\r\n"
        "if not errorlevel 1 goto LAUNCH_NEW\r\n"
        "copy /Y \"%SRC_EXE%\" \"%DST_EXE%\" >nul 2>nul\r\n"
        "if not errorlevel 1 (\r\n"
        "    del /F /Q \"%SRC_EXE%\" >nul 2>nul\r\n"
        "    goto LAUNCH_NEW\r\n"
        ")\r\n"
        "set /a RETRY+=1\r\n"
        "if %RETRY% GEQ 20 goto CLEANUP\r\n"
        "ping -n 2 127.0.0.1 >nul\r\n"
        "goto RETRY_MOVE\r\n"
        ":LAUNCH_NEW\r\n"
        f"{relaunch_block}"
        ":CLEANUP\r\n"
        "(goto) 2>nul & del \"%~f0\"\r\n"
    )


def launch_windows_self_updater(
    staged_exe_path: str,
    target_exe_path: str,
    current_pid: int | None = None,
    relaunch: bool = True,
) -> Tuple[bool, str]:
    """Khởi chạy script tự cập nhật chạy ngầm trên Windows để thay thế file .exe sau khi app thoát."""
    if os.name != "nt":
        return False, "Chức năng tự thay thế file .exe chỉ hỗ trợ trên Windows."
    if not staged_exe_path or not os.path.isfile(staged_exe_path):
        return False, "Không tìm thấy file cập nhật tạm để thay thế."
    if not target_exe_path:
        return False, "Không xác định được đường dẫn file ứng dụng đích."

    pid = int(current_pid if current_pid is not None else os.getpid())
    script_path = os.path.join(tempfile.gettempdir(), f"esp32_self_update_{pid}.cmd")
    script_content = build_windows_self_update_script(
        staged_exe_path=staged_exe_path,
        target_exe_path=target_exe_path,
        current_pid=pid,
        relaunch=relaunch,
    )

    try:
        with open(script_path, "w", encoding="utf-8", newline="") as fp:
            fp.write(script_content)

        # Không kết hợp DETACHED_PROCESS với CREATE_NO_WINDOW vì trên Windows 11
        # điều đó khiến findstr/tasklist con mở cửa sổ Windows Terminal mới.
        creation_flags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )
        startupinfo = None
        if hasattr(subprocess, "STARTUPINFO"):
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= getattr(subprocess, "STARTF_USESHOWWINDOW", 0)
            startupinfo.wShowWindow = 0  # SW_HIDE

        proc = subprocess.Popen(
            ["cmd.exe", "/c", script_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            startupinfo=startupinfo,
            creationflags=creation_flags,
        )
        try:
            from modules.single_instance import exempt_child_pid
            exempt_child_pid(proc.pid)
        except Exception:
            pass
        return True, script_path
    except Exception as exc:
        try:
            if os.path.exists(script_path):
                os.remove(script_path)
        except OSError:
            pass
        return False, f"Không thể khởi chạy trình tự cập nhật: {exc}"
