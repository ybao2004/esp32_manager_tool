# -*- coding: utf-8 -*-
"""
Bộ kiểm thử chuyên biệt cho phiên bản ESP32 Manager Tool v1.8:
1. Phiên bản v1.8 & không tồn tại Tkinter.
2. Khóa đơn thực thể (SingleInstanceGuard) ngăn mở nhiều cửa sổ và kích hoạt lại cửa sổ đang mở.
3. Đóng ứng dụng an toàn (on_closing / closeEvent): dừng luồng nền, đóng cổng COM/Serial, dừng QTimer & tiến trình con.
4. Khắc phục tương phản Light Mode cho Sidebar & StatusBar khi chuyển đổi Dark <-> Light.
5. Khắc phục danh sách Board Đích Tab 5 không bị trùng / kẹt widget cũ với Board Gốc COM.
"""
import ast
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtGui import QCloseEvent, QColor
from PyQt6.QtWidgets import QApplication, QCheckBox, QLabel, QMessageBox

from modules.config import APP_VERSION
from modules.single_instance import (
    SingleInstanceGuard,
    register_child_process,
    terminate_child_processes,
)
from modules.ui.dispatch import UiDispatcher
from modules.ui.main_window import MainWindow
from modules.ui.theme.tokens import get_tokens


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def test_app_version_is_v18_and_pure_pyqt6():
    """Xác nhận phiên bản >= v1.8 và không có bất kỳ lệnh import tkinter nào."""
    ver_tuple = tuple(int(x) for x in APP_VERSION.split(".")[:2])
    assert ver_tuple >= (1, 8)
    root_dir = Path(__file__).resolve().parent.parent
    py_files = [root_dir / "main.py"] + list((root_dir / "modules").rglob("*.py"))
    for fpath in py_files:
        tree = ast.parse(fpath.read_text(encoding="utf-8"), filename=str(fpath))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                assert all("tkinter" not in alias.name.lower() for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                assert "tkinter" not in (node.module or "").lower()


def test_single_instance_guard_blocks_duplicate_and_activates(qapp):
    """Mở phiên bản thứ 2 phải bị chặn và gửi tín hiệu ACTIVATE tới phiên bản đang chạy."""
    unique_id = f"esp32_test_guard_{os.getpid()}_{time.time_ns()}"
    activated = []

    guard1 = SingleInstanceGuard(app_id=unique_id, on_activate=lambda: activated.append(True))
    guard2 = SingleInstanceGuard(app_id=unique_id)

    try:
        assert guard1.acquire() is True
        assert guard1.is_acquired is True
        # Instance thứ 2 không thể chiếm khóa cùng lúc
        assert guard2.acquire() is False
        assert guard2.is_acquired is False

        # Gửi yêu cầu đánh thức cửa sổ đang chạy qua QLocalSocket
        assert guard2.notify_existing_instance(timeout_ms=1000) is True
        deadline = time.monotonic() + 1.5
        while not activated and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.02)
        assert len(activated) == 1
    finally:
        guard1.release()
        guard2.release()

    # Sau khi instance đầu giải phóng khóa, instance mới có thể khởi chạy
    guard3 = SingleInstanceGuard(app_id=unique_id)
    try:
        assert guard3.acquire() is True
    finally:
        guard3.release()


def test_safe_shutdown_stops_threads_serial_timers_and_children(qapp, tmp_path):
    """Đóng ứng dụng an toàn: dừng luồng quét COM, đóng Serial, dừng LogView timer & tiến trình con."""
    fake_cfg = tmp_path / "cfg_v18.json"
    with patch("modules.serial_util.list_com_ports_local", return_value=["COM9"]), \
         patch("modules.ui.main_window.CONFIG_FILE", str(fake_cfg), create=True):
        win = MainWindow(auto_start=True)
        win.show()
        qapp.processEvents()
        win.start_background_tasks()
        assert win._scan_thread is not None and win._scan_thread.is_alive()

        # Giả lập kết nối Serial Monitor đang mở
        mock_ser = MagicMock()
        mock_ser.is_open = True
        win.serial_connection = mock_ser

        # Đảm bảo flush timer của LogView đang chạy
        assert win.monitor_txt._flush_timer.isActive()

        # Tạo tiến trình con thật để xác minh terminate_child_processes dọn sạch khi thoát
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        register_child_process(proc)
        assert proc.poll() is None

        try:
            closed = win.on_closing()
            assert closed is True
            assert win._closing is True
            assert win.stop_scan.is_set()
            assert win.stop_serial_thread.is_set()
            assert not win._scan_thread.is_alive()
            mock_ser.close.assert_called_once()
            assert win.serial_connection is None
            assert not win.monitor_txt._flush_timer.isActive()
            assert getattr(win._dispatcher, "_accepting", True) is False
            assert proc.poll() is not None
        finally:
            if proc.poll() is None:
                proc.kill()
            terminate_child_processes()
            UiDispatcher.instance().reset()


def test_close_event_force_exit_confirmation(qapp, tmp_path):
    """Khi người dùng đóng cửa sổ bằng X trong lúc thiết bị bận, chỉ thoát cưỡng bức nếu xác nhận Yes."""
    fake_cfg = tmp_path / "cfg_v18_force.json"
    with patch("modules.serial_util.list_com_ports_local", return_value=[]), \
         patch("modules.ui.main_window.CONFIG_FILE", str(fake_cfg), create=True):
        win = MainWindow(auto_start=False)
        win.is_flashing.set()

        try:
            # Từ chối -> giữ cửa sổ
            ev_no = QCloseEvent()
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
                win.closeEvent(ev_no)
            assert not ev_no.isAccepted()
            assert not win._closing

            # Đồng ý -> dọn tài nguyên cưỡng bức và thoát
            ev_yes = QCloseEvent()
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                win.closeEvent(ev_yes)
            assert ev_yes.isAccepted()
            assert win._closing is True
            assert not win.is_flashing.is_set()
        finally:
            win.is_flashing.clear()
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()


def test_light_theme_sidebar_and_statusbar_contrast_sync(qapp, tmp_path):
    """Theme sáng không có Sidebar tối hay chữ StatusBar mất màu khi đổi giữa Dark <-> Light."""
    light_tok = get_tokens("engineering", "light")
    assert QColor(light_tok.sidebar_bg).lightness() > 210
    assert QColor(light_tok.sidebar_text).lightness() < 40

    fake_cfg = tmp_path / "cfg_v18_theme.json"
    with patch("modules.ui.main_window.CONFIG_FILE", str(fake_cfg), create=True):
        win = MainWindow(auto_start=False)
        try:
            assert f"v{APP_VERSION}" in win.windowTitle()

            # Đặt thông báo trạng thái (như Nháy LED trên Tab 5) khi đang ở Dark Mode
            win._apply_theme_selection("engineering", True)
            qapp.processEvents()
            win.set_status("Đang nháy LED nhận diện Board Gốc COM13 trong 5s...", "info")
            assert "#E6EDF3" in win.lbl_status.styleSheet().upper()

            # Chuyển sang Light Mode -> lbl_status phải lập tức đổi sang màu chữ tối (#0F172A), không còn #E6EDF3
            win._apply_theme_selection("engineering", False)
            qapp.processEvents()
            ss_light = win.lbl_status.styleSheet().upper()
            assert "#0F172A" in ss_light
            assert "#E6EDF3" not in ss_light
            assert "#0F172A" in win.lbl_progress_task.styleSheet().upper()
            assert "#0F172A" in win.lbl_progress_pct.styleSheet().upper()

            # Đổi lại qua RadioButton trong Cài đặt
            win.page_settings.rb_dark.setChecked(True)
            qapp.processEvents()
            assert "#E6EDF3" in win.lbl_status.styleSheet().upper()
            win.page_settings.rb_light.setChecked(True)
            qapp.processEvents()
            assert "#0F172A" in win.lbl_status.styleSheet().upper()
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()


def test_tab5_clone_targets_strictly_exclude_source_port(qapp, tmp_path):
    """
    Tab 5 (Board Gốc trực tiếp):
    - Cổng Board Đích không bao giờ trùng với cổng Board Gốc.
    - Không bị sót QCheckBox cũ khi rút cổng hoặc đổi Board Gốc (nhờ clear_children chuẩn PyQt6).
    - Chế độ 'Thư mục đã lưu' vẫn cho phép chọn toàn bộ cổng COM đang cắm làm đích.
    """
    fake_cfg = tmp_path / "cfg_v18_tab5.json"
    ports_holder = {"ports": ["COM3", "COM13"]}
    with patch("modules.serial_util.list_com_ports_local", side_effect=lambda: list(ports_holder["ports"])), \
         patch("modules.tabs.tab_backup_clone.list_com_ports_local", side_effect=lambda: list(ports_holder["ports"])), \
         patch("modules.ui.main_window.CONFIG_FILE", str(fake_cfg), create=True):
        win = MainWindow(auto_start=False)
        try:
            win.notebook.select(4)
            qapp.processEvents()

            # Khi Cổng COM trên cùng là COM3 -> Board Gốc đồng bộ COM3, Board Đích chỉ có COM13
            win.port_cb.blockSignals(True)
            win.port_cb.clear()
            win.port_cb.addItems(["COM3", "COM13"])
            win.port_cb.setCurrentText("COM3")
            win.port_cb.blockSignals(False)
            win.on_port_selected("COM3")
            qapp.processEvents()
            assert win.lbl_backup_src_port.text() == "COM3"
            assert win.backup_src_port_var.get() == "COM3"
            assert list(win.clone_target_vars.keys()) == ["COM13"]
            visible_cbs = [w for w in win.clone_target_ports_frame.winfo_children() if isinstance(w, QCheckBox)]
            assert [cb.text() for cb in visible_cbs] == ["Board Đích: COM13"]

            # Rút COM3 chỉ còn COM13: Cổng COM trên cùng & Board Gốc chuyển COM13 -> Board Đích loại sạch COM13
            ports_holder["ports"] = ["COM13"]
            win.saved_com_port = ""
            win.update_port_list("COM3", ["COM13"])
            qapp.processEvents()
            assert win.port_cb.currentText() == "COM13"
            assert win.lbl_backup_src_port.text() == "COM13"
            assert win.clone_target_vars == {}
            assert not any(
                isinstance(w, QCheckBox) for w in win.clone_target_ports_frame.winfo_children()
            )
            labels = [w for w in win.clone_target_ports_frame.winfo_children() if isinstance(w, QLabel)]
            assert len(labels) == 1
            assert "Chưa phát hiện thêm cổng COM đích" in labels[0].text()

            # Chuyển sang nguồn 'Thư mục đã lưu' -> COM13 trở lại danh sách đích hợp lệ
            win.var_clone_source_mode.set("saved_folder")
            qapp.processEvents()
            assert list(win.clone_target_vars.keys()) == ["COM13"]
            visible_cbs_folder = [
                w for w in win.clone_target_ports_frame.winfo_children() if isinstance(w, QCheckBox)
            ]
            assert [cb.text() for cb in visible_cbs_folder] == ["Board Đích: COM13"]

            # Chuyển ngược về 'Board Gốc trực tiếp' -> COM13 biến mất ngay khỏi Board Đích
            win.var_clone_source_mode.set("live_board")
            qapp.processEvents()
            assert win.clone_target_vars == {}
        finally:
            win.cleanup_resources(force=True)
            UiDispatcher.instance().reset()
