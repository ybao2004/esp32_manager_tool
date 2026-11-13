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


_QAPP_REF = None


def _ensure_qapp():
    global _QAPP_REF
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    _QAPP_REF = app
    return app


def test_icon_aliases_resolve_to_valid_icons():
    _ensure_qapp()
    from modules.ui.icons import get_icon
    for alias in (
        "chip", "trash", "folder", "window_console",
        "arrow_undo", "arrow_redo", "checkmark", "router",
    ):
        icon = get_icon(alias, "#212121", 20)
        assert not icon.isNull(), f"Expected non-null icon for alias {alias!r}"


def test_dialogs_service_askstring_and_non_qwidget_parent():
    _ensure_qapp()
    from PyQt6.QtWidgets import QWidget
    from modules.ui import dialogs_service
    fake_parent = SimpleNamespace()
    assert dialogs_service._valid_parent(fake_parent) is None
    real_widget = QWidget()
    assert dialogs_service._valid_parent(real_widget) is real_widget

    with patch("modules.ui.dialogs_service.QInputDialog.getText", return_value=("custom_val", True)) as mock_get:
        res = dialogs_service.askstring("Title", "Prompt", initialvalue="init", parent=fake_parent)
    assert res == "custom_val"
    assert mock_get.call_args.args[0] is None


def test_erase_region_dialog_and_show_erase_nvs(headless_app):
    _, app = headless_app
    from modules.ui.dialogs.erase_region_dialog import EraseRegionDialog

    dlg = EraseRegionDialog(SimpleNamespace(), "COM3")
    assert dlg.entry_offset.text() == "0x9000"
    assert dlg.entry_size.text() == "0x6000"
    dlg._on_erase()
    assert dlg.offset == 0x9000
    assert dlg.size == 0x6000
    assert dlg.result == (0x9000, 0x6000)

    with patch("modules.ui.dialogs.erase_region_dialog.EraseRegionDialog.exec", return_value=1), \
         patch("modules.tabs.tab_flasher.messagebox.askyesno", return_value=False):
        app._show_erase_nvs_dialog("COM3")


def test_preset_dialog_result_and_partition_to_bin(headless_app):
    _, app = headless_app
    from modules.ui.dialogs.preset_dialog import PresetSelectorDialog
    from modules.partition.partition_model import PartitionEntry, PartitionTable

    dlg = PresetSelectorDialog(SimpleNamespace(), is_dark_mode=True)
    dlg._on_apply()
    assert dlg.selected_preset is not None
    assert dlg.result is dlg.selected_preset

    table = PartitionTable()
    table.add_entry(PartitionEntry(name="nvs", type_str="data", subtype_str="nvs", offset=0x9000, size=0x5000))
    assert table.to_bin() == table.to_binary()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_bin = str(Path(tmpdir, "partitions.bin"))
        app.table = table
        app.current_partition_file_path = out_bin
        app._action_save()
        assert Path(out_bin).read_bytes() == table.to_binary()


def test_disk_map_mouse_callbacks_invoked():
    _ensure_qapp()
    from PyQt6.QtCore import QPointF, Qt, QEvent
    from PyQt6.QtGui import QMouseEvent
    from modules.partition.partition_model import PartitionEntry
    from modules.ui.widgets.disk_map import DiskMapWidget

    widget = DiskMapWidget()
    widget.resize(400, 80)
    part = PartitionEntry(name="app0", type_str="app", subtype_str="ota_0", offset=0x10000, size=0x100000)
    unalloc = PartitionEntry(name="Free", type_str="data", subtype_str="", offset=0x110000, size=0x100000, is_unallocated=True)
    widget.set_data([part, unalloc], flash_size=0x400000)
    widget.grab()

    on_select = Mock()
    on_unalloc = Mock()
    on_ctx = Mock()
    widget.on_select_entry = on_select
    widget.on_unallocated_click = on_unalloc
    widget.on_context_action = on_ctx

    assert len(widget._rendered_blocks) >= 2
    x1_0, y1_0, x2_0, y2_0, e0 = widget._rendered_blocks[0]
    pos0 = QPointF((x1_0 + x2_0) / 2.0, (y1_0 + y2_0) / 2.0)
    evt_left = QMouseEvent(
        QEvent.Type.MouseButtonPress, pos0, pos0,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(evt_left)
    on_select.assert_called_with(e0)

    evt_right = QMouseEvent(
        QEvent.Type.MouseButtonPress, pos0, pos0,
        Qt.MouseButton.RightButton, Qt.MouseButton.RightButton, Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(evt_right)
    assert on_ctx.called and on_ctx.call_args.args[0] == "full_context_menu"

    x1_1, y1_1, x2_1, y2_1, _ = widget._rendered_blocks[1]
    pos1 = QPointF((x1_1 + x2_1) / 2.0, (y1_1 + y2_1) / 2.0)
    evt_unalloc = QMouseEvent(
        QEvent.Type.MouseButtonPress, pos1, pos1,
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    widget.mousePressEvent(evt_unalloc)
    on_unalloc.assert_called_with(unalloc.offset, unalloc.size)


def test_backup_page_shared_vars_and_mode_sync(headless_app):
    _, app = headless_app
    assert app.var_backup_smart_trim is app.page_backup.var_backup_smart_trim
    assert app.var_clone_erase_first is app.page_backup.var_clone_erase_first
    assert app.var_clone_source_mode is app.page_backup.var_clone_source_mode

    app.var_clone_source_mode.set("saved_folder")
    assert app.page_backup.rb_folder.isChecked()
    assert not app.page_backup.rb_live.isChecked()

    app.var_clone_source_mode.set("live_board")
    assert app.page_backup.rb_live.isChecked()
    assert not app.page_backup.rb_folder.isChecked()


def test_settings_page_fkeys_save_and_restore_defaults(headless_app):
    _, app = headless_app
    app.page_settings._f_entries[0][0].setText("CUSTOM_LBL")
    app.page_settings._f_entries[0][1].setText("CUSTOM_CMD")
    app.page_settings._on_save_settings()
    assert app.control_labels[1] == "CUSTOM_LBL"
    assert app.control_commands[1] == "CUSTOM_CMD"

    app.page_settings._on_restore_defaults()
    assert app.control_labels[1] != "CUSTOM_LBL"


def test_monitor_history_and_wifi_autofill(headless_app):
    _, app = headless_app
    app.serial_connection = SimpleNamespace(is_open=True)
    app._send_serial_command = Mock()
    app.serial_input.delete("1.0", "end")
    app.serial_input.insert("1.0", "PING_TEST")
    app.on_serial_send()
    assert "PING_TEST" in app.page_monitor.cmd_history

    app.saved_wifi_credentials = {"LabWiFi": "SecretPass123"}
    app.wifi_cb.set("LabWiFi")
    assert app.wifi_pass_entry.get() == "SecretPass123"


def test_inspector_page_mac_oui_and_raw_log_toggle(headless_app):
    _, app = headless_app
    info = {
        "chip_line": "ESP32-S3 (QFN56)",
        "features_line": "WiFi, BLE",
        "flash_mb": 8.0,
        "flash_device": "4017",
        "psram_mb": 2,
    }
    app.page_inspector.update_from_parsed_info(info, None, "Winbond", "2 MB", "24:0A:C4:11:22:33", [])
    assert "Espressif" in app.page_inspector.kpi_mac.lbl_sub.text()

    app._last_inspected_info = dict(info)
    with patch.object(app, "_rerender_inspector_report") as spy:
        app.page_inspector.cb_raw_log.setChecked(not app.page_inspector.cb_raw_log.isChecked())
        assert spy.called


if __name__ == '__main__':
    unittest.main()
