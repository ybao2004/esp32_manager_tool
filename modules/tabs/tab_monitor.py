# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Tab 2: Serial Monitor & IoT Control Mixin
"""
import time
import threading
import codecs
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import serial
except ImportError:
    serial = None

from modules.config import (
    CONTROL_CONFIG, REPORT_FONT_SIZE, DARK_PALETTE, LIGHT_PALETTE,
    NETWORK_COMMANDS, So_dong_serial_toi_da
)

class MonitorTabMixin:
    """Mixin cung cấp giao diện và logic Serial Monitor & Bảng điều khiển IoT (Thẻ 2)."""

    def create_monitor_tab(self):
        self.monitor_tab.rowconfigure(0, weight=1)
        self.monitor_tab.columnconfigure(0, weight=1)
        
        paned_window = ttk.PanedWindow(self.monitor_tab, orient=tk.HORIZONTAL)
        paned_window.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        
        serial_pane = ttk.Frame(paned_window)
        # Sửa thành tỷ lệ 5:1 (Khung Serial lớn gấp 5 lần Khung Điều khiển)
        paned_window.add(serial_pane, weight=5) 
        serial_pane.columnconfigure(0, weight=1)
        serial_pane.rowconfigure(0, weight=1) 
        
        monitor_output_frame = ttk.Frame(serial_pane)
        monitor_output_frame.grid(row=0, column=0, sticky="nsew", pady=2)
        monitor_output_frame.columnconfigure(0, weight=1)
        monitor_output_frame.rowconfigure(0, weight=1)
        
        self.monitor_txt = tk.Text(monitor_output_frame, width=70, wrap="word", font=("Consolas", REPORT_FONT_SIZE), relief="flat", borderwidth=1, state="disabled")
        self.monitor_txt.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        vsb = ttk.Scrollbar(monitor_output_frame, orient="vertical", command=self.monitor_txt.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.monitor_txt.configure(yscrollcommand=vsb.set)
        
        self.monitor_txt.tag_configure('server_rx', foreground='#008000')

        net_ctrl_pane = ttk.Frame(paned_window)
        paned_window.add(net_ctrl_pane, weight=1) 
        net_ctrl_pane.columnconfigure(0, weight=1)
        
        wifi_frame = ttk.LabelFrame(net_ctrl_pane, text=" Cấu hình Mạng ", padding=(5, 5))
        wifi_frame.grid(row=0, column=0, sticky="new", padx=(5,0), pady=(0, 2))
        
        wifi_frame.columnconfigure(0, weight=0) 
        wifi_frame.columnconfigure(1, weight=1)
        wifi_frame.columnconfigure(2, weight=0)
        
        # --- 1. WiFi ---
        ttk.Label(wifi_frame, text="WiFi:").grid(row=0, column=0, sticky="w", padx=(0,5), pady=2)
        self.wifi_cb = ttk.Combobox(wifi_frame, values=[])
        self.wifi_cb.grid(row=0, column=1, columnspan=2, sticky="ew", pady=2)
        
        self.wifi_cb.bind("<<ComboboxSelected>>", self.on_wifi_selected)
        self.wifi_cb.bind("<FocusOut>", self.on_wifi_selected)
        
        # --- 2. Mật khẩu ---
        ttk.Label(wifi_frame, text="Mật khẩu:").grid(row=1, column=0, sticky="w", padx=(0,5), pady=2)
        self.wifi_pass_entry = ttk.Entry(wifi_frame, show="*")
        self.wifi_pass_entry.grid(row=1, column=1, sticky="ew", pady=2)
        
        self.var_show_pwd = tk.BooleanVar(value=False)
        self.cb_show_pwd = ttk.Checkbutton(wifi_frame, text="Hiện", variable=self.var_show_pwd, command=self.toggle_pwd_visibility)
        self.cb_show_pwd.grid(row=1, column=2, padx=(5, 0), sticky="w")
        
        # --- 3. IP Server ---
        ttk.Label(wifi_frame, text="IP Server:").grid(row=2, column=0, sticky="w", padx=(0,5), pady=2)
        self.ip_entry = ttk.Entry(wifi_frame)
        self.ip_entry.insert(0, self.default_ip) 
        self.ip_entry.grid(row=2, column=1, sticky="ew", pady=2)
        
        self.var_auto_connect_server = tk.BooleanVar(value=True)
        self.cb_auto_server = ttk.Checkbutton(wifi_frame, text="auto_connect", variable=self.var_auto_connect_server)
        self.cb_auto_server.grid(row=2, column=2, padx=(5, 0), sticky="w")
        
        # --- 4. Cổng ---
        ttk.Label(wifi_frame, text="Cổng:").grid(row=3, column=0, sticky="w", padx=(0,5), pady=2)
        self.port_entry = ttk.Entry(wifi_frame)
        self.port_entry.insert(0, self.default_port) 
        self.port_entry.grid(row=3, column=1, columnspan=2, sticky="ew", pady=2)
        
        # --- 5. Nút bấm Mạng ---
        buttons_wifi_frame = ttk.Frame(wifi_frame)
        buttons_wifi_frame.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 5))
        
        self.btn_scan_wifi = ttk.Button(buttons_wifi_frame, text="Quét WiFi", command=self.on_wifi_scan, width=12)
        self.btn_scan_wifi.grid(row=0, column=0, padx=(0, 5), sticky="w")
        
        self.btn_connect_wifi = ttk.Button(buttons_wifi_frame, text="Kết nối WiFi", command=self.toggle_wifi_connection, width=12)
        self.btn_connect_wifi.grid(row=0, column=1, padx=(0, 5), sticky="w")
        
        self.btn_connect_server = ttk.Button(buttons_wifi_frame, text="Kết nối Server", command=self.toggle_server_connection, width=14)
        self.btn_connect_server.grid(row=0, column=2, padx=(0, 5), sticky="w")
        
        # --- 6. Trạng thái kết nối ---
        self.wifi_status_lbl = tk.Label(wifi_frame, text="Chưa kết nối")
        self.wifi_status_lbl.grid(row=5, column=0, columnspan=3, sticky="w", padx=(0,5), pady=(2,0))
        
        ctrl_frame = ttk.LabelFrame(net_ctrl_pane, text=" Bảng Điều khiển ", padding=(5, 5))
        ctrl_frame.grid(row=1, column=0, sticky="nsew", padx=(5,0), pady=(2, 0))
        ctrl_frame.columnconfigure(0, weight=1)
        ctrl_frame.columnconfigure(1, weight=1)
        ctrl_frame.columnconfigure(2, weight=1) 
        
        self.f_buttons = [] 
        for index, i in enumerate(sorted(CONTROL_CONFIG)): 
            btn_text = self.control_labels.get(i, f"F{i}")
            btn = ttk.Button(ctrl_frame, text=btn_text, command=lambda x=i: self.on_control_click(x))
            btn.grid(row=index // 3, column=index % 3, sticky="ew", padx=2, pady=2, ipady=1)
            self.f_buttons.append(btn) 

        input_frame = ttk.LabelFrame(net_ctrl_pane, text=" Gửi dữ liệu Serial ", padding=(5,5))
        input_frame.grid(row=2, column=0, sticky="ew", padx=(5,0), pady=(10, 0)) 
        input_frame.columnconfigure(0, weight=1)
        
        self.serial_input = tk.Text(input_frame, height=5, width=15, font=("Consolas", REPORT_FONT_SIZE), wrap="word") 
        self.serial_input.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=0, pady=2)
        self.serial_input.bind("<Shift-Return>", self.on_serial_newline)
        self.serial_input.bind("<Return>", self.on_serial_send)
        input_frame.rowconfigure(0, weight=1)
        
        self.var_crlf = tk.BooleanVar(value=True)
        self.cb_crlf = ttk.Checkbutton(input_frame, text="Thêm \\r\\n", variable=self.var_crlf)
        self.cb_crlf.grid(row=1, column=0, sticky="w", pady=(2,0))

        buttons_send_frame = ttk.Frame(input_frame)
        buttons_send_frame.grid(row=1, column=1, sticky="e", pady=(2,0))

        self.reset_btn = ttk.Button(buttons_send_frame, text="Reset ESP", command=self.on_reset_esp)
        self.reset_btn.pack(side="left", padx=(0, 5))

        self.send_btn = ttk.Button(buttons_send_frame, text="Gửi", command=self.on_serial_send)
        self.send_btn.pack(side="left")

        self.req_status_lbl = tk.Label(net_ctrl_pane, text="Sẵn sàng.", font=("Segoe UI", 9, "italic"))
        self.req_status_lbl.grid(row=3, column=0, sticky="w", padx=(5,0), pady=(5,0))

    def on_wifi_selected(self, event=None):
        ssid = self.wifi_cb.get().strip()
        if hasattr(self, 'wifi_pass_entry') and self.wifi_pass_entry.winfo_exists():
            orig_state = str(self.wifi_pass_entry.cget("state"))
            if orig_state == "disabled":
                self.wifi_pass_entry.config(state="normal")
            self.wifi_pass_entry.delete(0, tk.END)
            if ssid and ssid in self.saved_wifi_credentials:
                self.wifi_pass_entry.insert(0, self.saved_wifi_credentials[ssid])
            if orig_state == "disabled":
                self.wifi_pass_entry.config(state="disabled")
            self.toggle_pwd_visibility()

    def toggle_pwd_visibility(self):
        if self.var_show_pwd.get():
            self.wifi_pass_entry.config(show="")
        else:
            self.wifi_pass_entry.config(show="*")

    def toggle_serial_connection(self):
        if self.serial_connection and self.serial_connection.is_open: 
            self.on_serial_disconnect()
        else: 
            self.on_serial_connect()

    def on_serial_connect(self):
        if self.is_flashing.is_set() or self.is_detecting.is_set() or getattr(self, "is_connecting", False):
            return
        self.is_connecting = True
        port = self.port_cb.get().strip()
        baud = self.baud_cb.get().strip()
        if not port: 
            self.is_connecting = False
            messagebox.showwarning("Thiếu Cổng", "Vui lòng chọn cổng COM.")
            return
        
        self.serial_toggle_btn.config(state="disabled")
        threading.Thread(target=self._connect_serial_thread, args=(port, baud), daemon=True).start()

    def _connect_serial_thread(self, port, baud):
        try:
            if baud == "Tự động":
                self.root.after(0, lambda: self.set_status(f"Đang tự động dò Baudrate cho {port}...", "info"))
                detected_baud = self.detect_baud_rate(port)
                if not detected_baud:
                    self.root.after(0, lambda: messagebox.showerror("Lỗi", "Không thể tự dò Baudrate. Vui lòng chọn thủ công."))
                    self.root.after(0, lambda: self.set_status("Lỗi: Dò Baudrate thất bại.", "error"))
                    self.root.after(0, lambda: self.serial_toggle_btn.config(state="normal"))
                    return
                baud = detected_baud
                self.root.after(0, lambda b=baud: self.baud_cb.set(b))

            self.root.after(0, lambda: self.set_status(f"Đang kết nối {port} @ {baud} bps...", "info"))
            if serial is None:
                raise RuntimeError("Thư viện 'pyserial' chưa được cài đặt.")
            self.serial_connection = serial.Serial(port, int(baud), timeout=0.1, write_timeout=1)
            self.saved_baudrate = str(baud)
            self.root.after(0, self._reset_monitor_line_state)
            
            self.root.after(0, lambda: self.set_status(f"Kết nối thành công! Đang đọc trên {port} @ {baud} bps", "success"))
            self.root.after(0, lambda: self.detect_btn.config(state="disabled"))
            self.root.after(0, lambda: self.serial_toggle_btn.config(text="Ngắt kết nối", state="normal"))
            self.root.after(0, lambda: self.monitor_txt.config(state="normal"))
            self.root.after(0, lambda: self._set_mcu_dependent_ui_state("normal"))
            self.root.after(0, self.save_config)
            
            # Each connection owns its cancellation event; never revive an old reader.
            self.stop_serial_thread = threading.Event()
            self.serial_thread = threading.Thread(
                target=self._serial_read_thread,
                args=(self.serial_connection, self.stop_serial_thread), daemon=True)
            self.serial_thread.start()

        except Exception as e:
            error_message = f"Không thể mở cổng {port}.\nLỗi: {e}"
            self.root.after(0, lambda msg=error_message: messagebox.showerror("Lỗi Kết nối", msg))
            self.serial_connection = None
            self.root.after(0, lambda: self.set_status("Lỗi: kết nối Serial thất bại.", "error"))
            self.root.after(0, lambda: self.serial_toggle_btn.config(state="normal"))
            
        finally:
            self.is_connecting = False

    def on_serial_disconnect(self):
        self.is_wifi_connected = False
        self.is_server_connected = False
        self.btn_connect_wifi.config(text="Kết nối WiFi")
        self.btn_connect_server.config(text="Kết nối Server")
        
        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        self.wifi_status_lbl.config(text="Chưa kết nối", fg=p["error"])
        
        if self.serial_connection: 
            self.stop_serial_thread.set()
            try:
                self.serial_connection.close()
            except Exception:
                pass
            self.serial_connection = None
            
        self.set_status("Đã ngắt kết nối.", "info")
        self.detect_btn.config(state="normal")
        self.serial_toggle_btn.config(text="Kết nối")
        self._set_mcu_dependent_ui_state("disabled")
        
    def _reset_monitor_line_state(self):
        self.is_new_line = True
        self._current_line_is_server_rx = False

    def _serial_read_thread(self, connection, stop_event):
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        feedback_buffer = ""
        while not stop_event.is_set() and connection.is_open:
            try:
                data = connection.read(1024)
                if data:
                    text = decoder.decode(data)
                    feedback_buffer += text
                    lines = []
                    while '\n' in feedback_buffer:
                        line, feedback_buffer = feedback_buffer.split('\n', 1)
                        lines.append(line.strip())
                    if len(feedback_buffer) > 4096:
                        feedback_buffer = feedback_buffer[-2048:]
                    self.root.after(0, self._deliver_serial_chunk, connection, stop_event, text, lines)
            except Exception:
                if not stop_event.is_set():
                    self.root.after(0, self._serial_session_failed, connection, stop_event)
                break

    def _deliver_serial_chunk(self, connection, stop_event, text, lines):
        if self.serial_connection is not connection or stop_event.is_set():
            return
        self.append_to_monitor(text)
        for line in lines:
            if self.serial_connection is not connection or stop_event.is_set():
                break
            self.process_esp_feedback(line)

    def _serial_session_failed(self, connection, stop_event):
        if self.serial_connection is connection and not stop_event.is_set():
            self.on_serial_disconnect()
            messagebox.showerror("Lỗi", "Mất kết nối với thiết bị đột ngột.")

    def process_esp_feedback(self, line):
        if not line.startswith("RES:"): return
        
        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        
        if line == "RES:SYSTEM_READY":
            self.is_wifi_connected = False
            self.is_server_connected = False
            self.btn_connect_wifi.config(text="Kết nối WiFi")
            self.btn_connect_server.config(text="Kết nối Server")
            self.wifi_status_lbl.config(text="Chưa kết nối", fg=p["error"])
            self.set_status("Cảnh báo: ESP32 vừa khởi động lại. Vui lòng nối mạng.", "warning")
            return
            
        if line.startswith("RES:WIFI|"):
            parts = line.split("|", 4)
            if len(parts) >= 2:
                ssid = parts[1]
                if ssid not in self.scanned_networks:
                    self.scanned_networks.append(ssid)
                    self.wifi_cb.config(values=self.scanned_networks)
            return
            
        if line == "RES:SCAN_START":
            self.scanned_networks = []
            current_typed = self.wifi_cb.get()
            self.wifi_cb.config(values=[])
            self.wifi_cb.set(current_typed)
            self.set_status("Đang cập nhật danh sách WiFi...", "info")
            
        elif line == "RES:WIFI_CONNECTED":
            self.is_wifi_connected = True
            self.btn_connect_wifi.config(text="Ngắt WiFi")
            self.wifi_status_lbl.config(text="Đã kết nối WiFi", fg=p["success"])
            self.set_status("Thành công: ESP32 đã kết nối WiFi!", "success")
            
            ssid = self.wifi_cb.get().strip()
            pwd = self.wifi_pass_entry.get()
            if ssid:
                self.saved_wifi_credentials[ssid] = pwd
                self.save_config()
            
            if self.var_auto_connect_server.get():
                self.root.after(1000, self.on_server_connect) 
                
        elif line == "RES:WIFI_FAIL":
            self.is_server_connected = False
            self.btn_connect_server.config(text="Kết nối Server")
            self.is_wifi_connected = False
            self.btn_connect_wifi.config(text="Kết nối WiFi")
            self.wifi_status_lbl.config(text="Sai Pass hoặc mất sóng", fg=p["error"])
            self.set_status("Lỗi: ESP32 không thể vào WiFi.", "error")
            
        elif line == "RES:WIFI_DISCONNECTED":
            self.is_server_connected = False
            self.btn_connect_server.config(text="Kết nối Server")
            self.is_wifi_connected = False
            self.btn_connect_wifi.config(text="Kết nối WiFi")
            self.wifi_status_lbl.config(text="Chưa kết nối", fg=p["error"])
            self.set_status("Thành công: ESP32 đã ngắt WiFi.", "success")
            
        elif line == "RES:SERVER_CONNECTED":
            self.is_server_connected = True
            self.btn_connect_server.config(text="Ngắt Server")
            self.wifi_status_lbl.config(text="Đã kết nối WiFi & Server", fg=p["success"])
            self.set_status("Thành công: ESP32 đã nối TCP Server!", "success")
            
        elif line == "RES:SERVER_FAIL:NO_WIFI":
            self.is_server_connected = False
            self.btn_connect_server.config(text="Kết nối Server")
            self.wifi_status_lbl.config(text="Lỗi: Cần nối WiFi trước", fg=p["error"])
            self.set_status("Lỗi: Không thể kết nối Server khi chưa có WiFi.", "error")
            
        elif line == "RES:SERVER_FAIL":
            self.is_server_connected = False
            self.btn_connect_server.config(text="Kết nối Server")
            self.wifi_status_lbl.config(text="Lỗi nối Server", fg=p["warning"])
            self.set_status("Lỗi: ESP32 không thể nối Server (Timeout).", "error")
            
        elif line == "RES:SERVER_DISCONNECTED":
            self.is_server_connected = False
            self.btn_connect_server.config(text="Kết nối Server")
            self.wifi_status_lbl.config(text="Đã kết nối WiFi", fg=p["success"])
            self.set_status("Thành công: ESP32 đã ngắt TCP Server.", "success")
            
        elif line.startswith("RES:CMD_SENT_TO_SERVER:"):
            cmd_sent = line.split(":", 2)[2]
            self.set_status(f"Thành công: Đã đẩy lệnh '{cmd_sent}' lên Server TCP.", "success")
            
        elif line == "RES:SERVER_NOT_CONNECTED":
            self.set_status("Cảnh báo: Lệnh chỉ chạy ở ESP32 (Chưa kết nối TCP Server).", "warning")
            
    def append_to_monitor(self, text):
        self.monitor_txt.config(state="normal")
        
        lines = text.split('\n')
        for i, line in enumerate(lines):
            is_server_rx = line.startswith("[SERVER_RX]") or (not self.is_new_line and getattr(self, '_current_line_is_server_rx', False))
            if self.is_new_line:
                self._current_line_is_server_rx = line.startswith("[SERVER_RX]")
                is_server_rx = self._current_line_is_server_rx

            tag_to_use = 'server_rx' if is_server_rx else None

            if self.var_timestamp.get() and self.is_new_line and line:
                timestamp = datetime.now().strftime("[%H:%M:%S.%f")[:-3] + "] "
                self.monitor_txt.insert("end", timestamp, tag_to_use)
            
            if line:
                self.monitor_txt.insert("end", line, tag_to_use)
            
            if i < len(lines) - 1:
                self.monitor_txt.insert("end", "\n", tag_to_use)
                self.is_new_line = True
                self._current_line_is_server_rx = False
            else:
                self.is_new_line = text.endswith('\n')
                if self.is_new_line:
                    self._current_line_is_server_rx = False
            
        current_lines = int(self.monitor_txt.index('end-1c').split('.')[0])
        if current_lines > So_dong_serial_toi_da: 
            self.monitor_txt.delete("1.0", "500.0")

        if self.var_autoscroll.get(): 
            self.monitor_txt.see("end")
        self.monitor_txt.config(state="disabled")
        
    def on_serial_send(self, event=None):
        data = self.serial_input.get("1.0", "end-1c")
        
        if not data.strip(): 
            if event: return "break" 
            return 
        
        self._send_serial_command(data, f"Đang gửi Serial: {data.strip()}...", "info")
        self.serial_input.delete("1.0", "end")
        if event: return "break" 

    def _send_serial_command(self, data_to_send, status_description="", status_level="info"):
        if self.serial_connection and self.serial_connection.is_open:
            if self.var_crlf.get() and not data_to_send.endswith("\n"): 
                data_to_send += "\r\n"
            try:
                self.serial_connection.write(data_to_send.encode('utf-8'))
                self.set_status(status_description, status_level)
            except Exception as e: 
                messagebox.showerror("Lỗi Gửi", f"Không thể gửi dữ liệu.\nLỗi: {e}")
        else:
            self.set_status("Lỗi: Chưa kết nối Serial!", "error")

    def on_wifi_scan(self):
        cmd = NETWORK_COMMANDS.get("SCAN_WIFI", "SCAN_WIFI")
        self._send_serial_command(cmd, "Đã gửi lệnh Quét WiFi...", "info")
        
    def toggle_wifi_connection(self):
        if not self.is_wifi_connected: 
            self.on_wifi_connect()
        else: 
            self.on_wifi_disconnect()

    def toggle_server_connection(self):
        if not self.is_server_connected: 
            self.on_server_connect()
        else: 
            self.on_server_disconnect()

    def on_wifi_connect(self):
        ssid = self.wifi_cb.get().strip()
        pwd = self.wifi_pass_entry.get()
        
        if not ssid:
            messagebox.showwarning("Thiếu thông tin", "Vui lòng chọn hoặc nhập tên WiFi (SSID) trước khi kết nối!")
            return
            
        set_cmd = f"SET_WIFI|{ssid}|{pwd}"
        self._send_serial_command(set_cmd, "Đang gửi cấu hình mạng...", "info")
        
        connect_cmd = NETWORK_COMMANDS.get("CONNECT_WIFI", "CONNECT_WIFI")
        self.root.after(100, lambda: self._send_serial_command(connect_cmd, "Đang chờ ESP32 nối WiFi...", "info"))
        
        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        self.wifi_status_lbl.config(text="Đang chờ kết nối...", fg=p["warning"]) 
        
    def on_wifi_disconnect(self):
        cmd = NETWORK_COMMANDS.get("DISCONNECT_WIFI", "DISCONNECT_WIFI")
        self._send_serial_command(cmd, "Đang chờ ESP32 ngắt WiFi...", "info")

    def on_server_connect(self):
        if not self.is_wifi_connected:
            messagebox.showwarning("Cảnh báo", "Vui lòng kết nối WiFi trước khi kết nối Server!")
            return
        
        ip = self.ip_entry.get().strip()
        port = self.port_entry.get().strip()
        
        if not ip:
            messagebox.showwarning("Cảnh báo", "Vui lòng nhập địa chỉ IP hoặc Hostname Server!")
            return
            
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            messagebox.showwarning("Cảnh báo", "Cổng Server không hợp lệ! Vui lòng nhập số trong khoảng 1 - 65535.")
            return
        
        set_cmd = f"SET_SERVER|{ip}|{port}"
        self._send_serial_command(set_cmd, "Đang gửi cấu hình Server...", "info")
        
        connect_cmd = NETWORK_COMMANDS.get("CONNECT_SERVER", "CONNECT_SERVER")
        self.root.after(100, lambda: self._send_serial_command(connect_cmd, f"Đang chờ ESP32 nối Server ({ip}:{port})...", "info"))
        
        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        self.wifi_status_lbl.config(text="Đang chờ nối Server...", fg=p["warning"])

    def on_server_disconnect(self):
        cmd = NETWORK_COMMANDS.get("DISCONNECT_SERVER", "DISCONNECT_SERVER")
        self._send_serial_command(cmd, "Đang chờ ESP32 ngắt Server...", "info")

    def on_control_click(self, f_number):
        command_to_send = self.control_commands.get(f_number, f"F{f_number}_PRESSED")
        self._send_serial_command(command_to_send, f"Đang gửi lệnh {command_to_send} (F{f_number})...", "info")

    def on_reset_esp(self):
        """Gửi lệnh RESET phần mềm và kích hoạt xung DTR/RTS để reset phần cứng ESP."""
        if not (self.serial_connection and self.serial_connection.is_open):
            self.set_status("Lỗi: Chưa kết nối Serial!", "error")
            return

        reset_cmd = "RESET"
        self._send_serial_command(reset_cmd, "Đang gửi tín hiệu Reset ESP...", "warning")

        def trigger_hardware_reset():
            try:
                time.sleep(0.05)
                self.serial_connection.setDTR(False)
                self.serial_connection.setRTS(True)
                time.sleep(0.1)
                self.serial_connection.setRTS(False)
                self.serial_connection.setDTR(False)
                self.root.after(0, lambda: self.set_status("Đã kích hoạt Reset ESP thành công!", "success"))
            except Exception as e:
                error_message = f"Reset phần cứng gặp lỗi: {e}"
                self.root.after(0, lambda msg=error_message: self.set_status(msg, "warning"))

        threading.Thread(target=trigger_hardware_reset, daemon=True).start()
