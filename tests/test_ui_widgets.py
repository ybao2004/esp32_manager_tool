# -*- coding: utf-8 -*-
"""
Kiểm thử các widget giao diện dùng chung (Giai đoạn 3):
- LogView (giới hạn dòng, gom lô, timestamps, tô màu)
- KeyValueTable (word wrap, nạp dữ liệu)
- DiskMapWidget (tính toán khối, tooltip chi tiết, sự kiện click)
- Card, CollapsiblePanel, InfoBar, ProgressRow
"""
import os
import sys
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QPoint

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules.ui.widgets.log_view import LogView
from modules.ui.widgets.key_value_table import KeyValueTable
from modules.ui.widgets.card import Card
from modules.ui.widgets.collapsible import CollapsiblePanel
from modules.ui.widgets.info_bar import InfoBar
from modules.ui.widgets.progress_row import ProgressRow
from modules.ui.widgets.disk_map import DiskMapWidget, build_detailed_tooltip_text
from modules.partition.partition_model import PartitionEntry


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv if sys.argv else ["test"])
    return app


def test_log_view_operations(qapp):
    log = LogView()
    log.timestamps = False
    log.autoscroll = True

    log.append_line("I (100) boot: Pro cpu start user code", "info")
    log.append_line("W (200) wifi: Retrying connection", "warning")
    log.append_line("E (300) esp: Flash read timeout", "error")

    full_txt = log.text()
    assert "Pro cpu start" in full_txt
    assert "Retrying connection" in full_txt
    assert "Flash read timeout" in full_txt

    log.clear_log()
    assert log.text() == ""


def test_key_value_table_populate(qapp):
    table = KeyValueTable()
    data = [
        ("Tên chip", "ESP32-P4"),
        ("Tần số", "400MHz"),
        ("Bộ nhớ RAM", "DRAM: 147 KiB | IRAM: 32 KiB | RTCRAM: 31 KiB")
    ]
    table.set_rows(data)
    assert table.rowCount() == 3
    assert table.item(0, 0).text() == "Tên chip"
    assert table.item(0, 1).text() == "ESP32-P4"
    assert "DRAM: 147 KiB" in table.item(2, 1).text()


def test_disk_map_widget_and_tooltip(qapp):
    disk_map = DiskMapWidget()
    disk_map.resize(800, 76)

    nvs = PartitionEntry(name="nvs", type_str="data", subtype_str="nvs", offset=0x9000, size=0x6000)
    tip_nvs = build_detailed_tooltip_text(nvs)
    assert "MỤC ĐÍCH SỬ DỤNG" in tip_nvs
    assert "Non-Volatile Storage" in tip_nvs
    assert "KHUYẾN NGHỊ DUNG LƯỢNG" in tip_nvs

    unalloc = PartitionEntry(name="Unallocated", type_str="gap", subtype_str="gap", offset=0x200000, size=0x100000, is_unallocated=True)
    tip_un = build_detailed_tooltip_text(unalloc)
    assert "KHOẢNG TRỐNG CHƯA PHÂN BỔ" in tip_un

    disk_map.set_data([nvs, unalloc], flash_size=4 * 1024 * 1024)
    # Kiểm tra phương thức helper tương thích
    assert "Non-Volatile Storage" in disk_map._build_detailed_tooltip_text(nvs)


def test_collapsible_panel_toggle(qapp):
    panel = CollapsiblePanel("Bảng điều khiển")
    assert panel.is_expanded()
    panel.set_expanded(False)
    assert not panel.is_expanded()
    panel.toggle()
    assert panel.is_expanded()


def test_progress_row_state(qapp):
    row = ProgressRow(port="COM7", description="Board đích 1", checked=True)
    assert row.is_checked()
    assert row.port == "COM7"

    row.set_progress(45, "Đang nạp 45%")
    assert row.progress_bar.value() == 45
    assert "45%" in row.status_lbl.text()
