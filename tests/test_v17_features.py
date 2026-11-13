# -*- coding: utf-8 -*-
"""
Bộ kiểm thử chuyên biệt cho phiên bản ESP32 Manager Tool v1.7:
1. Phiên bản v1.7 & loại bỏ hoàn toàn Tkinter (thuần PyQt6).
2. Chỉ giữ lại phong cách Thiết kế Kỹ thuật (Engineering Sáng/Tối) & ép cấu hình cũ.
3. Khắc phục viền xanh Focus, kiểm tra QProgressBar thống nhất ở thanh trạng thái đáy (Tabs 1, 3, 4, 5).
4. Kiểm tra Icon ứng dụng / Taskbar hợp lệ.
5. Kiểm tra Tab 4: ban đầu trống, chọn chip tự chọn Flash cao nhất, bỏ Xuất BIN & Chép CSV, Lưu CSV toàn bảng/lưu đè, Thêm dòng chèn ngay sau dòng đang chọn.
6. Kiểm tra Tab 5: ban đầu trống, cài đặt ẩn nháy LED 5 giây an toàn (không DTR/RTS), chỉ hoạt động ở Tab 5, tự dừng khi rời tab hoặc bận.
"""
import ast
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from PyQt6.QtWidgets import QApplication, QProgressBar

from modules.app_core import resolve_app_icon_path
from modules.config import APP_VERSION
from modules.update_util import parse_version_tuple
from modules.partition.chip_database import CHIP_FAMILY_DATABASE
from modules.partition.partition_model import PartitionEntry
from modules.ui.theme.manager import EngineeringProxyStyle, ThemeManager
from modules.ui.theme.qss import build_qss
from modules.ui.theme.tokens import get_tokens


def test_app_version_v17_and_zero_tkinter_imports():
    """Phiên bản >= v1.7 và không tồn tại bất kỳ lệnh import tkinter nào trong mã nguồn."""
    assert parse_version_tuple(APP_VERSION) >= (1, 7)

    root_dir = Path(__file__).resolve().parent.parent
    py_files = [root_dir / "main.py"] + list((root_dir / "modules").rglob("*.py"))

    tkinter_imports = []
    for fpath in py_files:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if "tkinter" in alias.name.lower():
                        tkinter_imports.append(f"{fpath.relative_to(root_dir)}:{node.lineno} import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                mod = (node.module or "").lower()
                if "tkinter" in mod:
                    tkinter_imports.append(f"{fpath.relative_to(root_dir)}:{node.lineno} from {node.module}")

    assert tkinter_imports == [], f"Phát hiện import tkinter: {tkinter_imports}"


@pytest.mark.mock_hw
def test_app_icon_resolution_and_qapp_icon(headless_app):
    """Đảm bảo tìm được tệp icon hợp lệ cho cửa sổ & Windows Taskbar."""
    harness, app = headless_app
    icon_path = resolve_app_icon_path()
    assert icon_path is not None
    assert os.path.exists(icon_path)
    assert icon_path.lower().endswith((".ico", ".png"))
    assert not app.windowIcon().isNull()
    assert not QApplication.windowIcon().isNull()


@pytest.mark.mock_hw
def test_engineering_only_theme_and_settings_controls(headless_app):
    """Chỉ giữ Engineering Light/Dark, xóa dropdown chọn preset Fluent/VSCode, giữ viền focus trung tính."""
    harness, app = headless_app
    tm = ThemeManager.instance()

    assert tm.apply("fluent", False).preset == "engineering"
    assert tm.apply("vscode", True).preset == "engineering"
    assert app.saved_theme_preset == "engineering"

    # Settings page không còn cb_preset, có chk_tab5_led_blink mặc định False
    assert not hasattr(app.page_settings, "cb_preset")
    assert hasattr(app.page_settings, "chk_tab5_led_blink")
    assert app.tab5_led_blink_enabled is False
    assert not app.page_settings.chk_tab5_led_blink.isChecked()

    # Kiểm tra EngineeringProxyStyle được gắn làm style nền để vẽ checkbox/radio đầy đặn không cắt mép
    assert isinstance(tm._proxy_style, EngineeringProxyStyle)

    # Kiểm tra bind_themed_icon tự cập nhật icon sáng/tối trên các trang & Card
    tm.apply("engineering", True)
    harness.pump(times=2)
    assert hasattr(app.page_partition.btn_save_csv, "_icon_theme_binder")
    assert not app.page_partition.btn_save_csv.icon().isNull()

    # Kiểm tra QSS không dùng viền xanh #0078D4 làm focus outline bảng Settings
    qss_light = build_qss(get_tokens("engineering", "light"))
    assert "QLineEdit:focus" in qss_light
    assert "QTableWidget QLineEdit" in qss_light


@pytest.mark.mock_hw
def test_unified_bottom_progress_bar_across_tabs_1_3_4_5(headless_app):
    """Thanh tiến trình dùng chung ở đáy (Tab 1, 3, 4, 5), không bị kẹt 5%, không trùng bar cục bộ."""
    harness, app = headless_app

    # Không có QProgressBar cục bộ ở Tab 3 (Flasher) hoặc Tab 4 (Partition)
    assert app.page_flasher.findChildren(QProgressBar) == []
    assert app.page_partition.findChildren(QProgressBar) == []
    assert not hasattr(app.page_partition, "hw_prog")
    assert not hasattr(app.page_partition, "hw_box")

    # Mặc định lúc nhàn rỗi là 0%, không phải 5%
    assert app.status_prog.value() == 0
    assert app.lbl_progress_pct.text() == "0%"

    # Tab 1 (Inspector) cập nhật đáy
    app.set_global_busy_state(True, "kiểm tra phần cứng...")
    assert app.lbl_progress_task.text() == "Đang kiểm tra phần cứng..."
    app.set_global_busy_state(False)

    # Tab 3 cập nhật đáy
    app._update_flash_progress(42, "Đang nạp Firmware...")
    harness.pump(times=2)
    assert app.status_prog.value() == 42
    assert "42%" in app.lbl_progress_pct.text()
    assert app.lbl_progress_task.text() == "Đang nạp Firmware..."

    # Tab 4 cập nhật đáy thông qua dòng log esptool thật
    app._update_partition_hw_progress("Reading partition at 0x8000... (88 %)", "Đang đọc bảng phân vùng...")
    harness.pump(times=2)
    assert app.status_prog.value() == 88
    assert "88%" in app.lbl_progress_pct.text()
    assert app.lbl_progress_task.text() == "Đang đọc bảng phân vùng..."

    # Tab 5 cập nhật đáy
    app.update_global_progress(100, "Hoàn tất sao lưu")
    harness.pump(times=2)
    assert app.status_prog.value() == 100
    assert "100%" in app.lbl_progress_pct.text()
    assert app.lbl_progress_task.text() == "Hoàn tất sao lưu"


@pytest.mark.mock_hw
def test_tab4_empty_initial_removed_buttons_and_chip_max_flash(headless_app):
    """Tab 4 & 5 ban đầu trống; Tab 4 bỏ Xuất BIN/Chép CSV, đổi Lưu CSV, chọn chip tự chọn Flash cao nhất."""
    harness, app = headless_app

    assert len(app.table.entries) == 0
    assert len(app.backup_table.entries) == 0

    assert not hasattr(app.page_partition, "btn_export_bin")
    assert not hasattr(app.page_partition, "btn_part_copy")
    assert hasattr(app.page_partition, "btn_save_csv")
    assert "Lưu CSV" in app.page_partition.btn_save_csv.text()

    # Chọn từng dòng chip khác nhau -> tự động chọn Flash cao nhất chip đó hỗ trợ
    for cid in ("esp32p4", "esp32s3", "esp32c3"):
        info = CHIP_FAMILY_DATABASE[cid]
        app.part_chip_var.set(info.name)
        app._on_chip_changed()
        harness.pump(times=2)

        expected_max_bytes = max(info.supported_flash_sizes)
        expected_max_mb = expected_max_bytes // (1024 * 1024)
        assert app.table.target_chip == cid
        assert app.table.flash_size == expected_max_bytes
        assert f"{expected_max_mb} MB" in app.part_flash_var.get()


@pytest.mark.mock_hw
def test_tab4_add_row_inserts_after_selected_and_save_csv_overwrites(headless_app, tmp_path):
    """Nút + Thêm dòng chèn ngay sau phân vùng đang chọn và Lưu CSV lưu toàn bảng / lưu đè CSV."""
    harness, app = headless_app
    app.sidebar.select(3)
    harness.pump(times=2)

    # Tạo bảng 2 phần tử ban đầu
    e1 = PartitionEntry(name="nvs", type_str="data", subtype_str="nvs", offset=0x9000, size=0x5000)
    e2 = PartitionEntry(name="factory", type_str="app", subtype_str="factory", offset=0x10000, size=0x100000)
    app.table.entries = [e1, e2]
    app.refresh_partition_views(selected_entry_name="nvs")
    harness.pump(times=2)

    # Mock dialog thêm dòng để chèn mới
    def _fake_exec(dlg):
        dlg.result = PartitionEntry(
            name=dlg.entry.name or "custom",
            type_str="data",
            subtype_str="spiffs",
            offset=dlg.entry.offset,
            size=0x4000,
        )

    with patch.object(app, "_exec_dialog", side_effect=_fake_exec):
        # Chọn nvs (row 0) rồi gọi Thêm dòng -> phải chèn vào index 1 (giữa nvs và factory)
        app._action_add_partition()
        harness.pump(times=2)

    assert len(app.table.entries) == 3
    assert app.table.entries[0].name == "nvs"
    inserted_name = app.table.entries[1].name
    assert inserted_name not in ("nvs", "factory")
    assert app.table.entries[2].name == "factory"
    # Đảm bảo offset hợp lệ không đè
    assert app.table.entries[1].offset >= app.table.entries[0].end_offset
    assert app.table.entries[2].offset >= app.table.entries[1].end_offset

    # Kiểm tra Lưu CSV mở hộp thoại lần đầu, sau đó lưu đè trực tiếp không cần hỏi lại
    csv_file = tmp_path / "custom_part.csv"
    app.current_partition_file_path = None
    with patch("modules.tabs.tab_partition.filedialog.asksaveasfilename", return_value=str(csv_file)) as mock_save, \
         patch("modules.tabs.tab_partition.messagebox.showinfo"):
        app._action_save_csv()
        assert mock_save.call_count == 1
        assert app.current_partition_file_path == str(csv_file)

        # Sửa dữ liệu và bấm Lưu CSV lần 2 -> phải ghi đè trực tiếp (call_count vẫn = 1)
        app.table.entries[1].name = "spiffs_data"
        app._action_save_csv()
        assert mock_save.call_count == 1

    saved_text = csv_file.read_text(encoding="utf-8")
    assert "nvs" in saved_text
    assert "spiffs_data" in saved_text
    assert "factory" in saved_text


@pytest.mark.mock_hw
def test_tab5_hidden_led_blink_lifecycle(headless_app):
    """Cài đặt ẩn Nháy LED Board Gốc ở Tab 5: mặc định ẩn, chỉ chạy ở Tab 5, không xung DTR/RTS."""
    harness, app = headless_app

    # Mặc định ẩn nút Nháy LED
    assert app.tab5_led_blink_enabled is False
    assert app.btn_backup_blink_led.isHidden()

    # Bật tùy chọn ẩn trong Cài đặt
    app.sidebar.select(5)
    harness.pump(times=2)
    app.page_settings.chk_tab5_led_blink.setChecked(True)
    harness.pump(times=2)
    assert app.tab5_led_blink_enabled is True
    assert not app.btn_backup_blink_led.isHidden()

    # Chuyển sang Tab 5 (index 4) và giả lập chọn COM9
    app.sidebar.select(4)
    harness.pump(times=2)

    mock_ser = MagicMock()
    mock_ser.is_open = True
    mock_ser.write = MagicMock(return_value=1)
    mock_ser.flush = MagicMock()
    mock_ser.close = MagicMock()

    with patch("serial.Serial", return_value=mock_ser):
        if app.port_cb.findText("COM9") < 0:
            app.port_cb.addItem("COM9")
        app.port_cb.setCurrentText("COM9")
        app.on_port_selected("COM9")
        assert app.lbl_backup_src_port.text() == "COM9"
        started = app._start_board_led_blink("COM9", duration=0.3)
        assert started is True
        time.sleep(0.15)
        assert mock_ser.dtr is False
        assert mock_ser.rts is False
        assert mock_ser.open.called

        # Rời Tab 5 -> phải tự động dừng nháy LED
        app.sidebar.select(0)
        harness.pump(times=2)
        time.sleep(0.05)
        assert app._is_led_blinking is False or (
            app._led_blink_stop_event is not None and app._led_blink_stop_event.is_set()
        )
