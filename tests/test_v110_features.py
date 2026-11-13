# -*- coding: utf-8 -*-
"""
Kiểm thử toàn diện cho phiên bản v1.10:
- Phân tích phần trăm tiến trình cho cả esptool v4 & v5 và dọn trạng thái 'Đang...' khi lỗi.
- Lazy-load esptool để tăng tốc khởi động.
- Bỏ popup thừa sau khi Đọc bảng phân vùng từ chip ở Tab 4.
- Tab 5: gom 1 hàng, Board Gốc dùng chung Cổng COM trên cùng, lọc khỏi Board Đích, Baudrate độc lập.
- Màn hình khởi động StartupSplash (không tác giả/giấy phép) và handoff pyi_splash.
"""
import ast
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QCheckBox, QPushButton

from modules.config import APP_NAME, APP_VERSION
from modules.esptool_util import (
    abort_active_esptool,
    parse_esptool_progress_percent,
)
from modules.ui.splash import StartupSplash, close_pyi_splash


def test_app_version_is_v110_and_zero_tkinter():
    """Phiên bản là 1.10 và không có import tkinter trong mã nguồn."""
    assert APP_VERSION == "1.10"
    root_dir = Path(__file__).resolve().parent.parent
    py_files = [root_dir / "main.py"] + list((root_dir / "modules").rglob("*.py"))
    for fpath in py_files:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all("tkinter" not in alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert "tkinter" not in (node.module or "").lower()


def test_parse_esptool_progress_percent_v4_and_v5():
    """Hỗ trợ trích xuất % tiến trình cho cả esptool v4 và v5 (kể cả có mã ANSI)."""
    assert parse_esptool_progress_percent("Writing at 0x00010000... (45 %)") == 45.0
    assert parse_esptool_progress_percent("Reading at 0x00008000... (100%)") == 100.0
    assert parse_esptool_progress_percent(
        "\r\x1b[1A\x1b[2KWriting at 0x00010000... [====>      ]  45.3% 12345/27000 bytes..."
    ) == 45.3
    assert parse_esptool_progress_percent("Reading flash... [==========] 100.0%") == 100.0
    assert parse_esptool_progress_percent("Connecting.......") is None
    assert parse_esptool_progress_percent("Flash voltage 105%") is None


def test_esptool_lazy_import_on_fresh_interpreter():
    """Import modules.esptool_util không kéo esptool nặng lúc khởi động app."""
    repo_root = Path(__file__).resolve().parent.parent
    code = (
        "import sys; "
        "import modules.esptool_util as eu; "
        "assert 'esptool' not in sys.modules; "
        "assert eu.esptool is None; "
        "assert eu.abort_active_esptool() == 0; "
        "assert 'esptool' not in sys.modules"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_abort_active_esptool_noop_when_unloaded():
    """abort_active_esptool phải an toàn và trả về 0 khi chưa nạp esptool."""
    import modules.esptool_util as eu

    old = eu.esptool
    eu.esptool = None
    try:
        assert abort_active_esptool() == 0
    finally:
        eu.esptool = old


def test_startup_splash_stages_without_author_or_license(headless_app):
    """StartupSplash cập nhật tiến độ, mô tả bước khởi động và không hiển thị tác giả/giấy phép."""
    _harness, _app = headless_app
    splash = StartupSplash()
    try:
        splash.set_stage(35, "Đang nạp phân hệ công cụ...")
        assert splash.progress_bar.value() == 35
        assert splash.lbl_pct.text() == "35%"
        assert splash.lbl_stage.text() == "Đang nạp phân hệ công cụ..."

        splash.set_stage(180, "Hoàn tất")
        assert splash.progress_bar.value() == 100
        splash.set_stage(-10, "Bắt đầu")
        assert splash.progress_bar.value() == 0

        assert not hasattr(splash, "lbl_footer")
        assert not hasattr(splash, "lbl_app_name")
        assert f"v{APP_VERSION}" in splash.lbl_version.text()
        assert f"{APP_NAME} v{APP_VERSION}" in splash.windowTitle()

        flags = splash.windowFlags()
        assert (flags & Qt.WindowType.WindowType_Mask) == Qt.WindowType.Window
        assert not bool(flags & Qt.WindowType.WindowStaysOnTopHint)

        # Click vào splash không làm ẩn màn hình khởi động đột ngột
        splash.show()
        QTest.mouseClick(splash, Qt.MouseButton.LeftButton)
        assert splash.isVisible()

        # pyi_splash fallback an toàn khi không đóng gói
        assert isinstance(close_pyi_splash(), bool)
    finally:
        splash.close()


@pytest.mark.mock_hw
def test_tab4_hw_read_partition_no_success_popup(headless_app, mock_esptool, mock_dialogs):
    """Đọc bảng phân vùng từ chip ở Tab 4 thành công chỉ báo trạng thái & log, không bật popup."""
    harness, app = headless_app
    app.port_cb.set("COM3")
    app.table.clear()

    app._hw_read_partition_table()
    harness.wait_for(
        lambda: not getattr(app, "_is_partition_hw_running", False) and len(app.table.entries) > 0,
        timeout=4.0,
    )

    assert len(app.table.entries) == 4
    assert len(mock_dialogs["showinfo"]) == 0
    assert "Đã đọc và giải mã bảng phân vùng" in app.req_status_lbl["text"]
    assert app.status_prog.value() == 100


@pytest.mark.mock_hw
def test_tab5_single_row_shared_com_independent_baud_and_target_exclusion(headless_app, mock_ports):
    """
    Tab 5:
    - Không còn dropdown Board Gốc / nút Quét COM thừa; các nút nằm trong 1 hàng ngang trên 1280px.
    - Board Gốc tự động đồng bộ từ Cổng COM trên cùng & loại khỏi Board Đích.
    - Baudrate Tab 5 độc lập hoàn toàn với Baudrate trên cùng.
    """
    harness, app = headless_app
    app.sidebar.select(4)
    app.resize(1280, 760)
    harness.pump(times=4)

    assert not hasattr(app.page_backup, "cb_backup_src_port")
    assert not hasattr(app.page_backup, "btn_backup_refresh_com")
    assert hasattr(app.page_backup, "lbl_backup_src_port")

    # Kiểm tra các nút top_card cùng nằm trên 1 hàng ngang khi cửa sổ 1280px
    controls_y = [
        app.page_backup.lbl_backup_src_port.mapTo(app.page_backup, app.page_backup.lbl_backup_src_port.rect().topLeft()).y(),
        app.page_backup.cb_backup_baud.mapTo(app.page_backup, app.page_backup.cb_backup_baud.rect().topLeft()).y(),
        app.page_backup.btn_backup_read_chip.mapTo(app.page_backup, app.page_backup.btn_backup_read_chip.rect().topLeft()).y(),
        app.page_backup.btn_backup_sel_all.mapTo(app.page_backup, app.page_backup.btn_backup_sel_all.rect().topLeft()).y(),
        app.page_backup.btn_backup_sel_fw.mapTo(app.page_backup, app.page_backup.btn_backup_sel_fw.rect().topLeft()).y(),
        app.page_backup.chk_backup_trim.mapTo(app.page_backup, app.page_backup.chk_backup_trim.rect().topLeft()).y(),
    ]
    assert max(controls_y) - min(controls_y) <= 12, f"Các nút không nằm cùng 1 hàng: y={controls_y}"

    # Baudrate độc lập giữa top ConnectionBar và Tab 5
    app.baud_cb.setCurrentText("115200")
    app.cb_backup_baud.setCurrentText("921600")
    harness.pump(times=2)
    assert app.baud_cb.currentText() == "115200"
    assert app.cb_backup_baud.currentText() == "921600"
    assert app.backup_baud_var.get() == "921600"

    app.baud_cb.setCurrentText("230400")
    harness.pump(times=2)
    assert app.cb_backup_baud.currentText() == "921600"

    # Đồng bộ Cổng COM trên cùng -> Board Gốc và loại khỏi Board Đích
    mock_ports.set_ports(["COM15", "COM13"])
    app.update_port_list("", ["COM15", "COM13"])
    app.port_cb.setCurrentText("COM15")
    app.on_port_selected("COM15")
    harness.pump(times=2)

    assert app.lbl_backup_src_port.text() == "COM15"
    assert app.backup_src_port_var.get() == "COM15"
    assert list(app.clone_target_vars.keys()) == ["COM13"]


@pytest.mark.mock_hw
def test_status_bar_clears_stale_dang_task_on_error(headless_app):
    """Khi tác vụ lỗi hoặc kết thúc bận với 0%, nhãn tiến trình không bị kẹt chữ 'Đang ...'."""
    harness, app = headless_app
    app.set_global_busy_state(True, "nhân bản sang 1 board đích")
    assert app.lbl_progress_task.text().startswith("Đang ")

    app.set_status("Lỗi khác dòng chip!", "error", progress=0)
    app.set_global_busy_state(False)
    harness.pump(times=2)

    assert not app.lbl_progress_task.text().startswith("Đang ")
    assert app.status_prog.value() == 0
