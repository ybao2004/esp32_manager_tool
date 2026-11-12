# -*- coding: utf-8 -*-
"""
Tier 2: Boundary & Corner Cases Test Suite.
Verifies robust exception handling, boundary enforcement, and failure recovery
across all modules of esp32_manager_tool without physical ESP32 hardware.
"""
import os
import pytest
import serial
from unittest.mock import patch

from modules.partition.partition_model import PartitionTable, PartitionEntry


@pytest.mark.tier2
@pytest.mark.mock_hw
class TestTier2Boundaries:
    """Boundary, corner case, and fault injection tests for esp32_manager_tool."""

    def test_tier2_port_empty_registry(self, headless_app, mock_ports):
        """TC-T2-PORT-01: When no serial ports exist in system, dropdown clears gracefully."""
        harness, app = headless_app
        mock_ports.clear()
        app.refresh_ports_dropdown()
        harness.pump(5)

        values = list(app.port_cb["values"])
        assert len(values) == 0
        assert app.port_cb.get() == ""

    def test_tier2_port_missing_on_connect_raises_cleanly(self, headless_app, monkeypatch, mock_dialogs):
        """TC-T2-PORT-02: Connecting to an unplugged port triggers clean error dialog."""
        harness, app = headless_app
        app.port_cb.set("COM99")
        app.baud_cb.set("115200")

        def _raise_missing(*args, **kwargs):
            raise serial.SerialException("could not open port 'COM99': FileNotFoundError")

        monkeypatch.setattr("serial.Serial", _raise_missing)
        monkeypatch.setattr("modules.tabs.tab_monitor.serial.Serial", _raise_missing, raising=False)

        app.on_serial_connect()
        harness.wait_for(lambda: len(mock_dialogs["showerror"]) > 0, timeout=3.0)

        assert app.serial_connection is None
        assert any("Không thể mở cổng" in m[1] for m in mock_dialogs["showerror"])
        assert app.serial_toggle_btn["text"] == "Kết nối"

    def test_tier2_port_busy_permission_denied(self, headless_app, monkeypatch, mock_dialogs):
        """TC-T2-PORT-03: Connecting to a COM port held by another app shows busy error."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        def _raise_permission(*args, **kwargs):
            raise serial.SerialException("could not open port 'COM3': PermissionError(13, 'Access is denied.')")

        monkeypatch.setattr("serial.Serial", _raise_permission)
        monkeypatch.setattr("modules.tabs.tab_monitor.serial.Serial", _raise_permission, raising=False)

        app.on_serial_connect()
        harness.wait_for(lambda: len(mock_dialogs["showerror"]) > 0, timeout=3.0)

        assert app.serial_connection is None
        assert any("Access is denied" in m[1] or "Không thể mở cổng" in m[1] for m in mock_dialogs["showerror"])

    def test_tier2_serial_sudden_disconnect_during_active_streaming(self, headless_app, mock_serial, mock_dialogs):
        """TC-T2-MON-01: Cable unplug during streaming triggers auto-disconnect and error notice."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        # Inject sudden disconnection fault
        mock_serial.fault_disconnect = True

        harness.wait_for(lambda: app.serial_connection is None, timeout=3.0)
        assert app.serial_connection is None
        assert app.serial_toggle_btn["text"] == "Kết nối"
        assert any("Mất kết nối với thiết bị đột ngột" in m[1] for m in mock_dialogs["showerror"])

    def test_tier2_serial_read_error_handled_gracefully(self, headless_app, mock_serial, mock_dialogs):
        """TC-T2-MON-02: UART framing/parity read error disconnects cleanly without GUI freeze."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        # Inject hardware read failure
        mock_serial.fault_read_error = serial.SerialException("Hardware parity / framing error")

        harness.wait_for(lambda: app.serial_connection is None, timeout=3.0)
        assert app.serial_connection is None
        assert app.serial_toggle_btn["text"] == "Kết nối"

    def test_tier2_serial_write_timeout_handled(self, headless_app, mock_serial, mock_dialogs):
        """TC-T2-MON-03: Serial buffer write timeout triggers error dialog."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        mock_serial.fault_write_timeout = True
        app._send_serial_command("CMD_BLOCKED")
        harness.pump(5)

        assert any("Không thể gửi dữ liệu" in m[1] for m in mock_dialogs["showerror"])
        app.on_serial_disconnect()

    def test_tier2_serial_send_when_disconnected_rejected(self, headless_app, mock_serial):
        """TC-T2-MON-04: Transmitting commands while disconnected updates status with error."""
        harness, app = headless_app
        app.serial_connection = None
        mock_serial.clear_transmitted()

        app._send_serial_command("CMD_OFFLINE")
        harness.pump(5)

        assert mock_serial.get_transmitted_bytes() == b""
        assert "Lỗi: Chưa kết nối Serial!" in app.req_status_lbl["text"]

    def test_tier2_serial_corrupted_non_utf8_bytes_handled(self, headless_app, mock_serial):
        """TC-T2-MON-05: Non-UTF8 junk bytes in UART stream do not raise decode exceptions."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        # Inject corrupt byte sequence followed by valid ASCII
        corrupt_payload = b"\x80\xFF\xFE\xAA\xBB\xCC\x00\x01\x02\r\nRECOVERED_STREAM_DATA\r\n"
        mock_serial.inject_rx_data(corrupt_payload)

        harness.wait_for(lambda: "RECOVERED_STREAM_DATA" in app.monitor_txt.get("1.0", "end"), timeout=3.0)
        content = app.monitor_txt.get("1.0", "end")
        assert "RECOVERED_STREAM_DATA" in content

        app.on_serial_disconnect()

    def test_tier2_chip_inspector_sync_timeout_shows_guidance(self, headless_app, mock_esptool):
        """TC-T2-INSP-01: Bootloader synchronization failure displays user troubleshooting guide."""
        harness, app = headless_app
        mock_esptool.fault_mode = "sync_error"
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        app.on_detect()
        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=4.0)

        content = app.inspector_txt.get("1.0", "end")
        assert "KHÔNG THỂ KẾT NỐI ĐỒNG BỘ VỚI CHIP ESP" in content
        assert "Nhấn và GIỮ nút BOOT" in content
        assert "Kiểm tra cáp USB" in content
        assert "Lỗi kiểm tra." in app.req_status_lbl["text"]

    def test_tier2_chip_inspector_auto_baud_fail_all(self, headless_app, mock_esptool):
        """TC-T2-INSP-02: Total failure across all probed baudrates returns None without crash."""
        _harness, app = headless_app
        mock_esptool.fault_mode = "baud_fail_all"
        detected = app.detect_baud_rate("COM3")
        assert detected is None

    def test_tier2_chip_inspector_unknown_chip_profile(self, headless_app, mock_esptool):
        """TC-T2-INSP-03: Hardware detection of an unknown chip model handles missing DB gracefully."""
        harness, app = headless_app
        mock_esptool.set_profile("ESP32-P5-Unknown")
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        app.on_detect()
        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=4.0)

        content = app.inspector_txt.get("1.0", "end")
        assert "ESP32-P5" in content
        assert "30:AE:A4" in content
        assert "Không có trong CSDL" in content

    def test_tier2_flash_missing_firmware_file_rejected(self, headless_app, mock_dialogs):
        """TC-T2-FLASH-01: Nonexistent binary path is rejected before invoking esptool."""
        harness, app = headless_app
        app.port_cb.set("COM3")

        row = app.flash_file_rows[0]
        row["var_enable"].set(True)
        row["path_entry"].delete(0, "end")
        row["path_entry"].insert(0, "C:/nonexistent_firmware_file_xyz.bin")
        row["offset_entry"].delete(0, "end")
        row["offset_entry"].insert(0, "0x10000")

        app.on_flash_write_click()
        harness.pump(5)

        assert any("không tồn tại" in m[1].lower() for m in mock_dialogs["showerror"])
        assert not app.is_flashing.is_set()

    def test_tier2_flash_invalid_offset_format_rejected(self, headless_app, dummy_firmware_file, mock_dialogs):
        """TC-T2-FLASH-02: Malformed offset string is rejected before invoking esptool."""
        harness, app = headless_app
        bin_path = dummy_firmware_file("valid.bin", size=1024)
        app.port_cb.set("COM3")

        row = app.flash_file_rows[0]
        row["var_enable"].set(True)
        row["path_entry"].delete(0, "end")
        row["path_entry"].insert(0, bin_path)
        row["offset_entry"].delete(0, "end")
        row["offset_entry"].insert(0, "INVALID_HEX_STRING")

        app.on_flash_write_click()
        harness.pump(5)

        assert any("không hợp lệ" in m[1].lower() for m in mock_dialogs["showerror"])
        assert not app.is_flashing.is_set()

    def test_tier2_flash_overlapping_binary_segments_rejected(self, headless_app, dummy_firmware_file, mock_dialogs):
        """TC-T2-FLASH-03: Overlapping flash binary segments are caught by validation."""
        harness, app = headless_app
        # File 1 starts at 0x1000 with 64KB size (spans 0x1000 to 0x11000), overlapping 0x8000
        big_file = dummy_firmware_file("big_boot.bin", size=65536)
        part_file = dummy_firmware_file("part.bin", size=3072)
        app.port_cb.set("COM3")

        r0 = app.flash_file_rows[0]
        r0["var_enable"].set(True)
        r0["path_entry"].delete(0, "end")
        r0["path_entry"].insert(0, big_file)
        r0["offset_entry"].delete(0, "end")
        r0["offset_entry"].insert(0, "0x1000")

        r1 = app.flash_file_rows[1]
        r1["var_enable"].set(True)
        r1["path_entry"].delete(0, "end")
        r1["path_entry"].insert(0, part_file)
        r1["offset_entry"].delete(0, "end")
        r1["offset_entry"].insert(0, "0x8000")

        app.on_flash_write_click()
        harness.pump(5)

        assert any("chồng lấn" in m[1].lower() or "không hợp lệ" in m[1].lower() for m in mock_dialogs["showerror"])
        assert not app.is_flashing.is_set()

    def test_tier2_flash_bad_md5_failure_reported(self, headless_app, mock_esptool, dummy_firmware_file):
        """TC-T2-FLASH-04: Flash write verification failure (bad MD5) updates error log and status."""
        harness, app = headless_app
        bin_path = dummy_firmware_file("corrupt_write.bin", size=2048)
        mock_esptool.fault_mode = "bad_md5"
        app.port_cb.set("COM3")

        row = app.flash_file_rows[0]
        row["var_enable"].set(True)
        row["path_entry"].delete(0, "end")
        row["path_entry"].insert(0, bin_path)
        row["offset_entry"].delete(0, "end")
        row["offset_entry"].insert(0, "0x10000")

        for r in app.flash_file_rows[1:]:
            r["var_enable"].set(False)

        app.on_flash_write_click()
        harness.wait_for(lambda: not app.is_flashing.is_set(), timeout=4.0)

        content = app.flasher_txt.get("1.0", "end")
        assert "LỖI KHI NẠP FLASH" in content or "MD5 of file does not match" in content
        assert "error" == app.current_status_level or "thất bại" in app.req_status_lbl["text"].lower()

    def test_tier2_partition_corrupt_binary_header_rejected(self):
        """TC-T2-PART-01: Loading corrupted partition binary bytes (< 32B or bad magic) handles cleanly."""
        table = PartitionTable()
        # Invalid 32 bytes with all 0xFF (missing 0xAA50 magic)
        corrupted_bytes = b"\xff" * 64
        table.from_binary(corrupted_bytes)
        assert len(table.entries) == 0

    def test_tier2_partition_total_size_exceeds_flash_size(self):
        """TC-T2-PART-02: Partition layout exceeding total chip flash capacity fails validation."""
        table = PartitionTable(flash_size=4 * 1024 * 1024)  # 4MB chip
        table.add_entry(PartitionEntry("nvs", "data", "nvs", 0x9000, 0x6000))
        table.add_entry(PartitionEntry("factory", "app", "factory", 0x10000, 0x300000))  # 3MB
        table.add_entry(PartitionEntry("extra", "data", "spiffs", 0x310000, 0x200000))   # 2MB -> ends at 0x510000 (5.06MB > 4MB)

        errors = table.validate()
        assert len(errors) > 0
        assert any("vượt quá dung lượng" in err for err in errors)

    def test_tier2_partition_write_oversized_file_rejected(self, headless_app, dummy_firmware_file, mock_dialogs):
        """TC-T2-PART-03: Flashing a binary larger than the partition allocation is blocked."""
        harness, app = headless_app
        app.port_cb.set("COM3")

        # Configure small 64KB partition
        app.table.clear()
        app.table.add_entry(PartitionEntry("small_nvs", "data", "nvs", 0x9000, 0x10000))  # 64KB
        app.refresh_partition_views()

        # Create oversized 128KB file
        oversized_file = dummy_firmware_file("oversized.bin", size=131072)
        mock_dialogs["return_open_filename"] = oversized_file

        # Select the entry on the treeview
        children = app.part_tree.get_children()
        assert len(children) > 0
        app.part_tree.selection_set(children[0])

        app._hw_write_selected_partition()
        harness.pump(5)

        assert any("quá lớn" in m[0].lower() or "quá lớn" in m[1].lower() for m in mock_dialogs["showerror"])
        assert not getattr(app, "_is_partition_hw_running", False)
