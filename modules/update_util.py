# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.0 - Update Checker & Downloader Utility
Kiểm tra phiên bản mới từ GitHub Releases API và tải trực tiếp file cập nhật.
"""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.error
import urllib.request
from typing import Callable, Dict, Any, Tuple


DEFAULT_REPO = "ybao2004/esp32_manager_tool"


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

    headers = {
        "User-Agent": "Esp32ManagerTool/1.0"
    }
    req = urllib.request.Request(download_url, headers=headers)
    temp_dest = dest_path + ".downloading"

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

        # Đổi tên file tạm sang file chính thức
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        os.rename(temp_dest, dest_path)
        return True, dest_path

    except Exception as e:
        if os.path.exists(temp_dest):
            try:
                os.remove(temp_dest)
            except OSError:
                pass
        return False, f"Lỗi khi tải file: {str(e)}"
