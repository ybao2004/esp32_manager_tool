import gc
import os
import shutil
import tempfile
from modules import qt_toolkit as tk
from modules.qt_toolkit import ttk
import unittest
from unittest.mock import Mock, patch

from modules.app_core import InspectorApp
from modules.help_content import quick_start_text, about_features_text
from tests.mock_hardware.app_harness import HeadlessAppHarness, _global_after_queue


class AppTabsAndFeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.root = HeadlessAppHarness.get_shared_root()
        except Exception as exc:
            raise unittest.SkipTest(f"Tcl/Tk unavailable: {exc}")

        cls.temp_dir = tempfile.mkdtemp()
        cls.fake_config = os.path.join(cls.temp_dir, "test_settings.json")
        cls.patcher_config = patch("modules.app_core.CONFIG_FILE", cls.fake_config)
        cls.patcher_config.start()
        cls.patcher_ports = patch("modules.serial_util.list_ports.comports", return_value=[])
        cls.patcher_ports.start()

    def tearDown(self):
        """Clean up widgets, cancel pending Tcl timers, and drain queues after each test."""
        self._cleanup_root(self.root)

    @classmethod
    def tearDownClass(cls):
        """Final cleanup of shared root, stopping patchers, and removing temp dir."""
        cls._cleanup_root(cls.root)
        try:
            cls.patcher_config.stop()
        except Exception:
            pass
        try:
            cls.patcher_ports.stop()
        except Exception:
            pass
        if os.path.exists(cls.temp_dir):
            try:
                shutil.rmtree(cls.temp_dir, ignore_errors=True)
            except Exception:
                pass
        gc.collect()

    @staticmethod
    def _cleanup_root(root):
        for child in list(root.winfo_children()):
            try:
                child.destroy()
            except Exception:
                pass
        try:
            if root.winfo_exists():
                timers = root.tk.call('after', 'info')
                for t in root.tk.splitlist(timers):
                    try:
                        root.after_cancel(t)
                    except Exception:
                        pass
        except Exception:
            pass
        while not _global_after_queue.empty():
            try:
                _global_after_queue.get_nowait()
            except Exception:
                break
        try:
            root.config(menu="")
        except Exception:
            pass
        gc.collect()
        try:
            if root.winfo_exists():
                root.update_idletasks()
                root.update()
        except Exception:
            pass

    def test_app_initializes_exactly_four_tabs(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            self.assertEqual(app.notebook.index('end'), 5)
            tab_texts = [app.notebook.tab(i, 'text').strip() for i in range(5)]
            self.assertEqual(tab_texts, [
                'Kiểm tra Phần cứng',
                'Serial Monitor & Điều khiển',
                'Nạp Flash Firmware (.bin)',
                'Phân vùng Bộ nhớ (Partition Wizard)',
                'Sao lưu & Nhân bản (Backup / Clone)'
            ])
            self.assertTrue(hasattr(app, 'partition_tab'))
            self.assertTrue(hasattr(app, 'backup_tab'))
            self.assertTrue(hasattr(app, 'disk_map'))
            self.assertTrue(hasattr(app, 'backup_disk_map'))
            self.assertFalse(hasattr(app, 'packager_tab'))
            self.assertFalse(hasattr(app, 'compiler_tab'))
            self.assertFalse(hasattr(app, 'btn_pack_project'))

    def test_partition_tab_columns_and_row_controls(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            cols = app.part_tree["columns"]
            self.assertEqual(cols[0], "stt")
            self.assertEqual(cols[1], "name")
            self.assertEqual(cols[2], "type")
            self.assertEqual(cols[3], "subtype")

            # Kiểm tra các hàng hiển thị số thứ tự sạch sẽ trong cột STT
            children = app.part_tree.get_children()
            self.assertGreater(len(children), 0)
            first_row_vals = app.part_tree.item(children[0], "values")
            self.assertEqual(first_row_vals[0], "#1")
            self.assertEqual(first_row_vals[1], "nvs")

            # Kiểm tra chèn dòng mới sau dòng đầu tiên
            initial_count = len(app.table.entries)
            app._action_add_after_row(children[0])
            self.assertEqual(len(app.table.entries), initial_count + 1)
            new_child = app.part_tree.get_children()[1]
            new_name = app._get_entry_name_from_iid(new_child)
            self.assertTrue(new_name.startswith("part_"))

            # Kiểm tra xóa dòng vừa chèn (mock messagebox.askyesno -> True)
            with patch('modules.qt_toolkit.messagebox.askyesno', return_value=True):
                app._action_delete_by_row(new_child)
            self.assertEqual(len(app.table.entries), initial_count)

    def test_partition_context_menu_has_only_column_options(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            entry = app.table.entries[0]
            event = Mock(x=10, y=10, x_root=100, y_root=100)
            row_id = app.part_tree.get_children()[0]

            for col in ['#2', '#3', '#4', '#5', '#6', '#7']:
                created_menus = []
                real_init = tk.Menu.__init__

                def capture_init(menu_inst, *args, **kwargs):
                    real_init(menu_inst, *args, **kwargs)
                    created_menus.append(menu_inst)

                with patch.object(tk.Menu, '__init__', capture_init), patch('modules.qt_toolkit.Menu.tk_popup'):
                    app._show_column_context_menu(event, entry, col, row_id)
                    self.assertGreater(len(created_menus), 0)
                    menu = created_menus[-1]
                    last_index = menu.index('end')
                    labels = [menu.entrycget(i, 'label') for i in range(last_index + 1) if menu.type(i) == 'command']
                    # Không có các lựa chọn mở hộp thoại chi tiết hoặc phần cứng ở cuối
                    for bad_str in ['Mở hộp thoại chi tiết', 'Sao lưu phân vùng', 'Xóa trắng', 'Nạp file']:
                        self.assertFalse(any(bad_str in lbl for lbl in labels), f"Phát hiện tùy chọn bị cấm '{bad_str}' trong cột {col}")
                    self.assertTrue(any('Chèn phân vùng mới sau dòng này' in lbl for lbl in labels), f"Thiếu tùy chọn chèn phân vùng trong cột {col}")
                    self.assertTrue(any('Xóa phân vùng' in lbl for lbl in labels), f"Thiếu tùy chọn xóa phân vùng trong cột {col}")

                    # Không có icon hoặc dấu bullet phía trước các lựa chọn
                    for lbl in labels:
                        self.assertFalse(lbl.startswith("•"), f"Phát hiện dấu bullet trong label: {lbl}")
                        for icon in ['📍', '⚡', '✏️', '➕', '🗑️', '⚙️', '🏷️', '📂', '💾', '🚩', '📋', '📌']:
                            self.assertNotIn(icon, lbl, f"Phát hiện icon '{icon}' trong label: {lbl}")

                    if col == '#7':
                        self.assertTrue(any('encrypted, readonly' in lbl for lbl in labels), "Thiếu lựa chọn cả 2 cờ trong cột Flags")

    def test_partition_double_click_opens_dialog(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            first_row = app.part_tree.get_children()[0]
            event = Mock(y=10)

            with patch.object(app, '_action_edit_selected') as mock_edit:
                with patch.object(app.part_tree, 'identify_row', return_value=first_row):
                    app._on_tree_double_click(event)
                    mock_edit.assert_called_once()

            with patch.object(app, '_action_add_partition') as mock_add:
                with patch.object(app.part_tree, 'identify_row', return_value=getattr(app, '_add_row_iid', '__add_row__')):
                    app._on_tree_double_click(event)
                    mock_add.assert_called_once()

    def test_partition_hw_logging_routes_to_monitor(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            with patch.object(app, 'append_to_monitor') as mock_append:
                app._log_partition_hw("NẠP BẢNG PHÂN VÙNG THÀNH CÔNG")
                mock_append.assert_called_once_with("[PARTITION_HW] NẠP BẢNG PHÂN VÙNG THÀNH CÔNG")

    def test_bluetooth_ports_filtered_by_default(self):
        from modules.serial_util import is_bluetooth_port
        mock_bt_port = Mock(description="Standard Serial over Bluetooth link (COM5)", hwid="BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000")
        mock_usb_port = Mock(description="Silicon Labs CP210x USB to UART Bridge (COM3)", hwid="USB\\VID_10C4&PID_EA60\\0001")
        self.assertTrue(is_bluetooth_port(mock_bt_port))
        self.assertFalse(is_bluetooth_port(mock_usb_port))

        with patch('modules.app_core.set_window_icon_native'), \
             patch('modules.app_core.get_bluetooth_com_ports', return_value=["COM5"]):
            app = InspectorApp(self.root)
            self.assertTrue(app.var_hide_bt_ports.get())
            self.assertEqual(app.ignored_com_ports, [])
            # Khi tích chọn ẩn Bluetooth (mặc định), COM5 tự động bị lọc dù ignored_com_ports rỗng
            filtered = app.filter_ignored_ports(["COM3", "COM5", "COM8"])
            self.assertEqual(filtered, ["COM3", "COM8"])
            # Khi bỏ tích ẩn Bluetooth, COM5 được hiển thị trở lại
            app.var_hide_bt_ports.set(False)
            filtered_unhidden = app.filter_ignored_ports(["COM3", "COM5", "COM8"])
            self.assertEqual(filtered_unhidden, ["COM3", "COM5", "COM8"])

    def test_inspector_heap_rows_and_determinate_progress(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            self.assertEqual(str(app.global_progress_bar.cget("mode")), "determinate")
            self.assertEqual(app.global_progress_pct_lbl.cget("text"), "0%")
            app._display_formatted_report({
                "chip_name_key": "ESP32-P4",
                "chip_line": "ESP32-P4 (revision v3.2)",
                "heap_regions": [
                    "DRAM: 6 KiB (@ 0x3FFAE6E0)",
                    "IRAM: 32 KiB (@ 0x40098000)",
                ],
            })
            content = app.inspector_txt.get("1.0", "end")
            self.assertIn("Vùng nhớ Heap #1:", content)
            self.assertIn("Vùng nhớ Heap #2:", content)
            self.assertGreater(int(app.inspector_txt.tag_cget("kv_hanging", "lmargin2") or 0), 0)

    def test_help_content_excludes_removed_features(self):
        qs = quick_start_text().lower()
        about = about_features_text().lower()
        for forbidden in ['đóng gói firmware', 'arduino-cli']:
            self.assertNotIn(forbidden, qs)
            self.assertNotIn(forbidden, about)

    def test_main_menu_and_top_controls_layout(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            # 1. Main menu bar chuẩn 5 mục: Tệp, Công cụ, Theme, Cài đặt, Giới thiệu
            self.assertTrue(hasattr(app, 'main_menu'))
            self.assertIsNotNone(app.main_menu)
            top_labels = [app.main_menu.entrycget(i, 'label') for i in range(app.main_menu.index('end') + 1) if app.main_menu.type(i) != 'tearoff']
            self.assertEqual(top_labels, ["Tệp", "Công cụ", "Theme", "Cài đặt", "Giới thiệu"])

            # Kiểm tra nội dung menu Tệp
            file_menu = app.main_menu.nametowidget(app.main_menu.entrycget(0, 'menu'))
            file_labels = [file_menu.entrycget(i, 'label') for i in range(file_menu.index('end') + 1) if file_menu.type(i) != 'tearoff' and file_menu.type(i) != 'separator']
            self.assertIn("Tạo mới", file_labels)
            self.assertIn("Mở...", file_labels)
            self.assertIn("Nhập...", file_labels)
            self.assertIn("Lưu", file_labels)
            self.assertIn("Lưu như...", file_labels)
            self.assertIn("Thoát", file_labels)

            # Kiểm tra nội dung menu Công cụ
            tools_menu = app.main_menu.nametowidget(app.main_menu.entrycget(1, 'menu'))
            tools_labels = [tools_menu.entrycget(i, 'label') for i in range(tools_menu.index('end') + 1) if tools_menu.type(i) != 'tearoff' and tools_menu.type(i) != 'separator']
            self.assertIn("Kiểm tra chip ESP", tools_labels)
            self.assertIn("Reset ESP", tools_labels)
            self.assertIn("Xóa toàn bộ Flash (Erase Chip)", tools_labels)
            self.assertIn("Kiểm tra cập nhật phần mềm...", tools_labels)

            # Kiểm tra nội dung menu Theme
            theme_menu = app.main_menu.nametowidget(app.main_menu.entrycget(2, 'menu'))
            theme_labels = [theme_menu.entrycget(i, 'label') for i in range(theme_menu.index('end') + 1) if theme_menu.type(i) != 'tearoff']
            self.assertIn("Giao diện Tối (Dark)", theme_labels)
            self.assertIn("Giao diện Sáng (Light)", theme_labels)

            # Kiểm tra các phương thức mở dialog độc lập
            self.assertTrue(hasattr(app, 'open_settings_dialog'))
            self.assertTrue(hasattr(app, 'open_about_dialog'))
            self.assertTrue(hasattr(app, 'open_update_dialog'))

            # 2. Controls frame is flat ttk.Frame, not LabelFrame
            self.assertIsInstance(app.controls_frame, ttk.Frame)
            self.assertNotIsInstance(app.controls_frame, ttk.LabelFrame)

            # 3. clear_monitor_btn is located in tab_monitor
            self.assertTrue(hasattr(app, 'clear_monitor_btn'))
            self.assertEqual(app.clear_monitor_btn.cget('text'), "Xóa màn hình")

            # 4. Chip default is "(Chưa chọn)" and toolbar has required actions
            self.assertEqual(app.part_chip_var.get(), "(Chưa chọn)")
            self.assertTrue(hasattr(app, '_action_copy_partition_config'))
            self.assertTrue(hasattr(app, '_action_clear_all_partitions'))
            self.assertTrue(hasattr(app, '_action_new_table'))
            self.assertTrue(hasattr(app, '_action_save'))
            self.assertTrue(hasattr(app, '_action_save_as'))

    def test_size_unit_parsing_and_auto_pack(self):
        from modules.dialogs.partition_dialogs import parse_with_unit
        self.assertEqual(parse_with_unit("64", "KB"), 64 * 1024)
        self.assertEqual(parse_with_unit("2", "MB"), 2 * 1024 * 1024)
        self.assertEqual(parse_with_unit("4096", "Bytes"), 4096)
        self.assertEqual(parse_with_unit("0x10000", "HEX"), 0x10000)

        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            self.assertTrue(hasattr(app, 'var_auto_align'))
            self.assertTrue(app.var_auto_align.get())
            # Test auto pack adjusts subsequent offsets properly
            app.table.entries[0].size = 32 * 1024
            app._cascade_auto_pack(from_idx=1)
            self.assertGreaterEqual(app.table.entries[1].offset, app.table.entries[0].end_offset)

    def test_streamlined_settings_and_standalone_dialogs(self):
        with patch('modules.app_core.set_window_icon_native'), patch('modules.dialogs.settings_dialog.set_window_icon_native'):
            app = InspectorApp(self.root)

            # 1. Hộp thoại Cài đặt tinh gọn: chỉ đúng 2 tab (Cài đặt chung, Nút chức năng)
            app.open_settings_dialog(0)
            settings_toplevel = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
            notebooks = [w for w in settings_toplevel.winfo_children() if isinstance(w, ttk.Notebook)]
            self.assertEqual(len(notebooks), 1)
            nb = notebooks[0]
            tab_names = [nb.tab(i, 'text').strip() for i in range(len(nb.tabs()))]
            self.assertEqual(len(tab_names), 2)
            self.assertIn("Cài đặt chung", tab_names[0])
            self.assertTrue(any("Nút chức năng" in name for name in tab_names))
            settings_toplevel.destroy()

            # 2. Hộp thoại Giới thiệu độc lập
            app.open_about_dialog()
            about_toplevel = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
            self.assertIn("Giới thiệu", about_toplevel.title())
            about_toplevel.destroy()

            # 3. Hộp thoại Cập nhật độc lập
            app.open_update_dialog()
            update_toplevel = [w for w in self.root.winfo_children() if isinstance(w, tk.Toplevel)][-1]
            self.assertIn("cập nhật", update_toplevel.title().lower())
            update_toplevel.destroy()

            # 4. Kiểm tra sự kiện MouseWheel sau khi đóng SettingsDialog không gây lỗi TclError
            self.root.update()
            try:
                self.root.event_generate('<MouseWheel>', delta=120)
                self.root.update()
            except Exception as ex:
                self.fail(f"MouseWheel generated error after settings dialog closed: {ex}")

    def test_auto_align_cascade_on_field_change(self):
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            self.assertTrue(app.var_auto_align.get())

            # Đổi kiểu phân vùng nvs từ data sang app -> offset phải tự động căn lên 0x10000 (64KB)
            nvs = app.table.entries[0]
            app._set_entry_field(nvs, 'type_str', 'app')
            self.assertEqual(nvs.offset, 0x10000)

            # Các phân vùng tiếp theo không được chồng lấn
            for i in range(1, len(app.table.entries)):
                prev = app.table.entries[i - 1]
                curr = app.table.entries[i]
                self.assertGreaterEqual(curr.offset, prev.end_offset)

            # Đổi dung lượng phân vùng nvs lên 128KB (0x20000)
            app._set_entry_field(nvs, 'size', 0x20000)
            for i in range(1, len(app.table.entries)):
                prev = app.table.entries[i - 1]
                curr = app.table.entries[i]
                self.assertGreaterEqual(curr.offset, prev.end_offset)

            # Toggle auto align checkbox
            app.var_auto_align.set(True)
            app._on_toggle_auto_align()
            self.assertEqual(app.table.entries[0].offset, 0x10000)

    def test_backup_clone_tab_disk_map_metadata_and_selection(self):
        from modules.tabs.tab_backup_clone import (
            compute_bytes_hashes,
            smart_trim_trailing_ff,
            infer_bootloader_offset_for_chip,
            build_backup_metadata_report,
        )
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            self.assertTrue(hasattr(app, 'backup_tree'))
            self.assertTrue(hasattr(app, 'backup_disk_map'))
            self.assertGreaterEqual(len(app.backup_regions), 5)

            # Kiểm tra chọn tất cả và chọn chỉ Firmware
            app._action_backup_select_all(True)
            self.assertTrue(all(r["selected"] for r in app.backup_regions))

            app._action_backup_select_firmware_only()
            by_name = {r["name"]: r["selected"] for r in app.backup_regions}
            self.assertTrue(by_name.get("bootloader"))
            self.assertTrue(by_name.get("partition_table"))
            self.assertFalse(by_name.get("nvs"))

            # Kiểm tra hàm cắt 0xFF và băm SHA-256 / MD5
            raw_payload = b"\xE9\x02\x00\x00" + b"\xAA" * 5000 + b"\xFF" * 8192
            trimmed = smart_trim_trailing_ff(raw_payload, min_keep_bytes=4096)
            self.assertLess(len(trimmed), len(raw_payload))
            self.assertEqual(len(trimmed) % 4096, 0)

            hashes = compute_bytes_hashes(trimmed)
            self.assertEqual(len(hashes["md5"]), 32)
            self.assertEqual(len(hashes["sha256"]), 64)

            self.assertEqual(infer_bootloader_offset_for_chip("ESP32-P4"), 0x2000)
            self.assertEqual(infer_bootloader_offset_for_chip("ESP32-S3"), 0x0)
            self.assertEqual(infer_bootloader_offset_for_chip("ESP32"), 0x1000)

            report = build_backup_metadata_report(
                chip_info={
                    "chip_name": "ESP32-P4 (revision v3.2)",
                    "mac": "E8:F6:0A:EB:89:94",
                    "flash_size": "16MB",
                    "crystal": "40MHz",
                    "features": "Dual Core + LP Core, 400MHz",
                    "source_port": "COM7",
                },
                saved_items=[{
                    "name": "factory",
                    "type_str": "app",
                    "subtype_str": "factory",
                    "offset": 0x10000,
                    "original_size": 0x100000,
                    "saved_size": len(trimmed),
                    "filename": "0x010000_factory.bin",
                    "md5": hashes["md5"],
                    "sha256": hashes["sha256"],
                }],
                backup_dir="C:/fake_backup",
                timestamp_str="2026-11-12 14:10:00",
            )
            self.assertIn("ESP32-P4 (revision v3.2)", report)
            self.assertIn("E8:F6:0A:EB:89:94", report)
            self.assertIn(hashes["sha256"], report)
            self.assertIn(hashes["md5"], report)

    def test_pyqt6_sidebar_toggle_and_zero_emoji_verification(self):
        import pathlib
        with patch('modules.app_core.set_window_icon_native'):
            app = InspectorApp(self.root)
            self.assertTrue(hasattr(app.notebook, "sidebar_frame"))
            self.assertTrue(hasattr(app.notebook, "btn_toggle_sidebar"))
            self.assertTrue(hasattr(app.notebook, "stack"))
            self.assertFalse(app.notebook.is_sidebar_collapsed)
            self.assertEqual(app.notebook.sidebar_frame.width(), 242)

            # Thu gọn Sidebar về dạng chỉ hiển thị icon vector (52px)
            app.notebook.toggle_sidebar()
            self.assertTrue(app.notebook.is_sidebar_collapsed)
            self.assertEqual(app.notebook.sidebar_frame.width(), 52)

            # Mở rộng lại Sidebar (242px)
            app.notebook.toggle_sidebar()
            self.assertFalse(app.notebook.is_sidebar_collapsed)
            self.assertEqual(app.notebook.sidebar_frame.width(), 242)

            # Đảm bảo không có bất kỳ emoji Unicode nào trong toàn bộ thư mục modules/
            allowed_punct = set('•–—…“”‘’─│┌┐└┘├┤┬┴┼═║╔╗╚╝╠╣╦╩╬▪▫►◄▲▼◆◇○●★☆✓✗✕✖➔➜➡⬅⬆⬇↔↕≤≥≠≈±×÷°µΩΩ【】')
            for py_file in pathlib.Path("modules").rglob("*.py"):
                content = py_file.read_text(encoding="utf-8")
                for ch in content:
                    if ord(ch) > 0x2000 and ch not in allowed_punct:
                        self.fail(f"Phát hiện ký tự emoji bị cấm '{ch}' ({hex(ord(ch))}) trong {py_file}")


if __name__ == '__main__':
    unittest.main()
