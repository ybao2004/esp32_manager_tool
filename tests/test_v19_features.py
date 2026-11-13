# -*- coding: utf-8 -*-
"""
Kiểm thử tính năng phiên bản v1.9 (Responsive FlowLayout, Đồng bộ Trạng thái,
Tương phản WCAG 2.2 AA DiskMapWidget, Đổi màu LogView sống & Chủ đề Card).
"""
import ast
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QPushButton, QWidget

from modules.config import APP_VERSION
from modules.partition.partition_model import PartitionEntry
from modules.ui.dispatch import UiDispatcher
from modules.ui.main_window import MainWindow
from modules.ui.theme.manager import ThemeManager
from modules.ui.theme.tokens import get_tokens
from modules.ui.widgets.card import Card
from modules.ui.widgets.disk_map import get_entry_color
from modules.ui.widgets.flow_layout import FlowLayout
from modules.ui.widgets.log_view import LogView


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _relative_luminance(hex_color: str) -> float:
    c = QColor(hex_color)
    channels = []
    for ch in (c.redF(), c.greenF(), c.blueF()):
        if ch <= 0.03928:
            channels.append(ch / 12.92)
        else:
            channels.append(((ch + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def _contrast_ratio(hex_a: str, hex_b: str) -> float:
    la = _relative_luminance(hex_a)
    lb = _relative_luminance(hex_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def test_app_version_is_v19():
    """Xác nhận phiên bản >= v1.9 và không dùng Tkinter."""
    assert tuple(int(x) for x in APP_VERSION.split(".")[:2]) >= (1, 9)
    root_dir = Path(__file__).resolve().parent.parent
    py_files = [root_dir / "main.py"] + list((root_dir / "modules").rglob("*.py"))
    for fpath in py_files:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all("tkinter" not in alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert "tkinter" not in (node.module or "").lower()


def test_flow_layout_wraps_and_expands_height(qapp):
    """FlowLayout phải tự xuống dòng và tăng chiều cao khi thu hẹp bề ngang."""
    host = QWidget()
    layout = FlowLayout(host, h_spacing=6, v_spacing=6)
    layout.setContentsMargins(0, 0, 0, 0)
    for i in range(8):
        btn = QPushButton(f"Nút công cụ {i}", host)
        btn.setMinimumWidth(110)
        layout.addWidget(btn)

    assert layout.hasHeightForWidth() is True
    h_wide = layout.heightForWidth(1000)
    h_narrow = layout.heightForWidth(320)
    assert h_wide > 0
    assert h_narrow > h_wide


def test_partition_flash_combo_sync_after_refresh(qapp, tmp_path):
    """Đổi flash_size của PartitionTable rồi refresh phải đồng bộ lại cb_part_flash."""
    fake_cfg = tmp_path / "cfg_v19_part.json"
    with patch("modules.ui.main_window.CONFIG_FILE", str(fake_cfg), create=True):
        win = MainWindow(auto_start=False)
        try:
            win.notebook.select(3)
            qapp.processEvents()
            win.cb_part_chip.setCurrentText("ESP32-S3")
            qapp.processEvents()

            win.table.flash_size = 16 * 1024 * 1024
            win.refresh_partition_views()
            qapp.processEvents()

            assert "16" in win.cb_part_flash.currentText()
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()


def test_disk_map_wcag_aa_contrast():
    """Mọi cặp màu nền/chữ trong DiskMapWidget phải đạt WCAG 2.2 AA (>= 4.5:1) trên Sáng và Tối."""
    samples = [
        PartitionEntry(name="free", type_str="data", subtype_str="", offset=0, size=4096, is_unallocated=True),
        PartitionEntry(name="bootloader", type_str="bootloader", subtype_str="", offset=0x1000, size=0x7000, is_system=True),
        PartitionEntry(name="ptable", type_str="partition_table", subtype_str="", offset=0x8000, size=0x1000, is_system=True),
        PartitionEntry(name="factory", type_str="app", subtype_str="factory", offset=0x10000, size=0x100000),
        PartitionEntry(name="ota_0", type_str="app", subtype_str="ota_0", offset=0x110000, size=0x100000),
        PartitionEntry(name="test_app", type_str="app", subtype_str="test", offset=0x210000, size=0x80000),
        PartitionEntry(name="nvs", type_str="data", subtype_str="nvs", offset=0x9000, size=0x5000),
        PartitionEntry(name="otadata", type_str="data", subtype_str="ota", offset=0xE000, size=0x2000),
        PartitionEntry(name="storage", type_str="data", subtype_str="spiffs", offset=0x300000, size=0x80000),
        PartitionEntry(name="phy_init", type_str="data", subtype_str="phy", offset=0xF000, size=0x1000),
        PartitionEntry(name="coredump", type_str="data", subtype_str="coredump", offset=0x380000, size=0x10000),
        PartitionEntry(name="custom", type_str="data", subtype_str="undefined", offset=0x390000, size=0x10000),
    ]
    for is_dark in (False, True):
        for entry in samples:
            bg, fg = get_entry_color(entry, is_dark=is_dark)
            ratio = _contrast_ratio(bg, fg)
            assert ratio >= 4.5, (
                f"Low contrast ({ratio:.2f}) for {entry.name}/{entry.type_str}/{entry.subtype_str} "
                f"is_dark={is_dark}: fg={fg} on bg={bg}"
            )


def _fragment_colors(log_view: LogView) -> list[str]:
    colors = []
    block = log_view.document().begin()
    while block.isValid():
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                cf = frag.charFormat()
                if cf.hasProperty(log_view._ROLE_PROP):
                    colors.append((cf.property(log_view._ROLE_PROP), cf.foreground().color().name().upper()))
            it += 1
        block = block.next()
    return colors


def test_log_view_recolors_existing_blocks_on_theme_switch(qapp):
    """Đổi Light <-> Dark phải tô lại màu các dòng log đã ghi trước đó."""
    mgr = ThemeManager.instance()
    mgr.apply("engineering", "light")
    light_tokens = get_tokens("engineering", "light")
    dark_tokens = get_tokens("engineering", "dark")

    lv = LogView()
    try:
        lv.insert("end", "Lỗi kết nối\n", "red")
        lv.insert("end", "Thành công\n", "green")
        lv.insert("end", "Nhấn mạnh\n", "blue")
        lv.insert("end", "Cảnh báo\n", "warning")
        qapp.processEvents()

        before = dict(_fragment_colors(lv))
        assert before["error"] == QColor(light_tokens.danger).name().upper()
        assert before["success"] == QColor(light_tokens.success).name().upper()
        assert before["accent"] == QColor(light_tokens.accent).name().upper()
        assert before["warning"] == QColor(light_tokens.warning).name().upper()

        mgr.apply("engineering", "dark")
        qapp.processEvents()

        after_dark = dict(_fragment_colors(lv))
        assert after_dark["error"] == QColor(dark_tokens.danger).name().upper()
        assert after_dark["success"] == QColor(dark_tokens.success).name().upper()
        assert after_dark["accent"] == QColor(dark_tokens.accent).name().upper()
        assert after_dark["warning"] == QColor(dark_tokens.warning).name().upper()
    finally:
        lv.stop()
        mgr.apply("engineering", "light")


def test_status_chip_badge_card_danger_and_idle_progress_sync(qapp, tmp_path):
    """Đồng bộ chip_badge, global_com_lbl, progress=0 khi sẵn sàng và Card(danger=True)."""
    fake_cfg = tmp_path / "cfg_v19_sync.json"
    with patch("modules.ui.main_window.CONFIG_FILE", str(fake_cfg), create=True):
        win = MainWindow(auto_start=False)
        try:
            assert win.global_com_lbl is win.lbl_conn

            # Huy hiệu chip phải cập nhật sau khi hiển thị báo cáo Inspector
            win._display_formatted_report({
                "chip_name_key": "ESP32-S3",
                "chip_line": "ESP32-S3",
                "flash_mb": 16,
                "psram_mb": 8,
                "crystal": "40MHz",
                "mac": "AA:BB:CC:DD:EE:FF",
            })
            qapp.processEvents()
            badge_text = win.conn_bar.chip_badge.text()
            assert "ESP32-S3" in badge_text
            assert "16MB Flash" in badge_text
            assert "8MB PSRAM" in badge_text

            # Tiến trình chạy -> Sẵn sàng phải đặt progress = 0%
            win.set_status("Đang nạp firmware...", "info", progress=45, task_label="Đang nạp")
            assert win.status_prog["value"] == 45
            assert win.lbl_progress_pct.text() == "45%"

            win.set_status("Sẵn sàng", "success", progress=None, task_label="")
            assert win.status_prog["value"] == 0
            assert win.lbl_progress_pct.text() == "0%"

            # Nút Serial đổi chữ không lỗi icon
            win.conn_bar.serial_toggle_btn.setText("Ngắt kết nối")
            win.conn_bar.serial_toggle_btn.setText("Kết nối")

            # Card(danger=True) dùng property QSS role='section_danger' thay vì màu cứng
            danger_card = Card("Vùng nguy hiểm", icon_name="delete", danger=True, parent=win)
            assert danger_card._title_lbl.property("role") == "section_danger"
            assert "#D32F2F" not in danger_card._title_lbl.styleSheet().upper()
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()
