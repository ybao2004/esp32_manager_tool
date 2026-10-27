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
from modules.serial_util import list_com_ports_local

from modules.tabs.tab_inspector import InspectorTabMixin
from modules.tabs.tab_monitor import MonitorTabMixin
from modules.tabs.tab_flasher import FlasherTabMixin
from modules.tabs.tab_partition import PartitionTabMixin
from modules.dialogs.settings_dialog import SettingsDialogMixin

class InspectorApp(
    InspectorTabMixin,
    MonitorTabMixin,
    FlasherTabMixin,
    PartitionTabMixin,
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
                    ignored_ports = config.get("ignored_com_ports", [])
                    self.ignored_com_ports = [str(port) for port in ignored_ports] if isinstance(ignored_ports, list) else []
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
            self.saved_auto_select_new = True
            if hasattr(self, 'var_auto_select_new'):
                self.var_auto_select_new.set(True)
            
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

    def create_widgets(self):
        self.main_frame = ttk.Frame(self.root, padding=5)
        self.main_frame.grid(sticky="nsew", row=0, column=0)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=1)
        self.main_frame.rowconfigure(1, weight=1)
        
        self.controls_frame = ttk.LabelFrame(self.main_frame, text=" Cài đặt chung & Điều khiển Serial ", padding=(5, 5))
        self.controls_frame.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        
        ttk.Label(self.controls_frame, text="COM Port:").grid(row=0, column=0, sticky="w", pady=2, padx=(0, 5))
        self.port_cb = ttk.Combobox(self.controls_frame, values=[], width=12, state="readonly", postcommand=self.refresh_ports_dropdown)
        self.port_cb.grid(row=0, column=1, sticky="w")
        self.port_cb.bind("<<ComboboxSelected>>", self.on_port_selected)
        
        self.var_auto_scan = tk.BooleanVar(value=True)
        ttk.Checkbutton(self.controls_frame, text="Tự động quét", variable=self.var_auto_scan).grid(row=0, column=2, padx=(5, 5))
        
        self.var_auto_select_new = tk.BooleanVar(value=self.saved_auto_select_new)
        ttk.Checkbutton(self.controls_frame, text="Ưu tiên cổng mới", variable=self.var_auto_select_new, command=self.save_config).grid(row=0, column=3, padx=(5, 10))
        
        ttk.Label(self.controls_frame, text="Baudrate:").grid(row=0, column=4, sticky="w", padx=(0, 5))
        self.baud_cb = ttk.Combobox(self.controls_frame, values=COMMON_BAUDS, width=10)
        self.baud_cb.set(self.saved_baudrate if self.saved_baudrate in COMMON_BAUDS else "Tự động") 
        self.baud_cb.grid(row=0, column=5, sticky="w")
        self.baud_cb.bind("<<ComboboxSelected>>", self.on_baud_selected)
        
        separator = ttk.Separator(self.controls_frame, orient='vertical')
        separator.grid(row=0, column=6, sticky='ns', padx=10, pady=2)
        
        self.serial_toggle_btn = ttk.Button(self.controls_frame, text="Kết nối", command=self.toggle_serial_connection)
        self.serial_toggle_btn.grid(row=0, column=7, padx=(0,5))
        
        self.clear_monitor_btn = ttk.Button(self.controls_frame, text="Xóa màn hình", command=lambda: self.on_clear(self.monitor_txt))
        self.clear_monitor_btn.grid(row=0, column=8, padx=5)
        
        self.var_autoscroll = tk.BooleanVar(value=Tu_dong_cuon)
        ttk.Checkbutton(self.controls_frame, text="Tự động cuộn", variable=self.var_autoscroll).grid(row=0, column=9, padx=(10,0))
        
        self.var_timestamp = tk.BooleanVar(value=Them_dau_thoi_gian)
        ttk.Checkbutton(self.controls_frame, text="Thêm Dấu thời gian", variable=self.var_timestamp).grid(row=0, column=10, padx=(5, 15))
        
        self.settings_btn = ttk.Button(self.controls_frame, text="Cài đặt", command=self.open_settings_dialog)
        self.settings_btn.grid(row=0, column=11, sticky="e")
        self.controls_frame.columnconfigure(11, weight=1) 
        
        self.notebook = ttk.Notebook(self.main_frame)
        self.notebook.grid(row=1, column=0, sticky="nsew", pady=5)
        self.inspector_tab = ttk.Frame(self.notebook)
        self.monitor_tab = ttk.Frame(self.notebook)
        self.flasher_tab = ttk.Frame(self.notebook)
        self.partition_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.inspector_tab, text=' Kiểm tra Phần cứng ')
        self.notebook.add(self.monitor_tab, text=' Serial Monitor & Điều khiển ')
        self.notebook.add(self.flasher_tab, text=' Nạp Flash Firmware (.bin) ')
        self.notebook.add(self.partition_tab, text=' Phân vùng Bộ nhớ (Partition Wizard) ')
        
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
        self.set_status("Sẵn sàng.", "info")

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
        if not self.ignored_com_ports:
            return raw_ports
        ignored = {x.strip().upper() for x in self.ignored_com_ports if x.strip()}
        return [p for p in raw_ports if p.strip().upper() not in ignored]

    def _check_and_update_ports(self, new_ports):
        if not self.root.winfo_exists():
            return
        if self.var_auto_scan.get() and not self.is_detecting.is_set() and not self.is_flashing.is_set():
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
                
    def on_closing(self):
        if self.is_flashing.is_set() or self.is_detecting.is_set() or getattr(self, "is_connecting", False):
            messagebox.showwarning("Tác vụ chưa hoàn tất", "Hãy đợi tác vụ hiện tại hoàn tất trước khi đóng ứng dụng.")
            return
        self.save_config()
        self.on_serial_disconnect()
        self.stop_scan.set()
        self.root.destroy()

    def set_status(self, s, level="info"): 
        self.current_status_level = level
        if hasattr(self, 'req_status_lbl') and self.req_status_lbl.winfo_exists():
            p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
            color_map = {
                "info": p["disabled_fg"], "success": p["success"],
                "error": p["error"], "warning": p["warning"]
            }
            color = color_map.get(level, p["disabled_fg"])
            self.root.after(0, lambda: self.req_status_lbl.config(text=s, fg=color))


def main():
    root = tk.Tk()
    app = InspectorApp(root)
    root.after(100, app.start_background_tasks)
    root.mainloop()
