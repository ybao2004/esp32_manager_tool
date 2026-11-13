# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Tab 1: Chip Inspector & Hardware Report Mixin
"""
import re
import threading
from datetime import datetime
from modules.ui import dialogs_service as messagebox
from modules.ui import dialogs_service as filedialog

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
    derive_mac_addresses, get_chip_data, esptool_command_succeeded,
    esptool_deep_inspection_context, decode_flash_device_id
)


class InspectorTabMixin:
    """Mixin cung cấp giao diện và logic chẩn đoán phần cứng chip ESP (Thẻ 1)."""
    detect_thread = None

    def create_inspector_tab(self):
        """Đã chuyển toàn bộ dựng giao diện sang InspectorPage thuần PyQt6."""
        return

    def log(self, s, tag=None): 
        self.inspector_txt.config(state="normal")
        self.inspector_txt.insert("end", s + "\n", tag)
        self.inspector_txt.see("end")
        self.inspector_txt.config(state="disabled")
        
    def on_clear(self, text_widget, clear_status=True):
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.config(state="disabled")
        if text_widget is getattr(self, "inspector_txt", None) and hasattr(self, "page_inspector"):
            try:
                self.page_inspector.reset_kpi_and_tables()
            except Exception:
                pass
        if clear_status: 
            self.set_status("Sẵn sàng.", "info", progress=0, task_label="Tiến trình: Sẵn sàng")
        
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
        self.is_detecting.set()
        if hasattr(self, 'set_global_busy_state'):
            self.set_global_busy_state(True, "kiểm tra thông tin phần cứng")
        else:
            self.detect_btn.config(state="disabled")
            self.serial_toggle_btn.config(state="disabled")
        self.set_status(f"Đang kiểm tra trên {port}...", "info", progress=0, task_label=f"Kiểm tra phần cứng ({port})")
        self.detect_thread = threading.Thread(target=self._detect_thread, args=(port, self.baud_cb.get()), daemon=True)
        self.detect_thread.start()

    def _post_detect_status(self, message: str, level: str = "info", progress=None):
        """Gửi cập nhật thanh trạng thái về luồng giao diện chính an toàn."""
        try:
            if getattr(self, "root", None) and hasattr(self.root, "after"):
                self.root.after(0, lambda m=message, lv=level, p=progress: self.set_status(m, lv, progress=p, task_label="Kiểm tra phần cứng"))
            else:
                self.set_status(message, level, progress=progress, task_label="Kiểm tra phần cứng")
        except Exception:
            pass

    def _rerender_inspector_report(self):
        """Vẽ lại báo cáo phần cứng từ dữ liệu đã quét gần nhất khi bật/tắt tùy chọn hiển thị."""
        cached = getattr(self, "_last_inspected_info", None)
        if cached:
            self._display_formatted_report(cached)

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
            self._post_detect_status("Đang đọc toàn diện thông tin chip, flash, firmware & boot log...", "info", progress=20)

            def on_inspect_stream(line):
                l_str = str(line)
                if "Connecting" in l_str:
                    self._post_detect_status("Đang đồng bộ kết nối Bootloader...", "info", progress=25)
                elif "Chip type:" in l_str or "Connected to" in l_str:
                    self._post_detect_status("Đã kết nối chip, đang nạp Stub Flasher...", "info", progress=35)
                elif "Flash Memory Information" in l_str or "Detected flash size" in l_str:
                    self._post_detect_status("Đang đọc thông tin Flash & JEDEC...", "info", progress=45)
                elif "Security Information" in l_str or "Flash Status & SFDP" in l_str:
                    self._post_detect_status("Đang đọc bảo mật phần cứng & SFDP...", "info", progress=55)
                elif "eFuse & Silicon Details" in l_str:
                    self._post_detect_status("Đang đọc thanh ghi eFuse & định danh Silicon...", "info", progress=65)
                elif "Partition Table" in l_str or "Bootloader Image" in l_str:
                    self._post_detect_status("Đang đọc Bootloader & Bảng phân vùng Flash...", "info", progress=75)
                elif "Application Firmware Information" in l_str:
                    self._post_detect_status("Đang phân tích Header & Metadata của Firmware...", "info", progress=85)
                elif "Hard resetting" in l_str:
                    self._post_detect_status("Đang thu thập nhật ký khởi động (Boot Log)...", "info", progress=92)

            with esptool_deep_inspection_context(
                capture_boot_log=True,
                boot_log_duration=2.2,
                progress_callback=on_inspect_stream
            ):
                outputs['flash_id'] = run_esptool_command(['--port', port, '--baud', baud, 'flash-id'])
            
            flash_out = outputs['flash_id']
            is_conn_error = "fatal error" in flash_out.lower() or "failed to connect" in flash_out.lower()

            # Nếu lệnh flash_id chưa lấy được MAC và không bị lỗi kết nối, fallback đọc thêm read_mac
            if not is_conn_error and not re.search(r"MAC\s*[:=]\s*([0-9A-Fa-f:.]{12,17})", flash_out):
                self._post_detect_status("Đang đọc địa chỉ MAC...", "info", progress=95)
                outputs['read_mac'] = run_esptool_command(['--port', port, '--baud', baud, 'read-mac'])

            has_error = any(not esptool_command_succeeded(output) for output in outputs.values())
            info = parse_esptool_output(outputs)
            self.root.after(0, self._display_formatted_report, info)
        except Exception as e:
            has_error = True
            error_str = str(e)
            if (serial is not None and isinstance(e, serial.SerialException)) or "could not open port" in error_str.lower():
                msg = (
                    f"Không thể mở cổng '{port}'.\n"
                    f"Cổng đang bị chiếm hoặc không phản hồi.\n\n"
                    "Hướng dẫn xử lý sự cố:\n"
                    "1. Kiểm tra xem có phần mềm khác (Arduino IDE, PlatformIO, PuTTY, Cura...) đang kết nối cổng này không.\n"
                    "2. Rút cáp USB cắm lại hoặc đổi sang cổng USB khác trên máy tính.\n"
                    "3. Đảm bảo driver cổng COM (CH340, CP210x, FTDI) đã được cài đặt chính xác."
                )
                self.root.after(0, lambda: messagebox.showerror("Lỗi Truy Cập Cổng COM", msg))
            else:
                self.root.after(0, self.log, "ĐÃ XẢY RA LỖI KHÁC:\n" + error_str)
        finally:
            final_prog = 0 if has_error else 100
            self.root.after(0, lambda p=final_prog: self.set_status("Lỗi kiểm tra." if has_error else "Hoàn thành.", "error" if has_error else "success", progress=p))
            if hasattr(self, 'set_global_busy_state'):
                self.root.after(0, lambda: self.set_global_busy_state(False))
            else:
                self.root.after(0, lambda: self.detect_btn.config(state="normal"))
                self.root.after(0, lambda: self.serial_toggle_btn.config(state="normal"))
            self.is_detecting.clear()

    def _display_formatted_report(self, info):
        self._last_inspected_info = info
        self.on_clear(self.inspector_txt, clear_status=False)
        if self.var_debug.get():
            self.log("--- OUTPUT THÔ TỪ ESPTOOL & BOOT LOG " + "-" * 37, 'header')
            self.log(info.get('raw', 'Không có output thô.').strip())
            self.log("-" * 74 + "\n")
            
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
        if clean_man_id:
            known_man = FLASH_MANUFACTURERS.get(clean_man_id)
            man_display = f"{known_man} (0x{clean_man_id.upper()})" if known_man else f"Không rõ (0x{clean_man_id.upper()})"
            man_short = known_man if known_man else f"Không rõ (0x{clean_man_id.upper()})"
        else:
            man_display = "N/A"
            man_short = "N/A"

        base_mac_raw = (info.get('mac') or "").replace(":", "").replace("-", "").strip()
        base_mac_hex = base_mac_raw if len(base_mac_raw) == 12 else None
        base_mac_formatted = ":".join(base_mac_hex[i:i+2] for i in range(0, 12, 2)) if base_mac_hex else None

        # --- 1. THÔNG TIN ĐỘNG & ĐỊNH DANH SILICON ---
        report_data = [
            ("Thông tin Động & Silicon (đọc từ chip)", None, 'header'),
            ("  Tên chip đầy đủ", info.get('chip_line', 'N/A'), None),
            ("  Các tính năng (Features)", info.get('features_line', 'N/A'), None),
            ("  Phiên bản Silicon", info.get('revision', 'N/A'), None),
            ("  Tần số thạch anh", info.get('crystal', 'N/A'), None),
        ]
        if info.get("cpu_freq_runtime"):
            report_data.append(("  Xung nhịp CPU thực tế", info["cpu_freq_runtime"], None))
        if info.get("usb_mode"):
            usb_str = info["usb_mode"]
            if info.get("usb_vid_pid"):
                usb_str += f" ({info['usb_vid_pid']})"
            report_data.append(("  Chế độ giao tiếp USB", usb_str, None))
        if info.get("console_uart_pins"):
            report_data.append(("  Chân Console UART", info["console_uart_pins"], None))
        if info.get("unique_id_128"):
            report_data.append(("  Mã định danh Unique ID", info["unique_id_128"], None))
        if info.get("efuse_pkg_version") or info.get("efuse_blk_version"):
            pkg_blk = " · ".join(
                p for p in [
                    f"Package: {info['efuse_pkg_version']}" if info.get("efuse_pkg_version") else None,
                    f"eFuse Block: {info['efuse_blk_version']}" if info.get("efuse_blk_version") else None,
                    f"Nguồn HP: {info['efuse_power_src']}" if info.get("efuse_power_src") else None,
                ] if p
            )
            report_data.append(("  Cấu hình Gói & Nguồn eFuse", pkg_blk, None))
        if info.get("efuse_temp_rating"):
            report_data.append(("  Dải nhiệt độ Chip (eFuse)", info["efuse_temp_rating"], None))
        board_label = info.get("board_info") or info.get("fw_board_name")
        if board_label:
            report_data.append(("  Bo mạch phát hiện (Board)", board_label, 'blue'))

        # --- 2. THÔNG TIN CHIP FLASH & PSRAM ---
        flash_dev_raw = info.get('flash_device', 'N/A')
        flash_dev_decoded = decode_flash_device_id(flash_dev_raw)
        flash_io_parts = []
        if info.get("runtime_flash_io"):
            flash_io_parts.append(info["runtime_flash_io"])
        elif info.get("app_flash_mode"):
            flash_io_parts.append(info["app_flash_mode"])
        elif info.get("bootloader_flash_mode"):
            flash_io_parts.append(info["bootloader_flash_mode"])
        if info.get("app_flash_speed") or info.get("bootloader_flash_speed"):
            flash_io_parts.append(info.get("app_flash_speed") or info.get("bootloader_flash_speed"))
        if info.get("flash_type_efuse"):
            flash_io_parts.append(f"eFuse: {info['flash_type_efuse']}")

        if 'psram_mb' in info:
            psram_str = f"{info['psram_mb']} MB"
            if info.get("psram_speed"):
                psram_str += f" @ {info['psram_speed']}"
            if info.get("psram_mode"):
                psram_str += f" ({info['psram_mode']})"
            elif info.get("psram_source"):
                psram_str += f" ({info['psram_source']})"
            psram_tag = 'green'
        elif info.get("fw_psram_driver"):
            psram_str = f"Hỗ trợ {info['fw_psram_driver']} (Phát hiện trong Firmware; chưa có thông số eFuse/Boot Log)"
            psram_tag = 'blue'
        else:
            psram_str = "Không phát hiện qua eFuse / Boot Log"
            psram_tag = None

        report_data.extend([
            ("Thông tin Chip Flash & PSRAM", None, 'header'),
            ("  Nhà sản xuất Flash", man_display, None),
            ("  ID Thiết bị Flash (JEDEC)", flash_dev_decoded, None),
            ("  Kích thước Flash", f"{info.get('flash_mb', 0):.2f} MB" if 'flash_mb' in info else "N/A", None),
        ])
        if flash_io_parts:
            report_data.append(("  Chế độ & Tốc độ Flash", " · ".join(flash_io_parts), None))
        if info.get("status_value"):
            report_data.append(("  Thanh ghi Trạng thái Flash", info["status_value"], None))
        if info.get("sfdp_info"):
            report_data.append(("  Thông số chuẩn JEDEC SFDP", info["sfdp_info"], None))

        report_data.append(("  Kích thước & Tốc độ PSRAM", psram_str, psram_tag))
        if info.get("psram_vendor") or info.get("psram_dev_id") or info.get("psram_density"):
            v_str = " · ".join(
                p for p in [
                    f"Vendor: {info['psram_vendor']}" if info.get("psram_vendor") else None,
                    f"Dev ID: {info['psram_dev_id']}" if info.get("psram_dev_id") else None,
                    f"Density: {info['psram_density']}" if info.get("psram_density") else None,
                    f"Good-Die: {info['psram_good_die']}" if info.get("psram_good_die") else None,
                ] if p
            )
            report_data.append(("    + Định danh Chip PSRAM", v_str, None))
        if info.get("psram_bit_mode") or info.get("psram_read_latency") or info.get("psram_drive_str"):
            bus_str = " · ".join(
                p for p in [
                    f"BitMode: {info['psram_bit_mode']}" if info.get("psram_bit_mode") else None,
                    f"ReadLatency: {info['psram_read_latency']}" if info.get("psram_read_latency") else None,
                    f"DriveStr: {info['psram_drive_str']}" if info.get("psram_drive_str") else None,
                    f"CS IO: {info['psram_cs_io']}" if info.get("psram_cs_io") else None,
                ] if p
            )
            report_data.append(("    + Cấu hình Bus PSRAM", bus_str, None))
        if info.get("psram_burst_len") or info.get("psram_srf"):
            b_str = " · ".join(
                p for p in [
                    f"BurstType: {info['psram_burst_type']}" if info.get("psram_burst_type") else None,
                    f"BurstLen: {info['psram_burst_len']}" if info.get("psram_burst_len") else None,
                    f"SRF: {info['psram_srf']}" if info.get("psram_srf") else None,
                ] if p
            )
            report_data.append(("    + Chế độ Burst & Làm tươi", b_str, None))
        if info.get("psram_test_status") or info.get("psram_heap_pool_kb"):
            t_str = info.get("psram_test_status", "N/A")
            if info.get("psram_heap_pool_kb"):
                t_str += f" · Cấp phát vào Heap: {info['psram_heap_pool_kb']:,} KB"
            report_data.append(("    + Kiểm tra Bộ nhớ PSRAM", t_str, 'green' if "OK" in t_str else None))

        # --- 3. THÔNG TIN FIRMWARE & BOOTLOADER ĐANG NẠP TRÊN CHIP ---
        has_fw_info = any(
            info.get(k) for k in (
                "app_project_name", "app_version", "app_idf_ver", "app_compile_time",
                "app_elf_sha256", "bootloader_idf_ver", "bootloader_flash_mode",
                "i2c_scan_summary", "bsp_hardware_status"
            )
        )
        if has_fw_info:
            report_data.append(("Thông tin Firmware & Ngoại vi (đọc từ Flash & Boot Log)", None, 'header'))
            if info.get("app_project_name"):
                report_data.append(("  Tên dự án (Project Name)", info["app_project_name"], 'blue'))
            if info.get("app_version"):
                report_data.append(("  Phiên bản App (Version)", info["app_version"], None))
            if info.get("app_idf_ver"):
                report_data.append(("  Phiên bản SDK (ESP-IDF)", info["app_idf_ver"], None))
            if info.get("app_compile_time"):
                report_data.append(("  Thời gian biên dịch", info["app_compile_time"], None))
            if info.get("app_elf_sha256"):
                sha_disp = info["app_elf_sha256"]
                if len(sha_disp) > 24:
                    sha_disp = f"{sha_disp[:16]}...{sha_disp[-8:]}"
                report_data.append(("  Mã băm ELF (SHA256)", sha_disp, None))
            if info.get("app_min_chip_rev") or info.get("app_max_chip_rev"):
                rev_req = f"Min: {info.get('app_min_chip_rev', 'N/A')} · Max: {info.get('app_max_chip_rev', 'Không giới hạn')}"
                report_data.append(("  Yêu cầu Revision Chip", rev_req, None))
            if info.get("app_offset") or info.get("app_entry_addr") or info.get("app_mmu_page_size"):
                app_cfg = " · ".join(
                    p for p in [
                        f"Offset: {info['app_offset']}" if info.get("app_offset") else None,
                        f"Entry: {info['app_entry_addr']}" if info.get("app_entry_addr") else None,
                        f"MMU Page: {info['app_mmu_page_size']}" if info.get("app_mmu_page_size") else None,
                    ] if p
                )
                report_data.append(("  Cấu trúc Image Firmware", app_cfg, None))
            if info.get("bootloader_idf_ver") or info.get("bootloader_flash_mode"):
                bl_str = " · ".join(
                    p for p in [
                        f"ESP-IDF: {info['bootloader_idf_ver']}" if info.get("bootloader_idf_ver") else None,
                        f"Flash IO: {info['bootloader_flash_mode']}" if info.get("bootloader_flash_mode") else None,
                        f"Speed: {info['bootloader_flash_speed']}" if info.get("bootloader_flash_speed") else None,
                        f"Header Size: {info['bootloader_flash_size_hdr']}" if info.get("bootloader_flash_size_hdr") else None,
                    ] if p
                )
                report_data.append(("  Thông tin Bootloader", bl_str, None))
            if info.get("i2c_scan_summary"):
                report_data.append(("  Quét ngoại vi I2C (BSP)", info["i2c_scan_summary"], None))
            if info.get("sdmmc_status"):
                report_data.append(("  Trạng thái Thẻ nhớ SDMMC", info["sdmmc_status"], None))
            if info.get("bsp_hardware_status"):
                report_data.append(("  Trạng thái Phần cứng BSP", info["bsp_hardware_status"], None))

        # --- 4. BẢNG PHÂN VÙNG & BỘ NHỚ HEAP ---
        if info.get("partitions") or info.get("heap_regions"):
            report_data.append(("Bảng Phân Vùng Flash & Bộ Nhớ Động (Heap)", None, 'header'))
            if info.get("partitions"):
                for idx, part_line in enumerate(info["partitions"], 1):
                    report_data.append((f"  Phân vùng #{idx}", part_line, None))
            if info.get("heap_regions"):
                for idx, heap_line in enumerate(info["heap_regions"], 1):
                    report_data.append((f"  Vùng nhớ Heap #{idx}", heap_line, None))

        # --- 5. THÔNG TIN BẢO MẬT & EFUSE ---
        has_security = any(
            info.get(k) for k in ("secure_boot", "flash_encryption", "security_flags", "security_key_purposes", "jtag_security")
        )
        if has_security:
            report_data.append(("Bảo mật Phần cứng & eFuse (Security Info)", None, 'header'))
            if info.get("secure_boot"):
                report_data.append(("  Khởi động an toàn (Secure Boot)", info["secure_boot"], None))
            if info.get("flash_encryption"):
                fe_str = info["flash_encryption"]
                if info.get("spi_boot_crypt_cnt"):
                    fe_str += f" (Crypt Count: {info['spi_boot_crypt_cnt']})"
                report_data.append(("  Mã hóa Flash (Flash Encryption)", fe_str, None))
            if info.get("jtag_security") or info.get("usb_security"):
                jtag_usb = " · ".join(
                    p for p in [
                        f"JTAG: {info['jtag_security']}" if info.get("jtag_security") else None,
                        f"USB: {info['usb_security']}" if info.get("usb_security") else None,
                    ] if p
                )
                report_data.append(("  Trạng thái Cổng Debug", jtag_usb, None))
            if info.get("security_key_purposes"):
                report_data.append(("  Mục đích Key Blocks", info["security_key_purposes"], None))
            if info.get("security_flags"):
                report_data.append(("  Cờ Bảo mật (Security Flags)", info["security_flags"], None))

        # --- 6. THÔNG SỐ KỸ THUẬT (CSDL) ---
        report_data.append(("Thông số Kỹ thuật (tra cứu từ CSDL)", None, 'header'))
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

        # --- 7. MẠNG & KẾT NỐI ---
        report_data.append(("Mạng & Kết nối", None, 'header'))
        report_data.extend([
            ("  Chuẩn Wi-Fi", (chip_data.get('wifi') if chip_data else None) or "Không hỗ trợ (hoặc qua chip đồng xử lý SDIO/SPI)", None), 
            ("  Chuẩn Bluetooth", (chip_data.get('bluetooth') if chip_data else None) or "Không hỗ trợ (hoặc qua chip đồng xử lý)", None)
        ])
        
        if base_mac_hex:
            report_data.append(("  Địa chỉ Base MAC (eFuse)", base_mac_formatted.upper(), 'blue'))
            macs = derive_mac_addresses(base_mac_hex)
            if chip_data and chip_data.get('wifi'): 
                report_data.extend([
                    ("    + MAC Wi-Fi Station", macs.get("MAC Wi-Fi Station"), None), 
                    ("    + MAC Wi-Fi AP", macs.get("MAC Wi-Fi AP"), None)
                ])
            if chip_data and chip_data.get('bluetooth'): 
                report_data.append(("    + MAC Bluetooth", macs.get("MAC Bluetooth"), None))
            if chip_data and not chip_data.get('wifi') and not chip_data.get('bluetooth'):
                report_data.append(("    + MAC Ethernet / Nội bộ", macs.get("MAC Ethernet / Nội bộ"), None))
        else: 
            report_data.append(("  Địa MAC", "Không đọc được", 'red'))
        
        if chip_data and chip_data.get('features'):
            report_data.extend([("Tính năng Nổi bật", None, 'header'), ("", ", ".join(chip_data['features']), None)])
        
        # --- 8. PHÂN TÍCH NGUỒN GỐC ---
        report_data.append(("Phân tích Nguồn gốc", None, 'header'))
        if base_mac_formatted:
            oui = get_mac_oui(base_mac_formatted) or base_mac_formatted[:8]
            if is_espressif_oui(base_mac_formatted):
                report_data.append(("  Nguồn gốc MAC (OUI)", f"Tiền tố được cấp cho Espressif ({oui})", 'green'))
                report_data.append(("", "OUI hỗ trợ nhận diện nhà cung cấp, không phải chứng thư chống giả tuyệt đối.", None))
                report_data.append(("  Chip Nhớ (Flash)", f"Flash {man_short} (ID: {info.get('flash_device', 'N/A')})", 'green' if not man_short.startswith("Không rõ") else 'blue'))
            else: 
                report_data.append(("  Nguồn gốc MAC (OUI)", f"Không thấy {oui} trong CSDL Espressif", 'red'))
            report_data.append(("  CSDL OUI", f"335 tiền tố · cập nhật {ESPRESSIF_OUI_UPDATED} · {ESPRESSIF_OUI_SOURCE}", None))
        else: 
            report_data.append(("  Nguồn gốc MAC (OUI)", "Không thể đối chiếu (thiếu MAC)", 'red'))

        extra_log_enabled = True
        if hasattr(self, "page_inspector") and hasattr(self.page_inspector, "var_extra_log"):
            extra_log_enabled = bool(self.page_inspector.var_extra_log.get())
        if extra_log_enabled:
            report_data.append(("Ý nghĩa Chỉ số MIPS & Năng lực Xử lý", None, 'header'))
            report_data.extend([
                ("", "• MIPS (Million Instructions Per Second): Đo lường số triệu chỉ thị lệnh vi xử lý có thể thực thi trong 1 giây.", None),
                ("", "• Phân cấp hiệu năng ứng dụng thực tế:", None),
                ("", "  - Dưới 200 MIPS (ESP8266): Tối ưu cho thiết bị IoT đơn giản, đọc cảm biến, truyền nhận HTTP/MQTT.", None),
                ("", "  - 300 - 600 MIPS (ESP32/S3/C3/C6): Xử lý đa nhiệm FreeRTOS, bảo mật SSL/TLS, âm thanh số & AI/ML nhẹ.", None),
                ("", "  - 1800+ MIPS (ESP32-P4): Xử lý giao diện cảm ứng độ nét cao (MIPI-DSI), hình ảnh Camera/H.264 & AI nâng cao.", None)
            ])
        
        key_width = max((len(k) for k, v, t in report_data if k and not k.startswith("---") and k.strip() != ""), default=25) + 2

        try:
            report_font = tkfont.Font(font=self.inspector_txt.cget("font"))
            kv_hang_px = report_font.measure(" " * (key_width + 1))
            indent_hang_px = report_font.measure("    ")
        except Exception:
            kv_hang_px = (key_width + 1) * 8
            indent_hang_px = 32

        self.inspector_txt.tag_configure('kv_hanging', lmargin2=kv_hang_px)
        self.inspector_txt.tag_configure('indented_hanging', lmargin2=indent_hang_px)
        
        self.inspector_txt.config(state="normal")
        for key, value, tag in report_data:
            if value is None: 
                self.inspector_txt.insert("end", f"\n{key}\n", tag)
            elif key == "": 
                tags = ('indented_hanging', tag) if tag else ('indented_hanging',)
                self.inspector_txt.insert("end", f"  {value}\n", tags)
            else: 
                tags = ('kv_hanging', tag) if tag else ('kv_hanging',)
                self.inspector_txt.insert("end", f"{key+':':<{key_width}} {value}\n", tags)
        if hasattr(self.inspector_txt, "verticalScrollBar"):
            self.inspector_txt.verticalScrollBar().setValue(0)
        self.inspector_txt.config(state="disabled")
        if hasattr(self, "page_inspector") and hasattr(self.page_inspector, "update_from_parsed_info"):
            try:
                self.page_inspector.update_from_parsed_info(
                    info, chip_data, man_display, psram_str, base_mac_formatted, report_data
                )
            except Exception:
                pass
        chip_badge_key = info.get("chip_name_key") or info.get("chip_line")
        if chip_badge_key and hasattr(self, "conn_bar") and self.conn_bar is not None:
            parts = [str(info.get("chip_name_key") or info.get("chip_line"))]
            if "flash_mb" in info and info.get("flash_mb"):
                f_mb = float(info["flash_mb"])
                f_str = f"{int(f_mb)}MB" if f_mb.is_integer() else f"{f_mb:.1f}MB"
                parts.append(f"{f_str} Flash")
            if "psram_mb" in info and info.get("psram_mb"):
                parts.append(f"{info['psram_mb']}MB PSRAM")
            self.conn_bar.set_chip_badge_info(" · ".join(parts), is_active=True)
                
    def detect_baud_rate(self, port):
        test_bauds = ["115200", "74880", "230400", "460800", "921600", "9600"]
        self._post_detect_status("Đang dò tìm Baudrate...", "info")
        for baud in test_bauds:
            self._post_detect_status(f"Đang thử @ {baud} bps...", "info")
            try:
                args = ['--port', port, '--baud', str(baud), 'flash-id']
                output = run_esptool_command(args)
                if "A fatal error occurred" not in output and ("Chip is" in output or "Chip type:" in output or "Detecting chip type" in output):
                    self._post_detect_status(f"Đã tìm thấy Baudrate: {baud}", "success")
                    return baud
            except Exception: 
                continue
        return None
