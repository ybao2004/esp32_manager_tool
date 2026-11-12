# -*- coding: utf-8 -*-
"""
Tier 1: Feature Coverage (Happy Path) Test Suite.
Verifies standard operational flows across all 4 tabs of esp32_manager_tool
using in-memory MockSerial, MockPortRegistry, and MockEsptoolEngine.
"""
import os
import time
import pytest

from modules.partition.partition_model import PartitionTable, PartitionEntry
from modules.config import CONTROL_CONFIG


@pytest.mark.tier1
@pytest.mark.mock_hw
class TestTier1Features:
    """Happy-path feature tests for esp32_manager_tool."""

    def test_tier1_port_scan_and_populate_dropdown(self, headless_app, mock_ports):
        """TC-T1-PORT-01: Verify COM ports are scanned and populated in the dropdown."""
        harness, app = headless_app
        mock_ports.set_ports({
            "COM3": ("Silicon Labs CP210x", "USB\\VID_10C4&PID_EA60"),
            "COM4": ("CH340 Serial", "USB\\VID_1A86&PID_7523")
        })
        app.refresh_ports_dropdown()
        harness.pump(5)

        values = list(app.port_cb["values"])
        assert "COM3" in values
        assert "COM4" in values
        assert app.port_cb.get() in ["COM3", "COM4"]

    def test_tier1_bluetooth_ports_filtered_by_default(self, headless_app, mock_ports):
        """TC-T1-PORT-02: Verify Bluetooth ports are excluded from standard port listings."""
        harness, app = headless_app
        mock_ports.set_ports({
            "COM3": ("CP2102 USB to UART", "USB\\VID_10C4&PID_EA60"),
            "COM5": ("Standard Serial over Bluetooth link", "BTHENUM\\{00001101-0000-1000}")
        })
        app.ignored_com_ports = ["COM5"]
        filtered = app.filter_ignored_ports(["COM3", "COM5"])
        assert filtered == ["COM3"]
        assert "COM5" not in filtered

    def test_tier1_serial_monitor_connect_and_receive_stream(self, headless_app, mock_serial):
        """TC-T1-MON-01: Verify serial monitor connection and text streaming to monitor_txt."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        assert app.serial_toggle_btn["text"] == "Ngắt kết nối"
        assert app.serial_connection.is_open is True

        # Inject simulated bootloader log
        boot_msg = "ESP-ROM:esp32-d0wd-v3\r\nBooting firmware v2.0...\r\n"
        mock_serial.inject_rx_data(boot_msg.encode("utf-8"))

        harness.wait_for(lambda: "ESP-ROM:esp32-d0wd-v3" in app.monitor_txt.get("1.0", "end"), timeout=3.0)
        content = app.monitor_txt.get("1.0", "end")
        assert "ESP-ROM:esp32-d0wd-v3" in content
        assert "Booting firmware v2.0..." in content

        app.on_serial_disconnect()
        harness.pump(5)
        assert app.serial_connection is None
        assert app.serial_toggle_btn["text"] == "Kết nối"

    def test_tier1_serial_monitor_send_command_with_crlf(self, headless_app, mock_serial):
        """TC-T1-MON-02A: Verify sending command via serial appends CRLF when enabled."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        mock_serial.clear_transmitted()
        app.var_crlf.set(True)
        app.serial_input.delete("1.0", "end")
        app.serial_input.insert("1.0", "AT+GMR")

        app.on_serial_send()
        harness.pump(5)

        sent = mock_serial.get_transmitted_bytes()
        assert sent == b"AT+GMR\r\n"
        assert app.serial_input.get("1.0", "end").strip() == ""
        app.on_serial_disconnect()

    def test_tier1_serial_monitor_send_command_without_crlf(self, headless_app, mock_serial):
        """TC-T1-MON-02B: Verify sending command raw when CRLF option is disabled."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        mock_serial.clear_transmitted()
        app.var_crlf.set(False)
        app.serial_input.delete("1.0", "end")
        app.serial_input.insert("1.0", "RAW_BINARY_PULSE")

        app.on_serial_send()
        harness.pump(5)

        sent = mock_serial.get_transmitted_bytes()
        assert sent == b"RAW_BINARY_PULSE"
        assert app.serial_input.get("1.0", "end").strip() == ""
        app.on_serial_disconnect()

    def test_tier1_iot_wifi_connect_and_feedback(self, headless_app, mock_serial):
        """TC-T1-MON-03A: Verify WiFi configuration and connection state transition."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        app.wifi_cb.set("Office_WiFi")
        app.wifi_pass_entry.delete(0, "end")
        app.wifi_pass_entry.insert(0, "Secret123")

        app.on_wifi_connect()
        # Wait for auto-responder to emit RES:WIFI_CONNECTED
        harness.wait_for(lambda: app.is_wifi_connected is True, timeout=3.0)

        assert app.is_wifi_connected is True
        assert app.btn_connect_wifi["text"] == "Ngắt WiFi"
        assert "Đã kết nối" in app.wifi_status_lbl["text"] or "Office_WiFi" in app.wifi_status_lbl["text"]

        app.on_serial_disconnect()

    def test_tier1_iot_wifi_disconnect(self, headless_app, mock_serial):
        """TC-T1-MON-03B: Verify WiFi disconnection state transition."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        app.is_wifi_connected = True
        app.btn_connect_wifi.config(text="Ngắt WiFi")

        app.on_wifi_disconnect()
        harness.wait_for(lambda: app.is_wifi_connected is False, timeout=3.0)

        assert app.is_wifi_connected is False
        assert app.btn_connect_wifi["text"] == "Kết nối WiFi"
        assert app.wifi_status_lbl["text"] == "Chưa kết nối"

        app.on_serial_disconnect()

    def test_tier1_iot_wifi_scan_populates_networks(self, headless_app, mock_serial):
        """TC-T1-MON-03C: Verify SCAN_WIFI populates network SSID combobox."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        app.scanned_networks.clear()
        app.on_wifi_scan()
        harness.wait_for(lambda: len(app.scanned_networks) >= 2, timeout=3.0)

        assert "MockHome_2.4G" in app.scanned_networks
        assert "Office_5G" in app.scanned_networks
        assert "MockHome_2.4G" in list(app.wifi_cb["values"])

        app.on_serial_disconnect()

    def test_tier1_iot_server_connect_and_disconnect(self, headless_app, mock_serial):
        """TC-T1-MON-03D: Verify TCP Server connect and disconnect state transitions."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        app.is_wifi_connected = True  # Prerequisite
        app.ip_entry.delete(0, "end")
        app.ip_entry.insert(0, "192.168.1.100")
        app.port_entry.delete(0, "end")
        app.port_entry.insert(0, "8888")

        app.on_server_connect()
        harness.wait_for(lambda: app.is_server_connected is True, timeout=3.0)

        assert app.is_server_connected is True
        assert app.btn_connect_server["text"] == "Ngắt Server"

        app.on_server_disconnect()
        harness.wait_for(lambda: app.is_server_connected is False, timeout=3.0)

        assert app.is_server_connected is False
        assert app.btn_connect_server["text"] == "Kết nối Server"

        app.on_serial_disconnect()

    def test_tier1_hardware_reset_trigger_pulses_pins(self, headless_app, mock_serial):
        """TC-T1-MON-04: Verify hardware reset triggers DTR/RTS pulsing and reset detection."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")
        app.on_serial_connect()
        harness.wait_for(lambda: app.serial_connection is not None and app.serial_connection.is_open, timeout=3.0)

        prev_count = mock_serial.reset_count
        app.on_reset_esp()
        harness.wait_for(lambda: mock_serial.reset_count > prev_count, timeout=3.0)

        assert mock_serial.reset_count > prev_count
        assert "RESET" in mock_serial.get_transmitted_text()

        app.on_serial_disconnect()

    def test_tier1_chip_inspector_full_detection(self, headless_app, mock_esptool):
        """TC-T1-INSP-01: Verify full chip and flash hardware inspection reporting."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        app.on_detect()
        harness.pump(5)
        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=6.0)

        content = app.inspector_txt.get("1.0", "end")
        assert "ESP32-D0WD-V3" in content
        assert "24:6F:28:AB:CD:EF" in content
        assert "4.00 MB" in content
        assert "Winbond" in content
        assert "Hoàn thành." in app.req_status_lbl["text"] or "success" == app.current_status_level

    def test_tier1_chip_inspector_auto_baud_detection(self, headless_app, mock_esptool):
        """TC-T1-INSP-02: Verify automatic baudrate probe succeeds at supported speed."""
        _harness, app = headless_app
        detected = app.detect_baud_rate("COM3")
        assert detected == "115200"

    def test_tier1_chip_inspector_s3_16mb_profile(self, headless_app, mock_esptool):
        """TC-T1-INSP-03: Verify chip inspection against an ESP32-S3 with 16MB Flash and PSRAM."""
        harness, app = headless_app
        mock_esptool.set_profile("ESP32-S3-16MB")
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        app.on_detect()
        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=4.0)

        content = app.inspector_txt.get("1.0", "end")
        assert "ESP32-S3" in content
        assert "16.00 MB" in content
        assert "GigaDevice" in content
        assert "8 MB" in content

    def test_tier1_flash_single_binary_firmware(self, headless_app, mock_esptool, dummy_firmware_file):
        """TC-T1-FLASH-01: Verify flashing a single application binary file."""
        harness, app = headless_app
        bin_path = dummy_firmware_file("app.bin", size=4096)

        app.port_cb.set("COM3")
        row = app.flash_file_rows[0]
        row["var_enable"].set(True)
        row["path_entry"].delete(0, "end")
        row["path_entry"].insert(0, bin_path)
        row["offset_entry"].delete(0, "end")
        row["offset_entry"].insert(0, "0x10000")

        for other_row in app.flash_file_rows[1:]:
            other_row["var_enable"].set(False)

        app.on_flash_write_click()
        harness.wait_for(lambda: not app.is_flashing.is_set() and app.flash_prog["value"] == 100, timeout=4.0)

        assert app.flash_prog["value"] == 100
        assert "NẠP FLASH THÀNH CÔNG" in app.flasher_txt.get("1.0", "end")
        last_cmd = mock_esptool.last_executed_command
        assert "write-flash" in last_cmd or "write_flash" in last_cmd
        assert "0x10000" in last_cmd
        assert bin_path in last_cmd

    def test_tier1_flash_multi_binary_firmware(self, headless_app, mock_esptool, dummy_firmware_file):
        """TC-T1-FLASH-02: Verify flashing multi-file images (bootloader, partition, app)."""
        harness, app = headless_app
        boot_bin = dummy_firmware_file("bootloader.bin", size=2048)
        part_bin = dummy_firmware_file("partitions.bin", size=3072)
        app_bin = dummy_firmware_file("application.bin", size=8192)

        app.port_cb.set("COM3")
        offsets_and_files = [("0x1000", boot_bin), ("0x8000", part_bin), ("0x10000", app_bin)]

        for idx, (offset, fpath) in enumerate(offsets_and_files):
            r = app.flash_file_rows[idx]
            r["var_enable"].set(True)
            r["path_entry"].delete(0, "end")
            r["path_entry"].insert(0, fpath)
            r["offset_entry"].delete(0, "end")
            r["offset_entry"].insert(0, offset)

        app.flash_file_rows[3]["var_enable"].set(False)

        app.on_flash_write_click()
        harness.pump(5, delay=0.01)
        harness.wait_for(lambda: not app.is_flashing.is_set() and app.flash_prog["value"] == 100, timeout=4.0)
        if getattr(app, "flash_thread", None) and app.flash_thread.is_alive():
            app.flash_thread.join(timeout=1.0)

        assert app.flash_prog["value"] == 100
        last_cmd = mock_esptool.last_executed_command
        assert "0x1000" in last_cmd
        assert "0x8000" in last_cmd
        assert "0x10000" in last_cmd

    def test_tier1_flash_erase_entire_chip(self, headless_app, mock_esptool, mock_dialogs):
        """TC-T1-FLASH-03: Verify erasing the entire flash chip."""
        harness, app = headless_app
        app.port_cb.set("COM3")

        app.on_erase_flash_click()
        harness.wait_for(lambda: not app.is_flashing.is_set() and app.flash_prog["value"] == 100, timeout=4.0)

        assert app.flash_prog["value"] == 100
        assert "XÓA SẠCH FLASH THÀNH CÔNG" in app.flasher_txt.get("1.0", "end")
        assert "erase-flash" in mock_esptool.last_executed_command or "erase_flash" in mock_esptool.last_executed_command

    def test_tier1_flash_erase_region_nvs(self, headless_app, mock_esptool, mock_dialogs):
        """TC-T1-FLASH-04: Verify erasing a specific flash memory region."""
        harness, app = headless_app
        app.port_cb.set("COM3")

        app._start_erase_nvs_thread("COM3", "0x9000", "0x6000")
        harness.wait_for(lambda: not app.is_flashing.is_set(), timeout=4.0)

        last_cmd = mock_esptool.last_executed_command
        assert "erase-region" in last_cmd or "erase_region" in last_cmd
        assert "0x9000" in last_cmd
        assert "0x6000" in last_cmd

    def test_tier1_partition_csv_roundtrip(self):
        """TC-T1-PART-01: Verify CSV import and export roundtrip preserving structure."""
        csv_source = (
            "# ESP-IDF Partition Table\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 0x100000,\n"
            "storage,  data, spiffs,  0x110000, 0x100000,\n"
        )
        table = PartitionTable(flash_size=4 * 1024 * 1024)
        table.from_csv(csv_source)

        assert len(table.entries) == 4
        assert table.entries[0].name == "nvs"
        assert table.entries[2].name == "factory"
        assert table.entries[2].offset == 0x10000
        assert table.entries[2].size == 0x100000

        exported = table.to_csv()
        table2 = PartitionTable(flash_size=4 * 1024 * 1024)
        table2.from_csv(exported)

        assert len(table2.entries) == 4
        for e1, e2 in zip(table.entries, table2.entries):
            assert e1.name == e2.name
            assert e1.offset == e2.offset
            assert e1.size == e2.size

    def test_tier1_partition_auto_pack_and_align(self):
        """TC-T1-PART-02: Verify auto-packing sets correct boundaries and alignment."""
        table = PartitionTable(flash_size=4 * 1024 * 1024, part_table_offset=0x8000)
        table.add_entry(PartitionEntry("nvs", "data", "nvs", 0x9000, 0x6000))
        table.add_entry(PartitionEntry("factory", "app", "factory", 0, 0x100000))  # Unset offset
        table.add_entry(PartitionEntry("storage", "data", "spiffs", 0, 0x80000))   # Unset offset

        table.auto_pack_and_align()

        # factory must be aligned to 64KB (0x10000)
        factory = next(e for e in table.entries if e.name == "factory")
        assert factory.offset % 0x10000 == 0
        assert factory.offset >= 0x10000

        # storage must be aligned to 4KB (0x1000)
        storage = next(e for e in table.entries if e.name == "storage")
        assert storage.offset % 0x1000 == 0
        assert storage.offset >= factory.end_offset
        assert table.validate() == []

    def test_tier1_partition_hw_read_table_from_chip(self, headless_app, mock_esptool, mock_dialogs):
        """TC-T1-PART-03: Verify reading and parsing partition table directly from chip."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.table.clear()

        app._hw_read_partition_table()
        harness.wait_for(lambda: not getattr(app, "_is_partition_hw_running", False) and len(app.table.entries) > 0, timeout=4.0)

        assert len(app.table.entries) == 4
        names = [e.name for e in app.table.entries]
        assert "nvs" in names
        assert "factory" in names
        assert "storage" in names
        assert "Đã đọc và giải mã bảng phân vùng" in app.req_status_lbl["text"]

    def test_tier1_partition_hw_flash_table_to_chip(self, headless_app, mock_esptool, mock_dialogs):
        """TC-T1-PART-04: Verify compiling and flashing the partition table binary to chip."""
        harness, app = headless_app
        app.port_cb.set("COM3")

        # Ensure valid table entries
        app.table.clear()
        app.table.add_entry(PartitionEntry("nvs", "data", "nvs", 0x9000, 0x6000))
        app.table.add_entry(PartitionEntry("factory", "app", "factory", 0x10000, 0x100000))

        app._hw_flash_partition_table()
        harness.wait_for(lambda: not getattr(app, "_is_partition_hw_running", False), timeout=4.0)

        last_cmd = mock_esptool.last_executed_command
        assert "write_flash" in last_cmd or "write-flash" in last_cmd
        assert "0x8000" in last_cmd
        assert "Đã nạp Bảng phân vùng xuống chip thành công!" in app.req_status_lbl["text"]
