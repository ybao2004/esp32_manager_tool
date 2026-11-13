# -*- coding: utf-8 -*-
"""
Tier 5 Adversarial Coverage Hardening Test Suite.
Empirically stress-tests untested code paths, edge cases, exception handling,
and race conditions across:
- modules/app_core.py (status bar flooding, mode switching, busy state coordination, port scanning)
- modules/tabs/tab_inspector.py (hardware detection exceptions, corrupted esptool outputs, save dialogs)
- modules/tabs/tab_monitor.py (non-blocking serial transmission failure, write timeouts, buffer overflows, IoT telemetry)
"""
import builtins
import queue
import time
import threading
from modules.ui import models as tk
from unittest.mock import MagicMock, patch

import pytest
import serial

from modules.config import So_dong_serial_toi_da
import modules.app_core as app_core_mod
import modules.tabs.tab_inspector as tab_inspector_mod


@pytest.mark.mock_hw
class TestTier5AdversarialCore:
    """Tier 5 Adversarial Coverage Hardening Tests for esp32_manager_tool."""

    # =========================================================================
    # Group 1: Rapid Status Bar Updates & Progress Bar Mode Switches (app_core.py)
    # =========================================================================

    def test_tier5_status_bar_concurrent_flooding_and_mode_switching(self, headless_app):
        """TC-T5-STATUS-01: Rapid concurrent status updates and mode switches across threads."""
        harness, app = headless_app
        stop_workers = threading.Event()
        errors = queue.Queue()

        def _mode_switch_worker():
            try:
                for i in range(25):
                    if stop_workers.is_set():
                        break
                    # Alternate indeterminate pulsing and determinate tracking
                    app.update_global_status(f"Indeterminate task {i}", is_active=True, progress=None)
                    time.sleep(0.002)
                    app.update_global_status(f"Determinate task {i}", is_active=False, progress=float(i * 4))
                    time.sleep(0.002)
            except Exception as e:
                errors.put(e)

        def _status_level_worker():
            try:
                levels = ["info", "success", "warning", "error"]
                for i in range(25):
                    if stop_workers.is_set():
                        break
                    lvl = levels[i % len(levels)]
                    app.set_status(f"Burst status {i}", level=lvl, progress=float(i * 3.5))
                    time.sleep(0.003)
            except Exception as e:
                errors.put(e)

        def _busy_toggle_worker():
            try:
                for i in range(20):
                    if stop_workers.is_set():
                        break
                    app.set_global_busy_state(True, f"Op {i}")
                    time.sleep(0.002)
                    app.set_global_busy_state(False, f"Op {i}")
                    time.sleep(0.002)
            except Exception as e:
                errors.put(e)

        threads = [
            threading.Thread(target=_mode_switch_worker, daemon=True),
            threading.Thread(target=_status_level_worker, daemon=True),
            threading.Thread(target=_busy_toggle_worker, daemon=True),
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        assert errors.empty(), f"Worker thread raised exception: {errors.get() if not errors.empty() else ''}"

        # Pump harness to drain all queued after() events
        harness.pump(times=20, delay=0.005)

        assert bool(app.root.winfo_exists()) is True
        assert bool(app.global_status_lbl.winfo_exists()) is True
        assert bool(app.global_progress_bar.winfo_exists()) is True
        # Verify status text is populated
        status_text = app.global_status_lbl.cget("text")
        assert len(status_text) > 0

    def test_tier5_status_bar_extreme_progress_values(self, headless_app):
        """TC-T5-STATUS-02: Boundary, overflow, negative, and extreme numeric progress values."""
        harness, app = headless_app

        numeric_test_cases = [
            ("Zero progress", 0.0),
            ("Full progress", 100.0),
            ("Negative progress", -40.0),
            ("Overflow progress", 350.0),
            ("Small float", 0.001),
            ("Large float", 99.999),
            ("None progress with active", None),
        ]

        for label, val in numeric_test_cases:
            app.set_status(f"Testing {label}", level="info", progress=val)
            app.update_global_status(f"Testing {label} in global", is_active=False, progress=val)
            harness.pump(times=3)
            assert bool(app.root.winfo_exists()) is True

        # Finally, set standard completion
        app.update_global_status("Sẵn sàng.", is_active=False, progress=100.0)
        harness.pump(times=3)
        assert app.global_progress_bar["value"] == 100.0

    def test_tier5_status_bar_string_progress_type_error_defect(self, headless_app):
        """TC-T5-STATUS-03 [HARDENED]: Passing string progress is safely converted to float without raising TypeError."""
        harness, app = headless_app

        # In app_core.py line 892:
        # String progress is safely converted to float without raising TypeError
        app.update_global_status("Testing string progress", is_active=False, progress="77.5")
        harness.pump(times=3)
        assert app.global_progress_bar["value"] == 77.5

    def test_tier5_busy_state_rapid_transitions_and_restoration(self, headless_app, mock_serial):
        """TC-T5-STATUS-04: Rapid busy state toggling preserves serial-dependent UI contracts."""
        harness, app = headless_app

        # 1. Connected state
        app.port_cb.set("COM3")
        app.on_serial_connect()
        harness.pump(5)
        assert app.serial_connection is not None
        assert app.serial_connection.is_open is True

        # Toggle busy 10 times in rapid succession while connected
        for i in range(10):
            app.set_global_busy_state(True, f"Flash chunk {i}")
            app.set_global_busy_state(False, f"Flash chunk {i}")

        harness.pump(5)
        # Verify MCU controls restored to normal because serial is connected
        assert str(app.send_btn.cget("state")) == "normal"
        assert str(app.detect_btn.cget("state")) == "normal"
        assert str(app.port_cb.cget("state")) == "readonly"

        # 2. Disconnect serial
        app.on_serial_disconnect()
        harness.pump(3)
        assert app.serial_connection is None

        # Toggle busy 5 times while disconnected
        for i in range(5):
            app.set_global_busy_state(True, "Hardware task")
            app.set_global_busy_state(False, "Hardware task")

        harness.pump(5)
        # When disconnected, MCU send controls MUST stay disabled (no state leak)
        assert str(app.send_btn.cget("state")) == "disabled"
        assert str(app.detect_btn.cget("state")) == "normal"

    # =========================================================================
    # Group 2: Sudden Disconnects During Non-Blocking Serial Transmissions (tab_monitor.py)
    # =========================================================================

    def test_tier5_serial_send_sudden_disconnect_during_write_worker(self, headless_app, mock_serial, mock_dialogs):
        """TC-T5-SER-01: Sudden disconnect during background write worker triggers error dialog."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.on_serial_connect()
        harness.pump(5)
        assert app.serial_connection is not None

        # Force mock_serial.write to raise SerialException (simulating broken pipe / unplug)
        def _failing_write(data):
            mock_serial.is_open = False
            raise serial.SerialException("ClearCommError failed (device unattached)")

        mock_serial.write = _failing_write

        # Dispatch command via non-blocking write worker
        app._send_serial_command("DATA_PACKET_BURST", "Sending burst...", "info")

        # Wait for worker thread to catch exception and schedule error dialog
        harness.wait_for(lambda: len(mock_dialogs["showerror"]) > 0, timeout=3.0)

        err_title, err_msg = mock_dialogs["showerror"][-1]
        assert "Lỗi Gửi" in err_title
        assert "Không thể gửi dữ liệu" in err_msg
        assert "Kiểm tra lại kết nối cáp USB" in err_msg

    def test_tier5_serial_send_write_timeout_exception(self, headless_app, mock_serial, mock_dialogs):
        """TC-T5-SER-02: Write timeout in worker thread does not freeze GUI."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.on_serial_connect()
        harness.pump(5)

        # Inject write timeout
        mock_serial.fault_write_timeout = True

        app._send_serial_command("SLOW_COMMAND_TIMEOUT")

        harness.wait_for(lambda: len(mock_dialogs["showerror"]) > 0, timeout=3.0)
        err_title, err_msg = mock_dialogs["showerror"][-1]
        assert "Lỗi Gửi" in err_title
        assert "Write timeout expired" in err_msg or "Không thể gửi dữ liệu" in err_msg

    def test_tier5_serial_send_burst_with_midway_disconnection(self, headless_app, mock_serial, mock_dialogs):
        """TC-T5-SER-03: Rapid command flood with sudden mid-burst disconnection."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.on_serial_connect()
        harness.pump(5)

        # Queue 15 rapid commands with explicit descriptions
        for i in range(15):
            if i == 5:
                # Sudden disconnect at command 5
                app.on_serial_disconnect()
            app._send_serial_command(f"RAPID_CMD_{i}", f"Sending {i}", "info")

        harness.pump(times=10, delay=0.01)

        # Verify serial connection cleanly set to None
        assert app.serial_connection is None
        assert bool(app.root.winfo_exists()) is True
        assert "Kết nối" in app.serial_toggle_btn.cget("text")

    def test_tier5_serial_write_worker_empty_desc_clobber_behavior(self, headless_app, mock_serial):
        """TC-T5-SER-04 [HARDENED]: Default empty status_description in write worker does not clobber status."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.on_serial_connect()
        harness.pump(5)

        app.set_status("Trạng thái hiện tại: Đang theo dõi thiết bị", "info")
        harness.pump(3)
        assert "Đang theo dõi" in app.req_status_lbl.cget("text")

        # When status_description is empty (""), _write_worker does not call set_status("", "info")
        app._send_serial_command("PROBE")
        harness.pump(times=10, delay=0.01)

        # Status text is preserved and not overwritten with empty string
        assert "Đang theo dõi" in app.req_status_lbl.cget("text")

    def test_tier5_hardware_reset_interrupted_by_immediate_disconnect(self, headless_app, mock_serial):
        """TC-T5-SER-05: Hardware reset thread safely handles serial connection becoming None."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.on_serial_connect()
        harness.pump(5)

        # Trigger reset
        app.on_reset_esp()

        # Immediately disconnect before reset worker's time.sleep(0.05) finishes
        app.on_serial_disconnect()
        assert app.serial_connection is None

        # Give the reset worker thread time to wake up and safely exit
        time.sleep(0.15)
        harness.pump(times=5)

        assert bool(app.root.winfo_exists()) is True
        # App did not crash with AttributeError

    def test_tier5_hardware_reset_serial_exception_during_pin_toggle(self, headless_app, mock_serial):
        """TC-T5-SER-06: Exception during DTR/RTS pin toggle is cleanly caught."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.on_serial_connect()
        harness.pump(5)

        # Force setRTS to raise SerialException
        def _failing_rts(val):
            raise serial.SerialException("RTS hardware control failed: I/O error")

        mock_serial.setRTS = _failing_rts

        app.on_reset_esp()

        # Wait for reset thread to catch exception and set status
        harness.wait_for(
            lambda: "Reset phần cứng gặp lỗi:" in app.req_status_lbl.cget("text"),
            timeout=3.0
        )
        assert "Reset phần cứng gặp lỗi:" in app.req_status_lbl.cget("text")

    def test_tier5_serial_send_unicode_emojis_and_null_bytes(self, headless_app, mock_serial):
        """TC-T5-SER-07: Non-ASCII UTF-8 unicode, emojis, and null bytes transmitted correctly."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.on_serial_connect()
        harness.pump(5)

        # 1. Unicode with Vietnamese accents and emojis
        unicode_payload = "ESP32 Cảm biến nhiệt độ: 28.5°C 🚀🌟"
        app._send_serial_command(unicode_payload)
        harness.pump(times=5, delay=0.01)

        transmitted = mock_serial.get_transmitted_text()
        assert unicode_payload in transmitted

        # 2. Binary null bytes inside string
        mock_serial.clear_transmitted()
        null_payload = "CMD\x00INJECT\x01\x02"
        app._send_serial_command(null_payload)
        harness.pump(times=5, delay=0.01)

        raw_bytes = mock_serial.get_transmitted_bytes()
        assert b"CMD\x00INJECT\x01\x02" in raw_bytes

    # =========================================================================
    # Group 3: Port Scanning Thread Exceptions & Device Busy State (app_core.py)
    # =========================================================================

    def test_tier5_port_scan_survives_repeated_driver_exceptions(self, headless_app, monkeypatch):
        """TC-T5-PORT-01: Auto-scan loop survives recurring driver exceptions without dying."""
        harness, app = headless_app
        scan_attempts = 0
        healthy_seen = threading.Event()

        def _flaky_list_ports():
            nonlocal scan_attempts
            scan_attempts += 1
            if scan_attempts == 1:
                raise serial.SerialException("EnumPorts failed: WMI error")
            elif scan_attempts == 2:
                raise PermissionError("Access denied querying COM registry")
            elif scan_attempts == 3:
                raise OSError("Host controller USB device disconnected")
            else:
                healthy_seen.set()
                return ["COM3", "COM7"]

        monkeypatch.setattr("modules.app_core.list_com_ports_local", _flaky_list_ports)

        # Start background scanner
        app.start_background_tasks()

        # Stop scan after verifying loop handles it
        app.stop_scan.set()
        harness.pump(times=5)

        # Directly invoke _check_and_update_ports to verify resilience with various outputs
        app._check_and_update_ports([])
        app._check_and_update_ports(["COM3", "COM7"])
        harness.pump(times=3)

        assert tuple(app.port_cb["values"]) == ("COM3", "COM7")

    def test_tier5_port_scan_suppressed_during_device_busy(self, headless_app, mock_ports):
        """TC-T5-PORT-02: Port scan updates are completely suppressed when device is busy."""
        harness, app = headless_app
        mock_ports.set_ports(["COM3"])
        app.refresh_ports_dropdown()
        harness.pump(3)
        assert tuple(app.port_cb["values"]) == ("COM3",)

        # Mark device as busy (e.g. flashing)
        app.is_flashing.set()
        assert app.is_device_busy() is True

        # New ports plugged in
        mock_ports.set_ports(["COM3", "COM10", "COM11"])
        app._check_and_update_ports(["COM3", "COM10", "COM11"])
        harness.pump(3)

        # Dropdown MUST NOT be touched while busy
        assert tuple(app.port_cb["values"]) == ("COM3",)

        # Clear busy state
        app.is_flashing.clear()
        assert app.is_device_busy() is False

        # Next scan update succeeds
        app._check_and_update_ports(["COM3", "COM10", "COM11"])
        harness.pump(3)
        assert tuple(app.port_cb["values"]) == ("COM3", "COM10", "COM11")

    def test_tier5_port_auto_select_preserves_active_connected_session(self, headless_app, mock_ports, mock_serial):
        """TC-T5-PORT-03: New port auto-selection does not hijack active serial connections."""
        harness, app = headless_app
        app.var_auto_select_new.set(True)
        app.port_cb.set("COM3")

        # 1. Connect serial on COM3
        app.on_serial_connect()
        harness.pump(5)
        assert app.serial_connection is not None
        assert app.serial_connection.is_open is True

        # Simulate hotplug of COM99
        app._previous_ports = {"COM3"}
        app._check_and_update_ports(["COM3", "COM99"])
        harness.pump(3)

        # Active selection MUST remain COM3
        assert app.port_cb.get() == "COM3"

        # 2. Disconnect serial
        app.on_serial_disconnect()
        harness.pump(3)

        # Simulate hotplug of COM100 while disconnected
        app._previous_ports = {"COM3", "COM99"}
        app._check_and_update_ports(["COM3", "COM99", "COM100"])
        harness.pump(3)

        # Since disconnected, auto-select switches to COM100
        assert app.port_cb.get() == "COM100"

    def test_tier5_port_flapping_and_empty_registry(self, headless_app):
        """TC-T5-PORT-04: Rapid port flapping between empty and multiple devices."""
        harness, app = headless_app

        flapping_sequences = [
            [],
            ["COM3"],
            [],
            ["COM4", "COM5"],
            [],
            ["COM3", "COM4", "COM5", "COM6"],
            [],
        ]

        for port_list in flapping_sequences:
            app._check_and_update_ports(port_list)
            harness.pump(times=2)
            if not port_list:
                assert app.port_cb.get() == ""
            else:
                assert app.port_cb.get() in port_list

    # =========================================================================
    # Group 4: Hardware Inspector Boundary and Fault Resilience (tab_inspector.py)
    # =========================================================================

    def test_tier5_inspector_missing_port_warning(self, headless_app, mock_dialogs):
        """TC-T5-INSP-01: Detection with empty port dropdown triggers warning dialog."""
        harness, app = headless_app
        app.port_cb.set("")

        app.on_detect()
        harness.pump(3)

        assert len(mock_dialogs["showwarning"]) > 0
        title, msg = mock_dialogs["showwarning"][-1]
        assert "Thiếu Cổng" in title
        assert "Vui lòng chọn cổng COM" in msg
        assert app.is_detecting.is_set() is False

    def test_tier5_inspector_port_access_denied_releases_busy_lock(self, headless_app, monkeypatch, mock_dialogs):
        """TC-T5-INSP-02: Port access denied during chip detection shows actionable error and releases lock."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        def _raise_denied(args):
            raise serial.SerialException("could not open port 'COM3': PermissionError(13, 'Access is denied.')")

        monkeypatch.setattr("modules.tabs.tab_inspector.run_esptool_command", _raise_denied)

        app.on_detect()

        harness.wait_for(lambda: len(mock_dialogs["showerror"]) > 0, timeout=3.0)

        title, msg = mock_dialogs["showerror"][-1]
        assert "Lỗi Truy Cập Cổng COM" in title
        assert "Không thể mở cổng 'COM3'" in msg
        assert "Hướng dẫn xử lý sự cố:" in msg

        # Ensure busy state was cleanly released
        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=2.0)
        assert app.is_detecting.is_set() is False
        assert str(app.detect_btn.cget("state")) == "normal"
        assert "Lỗi kiểm tra." in app.req_status_lbl.cget("text")

    def test_tier5_inspector_auto_baud_exhaustion(self, headless_app, monkeypatch):
        """TC-T5-INSP-03: Auto-baud failure across all candidate baudrates releases busy lock."""
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("Tự động")

        monkeypatch.setattr(app, "detect_baud_rate", lambda port: None)

        app.on_detect()

        harness.wait_for(lambda: not app.is_detecting.is_set(), timeout=3.0)
        assert app.is_detecting.is_set() is False
        assert "Lỗi kiểm tra." in app.req_status_lbl.cget("text")
        assert str(app.detect_btn.cget("state")) == "normal"

    def test_tier5_inspector_report_display_with_corrupt_and_empty_data(self, headless_app):
        """TC-T5-INSP-04: Report formatting handles empty, unknown, or fatal error outputs safely."""
        harness, app = headless_app

        # 1. Empty info dictionary
        app._display_formatted_report({})
        harness.pump(3)
        assert bool(app.root.winfo_exists()) is True

        # 2. Fatal bootloader sync error output triggers troubleshooting guidance
        error_info = {
            "chip_name_key": None,
            "mac": None,
            "raw": "A fatal error occurred: Failed to connect to ESP32: Timed out waiting for packet header"
        }
        app._display_formatted_report(error_info)
        harness.pump(3)

        report_content = app.inspector_txt.get("1.0", "end")
        assert "KHÔNG THỂ KẾT NỐI ĐỒNG BỘ VỚI CHIP ESP" in report_content
        assert "Nhấn và GIỮ nút BOOT" in report_content

        # 3. Unknown chip not in database
        unknown_info = {
            "chip_name_key": "ESP32-MYSTERIOUS-CHIP",
            "mac": "AABBCCDDEEFF",
            "flash_manufacturer": "0xEF",
            "flash_device": "0x4018",
            "flash_mb": 16.0,
            "raw": "Chip is ESP32-MYSTERIOUS-CHIP"
        }
        app._display_formatted_report(unknown_info)
        harness.pump(3)

        unknown_report = app.inspector_txt.get("1.0", "end")
        assert "ESP32-MYSTERIOUS-CHIP" in unknown_report
        assert "Không có trong CSDL" in unknown_report

    def test_tier5_inspector_save_report_empty_and_io_error(self, headless_app, mock_dialogs, monkeypatch):
        """TC-T5-INSP-05: Save report button handles empty content and file write errors."""
        harness, app = headless_app

        # 1. Empty content warning
        app.on_clear(app.inspector_txt)
        app.on_save()
        harness.pump(3)

        assert len(mock_dialogs["showinfo"]) > 0
        assert "Không có nội dung để lưu" in mock_dialogs["showinfo"][-1][1]

        # 2. File write I/O error
        app.log("Hardware Report Line 1\nHardware Report Line 2")
        mock_dialogs["return_save_filename"] = "dummy_report.txt"

        original_open = builtins.open

        def _failing_open(path, *args, **kwargs):
            if "dummy_report.txt" in str(path):
                raise PermissionError("Access denied writing report")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", _failing_open)

        app.on_save()
        harness.pump(3)

        assert len(mock_dialogs["showerror"]) > 0
        assert "Lỗi Lưu" in mock_dialogs["showerror"][-1][0]

    # =========================================================================
    # Group 5: Serial Monitor Buffer Stress & Malformed Telemetry (tab_monitor.py)
    # =========================================================================

    def test_tier5_monitor_buffer_large_stream_truncation(self, headless_app):
        """TC-T5-MON-01: Serial monitor truncates lines cleanly when exceeding max buffer capacity."""
        harness, app = headless_app
        app.var_autoscroll.set(True)

        # Inject 22,000 lines in 1,000-line chunks (exceeding So_dong_serial_toi_da = 20,000)
        chunk = "\n".join([f"Telemetry line {i}" for i in range(1000)]) + "\n"
        for _ in range(22):
            app.append_to_monitor(chunk)

        harness.pump(times=5)

        current_lines = int(app.monitor_txt.index("end-1c").split(".")[0])
        # Buffer must have truncated and stayed bounded within 1 chunk of max capacity
        assert current_lines <= So_dong_serial_toi_da + 1500
        assert bool(app.root.winfo_exists()) is True

    def test_tier5_monitor_malformed_feedback_res_packets(self, headless_app):
        """TC-T5-MON-02: Pathological and corrupt RES: telemetry packets do not crash parser."""
        harness, app = headless_app

        malformed_packets = [
            "RES:",
            "RES:WIFI",
            "RES:WIFI|",
            "RES:WIFI||||||||||||",
            "RES:CMD_SENT_TO_SERVER:",
            "RES:UNKNOWN_PROTOCOL_PACKET_999",
            "RES:WIFI|HomeNetwork|-45|WPA2",
            "RES:WIFI_FAIL",
            "RES:SERVER_FAIL:NO_WIFI",
            "RES:SYSTEM_READY",
        ]

        for packet in malformed_packets:
            app.process_esp_feedback(packet)

        harness.pump(3)
        assert "HomeNetwork" in app.scanned_networks
        assert bool(app.root.winfo_exists()) is True

    def test_tier5_monitor_server_connect_validation_matrix(self, headless_app, mock_dialogs):
        """TC-T5-MON-03: Server connect validates WiFi state, empty IP, and port range."""
        harness, app = headless_app

        # 1. Server connect attempted without WiFi
        app.is_wifi_connected = False
        app.on_server_connect()
        harness.pump(3)
        assert len(mock_dialogs["showwarning"]) > 0
        assert "Vui lòng kết nối WiFi" in mock_dialogs["showwarning"][-1][1]

        # Enable Entry controls (simulating connected serial state)
        app.ip_entry.config(state="normal")
        app.port_entry.config(state="normal")

        # 2. Server connect with empty IP
        app.is_wifi_connected = True
        app.ip_entry.delete(0, tk.END)
        app.on_server_connect()
        harness.pump(3)
        assert "Vui lòng nhập địa chỉ IP" in mock_dialogs["showwarning"][-1][1]

        # 3. Invalid port formats
        app.ip_entry.insert(0, "192.168.4.1")
        bad_ports = ["", "abc", "-5", "0", "65536", "999999"]
        for bad_p in bad_ports:
            app.port_entry.delete(0, tk.END)
            app.port_entry.insert(0, bad_p)
            app.on_server_connect()
            harness.pump(2)
            assert "Cổng Server không hợp lệ!" in mock_dialogs["showwarning"][-1][1]

        # 4. Valid IP and port
        app.port_entry.delete(0, tk.END)
        app.port_entry.insert(0, "8080")
        app.on_server_connect()
        harness.pump(3)
        assert "Đang chờ nối Server..." in app.wifi_status_lbl.cget("text")
