# -*- coding: utf-8 -*-
"""
Kiểm thử tính năng kiểm tra & cập nhật nội tuyến trong SettingsPage:
- Không mở cửa sổ UpdateDialog riêng
- Nút bật/tắt tự kiểm tra cập nhật (mặc định tắt) + lưu/nạp cấu hình
- Chuỗi dấu chấm đỏ hướng dẫn từ Sidebar -> Sub-tab Cài đặt -> Nút cập nhật
- Xử lý an toàn khi tải trùng đường dẫn file .exe đang chạy (tải tạm & tự thay thế)
"""
import json
import os
import time
from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QApplication

from modules.ui.dispatch import UiDispatcher
from modules.ui.main_window import MainWindow
from tests.mock_hardware.app_harness import HeadlessAppHarness


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    HeadlessAppHarness.get_shared_root()
    app = QApplication.instance()
    yield app


def _wait_until(qapp, predicate, timeout_s: float = 3.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    qapp.processEvents()
    return predicate()


def test_auto_check_default_off_and_persists_in_config(qapp, tmp_path):
    cfg_path = tmp_path / "settings_update_pref.json"
    with patch("modules.ui.main_window.CONFIG_FILE", str(cfg_path), create=True), \
         patch("modules.app_core.set_window_icon_native"):
        win = MainWindow(auto_start=False)
        try:
            assert win.saved_auto_check_updates is False
            assert win.page_settings.chk_auto_check_update.isChecked() is False

            with patch.object(win, "trigger_update_check") as mock_check:
                win.start_background_tasks()
                qapp.processEvents()
                mock_check.assert_not_called()

            # Bật tùy chọn và lưu cấu hình
            win.page_settings._syncing_update_prefs = True
            win.page_settings.chk_auto_check_update.setChecked(True)
            win.page_settings._syncing_update_prefs = False
            with patch("modules.ui.dialogs_service.show_info"):
                win.page_settings._on_save_settings()
            assert win.saved_auto_check_updates is True
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            assert data["auto_check_updates"] is True

            # Khôi phục mặc định phải đưa về False
            win.reset_config(confirm=False)
            assert win.saved_auto_check_updates is False
            assert win.page_settings.chk_auto_check_update.isChecked() is False
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()


def test_open_update_dialog_uses_inline_settings_without_new_window(qapp, tmp_path):
    cfg_path = tmp_path / "settings_inline_upd.json"
    fake_res = {
        "status": "success",
        "has_update": False,
        "latest_version": "v1.9",
        "release_name": "v1.9",
        "release_notes": "Up to date",
        "published_at": "2026-11-13",
        "download_url": "",
        "asset_name": "",
        "asset_size": 0,
    }
    with patch("modules.ui.main_window.CONFIG_FILE", str(cfg_path), create=True), \
         patch("modules.app_core.set_window_icon_native"), \
         patch("modules.ui.pages.settings_page.check_for_updates", return_value=fake_res), \
         patch("modules.ui.dialogs.about_update_dialogs.UpdateDialog") as mock_dlg:
        win = MainWindow(auto_start=False)
        try:
            win.open_update_dialog()
            assert win.stack.currentIndex() == 5
            assert win.page_settings.tabs.currentIndex() == 2
            mock_dlg.assert_not_called()

            done = _wait_until(
                qapp,
                lambda: not win.page_settings._update_check_in_progress
                and "mới nhất" in win.page_settings.lbl_update_status.text(),
            )
            assert done is True
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()


def test_red_dot_indicator_chain_shows_and_clears(qapp, tmp_path):
    cfg_path = tmp_path / "settings_red_dot.json"
    newer_res = {
        "status": "success",
        "has_update": True,
        "latest_version": "v2.0",
        "release_name": "Esp32 Manager Tool v2.0",
        "release_notes": "- New feature",
        "published_at": "2026-11-13",
        "download_url": "https://example.com/Esp32_manager_tool.exe",
        "asset_name": "Esp32_manager_tool.exe",
        "asset_size": 1024 * 1024,
    }
    up_to_date_res = {
        "status": "success",
        "has_update": False,
        "latest_version": "v1.9",
        "release_name": "v1.9",
        "release_notes": "Latest",
        "published_at": "2026-11-13",
        "download_url": "",
        "asset_name": "",
        "asset_size": 0,
    }
    with patch("modules.ui.main_window.CONFIG_FILE", str(cfg_path), create=True), \
         patch("modules.app_core.set_window_icon_native"), \
         patch("modules.ui.pages.settings_page.is_running_frozen", return_value=True), \
         patch("modules.ui.pages.settings_page.os.name", "nt"):
        win = MainWindow(auto_start=False)
        try:
            # 1. Phát hiện bản cập nhật mới -> chấm đỏ hiện từ Sidebar -> Sub-tab 0 -> nút Cập nhật ngay
            with patch("modules.ui.pages.settings_page.check_for_updates", return_value=newer_res):
                win.trigger_update_check(silent=True)
                ok = _wait_until(qapp, lambda: win.has_available_update is True)
                assert ok is True

            assert win.sidebar.has_settings_badge() is True
            assert not win.page_settings.tabs.tabBar().tabIcon(2).isNull()
            assert not win.page_settings.btn_update_now.isHidden()
            assert win.page_settings._btn_update_now_badge.is_active() is True
            assert win.page_settings._btn_chk_badge.is_active() is False

            # 2. Kiểm tra lại thấy đã là bản mới nhất -> tắt toàn bộ chấm đỏ
            with patch("modules.ui.pages.settings_page.check_for_updates", return_value=up_to_date_res):
                win.trigger_update_check(silent=False)
                cleared = _wait_until(qapp, lambda: win.has_available_update is False)
                assert cleared is True

            assert win.sidebar.has_settings_badge() is False
            assert win.page_settings.tabs.tabBar().tabIcon(2).isNull()
            assert win.page_settings._btn_update_now_badge.is_active() is False
            assert win.page_settings._btn_chk_badge.is_active() is False
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()


def test_direct_update_downloads_without_save_as_dialog(qapp, tmp_path):
    cfg_path = tmp_path / "settings_same_exe.json"
    running_exe = str(tmp_path / "Esp32_manager_tool.exe")
    with open(running_exe, "wb") as fp:
        fp.write(b"running")

    with patch("modules.ui.main_window.CONFIG_FILE", str(cfg_path), create=True), \
         patch("modules.app_core.set_window_icon_native"):
        win = MainWindow(auto_start=False)
        try:
            win.page_settings.latest_update_info = {
                "status": "success",
                "has_update": True,
                "latest_version": "v2.0",
                "download_url": "https://example.com/Esp32_manager_tool.exe",
                "asset_name": "Esp32_manager_tool.exe",
            }
            with patch("modules.ui.pages.settings_page.get_running_executable_path", return_value=running_exe), \
                 patch("modules.ui.pages.settings_page.os.name", "nt"), \
                 patch.object(win.page_settings, "_start_update_download") as mock_dl:
                win.page_settings._on_update_now_click()
                mock_dl.assert_called_once()
                args, kwargs = mock_dl.call_args
                # File tải về phải là đường dẫn tạm khác với running_exe, còn self_update_target là running_exe
                assert args[1] != running_exe
                assert "esp32_manager_update_" in os.path.basename(args[1])
                assert kwargs.get("self_update_target") == running_exe
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()


def test_update_tab_layout_and_zero_overlap_across_window_sizes(qapp, tmp_path):
    cfg_path = tmp_path / "settings_update_geom.json"
    with patch("modules.ui.main_window.CONFIG_FILE", str(cfg_path), create=True), \
         patch("modules.app_core.set_window_icon_native"), \
         patch("modules.ui.pages.settings_page.is_running_frozen", return_value=True), \
         patch("modules.ui.pages.settings_page.os.name", "nt"):
        win = MainWindow(auto_start=False)
        try:
            for w_size in [(1280, 720), (960, 580)]:
                win.resize(*w_size)
                win.show()
                win.notebook.select(5)
                page = win.page_settings
                page.select_sub_tab(2)
                assert page.tabs.currentIndex() == 2

                page._apply_update_check_result(
                    {
                        "status": "success",
                        "has_update": True,
                        "latest_version": "v2.0",
                        "release_name": "Esp32 Manager Tool v2.0",
                        "published_at": "2026-11-13",
                        "release_notes": "Line 1\nLine 2\nLine 3",
                        "asset_name": "Esp32_manager_tool.exe",
                        "asset_size": 67170000,
                        "download_url": "https://example.com/Esp32_manager_tool.exe",
                    },
                    silent=False,
                )
                assert not page.btn_update_now.isHidden()

                page.pb_update_download.setVisible(True)
                page.lbl_download_status.setVisible(True)
                page.lbl_download_status.setText("Đang tải: 0.09 MB / 67.17 MB (0.1%)")
                page.btn_cancel_update.setVisible(True)
                page.update_progress_box.setVisible(True)
                qapp.processEvents()

                r_prog = page.update_progress_box.geometry()
                r_txt = page.txt_release_notes.geometry()
                assert not r_prog.intersects(r_txt)
                assert r_prog.bottom() < r_txt.top()
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()
