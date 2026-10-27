import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from modules.binary_scanner import scan_project_bin_files
from modules.app_core import InspectorApp
from modules.tabs.tab_flasher import FlasherTabMixin
from modules.tabs.tab_monitor import MonitorTabMixin


class AuditRegressions(unittest.TestCase):
    def test_scan_selects_one_build_despite_crossed_timestamps(self):
        with tempfile.TemporaryDirectory() as directory:
            for folder, name, stamp in (
                ('A', 'bootloader.bin', 30), ('A', 'firmware.bin', 10),
                ('B', 'bootloader.bin', 10), ('B', 'firmware.bin', 30),
            ):
                path = Path(directory, folder, name)
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b'x' * 32)
                os.utime(path, (stamp, stamp))
            selected = [item for item in scan_project_bin_files(directory) if item['enabled']]
            self.assertEqual(len(selected), 2)
            self.assertEqual(len({Path(item['path']).parent for item in selected}), 1)

    def test_missing_manifest_member_aborts_scan(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'bootloader.bin').write_bytes(b'x' * 32)
            Path(directory, 'flasher_args.json').write_text(json.dumps({
                'flash_files': {'0x1000': 'bootloader.bin', '0x10000': 'missing.bin'},
            }), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'missing.bin'):
                scan_project_bin_files(directory)

    def test_malformed_manifest_does_not_fall_back_to_guesses(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, 'firmware.bin').write_bytes(b'x' * 32)
            Path(directory, 'flasher_args.json').write_text('{broken', encoding='utf-8')
            with self.assertRaises(ValueError):
                scan_project_bin_files(directory)

    def test_lost_wifi_clears_server_state(self):
        for response in ('RES:WIFI_DISCONNECTED', 'RES:WIFI_FAIL'):
            app = SimpleNamespace(is_dark_mode=False, is_wifi_connected=True,
                                  is_server_connected=True, btn_connect_wifi=Mock(),
                                  btn_connect_server=Mock(), wifi_status_lbl=Mock(), set_status=Mock())
            MonitorTabMixin.process_esp_feedback(app, response)
            self.assertFalse(app.is_wifi_connected)
            self.assertFalse(app.is_server_connected)
            app.btn_connect_server.config.assert_called_with(text='Kết nối Server')

    def test_password_whitespace_is_preserved_in_command(self):
        app = SimpleNamespace(wifi_cb=Mock(), wifi_pass_entry=Mock(), root=Mock(),
                              is_dark_mode=False, wifi_status_lbl=Mock(), _send_serial_command=Mock())
        app.wifi_cb.get.return_value = 'network'
        app.wifi_pass_entry.get.return_value = ' secret '
        MonitorTabMixin.on_wifi_connect(app)
        self.assertEqual(app._send_serial_command.call_args.args[0], 'SET_WIFI|network| secret ')

    def test_close_keeps_window_alive_during_device_operation(self):
        for active in ('is_flashing', 'is_detecting'):
            app = SimpleNamespace(root=Mock(), save_config=Mock(), is_connecting=False,
                                  is_flashing=threading.Event(), is_detecting=threading.Event())
            getattr(app, active).set()
            with patch('modules.app_core.messagebox.showwarning'):
                InspectorApp.on_closing(app)
            app.root.destroy.assert_not_called()
            app.save_config.assert_not_called()

    def test_erase_reserves_device_before_delayed_start(self):
        app = SimpleNamespace(port_cb=Mock(), root=Mock(), is_flashing=threading.Event(),
                              is_detecting=threading.Event(), is_connecting=False,
                              serial_connection=SimpleNamespace(is_open=True),
                              on_serial_disconnect=Mock(), _set_flash_ui_state=Mock())
        app.port_cb.get.return_value = 'COM3'
        with patch('modules.tabs.tab_flasher.messagebox.askyesno', return_value=True):
            FlasherTabMixin.on_erase_flash_click(app)
        self.assertTrue(app.is_flashing.is_set())
        app._set_flash_ui_state.assert_called_with('disabled')
        self.assertEqual(app.root.after.call_args.args[0], 400)


if __name__ == '__main__':
    unittest.main()
