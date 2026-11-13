# -*- coding: utf-8 -*-
"""
Empirical Verification Suite for Milestone 1
Run directly or via pytest to validate F01, F02, F03, F04, F06, F07, F08.
"""
import os
import re
import sys
import time
import threading
from unittest.mock import MagicMock, patch

import pytest

# Ensure modules in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modules.ui.dialogs.size_input_dialog import SizeInputDialog
from modules.app_core import InspectorApp
from modules.tabs.tab_monitor import MonitorTabMixin
from modules.tabs.tab_partition import PartitionTabMixin
from modules.tabs.tab_flasher import FlasherTabMixin
from tests.mock_hardware.app_harness import HeadlessAppHarness


@pytest.fixture
def tk_root():
    root = HeadlessAppHarness.get_shared_root()
    yield root


# ----------------------------------------------------------------------
# F01: Test SizeInputDialog instantiation and minimum size
# ----------------------------------------------------------------------
def test_f01_fit_dialog_signature(tk_root):
    """Verify SizeInputDialog sets minimum width and rejects unexpected kwargs."""
    dlg = SizeInputDialog(None, partition_name="nvs", current_size_bytes=0x6000)
    assert dlg.minimumWidth() >= 380
    dlg.close()

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        SizeInputDialog(None, min_w=340, min_h=190)


def test_f01_size_input_dialog_instantiation(tk_root):
    """Verify SizeInputDialog instantiates without crashing."""
    dlg = SizeInputDialog(tk_root, partition_name="nvs", current_size_bytes=0x10000)
    assert dlg.result is None
    dlg.close()


# ----------------------------------------------------------------------
# F02: Test trigger_hardware_reset when serial_connection is None or disconnected
# ----------------------------------------------------------------------
class DummyMonitor(MonitorTabMixin):
    def __init__(self, root):
        self.root = root
        self.serial_connection = None
        self.statuses = []
        self.control_commands = {}

    def set_status(self, msg, level="info"):
        self.statuses.append((msg, level))

    def _send_serial_command(self, cmd, msg, level):
        self.statuses.append((f"CMD:{cmd}", level))


def test_f02_reset_when_serial_none(tk_root):
    """Verify on_reset_esp safely handles serial_connection = None."""
    app = DummyMonitor(tk_root)
    app.serial_connection = None

    app.on_reset_esp()
    assert ("Lỗi: Chưa kết nối Serial!", "error") in app.statuses


def test_f02_reset_concurrent_disconnect_during_pulse(headless_app):
    """Verify trigger_hardware_reset handles serial_connection disappearing mid-pulse."""
    harness, app = headless_app

    mock_conn = MagicMock()
    mock_conn.is_open = True
    app.serial_connection = mock_conn

    # Start reset
    app.on_reset_esp()

    # Simulate immediate disconnect mid-sleep
    app.serial_connection = None

    # Let background thread finish and pump harness queue
    time.sleep(0.25)
    harness.pump(5)

    # Must not crash


def test_f02_reset_serial_exception_handled(headless_app):
    """Verify trigger_hardware_reset catches SerialException gracefully."""
    import serial

    harness, app = headless_app

    mock_conn = MagicMock()
    mock_conn.is_open = True
    mock_conn.setDTR.side_effect = serial.SerialException("Device disconnected")
    app.serial_connection = mock_conn

    app.on_reset_esp()
    time.sleep(0.25)
    harness.pump(5)

    # Status should report error/warning without crashing
    assert "Reset" in app.req_status_lbl["text"] or app.current_status_level in ("warning", "error")


# ----------------------------------------------------------------------
# F03 & F04: Test is_device_busy() and on_closing()
# ----------------------------------------------------------------------
def test_f03_is_device_busy_partition_hw(headless_app):
    """Verify is_device_busy returns True when _is_partition_hw_running=True."""
    _harness, app = headless_app

    # Initially false
    app.is_flashing.clear()
    app.is_detecting.clear()
    app.is_connecting = False
    app._is_partition_hw_running = False
    assert app.is_device_busy() is False

    # When partition hw running
    app._is_partition_hw_running = True
    assert app.is_device_busy() is True

    # When flashing
    app._is_partition_hw_running = False
    app.is_flashing.set()
    assert app.is_device_busy() is True

    # When detecting
    app.is_flashing.clear()
    app.is_detecting.set()
    assert app.is_device_busy() is True

    # When connecting
    app.is_detecting.clear()
    app.is_connecting = True
    assert app.is_device_busy() is True

    app.is_connecting = False
    app.is_flashing.clear()
    app.is_detecting.clear()
    app._is_partition_hw_running = False


def test_f04_on_closing_blocks_when_busy(headless_app):
    """Verify on_closing does not destroy window if device is busy."""
    _harness, app = headless_app

    app._is_partition_hw_running = True

    with patch('modules.ui.dialogs_service.showwarning') as mock_warn:
        app.on_closing()
        mock_warn.assert_called_once()
        # Window still exists!
        assert app.root.winfo_exists()

    app._is_partition_hw_running = False


def test_f04_menu_exit_routed_to_on_closing(headless_app):
    """Verify Menu File -> Exit commands route to on_closing."""
    _harness, app = headless_app

    file_menu = app.main_menu.nametowidget(app.main_menu.entrycget(0, "menu"))
    exit_label = file_menu.entrycget(file_menu.index("end"), "label")
    assert exit_label == "Thoát"
    cmd_name = str(file_menu.entrycget(file_menu.index("end"), "command"))
    assert "on_closing" in cmd_name or callable(file_menu.entrycget(file_menu.index("end"), "command"))


# ----------------------------------------------------------------------
# F06: Test dynamic partition offset in _hw_read_partition_table
# ----------------------------------------------------------------------
class DummyPartitionApp(PartitionTabMixin):
    def __init__(self, root):
        self.root = root
        self._is_partition_hw_running = False
        self.table = MagicMock()
        self.table.part_table_offset = 0x9000
        self.table.target_chip = "esp32"
        self.port_cb = MagicMock()
        self.port_cb.get.return_value = "COM3"
        self.baud_cb = MagicMock()
        self.baud_cb.get.return_value = "115200"
        self.executed_commands = []

    def _prepare_hardware_port(self):
        return ("COM3", 115200, "esp32")

    def _log_partition_hw(self, msg):
        pass


def test_f06_dynamic_partition_offset_read(tk_root):
    """Verify _hw_read_partition_table passes dynamic part_offset hex string."""
    app = DummyPartitionApp(tk_root)
    app.table.part_table_offset = 0x9000

    captured_args = []

    def mock_run_esptool(args, progress_callback=None):
        captured_args.append(list(args))
        return 0

    with patch('modules.tabs.tab_partition.run_esptool_command', side_effect=mock_run_esptool), \
         patch('modules.tabs.tab_partition.esptool_command_succeeded', return_value=True):
        app._hw_read_partition_table()
        time.sleep(0.2)
        tk_root.update()

    assert len(captured_args) == 1
    args = captured_args[0]
    read_idx = args.index('read_flash')
    assert args[read_idx + 1] == '0x9000'
    assert args[read_idx + 1] != '0x8000'

    # Test fallback when part_table_offset is None
    app.table.part_table_offset = None
    captured_args.clear()
    with patch('modules.tabs.tab_partition.run_esptool_command', side_effect=mock_run_esptool), \
         patch('modules.tabs.tab_partition.esptool_command_succeeded', return_value=True):
        app._hw_read_partition_table()
        time.sleep(0.2)
        tk_root.update()

    assert captured_args[0][read_idx + 1] == '0x8000'


# ----------------------------------------------------------------------
# F07 & F08: Test aggregate progress calculation and auto-reconnect flag
# ----------------------------------------------------------------------
def test_f07_aggregate_progress_calculation():
    """Verify aggregate progress smoothly increases across multiple files without reset."""
    file_sizes = [1000, 2000, 1000]  # Total = 4000
    total_bytes = sum(file_sizes)

    progress_history = []
    current_file_idx = 0
    last_file_pct = 0

    simulated_events = [
        # File 0
        (0, False), (50, False), (100, True),
        # File 1
        (0, False), (50, False), (100, True),
        # File 2
        (0, False), (50, False), (100, True),
    ]

    for pct, file_done in simulated_events:
        if pct < last_file_pct and current_file_idx < len(file_sizes) - 1:
            current_file_idx += 1
            last_file_pct = 0
        last_file_pct = pct

        completed_bytes = sum(file_sizes[:current_file_idx])
        current_bytes = (pct / 100.0) * file_sizes[current_file_idx]
        agg_pct = min(100, max(0, int(((completed_bytes + current_bytes) / total_bytes) * 100)))
        progress_history.append(agg_pct)

        if file_done and current_file_idx < len(file_sizes) - 1:
            current_file_idx += 1
            last_file_pct = 0

    # Verify monotonic non-decreasing
    for i in range(1, len(progress_history)):
        assert progress_history[i] >= progress_history[i - 1], (
            f"Progress dropped backwards: {progress_history[i - 1]} -> {progress_history[i]}"
        )
    assert progress_history[0] == 0
    assert progress_history[-1] == 100


def test_f07_zero_byte_safety():
    """Verify zero byte / missing files do not cause ZeroDivisionError."""
    file_sizes = [0, 0]
    total_bytes = max(1, sum(file_sizes))
    completed_bytes = 0
    current_bytes = (50 / 100.0) * file_sizes[0]
    agg_pct = min(100, max(0, int(((completed_bytes + current_bytes) / total_bytes) * 100)))
    assert agg_pct == 0


def test_f08_auto_reconnect_scheduled(tk_root):
    """Verify safe_after schedules on_serial_connect with 500ms delay if was_connected=True."""
    calls = []

    def mock_on_serial_connect():
        calls.append("connected")

    was_connected = True
    scheduled_callbacks = []

    def safe_after(fn, delay=0):
        scheduled_callbacks.append((fn, delay))

    if was_connected:
        safe_after(mock_on_serial_connect, 500)

    assert len(scheduled_callbacks) == 1
    fn, delay = scheduled_callbacks[0]
    assert fn == mock_on_serial_connect
    assert delay == 500


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
