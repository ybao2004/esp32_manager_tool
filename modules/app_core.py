# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Core Application Controller
"""
import sys
import os
import json
import re
import time
import threading
import codecs
import tkinter as tk
from tkinter import ttk, messagebox

from modules.config import (
    CONFIG_FILE, DEFAULT_GEOMETRY, CONTROL_CONFIG,
    DARK_PALETTE, LIGHT_PALETTE, COMMON_BAUDS, REPORT_FONT_SIZE,
    Tu_dong_cuon, Them_dau_thoi_gian, APP_NAME, APP_VERSION
)
from modules.win32_util import set_window_icon_native
from modules.serial_util import list_com_ports_local, get_bluetooth_com_ports

from modules.tabs.tab_inspector import InspectorTabMixin
from modules.tabs.tab_monitor import MonitorTabMixin
from modules.tabs.tab_flasher import FlasherTabMixin
from modules.tabs.tab_partition import PartitionTabMixin
from modules.tabs.tab_backup_clone import BackupCloneTabMixin
from modules.dialogs.settings_dialog import SettingsDialogMixin

class InspectorApp(
    InspectorTabMixin,
    MonitorTabMixin,
    FlasherTabMixin,
    PartitionTabMixin,
    BackupCloneTabMixin,
    SettingsDialogMixin
):
    """
    Trình điều khiển trung tâm ứng dụng ESP Tool & Hardware Inspector v2.0.
    Tập hợp các Tab giao diện và dịch vụ hệ thống thông qua kiến trúc Mixin.
    """

    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        self.root.geometry(DEFAULT_GEOMETRY)
        
        # Thiết lập Icon cho cửa sổ và Taskbar (chuẩn Win32 High-DPI sắc nét)
        base_dir = getattr(sys, '_MEIPASS', None)
        if not base_dir:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        set_window_icon_native(self.root, base_dir=base_dir)
        
        self.stop_scan = threading.Event()
        self.is_detecting = threading.Event()
        self.stop_serial_thread = threading.Event()
        
        self.serial_connection = None
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.is_new_line = True
        self.feedback_buffer = "" 
        
        self.scanned_networks = []
        self.is_wifi_connected = False 
        self.is_server_connected = False 
        self.current_status_level = "info"
        
        # Biến cấu hình mặc định
        self.is_dark_mode = False
        self.saved_wifi_credentials = {}
        self.saved_geometry = DEFAULT_GEOMETRY
        self.saved_is_zoomed = False
        self.saved_com_port = ""
        self.saved_baudrate = "Tự động"
        self.ignored_com_ports = []
        self.saved_hide_bluetooth_ports = True
        self.saved_auto_select_new = True
        self._previous_ports = set()
        
        # Biến cấu hình có thể chỉnh sửa, load từ CONTROL_CONFIG
        self.default_ip = "192.168.4.1"
        self.default_port = "100"
        self.control_labels = {i: CONTROL_CONFIG.get(i, (f"F{i}", f"CMD_{i}"))[0] for i in sorted(CONTROL_CONFIG)}
        self.control_commands = {i: CONTROL_CONFIG.get(i, (f"F{i}", f"CMD_{i}"))[1] for i in sorted(CONTROL_CONFIG)}
        
        # Biến cấu hình nạp Flash (.bin)
        self.is_flashing = threading.Event()
        self.saved_flash_rows = []
        self.saved_flash_baud = "460800"
        self.saved_flash_chip = "auto"
        self.saved_flash_erase = False

        # Load cấu hình từ ổ cứng
        self.load_config()
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.img_unchecked = tk.PhotoImage(width=20, height=16)
        self.img_checked = tk.PhotoImage(width=20, height=16)
        self.img_disabled_unchecked = tk.PhotoImage(width=20, height=16)
        self.img_disabled_checked = tk.PhotoImage(width=20, height=16)

        try:
            self.style.element_create("custom.indicator", "image", self.img_unchecked, 
                                      ("disabled", "selected", self.img_disabled_checked), 
                                      ("disabled", self.img_disabled_unchecked), 
                                      ("pressed", "selected", self.img_checked), 
                                      ("active", "selected", self.img_checked), 
                                      ("selected", self.img_checked), 
                                      ("active", self.img_unchecked))
            
            self.style.layout("TCheckbutton", [('Checkbutton.padding', {'sticky': 'nswe', 'children': [
                ('custom.indicator', {'side': 'left', 'sticky': ''}), 
                ('Checkbutton.focus', {'side': 'left', 'sticky': 'w', 'children': [
                    ('Checkbutton.label', {'sticky': 'nswe'})
                ]})
            ]})])
        except tk.TclError: 
            pass 
        
        self.f_buttons = []
        self.create_widgets()
        self.apply_theme()
        
        # Phục hồi vị trí cửa sổ
        if self.saved_geometry:
            self.root.after(10, lambda: self.root.geometry(self.saved_geometry))
        if self.saved_is_zoomed:
            self.root.after(20, lambda: self.root.state('zoomed'))

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if not isinstance(config, dict):
                        raise ValueError("Nội dung file cấu hình không phải JSON object.")

                    wifi_credentials = config.get("wifi_credentials", {})
                    self.saved_wifi_credentials = {
                        str(key): str(value)
                        for key, value in wifi_credentials.items()
                    } if isinstance(wifi_credentials, dict) else {}
                    self.is_dark_mode = config.get("is_dark_mode", False) is True
                    geom = config.get("geometry")
                    if isinstance(geom, str) and re.fullmatch(r"\d+x\d+[+-]\d+[+-]\d+", geom):
                        self.saved_geometry = geom
                    self.saved_is_zoomed = config.get("is_zoomed", False) is True
                    self.saved_com_port = str(config.get("last_com_port", "") or "")
                    self.saved_baudrate = str(config.get("last_baudrate", "Tự động") or "Tự động")
                    if "hide_bluetooth_ports" in config:
                        self.saved_hide_bluetooth_ports = config.get("hide_bluetooth_ports", True) is not False
                        ignored_ports = config.get("ignored_com_ports", [])
                        self.ignored_com_ports = [str(port) for port in ignored_ports if str(port).strip()] if isinstance(ignored_ports, list) else []
                    else:
                        # Di trú từ bản cũ (v1.0): bật tự động ẩn Bluetooth bằng checkbox và làm sạch ô nhập tay
                        self.saved_hide_bluetooth_ports = True
                        self.ignored_com_ports = []
                    self.saved_auto_select_new = config.get("auto_select_new_port", True) is not False
                    
                    self.default_ip = str(config.get("default_ip", "192.168.4.1") or "192.168.4.1")
                    self.default_port = str(config.get("default_port", "100") or "100")
                    
                    loaded_labels = config.get("control_labels", {})
                    if isinstance(loaded_labels, dict):
                        for k, v in loaded_labels.items():
                            if str(k).isdigit() and int(k) in CONTROL_CONFIG:
                                self.control_labels[int(k)] = str(v)
                            
                    loaded_cmds = config.get("control_commands", {})
                    if isinstance(loaded_cmds, dict):
                        for k, v in loaded_cmds.items():
                            if str(k).isdigit() and int(k) in CONTROL_CONFIG:
                                self.control_commands[int(k)] = str(v)
                            
                    flash_rows = config.get("flash_rows", [])
                    self.saved_flash_rows = []
                    if isinstance(flash_rows, list):
                        for row in flash_rows[:4]:
                            if isinstance(row, dict):
                                self.saved_flash_rows.append({
                                    "enabled": row.get("enabled", False) is True,
                                    "path": str(row.get("path", "") or ""),
                                    "offset": str(row.get("offset", "") or ""),
                                })
                    self.saved_flash_baud = str(config.get("flash_baud", "460800") or "460800")
                    self.saved_flash_chip = str(config.get("flash_chip", "auto") or "auto")
                    self.saved_flash_erase = config.get("flash_erase", False) is True
            except Exception as e:
                print(f"Lỗi đọc file cấu hình: {e}")

    def save_config(self):
        geom = self.root.geometry()
        is_zoomed = False
        try:
            is_zoomed = self.root.state() == 'zoomed'
        except Exception:
            pass

        if is_zoomed:
            match = re.match(r"(\d+x\d+)", geom)
            if match:
                geom = f"{match.group(1)}+0+0"

        current_port = self.port_cb.get().strip() if hasattr(self, 'port_cb') else ""
        current_baud = self.baud_cb.get().strip() if hasattr(self, 'baud_cb') else ""
        last_port = current_port or self.saved_com_port
        last_baud = current_baud or self.saved_baudrate or "Tự động"
        self.saved_com_port = last_port
        self.saved_baudrate = last_baud
        auto_new = self.var_auto_select_new.get() if hasattr(self, 'var_auto_select_new') else self.saved_auto_select_new
        hide_bt = self.var_hide_bt_ports.get() if hasattr(self, 'var_hide_bt_ports') else self.saved_hide_bluetooth_ports
        self.saved_hide_bluetooth_ports = hide_bt

        flash_rows_data = []
        if hasattr(self, 'flash_file_rows'):
            for row in self.flash_file_rows:
                flash_rows_data.append({
                    "enabled": row["var_enable"].get(),
                    "path": row["path_entry"].get().strip(),
                    "offset": row["offset_entry"].get().strip()
                })
        else:
            flash_rows_data = self.saved_flash_rows

        flash_baud_val = self.flash_baud_cb.get().strip() if hasattr(self, 'flash_baud_cb') else self.saved_flash_baud
        flash_chip_val = self.flash_chip_cb.get().strip() if hasattr(self, 'flash_chip_cb') else self.saved_flash_chip
        flash_erase_val = self.var_flash_erase.get() if hasattr(self, 'var_flash_erase') else self.saved_flash_erase

        config = {
            "wifi_credentials": self.saved_wifi_credentials,
            "is_dark_mode": self.is_dark_mode,
            "geometry": geom,
            "is_zoomed": is_zoomed,
            "last_com_port": last_port,
            "last_baudrate": last_baud,
            "ignored_com_ports": self.ignored_com_ports,
            "hide_bluetooth_ports": hide_bt,
            "auto_select_new_port": auto_new,
            "default_ip": self.default_ip,
            "default_port": self.default_port,
            "control_labels": self.control_labels,
            "control_commands": self.control_commands,
            "flash_rows": flash_rows_data,
            "flash_baud": flash_baud_val,
            "flash_chip": flash_chip_val,
            "flash_erase": flash_erase_val
        }
        temp_config = f"{CONFIG_FILE}.{os.getpid()}.tmp"
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(temp_config, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_config, CONFIG_FILE)
        except Exception as e:
            print(f"Lỗi lưu file cấu hình: {e}")
            try:
                if os.path.exists(temp_config):
                    os.remove(temp_config)
            except OSError:
                pass

    def reset_config(self):
        if messagebox.askyesno("Xác nhận", "Bạn có chắc chắn muốn khôi phục cài đặt gốc?\n(Mật khẩu WiFi đã lưu, cấu hình và màu nền sẽ bị xóa)"):
            if os.path.exists(CONFIG_FILE):
                try:
                    os.remove(CONFIG_FILE)
                except Exception:
                    pass
            self.saved_wifi_credentials = {}
            self.is_dark_mode = False
            self.saved_geometry = DEFAULT_GEOMETRY
            self.saved_is_zoomed = False
            self.saved_com_port = ""
            self.saved_baudrate = "Tự động"
            self.ignored_com_ports = []
            self.saved_hide_bluetooth_ports = True
            self.saved_auto_select_new = True
            if hasattr(self, 'var_auto_select_new'):
                self.var_auto_select_new.set(True)
            if hasattr(self, 'var_hide_bt_ports'):
                self.var_hide_bt_ports.set(True)
            
            self.default_ip = "192.168.4.1"
            self.default_port = "100"
            self.control_labels = {i: CONTROL_CONFIG.get(i, (f"F{i}", f"CMD_{i}"))[0] for i in sorted(CONTROL_CONFIG)}
            self.control_commands = {i: CONTROL_CONFIG.get(i, (f"F{i}", f"CMD_{i}"))[1] for i in sorted(CONTROL_CONFIG)}
            
            self.root.state('normal')
            self.root.geometry(DEFAULT_GEOMETRY)
            self.apply_theme()
            
            if hasattr(self, 'wifi_pass_entry') and self.wifi_pass_entry.winfo_exists():
                orig_w_state = str(self.wifi_pass_entry.cget("state"))
                if orig_w_state == "disabled": self.wifi_pass_entry.config(state="normal")
                self.wifi_pass_entry.delete(0, tk.END)
                if orig_w_state == "disabled": self.wifi_pass_entry.config(state="disabled")

            self.wifi_cb.set('')
            self.wifi_cb['values'] = []
            self.baud_cb.set("Tự động")
            self.port_cb.set("")
            
            if hasattr(self, 'ip_entry') and self.ip_entry.winfo_exists():
                orig_ip_state = str(self.ip_entry.cget("state"))
                if orig_ip_state == "disabled": 
                    self.ip_entry.config(state="normal")
                    self.port_entry.config(state="normal")
                self.ip_entry.delete(0, tk.END)
                self.ip_entry.insert(0, self.default_ip)
                self.port_entry.delete(0, tk.END)
                self.port_entry.insert(0, self.default_port)
                if orig_ip_state == "disabled": 
                    self.ip_entry.config(state="disabled")
                    self.port_entry.config(state="disabled")
            
            for index, i in enumerate(sorted(CONTROL_CONFIG)):
                if index < len(self.f_buttons):
                    self.f_buttons[index].config(text=self.control_labels[i])

            # Khôi phục danh sách nạp Flash
            self.saved_flash_rows = []
            self.saved_flash_baud = "460800"
            self.saved_flash_chip = "auto"
            self.saved_flash_erase = False
            default_offsets = ["0x1000", "0x8000", "0xe000", "0x10000"]
            if hasattr(self, 'flash_file_rows'):
                for idx, row in enumerate(self.flash_file_rows):
                    row["var_enable"].set(idx == 0)
                    row["path_entry"].delete(0, tk.END)
                    row["offset_entry"].delete(0, tk.END)
                    row["offset_entry"].insert(0, default_offsets[idx] if idx < len(default_offsets) else "0x0")
                    self._update_file_size_display(idx)
            if hasattr(self, 'flash_baud_cb'):
                self.flash_baud_cb.set("460800")
            if hasattr(self, 'flash_chip_cb'):
                self.flash_chip_cb.set("auto")
            if hasattr(self, 'var_flash_erase'):
                self.var_flash_erase.set(False)

            self.save_config()
                    
            messagebox.showinfo("Thành công", "Đã khôi phục cài đặt mặc định.")
            return True
        return False

    def _set_theme(self, is_dark: bool):
        """Chuyển đổi giao diện Sáng / Tối trực tiếp từ thanh Menu"""
        if self.is_dark_mode != is_dark:
            self.toggle_theme()

    def _tool_inspect_chip(self):
        """Chuyển sang Tab Thông tin phần cứng và kích hoạt kiểm tra chip."""
        if hasattr(self, "inspector_tab"):
            self.notebook.select(self.inspector_tab)
        if hasattr(self, "on_detect"):
            self.on_detect()

    def _create_main_menu(self):
        """Khởi tạo thanh Menu Bar chuẩn của cửa sổ chính: Tệp, Công cụ, Theme, Cài đặt, Giới thiệu"""
        self.main_menu = tk.Menu(self.root, tearoff=0)
        self.root.config(menu=self.main_menu)

        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE

        # 1. Menu Tệp (File): Tạo mới, Mở, Nhập, Separator, Lưu, Lưu như, Separator, Thoát
        file_menu = tk.Menu(self.main_menu, tearoff=0)
        self.main_menu.add_cascade(label="Tệp", menu=file_menu)

        file_menu.add_command(
            label="Tạo mới",
            command=lambda: (self.notebook.select(self.partition_tab), self._action_new_table() if hasattr(self, '_action_new_table') else None)
        )
        file_menu.add_command(
            label="Mở...",
            command=lambda: (self.notebook.select(self.partition_tab), self._action_open_file() if hasattr(self, '_action_open_file') else None)
        )
        file_menu.add_command(
            label="Nhập...",
            command=lambda: (self.notebook.select(self.partition_tab), self._action_presets() if hasattr(self, '_action_presets') else None)
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Lưu",
            command=lambda: (self.notebook.select(self.partition_tab), self._action_save() if hasattr(self, '_action_save') else None)
        )
        file_menu.add_command(
            label="Lưu như...",
            command=lambda: (self.notebook.select(self.partition_tab), self._action_save_as() if hasattr(self, '_action_save_as') else None)
        )
        file_menu.add_separator()
        file_menu.add_command(
            label="Thoát",
            command=self.on_closing
        )

        # 2. Menu Công cụ (Tools): Kiểm tra chip, Reset, Xóa toàn bộ Flash, Kiểm tra cập nhật
        tools_menu = tk.Menu(self.main_menu, tearoff=0)
        self.main_menu.add_cascade(label="Công cụ", menu=tools_menu)

        tools_menu.add_command(
            label="Kiểm tra chip ESP",
            command=self._tool_inspect_chip
        )
        tools_menu.add_command(
            label="Reset ESP",
            command=self.on_reset_esp
        )
        tools_menu.add_command(
            label="Xóa toàn bộ Flash (Erase Chip)",
            command=self.on_erase_flash_click
        )
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Kiểm tra cập nhật phần mềm...",
            command=self.open_update_dialog
        )

        # 3. Menu Theme (Giao diện): Giao diện Tối, Giao diện Sáng
        theme_menu = tk.Menu(self.main_menu, tearoff=0)
        self.main_menu.add_cascade(label="Theme", menu=theme_menu)

        theme_menu.add_command(
            label="Giao diện Tối (Dark)",
            command=lambda: self._set_theme(True)
        )
        theme_menu.add_command(
            label="Giao diện Sáng (Light)",
            command=lambda: self._set_theme(False)
        )

        # 4. Cài đặt (Mở trực tiếp Hộp thoại Cài đặt tinh gọn)
        self.main_menu.add_command(
            label="Cài đặt",
            command=self.open_settings_dialog
        )

        # 5. Giới thiệu (Mở trực tiếp Hộp thoại Giới thiệu độc lập)
        self.main_menu.add_command(
            label="Giới thiệu",
            command=self.open_about_dialog
        )

    def create_widgets(self):
        try:
            self.root.minsize(1080, 650)
        except Exception:
            pass
        self.main_frame = ttk.Frame(self.root, padding=5)
        self.main_frame.grid(sticky="nsew", row=0, column=0)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)
        self.main_frame.rowconfigure(2, weight=0)
        
        self._create_main_menu()

        # Thanh điều khiển Serial trên cùng (phẳng, không viền LabelFrame)
        self.controls_frame = ttk.Frame(self.main_frame, padding=(6, 4))
        self.controls_frame.grid(row=0, column=0, sticky="ew", padx=2, pady=(2, 4))
        
        ttk.Label(self.controls_frame, text="COM Port:").grid(row=0, column=0, sticky="w", pady=2, padx=(0, 5))
        self.port_cb = ttk.Combobox(self.controls_frame, values=[], width=12, state="readonly", postcommand=self.refresh_ports_dropdown)
        self.port_cb.grid(row=0, column=1, sticky="w")
        self.port_cb.bind("<<ComboboxSelected>>", self.on_port_selected)
        
        self.var_auto_scan = tk.BooleanVar(value=True)
        self.var_auto_select_new = tk.BooleanVar(value=self.saved_auto_select_new)
        self.var_hide_bt_ports = tk.BooleanVar(value=self.saved_hide_bluetooth_ports)
        
        ttk.Label(self.controls_frame, text="Baudrate:").grid(row=0, column=2, sticky="w", padx=(12, 5))
        self.baud_cb = ttk.Combobox(self.controls_frame, values=COMMON_BAUDS, width=10)
        self.baud_cb.set(self.saved_baudrate if self.saved_baudrate in COMMON_BAUDS else "Tự động") 
        self.baud_cb.grid(row=0, column=3, sticky="w")
        self.baud_cb.bind("<<ComboboxSelected>>", self.on_baud_selected)
        
        self.serial_toggle_btn = ttk.Button(self.controls_frame, text="Kết nối", command=self.toggle_serial_connection)
        self.serial_toggle_btn.grid(row=0, column=4, padx=(10, 5))
        
        separator = ttk.Separator(self.controls_frame, orient='vertical')
        separator.grid(row=0, column=5, sticky='ns', padx=10, pady=2)
        
        self.var_autoscroll = tk.BooleanVar(value=Tu_dong_cuon)
        ttk.Checkbutton(self.controls_frame, text="Tự động cuộn", variable=self.var_autoscroll).grid(row=0, column=6, padx=(5, 5))
        
        self.var_timestamp = tk.BooleanVar(value=Them_dau_thoi_gian)
        ttk.Checkbutton(self.controls_frame, text="Thêm Dấu thời gian", variable=self.var_timestamp).grid(row=0, column=7, padx=(5, 10)) 
        
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=1, column=0, sticky="nsew", pady=5)
        self.inspector_tab = ttk.Frame(self.notebook)
        self.monitor_tab = ttk.Frame(self.notebook)
        self.flasher_tab = ttk.Frame(self.notebook)
        self.partition_tab = ttk.Frame(self.notebook)
        self.backup_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.inspector_tab, text=' Kiểm tra Phần cứng ')
        self.notebook.add(self.monitor_tab, text=' Serial Monitor & Điều khiển ')
        self.notebook.add(self.flasher_tab, text=' Nạp Flash Firmware (.bin) ')
        self.notebook.add(self.partition_tab, text=' Phân vùng Bộ nhớ (Partition Wizard) ')
        self.notebook.add(self.backup_tab, text=' Sao lưu & Nhân bản (Backup / Clone) ')
        
        self.notebook.select(self.monitor_tab)
        
        self.inspector_tab.columnconfigure(0, weight=1)
        self.inspector_tab.rowconfigure(1, weight=1)
        self.flasher_tab.columnconfigure(0, weight=1)
        self.flasher_tab.rowconfigure(0, weight=0)
        self.flasher_tab.rowconfigure(1, weight=0)
        self.flasher_tab.rowconfigure(2, weight=1)
        
        self.create_inspector_tab()
        self.create_monitor_tab()
        self.create_flasher_tab()
        self.create_partition_tab()
        self.create_backup_tab()

        # Thanh trạng thái & tiến trình toàn cục ở đáy cửa sổ chính (Global Status Bar)
        self.status_bar_frame = ttk.Frame(self.main_frame, padding=(6, 3))
        self.status_bar_frame.grid(row=2, column=0, sticky="ew", padx=2, pady=(2, 0))
        self.status_bar_frame.columnconfigure(1, weight=1)

        self.global_status_icon_lbl = ttk.Label(self.status_bar_frame, text="ℹ️", font=("Segoe UI", 9))
        self.global_status_icon_lbl.grid(row=0, column=0, sticky="w", padx=(0, 4))

        self.global_status_lbl = ttk.Label(self.status_bar_frame, text="Sẵn sàng.", font=("Segoe UI", 9))
        self.global_status_lbl.grid(row=0, column=1, sticky="w")

        self.global_progress_bar = ttk.Progressbar(
            self.status_bar_frame, orient="horizontal", mode="determinate", length=180, maximum=100, value=0
        )
        self.global_progress_bar.grid(row=0, column=2, sticky="e", padx=(8, 4))

        self.global_progress_pct_lbl = ttk.Label(
            self.status_bar_frame, text="0%", width=5, anchor="w", font=("Segoe UI", 9, "bold")
        )
        self.global_progress_pct_lbl.grid(row=0, column=3, sticky="e", padx=(0, 10))

        self.global_com_lbl = ttk.Label(self.status_bar_frame, text="COM: Chưa kết nối", font=("Segoe UI", 9, "italic"))
        self.global_com_lbl.grid(row=0, column=4, sticky="e", padx=(0, 4))

        self._set_mcu_dependent_ui_state("disabled")

    def _set_mcu_dependent_ui_state(self, ui_state):
        self.btn_scan_wifi.config(state=ui_state)
        self.btn_connect_wifi.config(state=ui_state)
        self.btn_connect_server.config(state=ui_state)
        self.wifi_cb.config(state=ui_state)
        self.wifi_pass_entry.config(state=ui_state)
        self.ip_entry.config(state=ui_state)
        self.port_entry.config(state=ui_state)
        self.cb_auto_server.config(state=ui_state)
        
        for btn in self.f_buttons: 
            btn.config(state=ui_state)
            
        self.serial_input.config(state=ui_state)
        self.send_btn.config(state=ui_state)
        if hasattr(self, 'reset_btn'):
            self.reset_btn.config(state=ui_state)
        self.cb_crlf.config(state=ui_state)
        self.cb_show_pwd.config(state=ui_state)

    def _draw_checkbox_image(self, img, border_color, bg_color, parent_bg, check_color=None):
        width = 20; height = 16; box_size = 14; offset_x = 1; offset_y = 1
        row_data = []
        for y in range(height):
            row = []
            for x in range(width):
                if offset_x <= x < offset_x + box_size and offset_y <= y < offset_y + box_size:
                    if x == offset_x or x == offset_x + box_size - 1 or y == offset_y or y == offset_y + box_size - 1: 
                        row.append(border_color)
                    else: 
                        row.append(bg_color)
                else: 
                    row.append(parent_bg)
            row_data.append("{" + " ".join(row) + "}")
        img.put(" ".join(row_data))
        if check_color:
            check_pts = [(4,8), (5,9), (6,10), (7,11), (8,10), (9,9), (10,8), (11,7), (12,6), 
                         (4,9), (5,10), (6,11), (7,12), (8,11), (9,10), (10,9), (11,8), (12,7)]
            for x, y in check_pts: 
                img.put(check_color, (x, y))

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        
        self._draw_checkbox_image(self.img_unchecked, p["border"], p["text_bg"], p["bg"])
        self._draw_checkbox_image(self.img_checked, p["accent"], p["accent"], p["bg"], "#ffffff") 
        self._draw_checkbox_image(self.img_disabled_unchecked, p["border"], p["disabled_bg"], p["bg"])
        self._draw_checkbox_image(self.img_disabled_checked, p["border"], p["disabled_bg"], p["bg"], p["disabled_fg"])

        self.root.configure(bg=p["bg"])
        
        select_bg = p.get("select_bg", p["accent"])
        select_fg = p.get("select_fg", "#ffffff")

        self.inspector_txt.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["fg"], selectbackground=select_bg, selectforeground=select_fg)
        self.monitor_txt.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["fg"], selectbackground=select_bg, selectforeground=select_fg)
        if hasattr(self, 'flasher_txt') and self.flasher_txt.winfo_exists():
            self.flasher_txt.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["fg"], selectbackground=select_bg, selectforeground=select_fg)
            self.flasher_txt.tag_configure('header', font=("Consolas", REPORT_FONT_SIZE, 'bold'), foreground=p["text_fg"], selectforeground=select_fg, selectbackground=select_bg)
            self.flasher_txt.tag_configure('green', foreground=p["success"], selectforeground=select_fg, selectbackground=select_bg)
            self.flasher_txt.tag_configure('blue', foreground=p["accent"], selectforeground=select_fg, selectbackground=select_bg)
            self.flasher_txt.tag_configure('red', foreground=p["error"], selectforeground=select_fg, selectbackground=select_bg)

        if hasattr(self, 'serial_input') and isinstance(self.serial_input, tk.Text):
            self.serial_input.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["text_fg"], selectbackground=select_bg, selectforeground=select_fg)

        if hasattr(self, 'disk_map'):
            self.disk_map.set_theme_mode(self.is_dark_mode)
        if hasattr(self, 'backup_disk_map'):
            self.backup_disk_map.set_theme_mode(self.is_dark_mode)
        if hasattr(self, 'backup_log_txt') and self.backup_log_txt.winfo_exists():
            self.backup_log_txt.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["fg"], selectbackground=select_bg, selectforeground=select_fg)
            self.backup_log_txt.tag_configure('header', font=("Consolas", REPORT_FONT_SIZE, 'bold'), foreground=p["text_fg"], selectforeground=select_fg, selectbackground=select_bg)
            self.backup_log_txt.tag_configure('green', foreground=p["success"], selectforeground=select_fg, selectbackground=select_bg)
            self.backup_log_txt.tag_configure('blue', foreground=p["accent"], selectforeground=select_fg, selectbackground=select_bg)
            self.backup_log_txt.tag_configure('red', foreground=p["error"], selectforeground=select_fg, selectbackground=select_bg)
        if hasattr(self, 'txt_partition_val') and self.txt_partition_val.winfo_exists():
            self.txt_partition_val.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["fg"])
        if hasattr(self, 'txt_partition_log') and self.txt_partition_log.winfo_exists():
            self.txt_partition_log.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["fg"])
        if hasattr(self, 'txt_partition_doc') and self.txt_partition_doc.winfo_exists():
            self.txt_partition_doc.configure(bg=p["text_bg"], fg=p["text_fg"], insertbackground=p["fg"])
            
        self.inspector_txt.tag_configure('header', font=("Consolas", REPORT_FONT_SIZE, 'bold'), foreground=p["text_fg"], selectforeground=select_fg, selectbackground=select_bg)
        self.inspector_txt.tag_configure('green', foreground=p["success"], selectforeground=select_fg, selectbackground=select_bg)
        self.inspector_txt.tag_configure('blue', foreground=p["accent"], selectforeground=select_fg, selectbackground=select_bg)
        self.inspector_txt.tag_configure('red', foreground=p["error"], selectforeground=select_fg, selectbackground=select_bg)
        
        self.monitor_txt.tag_configure('server_rx', foreground="#00fa9a" if self.is_dark_mode else "#008000", selectforeground=select_fg, selectbackground=select_bg)
        
        self.wifi_status_lbl.configure(bg=p["bg"], fg=p["success"] if self.is_wifi_connected else p["error"])
        
        color_map = {
            "info": p["disabled_fg"], "success": p["success"],
            "error": p["error"], "warning": p["warning"]
        }
        self.req_status_lbl.configure(bg=p["bg"], fg=color_map.get(self.current_status_level, p["disabled_fg"]))
        if hasattr(self, 'global_status_lbl') and self.global_status_lbl.winfo_exists():
            self.global_status_lbl.configure(foreground=color_map.get(self.current_status_level, p["fg"]))
        if hasattr(self, 'global_progress_pct_lbl') and self.global_progress_pct_lbl.winfo_exists():
            self.global_progress_pct_lbl.configure(foreground=p["fg"])
        if hasattr(self, 'global_com_lbl') and self.global_com_lbl.winfo_exists():
            self.global_com_lbl.configure(foreground=p["disabled_fg"])

        self.style.theme_use('clam') 
        self.style.configure(".", background=p["bg"], foreground=p["fg"], fieldbackground=p["text_bg"])
        
        self.style.configure("TButton", background=p["btn_bg"], foreground=p["fg"], borderwidth=1, bordercolor=p["border"], lightcolor=p["btn_bg"], darkcolor=p["btn_bg"])
        self.style.map("TButton", 
                       background=[('disabled', p["disabled_bg"]), ('active', p["btn_hover"]), ('pressed', p["btn_pressed"])], 
                       foreground=[('disabled', p["disabled_fg"])], 
                       bordercolor=[('disabled', p["border"])], 
                       lightcolor=[('disabled', p["disabled_bg"]), ('active', p["btn_hover"]), ('pressed', p["btn_pressed"])], 
                       darkcolor=[('disabled', p["disabled_bg"]), ('active', p["btn_hover"]), ('pressed', p["btn_pressed"])])
        
        self.style.configure("Accent.TButton", foreground=p["accent"], font=('Segoe UI', 10, 'bold'))
        
        self.style.configure("TEntry", fieldbackground=p["text_bg"], foreground=p["text_fg"], borderwidth=1, bordercolor=p["border"], lightcolor=p["text_bg"], darkcolor=p["text_bg"], insertcolor=p["text_fg"])
        self.style.map("TEntry", 
                       fieldbackground=[('disabled', p["disabled_bg"])], 
                       foreground=[('disabled', p["disabled_fg"])], 
                       lightcolor=[('disabled', p["disabled_bg"])], 
                       darkcolor=[('disabled', p["disabled_bg"])])
        
        self.style.configure("TCombobox", fieldbackground=p["text_bg"], foreground=p["text_fg"], borderwidth=1, bordercolor=p["border"], lightcolor=p["text_bg"], darkcolor=p["text_bg"], arrowcolor=p["fg"], insertcolor=p["text_fg"])
        self.style.map("TCombobox", 
                       fieldbackground=[('disabled', p["disabled_bg"])], 
                       foreground=[('disabled', p["disabled_fg"])], 
                       lightcolor=[('disabled', p["disabled_bg"])], 
                       darkcolor=[('disabled', p["disabled_bg"])])
                       
        self.root.option_add('*TCombobox*Listbox.background', p["text_bg"])
        self.root.option_add('*TCombobox*Listbox.foreground', p["text_fg"])
        self.root.option_add('*TCombobox*Listbox.selectBackground', p["accent"])
        self.root.option_add('*TCombobox*Listbox.selectForeground', '#ffffff')
        
        self.style.configure("TCheckbutton", background=p["bg"], foreground=p["fg"], focuscolor=p["bg"])
        self.style.map("TCheckbutton", background=[('active', p["bg"])], foreground=[('disabled', p["disabled_fg"])])
        
        self.style.configure("TLabel", background=p["bg"], foreground=p["fg"])
        self.style.configure("TFrame", background=p["bg"])
        
        self.style.configure("TLabelframe", background=p["bg"], foreground=p["fg"], borderwidth=1, bordercolor=p["border"], lightcolor=p["bg"], darkcolor=p["bg"])
        self.style.configure("TLabelframe.Label", background=p["bg"], foreground=p["fg"])
        
        self.style.configure("TNotebook", background=p["bg"], borderwidth=0)
        self.style.configure("TNotebook.Tab", background=p["disabled_bg"], foreground=p["fg"], borderwidth=1, bordercolor=p["border"], lightcolor=p["disabled_bg"])
        self.style.map("TNotebook.Tab", background=[("selected", p["bg"])], lightcolor=[("selected", p["bg"])])
        
        self.style.configure("TProgressbar", thickness=16, troughcolor=p["text_bg"], background=p["accent"], bordercolor=p["border"])
        
        if hasattr(self, 'wifi_pass_entry') and self.wifi_pass_entry.winfo_exists():
            self.toggle_pwd_visibility()

    def start_background_tasks(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        threading.Thread(target=self._auto_scan_ports, daemon=True).start()
        self.set_status("Sẵn sàng.", "info", progress=0)

    def _auto_scan_ports(self):
        while not self.stop_scan.is_set():
            try:
                new_ports = list_com_ports_local()
                if self.stop_scan.is_set():
                    break
                self.root.after(0, self._check_and_update_ports, new_ports)
            except Exception: 
                pass
            time.sleep(2)

    def filter_ignored_ports(self, raw_ports):
        ignored = {x.strip().upper() for x in (self.ignored_com_ports or []) if x and x.strip()}
        hide_bt = (
            self.var_hide_bt_ports.get()
            if hasattr(self, 'var_hide_bt_ports')
            else getattr(self, 'saved_hide_bluetooth_ports', True)
        )
        if hide_bt:
            try:
                for bt_port in get_bluetooth_com_ports():
                    if bt_port and bt_port.strip():
                        ignored.add(bt_port.strip().upper())
            except Exception:
                pass
        if not ignored:
            return list(raw_ports)
        return [p for p in raw_ports if p.strip().upper() not in ignored]

    def _check_and_update_ports(self, new_ports):
        if not self.root.winfo_exists():
            return
        busy = self.is_device_busy() if callable(getattr(self, 'is_device_busy', None)) else InspectorApp.is_device_busy(self)
        if busy:
            return
        if self.var_auto_scan.get():
            filtered_ports = self.filter_ignored_ports(new_ports)
            current_selection = self.port_cb.get().strip()
            
            newly_added = [p for p in filtered_ports if p not in self._previous_ports]
            self._previous_ports = set(filtered_ports)
            
            if hasattr(self, 'var_auto_select_new') and self.var_auto_select_new.get() and newly_added and not (self.serial_connection and self.serial_connection.is_open):
                latest_new_port = newly_added[-1]
                if tuple(filtered_ports) != tuple(self.port_cb['values']):
                    self.port_cb['values'] = filtered_ports
                self.port_cb.set(latest_new_port)
                self.saved_com_port = latest_new_port
                self.save_config()
                self.set_status(f"Đã tự động chọn cổng mới cắm: {latest_new_port}", "info")
                if hasattr(self, '_refresh_backup_ports') and callable(self._refresh_backup_ports):
                    try:
                        self._refresh_backup_ports()
                    except Exception:
                        pass
            else:
                self.update_port_list(current_selection, filtered_ports)

    def refresh_ports_dropdown(self):
        new_ports = list_com_ports_local()
        filtered_ports = self.filter_ignored_ports(new_ports)
        self._previous_ports = set(filtered_ports)
        current_selection = self.port_cb.get().strip()
        self.update_port_list(current_selection, filtered_ports)

    def on_port_selected(self, event=None):
        port = self.port_cb.get().strip()
        if port:
            self.saved_com_port = port
            self.save_config()

    def on_baud_selected(self, event=None):
        baud = self.baud_cb.get().strip()
        if baud:
            self.saved_baudrate = baud
            self.save_config()

    def on_serial_newline(self, event=None):
        self.serial_input.insert(tk.INSERT, "\n")
        return "break"

    def update_port_list(self, current_selection, new_ports):
        if self.root.winfo_exists():
            if tuple(new_ports) != tuple(self.port_cb['values']):
                self.port_cb['values'] = new_ports
            
            if self.saved_com_port and self.saved_com_port in new_ports:
                self.port_cb.set(self.saved_com_port)
            elif current_selection and current_selection in new_ports:
                self.port_cb.set(current_selection)
            elif new_ports:
                self.port_cb.set(new_ports[0])
            else:
                self.port_cb.set("")

            if hasattr(self, '_refresh_backup_ports') and callable(self._refresh_backup_ports):
                try:
                    self._refresh_backup_ports()
                except Exception:
                    pass
                
    def is_device_busy(self) -> bool:
        """Kiểm tra xem bất kỳ tác vụ phần cứng nào đang chạy trên bất kỳ Tab nào."""
        flashing = hasattr(self, 'is_flashing') and (self.is_flashing.is_set() if hasattr(self.is_flashing, 'is_set') else bool(self.is_flashing))
        detecting = hasattr(self, 'is_detecting') and (self.is_detecting.is_set() if hasattr(self.is_detecting, 'is_set') else bool(self.is_detecting))
        connecting = bool(getattr(self, "is_connecting", False))
        partition_hw = bool(getattr(self, "_is_partition_hw_running", False))
        backup_hw = bool(getattr(self, "_is_backup_hw_running", False))
        return bool(flashing or detecting or connecting or partition_hw or backup_hw)

    def set_global_busy_state(self, is_busy: bool, operation_name: str = "") -> None:
        """Cập nhật trạng thái bận toàn hệ thống, vô hiệu hóa/kích hoạt lại các điều khiển trên tất cả các tab, và cập nhật thanh trạng thái."""
        state = "disabled" if is_busy else "normal"

        if hasattr(self, 'detect_btn') and hasattr(self.detect_btn, 'config'):
            try:
                self.detect_btn.config(state=state)
            except Exception:
                pass

        if hasattr(self, 'serial_toggle_btn') and hasattr(self.serial_toggle_btn, 'config'):
            try:
                self.serial_toggle_btn.config(state=state)
            except Exception:
                pass

        if hasattr(self, '_set_flash_ui_state') and callable(self._set_flash_ui_state):
            try:
                self._set_flash_ui_state(state)
            except Exception:
                pass

        if hasattr(self, '_set_partition_ui_state') and callable(self._set_partition_ui_state):
            try:
                self._set_partition_ui_state(state)
            except Exception:
                pass

        if hasattr(self, '_set_backup_ui_state') and callable(self._set_backup_ui_state):
            try:
                self._set_backup_ui_state(state)
            except Exception:
                pass

        if hasattr(self, 'port_cb') and hasattr(self.port_cb, 'config'):
            try:
                self.port_cb.config(state="disabled" if is_busy else "readonly")
            except Exception:
                pass

        if hasattr(self, 'baud_cb') and hasattr(self.baud_cb, 'config'):
            try:
                self.baud_cb.config(state="disabled" if is_busy else "readonly")
            except Exception:
                pass

        # Vô hiệu hóa các điều khiển gửi lệnh trên Tab 2 khi bận
        if is_busy:
            if hasattr(self, '_set_mcu_dependent_ui_state') and callable(self._set_mcu_dependent_ui_state):
                try:
                    self._set_mcu_dependent_ui_state("disabled")
                except Exception:
                    pass
        else:
            if hasattr(self, 'serial_connection') and self.serial_connection and getattr(self.serial_connection, 'is_open', False):
                if hasattr(self, '_set_mcu_dependent_ui_state') and callable(self._set_mcu_dependent_ui_state):
                    try:
                        self._set_mcu_dependent_ui_state("normal")
                    except Exception:
                        pass

        if operation_name and hasattr(self, 'update_global_status'):
            msg = f"Đang {operation_name}..." if is_busy else f"Đã hoàn tất {operation_name}."
            self.update_global_status(msg, is_active=is_busy, progress=5.0 if is_busy else 100.0)
        elif operation_name and hasattr(self, 'set_status'):
            msg = f"Đang {operation_name}..." if is_busy else f"Đã hoàn tất {operation_name}."
            self.set_status(msg, "warning" if is_busy else "info", progress=5.0 if is_busy else 100.0)
        elif not is_busy:
            if hasattr(self, 'global_progress_bar') and self.global_progress_bar.winfo_exists():
                try:
                    self.global_progress_bar.stop()
                    self.global_progress_bar.config(mode="determinate")
                except Exception:
                    pass

    def on_closing(self):
        busy = self.is_device_busy() if callable(getattr(self, 'is_device_busy', None)) else InspectorApp.is_device_busy(self)
        if busy:
            messagebox.showwarning("Tác vụ chưa hoàn tất", "Hãy đợi tác vụ hiện tại hoàn tất trước khi đóng ứng dụng.")
            return
        self.save_config()
        self.on_serial_disconnect()
        self.stop_scan.set()
        self.root.destroy()

    def set_status(self, s, level="info", progress=None): 
        self.current_status_level = level
        try:
            if not getattr(self, 'root', None) or not self.root.winfo_exists():
                return
        except Exception:
            return

        p = DARK_PALETTE if getattr(self, 'is_dark_mode', False) else LIGHT_PALETTE
        color_map = {
            "info": p["disabled_fg"], "success": p["success"],
            "error": p["error"], "warning": p["warning"]
        }
        icon_map = {
            "info": "ℹ️",
            "success": "✅",
            "warning": "⚠️",
            "error": "❌"
        }
        color = color_map.get(level, p["disabled_fg"])
        icon = icon_map.get(level, "ℹ️")

        def _apply():
            if hasattr(self, 'req_status_lbl') and self.req_status_lbl.winfo_exists():
                try:
                    self.req_status_lbl.config(text=s, fg=color)
                except Exception:
                    pass
            if hasattr(self, 'global_status_lbl') and self.global_status_lbl.winfo_exists():
                try:
                    self.global_status_lbl.config(text=s, foreground=color)
                except Exception:
                    pass
            if hasattr(self, 'global_status_icon_lbl') and self.global_status_icon_lbl.winfo_exists():
                try:
                    self.global_status_icon_lbl.config(text=icon)
                except Exception:
                    pass
            if progress is not None:
                try:
                    prog_val = float(progress)
                    pct_disp = int(round(max(0.0, min(100.0, prog_val))))
                    if hasattr(self, 'global_progress_bar') and self.global_progress_bar.winfo_exists():
                        self.global_progress_bar.stop()
                        self.global_progress_bar.config(mode="determinate", value=prog_val)
                    if hasattr(self, 'global_progress_pct_lbl') and self.global_progress_pct_lbl.winfo_exists():
                        self.global_progress_pct_lbl.config(text=f"{pct_disp}%")
                except Exception:
                    pass

        try:
            self.root.after(0, _apply)
        except Exception:
            pass

    def update_global_status(self, text: str, is_active: bool = False, progress: float = None) -> None:
        """Cập nhật text trạng thái, chỉ báo đang chạy và giá trị thanh tiến trình toàn cục tại đáy cửa sổ chính."""
        prog_num = None
        if progress is not None:
            try:
                prog_num = float(progress)
            except (ValueError, TypeError):
                pass
        elif is_active:
            prog_num = 5.0
        level = "warning" if is_active else ("info" if prog_num is None or prog_num < 100 else "success")
        self.set_status(text, level=level, progress=prog_num)

        def _apply_bar():
            if not hasattr(self, 'global_progress_bar') or not self.global_progress_bar.winfo_exists():
                return
            try:
                self.global_progress_bar.stop()
                if prog_num is not None:
                    self.global_progress_bar.config(mode="determinate", value=prog_num)
                    pct_disp = int(round(max(0.0, min(100.0, prog_num))))
                    if hasattr(self, 'global_progress_pct_lbl') and self.global_progress_pct_lbl.winfo_exists():
                        self.global_progress_pct_lbl.config(text=f"{pct_disp}%")
                else:
                    self.global_progress_bar.config(mode="determinate")
            except Exception:
                pass

        try:
            self.root.after(0, _apply_bar)
        except Exception:
            pass


def main():
    root = tk.Tk()
    app = InspectorApp(root)
    root.after(100, app.start_background_tasks)
    root.mainloop()
