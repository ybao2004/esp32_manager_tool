import tkinter as tk
from tkinter import ttk
import unittest
from unittest.mock import Mock, patch

from modules.app_core import InspectorApp
from modules.help_content import quick_start_text, about_features_text


class AppTabsAndFeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = tk.Tk()
            cls.root.withdraw()
        except tk.TclError as exc:
            raise unittest.SkipTest(f"Tcl/Tk unavailable: {exc}")

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def test_app_initializes_exactly_four_tabs(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            self.assertEqual(app.notebook.index('end'), 4)
            tab_texts = [app.notebook.tab(i, 'text').strip() for i in range(4)]
            self.assertEqual(tab_texts, [
                'Kiểm tra Phần cứng',
                'Serial Monitor & Điều khiển',
                'Nạp Flash Firmware (.bin)',
                'Phân vùng Bộ nhớ (Partition Wizard)'
            ])
            self.assertTrue(hasattr(app, 'partition_tab'))
            self.assertTrue(hasattr(app, 'disk_map'))
            self.assertFalse(hasattr(app, 'packager_tab'))
            self.assertFalse(hasattr(app, 'compiler_tab'))
            self.assertFalse(hasattr(app, 'btn_pack_project'))

    def test_help_content_excludes_removed_features(self):
        qs = quick_start_text().lower()
        about = about_features_text().lower()
        for forbidden in ['đóng gói firmware', 'arduino-cli']:
            self.assertNotIn(forbidden, qs)
            self.assertNotIn(forbidden, about)


if __name__ == '__main__':
    unittest.main()
