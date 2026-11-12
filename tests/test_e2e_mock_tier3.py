"""Tier 3 E2E Tests: Cross-feature interaction, Mutex Locking, State Transitions.

Test Cases:
1. TC-T3-MUTEX-01: Auto-disconnect serial before chip inspect.
2. TC-T3-MUTEX-02: Auto-disconnect serial before firmware flash write & auto-restore.
3. TC-T3-MUTEX-03: Auto-disconnect serial before partition table write/read.
4. TC-T3-MUTEX-04: Mutual exclusion locks detect/erase/partition while flashing is active.
5. TC-T3-MUTEX-05: Global busy state locks/unlocks navigation & toolbar widgets.
6. TC-T3-PORT-01: Port dropdown change while serial connected preserves active session.
7. TC-T3-CLOSE-01: Application close attempt is blocked while hardware task is busy.
8. TC-T3-SYNC-01: Chip inspector and partition wizard chip family/size synchronization.
"""

from unittest.mock import MagicMock
import pytest


@pytest.mark.tier3
@pytest.mark.mock_hw
class TestTier3Interactions:

    def test_tier3_auto_disconnect_serial_before_chip_inspect(self, headless_app, mock_serial, mock_esptool):
        """TC-T3-MUTEX-01: Opening chip inspector automatically disconnects active Serial session."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # 1. Connect serial monitor
        app.on_serial_connect()
        harness.pump(times=5)
        assert app.serial_connection is not None
        assert app.serial_connection.is_open is True

        # 2. Trigger Chip Inspection
        app.on_detect()
        harness.pump(times=5)

        # Serial monitor should be disconnected to free the COM port for esptool
        assert app.serial_connection is None or app.serial_connection.is_open is False
        assert "Kết nối" in app.serial_toggle_btn["text"]

        # 3. Wait for detection to complete
        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=5.0)
        assert "ESP32-D0WD-V3" in app.inspector_txt.get("1.0", "end")

    def test_tier3_auto_disconnect_serial_before_flash_write(self, headless_app, mock_serial, mock_esptool, dummy_firmware_file):
        """TC-T3-MUTEX-02: Starting firmware flash automatically disconnects active Serial session."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # Connect serial
        app.on_serial_connect()
        harness.pump(5)
        assert app.serial_connection is not None
        assert app.serial_connection.is_open is True
        old_serial = app.serial_connection

        # Configure firmware row
        fw_path = dummy_firmware_file("app.bin", 2048)
        row = app.flash_file_rows[0]
        row["var_enable"].set(True)
        row["path_entry"].delete(0, "end")
        row["path_entry"].insert(0, fw_path)
        row["offset_entry"].delete(0, "end")
        row["offset_entry"].insert(0, "0x10000")

        # Start flash write
        app.on_flash_write_click()
        harness.pump(5)

        # While flash is running or just started, serial monitor must have been disconnected
        assert old_serial.is_open is False

        # Wait for flash to complete
        harness.wait_for(lambda: not app.is_flashing.is_set(), timeout=6.0)
        assert "NẠP FLASH THÀNH CÔNG" in app.flasher_txt.get("1.0", "end")

    def test_tier3_auto_disconnect_serial_before_partition_flash(self, headless_app, mock_serial, mock_esptool):
        """TC-T3-MUTEX-03: Partition table hardware operations safely disconnect active Serial session."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # Connect serial
        app.on_serial_connect()
        harness.pump(times=5)
        assert app.serial_connection is not None
        assert app.serial_connection.is_open is True
        old_serial = app.serial_connection

        # Run hardware read partition table
        app._hw_read_partition_table()
        harness.pump(times=5)

        # Serial monitor should be disconnected
        assert old_serial.is_open is False

        # Wait for partition read worker to finish
        harness.wait_for(lambda: not getattr(app, "_is_partition_hw_running", False), timeout=6.0)
        assert len(app.table.entries) >= 2

    def test_tier3_mutual_exclusion_locks_detect_erase_partition_while_flashing(self, headless_app, mock_dialogs):
        """TC-T3-MUTEX-04: Background flash operation blocks inspection, erase, and partition hardware calls."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # Simulate active flashing lock
        app.is_flashing.set()
        assert app.is_device_busy() is True

        # Attempt detect
        app.on_detect()
        assert not app.is_detecting.is_set()

        # Attempt erase click
        app.on_erase_flash_click()
        assert any("Bận" in str(item) or "bận" in str(item) for item in mock_dialogs["showwarning"])

        # Attempt partition read
        app._hw_read_partition_table()
        assert not getattr(app, "_is_partition_hw_running", False)

        # Release lock
        app.is_flashing.clear()
        assert app.is_device_busy() is False

    def test_tier3_global_busy_state_ui_lockout(self, headless_app):
        """TC-T3-MUTEX-05: Global busy state disables toolbar controls and restores them on idle."""
        _harness, app = headless_app

        # Lock controls
        app.set_global_busy_state(True, "đang chạy tác vụ kiểm thử")
        assert str(app.detect_btn["state"]) == "disabled"
        assert str(app.serial_toggle_btn["state"]) == "disabled"
        assert str(app.port_cb["state"]) == "disabled"

        # Unlock controls
        app.set_global_busy_state(False)
        assert str(app.detect_btn["state"]) == "normal"
        assert str(app.serial_toggle_btn["state"]) == "normal"
        assert str(app.port_cb["state"]) in ("readonly", "normal")

    def test_tier3_port_dropdown_change_while_connected_preserves_active_session(self, headless_app, mock_serial, mock_ports):
        """TC-T3-PORT-01: Changing dropdown value does not sever or crash an ongoing serial connection."""
        harness, app = headless_app
        mock_ports.set_ports(["COM3", "COM4"])
        app.port_cb["values"] = ["COM3", "COM4"]
        app.port_cb.set("COM3")

        # Connect on COM3
        app.on_serial_connect()
        harness.pump(times=5)
        active_conn = app.serial_connection
        assert active_conn is not None and active_conn.is_open is True
        assert active_conn.port == "COM3"

        # User changes dropdown to COM4
        app.port_cb.set("COM4")
        harness.pump(times=5)

        # The existing connection on COM3 must remain open and intact
        assert app.serial_connection is active_conn
        assert app.serial_connection.is_open is True

        # Disconnecting properly closes the original connection
        app.on_serial_disconnect()
        assert active_conn.is_open is False

    def test_tier3_window_close_blocked_during_hardware_task(self, headless_app, mock_dialogs, monkeypatch):
        """TC-T3-CLOSE-01: Closing the window while device is busy is rejected with a warning dialog."""
        _harness, app = headless_app

        mock_destroy = MagicMock()
        monkeypatch.setattr(app.root, "destroy", mock_destroy)

        # 1. While busy
        app.is_flashing.set()
        app.on_closing()

        # destroy must not be called
        assert not mock_destroy.called
        assert any("Tác vụ chưa hoàn tất" in str(item) for item in mock_dialogs["showwarning"])

        # 2. When idle
        app.is_flashing.clear()
        app.on_closing()
        assert mock_destroy.called

    def test_tier3_flash_size_sync_between_inspector_and_partition_wizard(self, headless_app, mock_esptool):
        """TC-T3-SYNC-01: Chip inspector detection synchronizes chip family and capacity with partition wizard."""
        harness, app = headless_app
        mock_esptool.set_profile("ESP32-S3-16MB")
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # Run inspector detection
        app.on_detect()
        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=5.0)

        # Verify Chip Inspector reports ESP32-S3 with 16MB flash
        inspector_output = app.inspector_txt.get("1.0", "end")
        assert "ESP32-S3" in inspector_output
        assert "16.00 MB" in inspector_output

        # Synchronize / select ESP32-S3 in Partition Wizard
        app.part_chip_var.set("ESP32-S3")
        app._on_chip_changed()
        assert app.table.target_chip == "esp32s3"
        assert app.table.bootloader_offset == 0x0000
        assert "16 MB" in app.cb_part_flash["values"]

        # Select 16 MB flash capacity matching the inspected hardware
        app.part_flash_var.set("16 MB")
        app._on_flash_size_changed()
        assert app.table.flash_size == 16 * 1024 * 1024

        # Read partition table from chip
        app.table.clear()
        assert len(app.table.entries) == 0

        app._hw_read_partition_table()
        harness.wait_for(lambda: len(app.table.entries) >= 4 and not getattr(app, "_is_partition_hw_running", False), timeout=6.0)
        harness.pump(10)

        assert len(app.table.entries) == 4
        assert app.table.entries[0].name == "nvs"
        assert app.table.entries[2].name == "factory"
