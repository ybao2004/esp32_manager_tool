# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Tab 1: Chip Inspector & Hardware Report Mixin
"""
import re
import threading
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

try:
    import serial
except ImportError:
    serial = None

from modules.config import REPORT_FONT_SIZE, FLASH_MANUFACTURERS
from modules.mac_database import (
    ESPRESSIF_OUI_SOURCE, ESPRESSIF_OUI_UPDATED, get_mac_oui, is_espressif_oui
)
from modules.esptool_util import (
    run_esptool_command, parse_esptool_output,
    derive_mac_addresses, get_chip_data, esptool_command_succeeded
)

class InspectorTabMixin:
    """Mixin cung cấp giao diện và logic chẩn đoán phần cứng chip ESP (Thẻ 1)."""

    def create_inspector_tab(self):
        buttons_frame = ttk.LabelFrame(self.inspector_tab, text=" Tác vụ ", padding=(10, 5))
        buttons_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        self.detect_btn = ttk.Button(buttons_frame, text="KIỂM TRA TOÀN DIỆN", command=self.on_detect, style="Accent.TButton")
        self.detect_btn.pack(side="left", padx=(0,5))
        
        ttk.Button(buttons_frame, text="Lưu Báo Cáo", command=self.on_save).pack(side="left", padx=5)
        
        self.clear_inspector_btn = ttk.Button(buttons_frame, text="Xóa", command=lambda: self.on_clear(self.inspector_txt))
        self.clear_inspector_btn.pack(side="left", padx=5)
        
        self.var_debug = tk.BooleanVar(value=False)
        ttk.Checkbutton(buttons_frame, text="Hiển thị Output Thô", variable=self.var_debug).pack(side="left", padx=(15,0))
        
        report_frame = ttk.Frame(self.inspector_tab)
        report_frame.grid(row=1, column=0, sticky="nsew")
        report_frame.columnconfigure(0, weight=1)
        report_frame.rowconfigure(0, weight=1)
        
        self.inspector_txt = tk.Text(report_frame, width=100, wrap="word", font=("Consolas", REPORT_FONT_SIZE), relief="flat", borderwidth=1, state="disabled")
        self.inspector_txt.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        vsb = ttk.Scrollbar(report_frame, orient="vertical", command=self.inspector_txt.yview)
        vsb.grid(row=0, column=1, sticky="ns")
        self.inspector_txt.configure(yscrollcommand=vsb.set)
        self.inspector_txt.tag_configure('header', font=("Consolas", REPORT_FONT_SIZE, 'bold'))

    def log(self, s, tag=None): 
        self.inspector_txt.config(state="normal")
        self.inspector_txt.insert("end", s + "\n", tag)
        self.inspector_txt.see("end")
        self.inspector_txt.config(state="disabled")
        
    def on_clear(self, text_widget, clear_status=True):
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.config(state="disabled")
        if clear_status: 
            self.set_status("Sẵn sàng.", "info")
        
    def on_save(self):
        content = self.inspector_txt.get("1.0", "end").strip()
        if not content: 
            messagebox.showinfo("Lưu", "Không có nội dung để lưu.")
        else:
            chip_name_match = re.search(r"Loại chip:\s*(\S+)", content)
            chip_name = chip_name_match.group(1) if chip_name_match else "ESP_Device"
            default_filename = f"Report_{chip_name}_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.txt"
            fpath = filedialog.asksaveasfilename(initialfile=default_filename, defaultextension=".txt", filetypes=[("Text File","*.txt")])
            if fpath:
                try:
                    with open(fpath, "w", encoding="utf-8") as f: 
                        f.write(content)
                    messagebox.showinfo("Lưu", f"Báo cáo đã được lưu vào {fpath}")
                except Exception as e: 
                    messagebox.showerror("Lỗi Lưu", str(e))

    def on_detect(self):
        if self.is_flashing.is_set() or self.is_detecting.is_set() or getattr(self, "is_connecting", False):
            return
        port = self.port_cb.get().strip()
        if not port: 
            messagebox.showwarning("Thiếu Cổng", "Vui lòng chọn cổng COM.")
            return
        
        if self.serial_connection and self.serial_connection.is_open:
            self.on_serial_disconnect()
            self.is_detecting.set()
            self.detect_btn.config(state="disabled")
            self.serial_toggle_btn.config(state="disabled")
            self.root.after(500, lambda: self._start_detect_thread(port))
        else:
            self._start_detect_thread(port)
            
    def _start_detect_thread(self, port):
        self.on_clear(self.inspector_txt, clear_status=False)
        self.set_status(f"Đang kiểm tra trên {port}...", "info")
        self.detect_btn.config(state="disabled")
        self.serial_toggle_btn.config(state="disabled") 
        self.is_detecting.set()
        threading.Thread(target=self._detect_thread, args=(port, self.baud_cb.get()), daemon=True).start()

    def _detect_thread(self, port, baud):
        has_error = False
        try:
            if baud == 'Tự động':
                detected_baud = self.detect_baud_rate(port)
                if not detected_baud: 
                    raise Exception("Không thể tự động dò tìm Baudrate. Vui lòng chọn thủ công.")
                baud = detected_baud
                self.saved_baudrate = str(baud)
                self.root.after(0, lambda b=baud: self.baud_cb.set(b))
                self.root.after(0, self.save_config)
            outputs = {}
            self.set_status("Đang đọc thông tin chip & flash...", "info")
            outputs['flash_id'] = run_esptool_command(['--port', port, '--baud', baud, 'flash-id'])
            
            flash_out = outputs['flash_id']
            is_conn_error = "fatal error" in flash_out.lower() or "failed to connect" in flash_out.lower()

            # Nếu lệnh flash_id chưa lấy được MAC và không bị lỗi kết nối, fallback đọc thêm read_mac
            if not is_conn_error and not re.search(r"MAC\s*[:=]\s*([0-9A-Fa-f:.]{12,17})", flash_out):
                self.set_status("Đang đọc địa chỉ MAC...", "info")
                outputs['read_mac'] = run_esptool_command(['--port', port, '--baud', baud, 'read-mac'])

            has_error = any(not esptool_command_succeeded(output) for output in outputs.values())
            info = parse_esptool_output(outputs)
            self.root.after(0, self._display_formatted_report, info)
        except Exception as e:
            has_error = True
            error_str = str(e)
            if (serial is not None and isinstance(e, serial.SerialException)) or "could not open port" in error_str.lower():
                self.root.after(0, lambda: messagebox.showerror("Lỗi Truy Cập Cổng COM", f"Không thể mở cổng '{port}'.\nCổng đang bị chiếm. Vui lòng thử lại."))
            else:
                self.root.after(0, self.log, "ĐÃ XẢY RA LỖI KHÁC:\n" + error_str)
        finally:
            self.root.after(0, lambda: self.set_status("Lỗi kiểm tra." if has_error else "Hoàn thành.", "error" if has_error else "success"))
            self.root.after(0, lambda: self.detect_btn.config(state="normal"))
            self.root.after(0, lambda: self.serial_toggle_btn.config(state="normal"))
            self.is_detecting.clear()

    def _display_formatted_report(self, info):
        self.on_clear(self.inspector_txt, clear_status=False)
        if self.var_debug.get():
            self.log("--- OUTPUT THÔ TỪ ESPTOOL " + "-"*48, 'header')
            self.log(info.get('raw', 'Không có output thô.').strip())
            self.log("-" * 72 + "\n")
            
        # Kiểm tra nếu esptool không thể sync được với bootloader
        raw_text = info.get('raw', '')
        if not info.get('chip_name_key') and not info.get('mac') and ("fatal error" in raw_text.lower() or "failed to connect" in raw_text.lower()):
            self.inspector_txt.config(state="normal")
            self.inspector_txt.insert("end", "\nKHÔNG THỂ KẾT NỐI ĐỒNG BỘ VỚI CHIP ESP\n", 'red')
            self.inspector_txt.insert("end", "─" * 65 + "\n", 'red')
            self.inspector_txt.insert("end", "Nguyên nhân: esptool không nhận được phản hồi bootloader từ chip qua cổng Serial.\n\n")
            self.inspector_txt.insert("end", "Các bước khắc phục khuyến nghị:\n", 'header')
            self.inspector_txt.insert("end", " 1. Nhấn và GIỮ nút BOOT (hoặc GPIO0 nối GND) trên mạch ESP trước khi bấm 'Kiểm tra'.\n")
            self.inspector_txt.insert("end", " 2. Kiểm tra cáp USB (đảm bảo cáp có đường truyền Data, không dùng cáp chỉ sạc nguồn).\n")
            self.inspector_txt.insert("end", " 3. Thử đổi Baudrate về 115200 bps thay vì Tự động.\n")
            self.inspector_txt.insert("end", " 4. Kiểm tra xem có phần mềm khác (Arduino IDE, PlatformIO, PuTTY) đang chiếm cổng COM không.\n\n")
            self.inspector_txt.insert("end", "Chi tiết lỗi từ esptool:\n", 'header')
            self.inspector_txt.insert("end", f"  {raw_text.strip()}\n")
            self.inspector_txt.see("end")
            self.inspector_txt.config(state="disabled")
            return

        chip_data = get_chip_data(info.get('chip_name_key'))
        man_id = info.get('flash_manufacturer', '')
        clean_man_id = man_id.lower().replace("0x", "").strip()
        man_name = FLASH_MANUFACTURERS.get(clean_man_id, f"Không rõ (0x{clean_man_id.upper()})" if clean_man_id else "N/A")
        base_mac_hex = info.get('mac')
        base_mac_formatted = ":".join(base_mac_hex[i:i+2] for i in range(0, 12, 2)) if base_mac_hex else None
        
        report_data = [
            ("Thông tin Động (đọc từ chip)", None, 'header'),
            ("  Tên chip đầy đủ", info.get('chip_line', 'N/A'), None),
            ("  Các tính năng (Features)", info.get('features_line', 'N/A'), None),
            ("  Phiên bản Silicon", info.get('revision', 'N/A'), None),
            ("  Tần số thạch anh", info.get('crystal', 'N/A'), None),
            ("Thông tin Chip Flash & PSRAM", None, 'header'),
            ("  Nhà sản xuất Flash", f"{man_name} (0x{clean_man_id.upper()})" if clean_man_id else "N/A", None),
            ("  ID Flash", info.get('flash_device', 'N/A'), None),
            ("  Kích thước Flash", f"{info.get('flash_mb', 0):.2f} MB" if 'flash_mb' in info else "N/A", None),
            ("  Kích thước PSRAM", f"{info['psram_mb']} MB" if 'psram_mb' in info else "Không hỗ trợ", None),
            ("Thông số Kỹ thuật (tra cứu từ CSDL)", None, 'header')
        ]
        
        if chip_data:
            report_data.extend([
                ("  Loại chip", chip_data['name'], None), 
                ("  Kiến trúc CPU", chip_data['architecture'], None),
                ("  Số nhân CPU", chip_data['cores'], None), 
                ("  Tần số CPU hỗ trợ", f"{', '.join(map(str, chip_data['cpu_freq_mhz']))} MHz", None),
                ("  Năng lực tính toán (MIPS)", chip_data.get('mips_max', 'N/A'), 'blue'),
                ("  Kích thước SRAM", f"{chip_data['sram_kb']} KB", None), 
                ("  Kích thước ROM", f"{chip_data['rom_kb']} KB", None)
            ])
        else: 
            report_data.append(("  Loại chip", f"{info.get('chip_name_key', 'Unknown')} (Không có trong CSDL)", 'red'))
        
        report_data.append(("Mạng & Kết nối", None, 'header'))
        report_data.extend([
            ("  Chuẩn Wi-Fi", (chip_data.get('wifi') if chip_data else None) or "Không hỗ trợ", None), 
            ("  Chuẩn Bluetooth", (chip_data.get('bluetooth') if chip_data else None) or "Không hỗ trợ", None)
        ])
        
        if base_mac_hex:
            macs = derive_mac_addresses(base_mac_hex)
            if chip_data and chip_data.get('wifi'): 
                report_data.extend([
                    ("    + MAC Wi-Fi Station", macs.get("MAC Wi-Fi Station"), None), 
                    ("    + MAC Wi-Fi AP", macs.get("MAC Wi-Fi AP"), None)
                ])
            if chip_data and chip_data.get('bluetooth'): 
                report_data.append(("    + MAC Bluetooth", macs.get("MAC Bluetooth"), None))
        else: 
            report_data.append(("  Địa MAC", "Không đọc được", 'red'))
        
        if chip_data and chip_data.get('features'):
            report_data.extend([("Tính năng Nổi bật", None, 'header'), ("", ", ".join(chip_data['features']), None)])
        
        report_data.append(("Phân tích Nguồn gốc", None, 'header'))
        if base_mac_formatted:
            oui = get_mac_oui(base_mac_formatted) or base_mac_formatted[:8]
            if is_espressif_oui(base_mac_formatted):
                report_data.append(("  Nguồn gốc MAC (OUI)", f"Tiền tố được cấp cho Espressif ({oui})", 'green'))
                report_data.append(("", "OUI hỗ trợ nhận diện nhà cung cấp, không phải chứng thư chống giả tuyệt đối.", None))
                report_data.append(("  Chip Nhớ (Flash)", f"Flash {man_name} (ID: {info.get('flash_device', 'N/A')})", 'green' if not man_name.startswith("Không rõ") else 'blue'))
            else: 
                report_data.append(("  Nguồn gốc MAC (OUI)", f"Không thấy {oui} trong CSDL Espressif", 'red'))
            report_data.append(("  CSDL OUI", f"335 tiền tố · cập nhật {ESPRESSIF_OUI_UPDATED} · {ESPRESSIF_OUI_SOURCE}", None))
        else: 
            report_data.append(("  Nguồn gốc MAC (OUI)", "Không thể đối chiếu (thiếu MAC)", 'red'))

        report_data.append(("Ý nghĩa Chỉ số MIPS & Năng lực Xử lý", None, 'header'))
        report_data.extend([
            ("", "• MIPS (Million Instructions Per Second): Đo lường số triệu chỉ thị lệnh vi xử lý có thể thực thi trong 1 giây.", None),
            ("", "• Phân cấp hiệu năng ứng dụng thực tế:", None),
            ("", "  - Dưới 200 MIPS (ESP8266): Tối ưu cho thiết bị IoT đơn giản, đọc cảm biến, truyền nhận HTTP/MQTT.", None),
            ("", "  - 300 - 600 MIPS (ESP32/S3/C3/C6): Xử lý đa nhiệm FreeRTOS, bảo mật SSL/TLS, âm thanh số & AI/ML nhẹ.", None),
            ("", "  - 1800+ MIPS (ESP32-P4): Xử lý giao diện cảm ứng độ nét cao (MIPI-DSI), hình ảnh Camera/H.264 & AI nâng cao.", None)
        ])
        
        key_width = max((len(k) for k, v, t in report_data if k and not k.startswith("---") and k.strip() != ""), default=25) + 2
        
        self.inspector_txt.config(state="normal")
        for key, value, tag in report_data:
            if value is None: 
                self.inspector_txt.insert("end", f"\n{key}\n", tag)
            elif key == "": 
                self.inspector_txt.insert("end", f"  {value}\n", tag)
            else: 
                self.inspector_txt.insert("end", f"{key+':':<{key_width}} {value}\n", tag)
        self.inspector_txt.see("end")
        self.inspector_txt.config(state="disabled")
                
    def detect_baud_rate(self, port):
        test_bauds = ["115200", "74880", "230400", "460800", "921600", "9600"]
        self.set_status(f"Đang dò tìm Baudrate...", "info")
        for baud in test_bauds:
            self.set_status(f"Đang thử @ {baud} bps...", "info")
            try:
                args = ['--port', port, '--baud', str(baud), 'flash-id']
                output = run_esptool_command(args)
                if "A fatal error occurred" not in output and ("Chip is" in output or "Chip type:" in output or "Detecting chip type" in output):
                    self.set_status(f"Đã tìm thấy Baudrate: {baud}", "success")
                    return baud
            except Exception: 
                continue
        return None
