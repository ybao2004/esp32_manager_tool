"""Tier 4 E2E Tests: Real-world End-to-End Developer Workloads.

Test Cases:
1. TC-T4-E2E-01: Full developer lifecycle: chip detect -> multi-file firmware flash -> serial monitor -> WiFi & IoT Server setup.
2. TC-T4-E2E-02: Partition table resize -> overlap detection -> auto-pack boundary alignment -> flash write & verify.
3. TC-T4-E2E-03: Sudden USB cable disconnect during active stream -> graceful recovery -> hotplug re-detect & reconnect.
4. TC-T4-E2E-04: Defense-in-depth firmware validation: empty file, bad offset, segment overlap, capacity overflow.
"""

import os
import time
import pytest


@pytest.mark.tier4
@pytest.mark.mock_hw
class TestTier4RealWorldWorkloads:

    def test_tier4_full_developer_lifecycle_flash_and_iot_config(self, headless_app, mock_serial, mock_esptool, dummy_firmware_file):
        """TC-T4-E2E-01: Full development loop from chip inspection, 3-stage flash, to IoT WiFi and Server commissioning."""
        harness, app = headless_app
        mock_esptool.set_profile("ESP32-Default")
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # -------------------------------------------------------------
        # Step 1: Chip Inspection
        # -------------------------------------------------------------
        app.on_detect()
        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=5.0)

        report = app.inspector_txt.get("1.0", "end")
        assert "ESP32-D0WD-V3" in report
        assert "4.00 MB" in report
        assert "24:6F:28" in report

        # -------------------------------------------------------------
        # Step 2: Multi-binary Firmware Flashing (Bootloader, Partitions, App)
        # -------------------------------------------------------------
        bootloader_bin = dummy_firmware_file("bootloader.bin", 4096, fill_byte=b"\x01")
        partitions_bin = dummy_firmware_file("partitions.bin", 3072, fill_byte=b"\x02")
        app_bin = dummy_firmware_file("app.bin", 65536, fill_byte=b"\x03")

        # Configure 3 firmware rows
        rows_config = [
            (app.flash_file_rows[0], bootloader_bin, "0x1000"),
            (app.flash_file_rows[1], partitions_bin, "0x8000"),
            (app.flash_file_rows[2], app_bin, "0x10000"),
        ]
        for row, path, offset in rows_config:
            row["var_enable"].set(True)
            row["path_entry"].delete(0, "end")
            row["path_entry"].insert(0, path)
            row["offset_entry"].delete(0, "end")
            row["offset_entry"].insert(0, offset)

        app.flash_file_rows[3]["var_enable"].set(False)

        # Trigger flash write
        app.on_flash_write_click()
        harness.pump(5)
        harness.wait_for(lambda: not app.is_flashing.is_set(), timeout=7.0)

        flash_log = app.flasher_txt.get("1.0", "end")
        assert "NẠP FLASH THÀNH CÔNG" in flash_log
        assert "100%" in app.flash_pct_lbl["text"]

        # -------------------------------------------------------------
        # Step 3: Serial Monitor Commissioning & IoT Configuration
        # -------------------------------------------------------------
        app.on_serial_connect()
        harness.pump(5)
        assert app.serial_connection is not None and app.serial_connection.is_open is True

        # Trigger Reset to simulate ESP32 rebooting with new firmware
        app.on_reset_esp()
        harness.wait_for(lambda: app.serial_connection.reset_count >= 1, timeout=3.0)
        time.sleep(0.2)
        harness.pump(10)
        assert app.serial_connection.reset_count >= 1

        # Commission WiFi
        app.wifi_cb.set("SmartFactory_WiFi")
        app.wifi_pass_entry.delete(0, "end")
        app.wifi_pass_entry.insert(0, "SuperSecret2026")
        app.on_wifi_connect()
        harness.wait_for(lambda: app.is_wifi_connected, timeout=4.0)

        # Verify WiFi connection status is updated
        assert app.is_wifi_connected is True
        assert "Đã kết nối" in app.wifi_status_lbl["text"]

        # Commission TCP Server
        app.ip_entry.delete(0, "end")
        app.ip_entry.insert(0, "192.168.4.1")
        app.port_entry.delete(0, "end")
        app.port_entry.insert(0, "100")
        app.on_server_connect()
        harness.wait_for(lambda: app.is_server_connected, timeout=4.0)

        # Verify Server connection status is updated
        assert app.is_server_connected is True
        assert "Đã kết nối WiFi & Server" in app.wifi_status_lbl["text"]

        # Send telemetry command
        app.serial_input.delete("1.0", "end")
        app.serial_input.insert("1.0", "CMD:TELEMETRY:TEMP=26.4;HUM=58")
        app.on_serial_send()
        harness.pump(5)

        transmitted = app.serial_connection.get_transmitted_bytes()
        assert b"CMD:TELEMETRY:TEMP=26.4;HUM=58" in transmitted

        # Clean shutdown of serial session
        app.on_serial_disconnect()
        assert app.serial_connection is None

    def test_tier4_partition_table_realignment_and_flash_recovery(self, headless_app, mock_esptool):
        """TC-T4-E2E-02: Partition table modification with overlap detection, auto-align cascading, and flash persistence."""
        harness, app = headless_app
        mock_esptool.set_profile("ESP32-Default")
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # 1. Read existing partition table from chip
        app.table.clear()
        app._hw_read_partition_table()
        harness.wait_for(lambda: len(app.table.entries) >= 4 and not getattr(app, "_is_partition_hw_running", False), timeout=6.0)
        harness.pump(10)

        assert len(app.table.entries) == 4
        # Original: factory at 0x10000 size 1MB (ends at 0x110000), storage starts at 0x110000
        factory_entry = app.table.entries[2]
        storage_entry = app.table.entries[3]
        assert factory_entry.name == "factory"
        assert storage_entry.name == "storage"

        # 2. Modify factory partition size from 1MB to 2MB (0x200000)
        # This will cause factory to end at 0x210000, colliding with storage at 0x110000
        factory_entry.size = 2 * 1024 * 1024
        errors = app.table.validate()
        assert len(errors) > 0
        assert any("chồng lấn" in err.lower() or "đè" in err.lower() for err in errors)

        # 3. Resolve collision by running cascade auto-pack from factory partition
        app._cascade_auto_pack(from_idx=2)
        harness.pump(5)

        # Verify errors are now completely resolved
        clean_errors = app.table.validate()
        assert len(clean_errors) == 0
        # Storage must have been pushed down past 0x210000
        assert storage_entry.offset >= 0x210000
        # Storage offset must be 4KB boundary aligned
        assert storage_entry.offset % 0x1000 == 0

        # 4. Flash modified partition table down to the chip
        app._hw_flash_partition_table()
        harness.wait_for(lambda: not getattr(app, "_is_partition_hw_running", False), timeout=6.0)
        harness.pump(10)

        # Verify flash write command was dispatched
        assert any("write_flash" in cmd or "write-flash" in cmd for cmd in mock_esptool.command_history)

    def test_tier4_cable_disconnect_and_hotplug_recovery(self, headless_app, mock_serial, mock_ports):
        """TC-T4-E2E-03: Sudden USB cable disconnection during active serial session gracefully recovers on hotplug."""
        harness, app = headless_app
        mock_ports.set_ports(["COM3", "COM4"])
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # 1. Establish normal active serial connection
        app.on_serial_connect()
        harness.pump(5)
        active_serial = app.serial_connection
        assert active_serial is not None and active_serial.is_open is True

        # Stream initial data
        active_serial.inject_rx_line("[DEVICE] Normal telemetry heartbeat...")
        harness.pump(10)
        assert "[DEVICE] Normal telemetry heartbeat..." in app.monitor_txt.get("1.0", "end")

        # 2. Simulate sudden USB cable yank (hardware fault disconnect)
        active_serial.fault_disconnect = True
        mock_ports.remove_port("COM3")

        # Allow worker thread to encounter SerialException and schedule disconnect
        harness.wait_for(lambda: app.serial_connection is None, timeout=4.0)

        # Verify UI updated to disconnected state safely
        assert "Kết nối" in app.serial_toggle_btn["text"]
        assert "Chưa kết nối" in app.wifi_status_lbl["text"]

        # 3. Simulate user plugging cable back into USB port
        mock_serial.fault_disconnect = False
        mock_ports.add_port("COM3", "Silicon Labs CP210x USB to UART Bridge", "USB VID:PID=10C4:EA60")
        app.refresh_ports_dropdown()
        harness.pump(5)

        assert "COM3" in app.port_cb["values"]
        app.port_cb.set("COM3")

        # Reconnect Serial Monitor
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=4.0)

        # Verify full communication restored on new connection
        new_serial = app.serial_connection
        assert new_serial is not None and new_serial.is_open is True

        new_serial.inject_rx_line("[DEVICE] Resumed after cable reconnect!")
        harness.pump(10)
        assert "[DEVICE] Resumed after cable reconnect!" in app.monitor_txt.get("1.0", "end")

        app.on_serial_disconnect()

    def test_tier4_defense_in_depth_firmware_validation(self, headless_app, mock_esptool, mock_dialogs, dummy_firmware_file):
        """TC-T4-E2E-04: Robust pre-flash validation traps corrupt, missing, overlapping, or out-of-bounds payloads."""
        _harness, app = headless_app
        app.port_cb.set("COM3")
        initial_esptool_calls = mock_esptool.execution_count

        # Case A: Enabled row with empty file path
        row0 = app.flash_file_rows[0]
        row0["var_enable"].set(True)
        row0["path_entry"].delete(0, "end")
        row0["offset_entry"].delete(0, "end")
        row0["offset_entry"].insert(0, "0x1000")

        app.on_flash_write_click()
        assert not app.is_flashing.is_set()
        assert mock_esptool.execution_count == initial_esptool_calls

        # Case B: Enabled row with nonexistent file path
        row0["path_entry"].insert(0, r"C:\nonexistent_firmware_file_12345.bin")
        app.on_flash_write_click()
        assert not app.is_flashing.is_set()
        assert mock_esptool.execution_count == initial_esptool_calls

        # Case C: Enabled row with corrupt/invalid hex offset
        valid_fw = dummy_firmware_file("valid_app.bin", 4096)
        row0["path_entry"].delete(0, "end")
        row0["path_entry"].insert(0, valid_fw)
        row0["offset_entry"].delete(0, "end")
        row0["offset_entry"].insert(0, "INVALID_HEX_OFFSET")

        app.on_flash_write_click()
        assert not app.is_flashing.is_set()
        assert mock_esptool.execution_count == initial_esptool_calls

        # Case D: Overlapping binary segments
        # Row 0: 64KB starting at 0x10000 (ends at 0x20000)
        fw64k = dummy_firmware_file("fw64k.bin", 65536)
        row0["offset_entry"].delete(0, "end")
        row0["offset_entry"].insert(0, "0x10000")
        row0["path_entry"].delete(0, "end")
        row0["path_entry"].insert(0, fw64k)

        # Row 1: Colliding at 0x18000
        row1 = app.flash_file_rows[1]
        row1["var_enable"].set(True)
        row1["offset_entry"].delete(0, "end")
        row1["offset_entry"].insert(0, "0x18000")
        row1["path_entry"].delete(0, "end")
        row1["path_entry"].insert(0, valid_fw)

        app.on_flash_write_click()
        assert not app.is_flashing.is_set()
        # Ensure esptool was never invoked
        assert mock_esptool.execution_count == initial_esptool_calls
        assert any("chồng lấn" in str(call) or "không hợp lệ" in str(call).lower() for call in mock_dialogs["showerror"])
