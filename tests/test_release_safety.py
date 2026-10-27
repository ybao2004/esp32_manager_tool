import tempfile
import threading
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from modules.binary_scanner import scan_project_bin_files
from modules.tabs.tab_monitor import MonitorTabMixin
from modules.app_core import InspectorApp
from modules.dialogs.layout_util import fit_dialog


class ReleaseSafetyTests(unittest.TestCase):
    def test_dialog_fits_requested_content_instead_of_fixed_height(self):
        dialog = Mock()
        dialog.winfo_screenwidth.return_value = 1920
        dialog.winfo_screenheight.return_value = 1080
        dialog.winfo_reqwidth.return_value = 600
        dialog.winfo_reqheight.return_value = 550
        parent = Mock()
        parent.winfo_x.return_value = 20
        parent.winfo_y.return_value = 20
        parent.winfo_width.return_value = 1200
        parent.winfo_height.return_value = 800
        fit_dialog(dialog, parent, 440, 235)
        dialog.minsize.assert_called_once_with(600, 550)
        dialog.resizable.assert_called_once_with(True, True)
        dialog.geometry.assert_called_once_with('600x550+320+145')

    def test_unknown_files_and_merged_images_are_not_auto_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename in ('firmware.bin', 'firmware_merged_0x0.bin', 'littlefs.bin', 'backup.bin'):
                Path(directory, filename).write_bytes(b'x' * 32)
            items = scan_project_bin_files(directory)
            self.assertEqual([Path(x['path']).name for x in items if x['enabled']], ['firmware.bin'])
            filesystem = next(x for x in items if Path(x['path']).name == 'littlefs.bin')
            self.assertEqual(filesystem['offset'], '')

    def test_old_reader_cannot_disconnect_new_connection(self):
        old, new = object(), object()
        app = SimpleNamespace(serial_connection=new, on_serial_disconnect=Mock())
        with patch('modules.tabs.tab_monitor.messagebox.showerror') as error:
            MonitorTabMixin._serial_session_failed(app, old, threading.Event())
        app.on_serial_disconnect.assert_not_called()
        error.assert_not_called()

    def test_queued_old_feedback_is_dropped(self):
        old, new = object(), object()
        app = SimpleNamespace(serial_connection=new, append_to_monitor=Mock(), process_esp_feedback=Mock())
        MonitorTabMixin._deliver_serial_chunk(app, old, threading.Event(), 'old', ['RES:WIFI_CONNECTED'])
        app.append_to_monitor.assert_not_called()
        app.process_esp_feedback.assert_not_called()

    def test_cancelled_session_drops_queued_output(self):
        connection = object()
        stop = threading.Event()
        stop.set()
        app = SimpleNamespace(serial_connection=connection, append_to_monitor=Mock(), process_esp_feedback=Mock())
        MonitorTabMixin._deliver_serial_chunk(app, connection, stop, 'old', [])
        app.append_to_monitor.assert_not_called()

    def test_current_session_delivers_text_and_feedback(self):
        connection = object()
        app = SimpleNamespace(serial_connection=connection, append_to_monitor=Mock(), process_esp_feedback=Mock())
        MonitorTabMixin._deliver_serial_chunk(app, connection, threading.Event(), 'hello', ['RES:SYSTEM_READY'])
        app.append_to_monitor.assert_called_once_with('hello')
        app.process_esp_feedback.assert_called_once_with('RES:SYSTEM_READY')

    def test_close_during_flashing_does_not_destroy_window(self):
        app = SimpleNamespace(root=Mock(), save_config=Mock(), is_flashing=threading.Event(),
                              is_detecting=threading.Event(), is_connecting=False)
        app.is_flashing.set()
        with patch('modules.app_core.messagebox.showwarning'):
            InspectorApp.on_closing(app)
        app.root.destroy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
