# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Tab 3: Firmware Flasher & Erase Tools Mixin
"""
import os
import re
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from modules.dialogs.layout_util import fit_dialog
from modules.win32_util import set_window_icon_native
from modules.config import FLASH_BAUDS, FLASH_CHIP_TARGETS, REPORT_FONT_SIZE
from modules.binary_scanner import validate_binary_segments
from modules.esptool_util import run_esptool_command, esptool_command_succeeded

class FlasherTabMixin:
    """Mixin cung cấp giao diện và logic Nạp Firmware & Công cụ Xóa Flash (Thẻ 3)."""

    def create_flasher_tab(self):
        """Khởi tạo giao diện Nạp Flash Firmware (.bin) đa file."""
        self.flasher_tab.columnconfigure(0, weight=1)
        self.flasher_tab.rowconfigure(0, weight=0)
        self.flasher_tab.rowconfigure(1, weight=0)
        self.flasher_tab.rowconfigure(2, weight=1)

        # 1. Khung cấu hình Nạp & Công cụ Xóa bộ nhớ
        cfg_frame = ttk.LabelFrame(self.flasher_tab, text=" Cấu hình Nạp Flash & Công cụ Xóa ", padding=(10, 6))
        cfg_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(4, 2))
        cfg_frame.columnconfigure(4, weight=1)

        ttk.Label(cfg_frame, text="Mục tiêu Chip:").grid(row=0, column=0, sticky="w", padx=(0, 4), pady=2)
        self.flash_chip_cb = ttk.Combobox(cfg_frame, values=FLASH_CHIP_TARGETS, width=11, state="readonly")
        self.flash_chip_cb.set(self.saved_flash_chip if self.saved_flash_chip in FLASH_CHIP_TARGETS else "auto")
        self.flash_chip_cb.grid(row=0, column=1, sticky="w", padx=(0, 12), pady=2)

        ttk.Label(cfg_frame, text="Tốc độ Nạp (Baud):").grid(row=0, column=2, sticky="w", padx=(0, 4), pady=2)
        self.flash_baud_cb = ttk.Combobox(cfg_frame, values=FLASH_BAUDS, width=11, state="readonly")
        self.flash_baud_cb.set(self.saved_flash_baud if self.saved_flash_baud in FLASH_BAUDS else "460800")
        self.flash_baud_cb.grid(row=0, column=3, sticky="w", padx=(0, 12), pady=2)

        self.var_flash_erase = tk.BooleanVar(value=self.saved_flash_erase)
        self.cb_flash_erase = ttk.Checkbutton(cfg_frame, text="Xóa sạch Flash trước khi nạp (--erase-all)", variable=self.var_flash_erase)
        self.cb_flash_erase.grid(row=0, column=4, sticky="w", padx=(0, 10), pady=2)

        sep = ttk.Separator(cfg_frame, orient="vertical")
        sep.grid(row=0, column=5, sticky="ns", padx=8, pady=2)

        self.btn_erase_flash = ttk.Button(cfg_frame, text="Xóa Toàn Bộ Flash", command=self.on_erase_flash_click)
        self.btn_erase_flash.grid(row=0, column=6, sticky="e", padx=(0, 6), pady=2)
        self.btn_erase_only = self.btn_erase_flash

        self.btn_erase_nvs = ttk.Button(cfg_frame, text="Xóa vùng Flash", command=self.on_erase_nvs_click)
        self.btn_erase_nvs.grid(row=0, column=7, sticky="e", padx=(0, 6), pady=2)


        # 2. Khung Danh sách File .bin cần nạp
        files_frame = ttk.LabelFrame(self.flasher_tab, text=" Danh sách File Firmware (.bin) & Offset nạp ", padding=(10, 6))
        files_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=2)
        files_frame.columnconfigure(2, weight=1)

        headers = ["Kích hoạt", "STT", "Đường dẫn File .bin", "Duyệt...", "Địa chỉ Offset", "Kích thước File"]
        ttk.Label(files_frame, text=headers[0], font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=6, pady=(0, 3))
        ttk.Label(files_frame, text=headers[1], font=("Segoe UI", 9, "bold")).grid(row=0, column=1, padx=6, pady=(0, 3))
        ttk.Label(files_frame, text=headers[2], font=("Segoe UI", 9, "bold")).grid(row=0, column=2, sticky="w", padx=6, pady=(0, 3))
        ttk.Label(files_frame, text=headers[3], font=("Segoe UI", 9, "bold")).grid(row=0, column=3, padx=6, pady=(0, 3))
        ttk.Label(files_frame, text=headers[4], font=("Segoe UI", 9, "bold")).grid(row=0, column=4, padx=6, pady=(0, 3))
        ttk.Label(files_frame, text=headers[5], font=("Segoe UI", 9, "bold")).grid(row=0, column=5, padx=6, pady=(0, 3))

        default_offsets = ["0x1000", "0x8000", "0xe000", "0x10000"]
        self.flash_file_rows = []

        for idx in range(4):
            r_idx = idx + 1
            var_en = tk.BooleanVar(value=(idx == 0))
            if self.saved_flash_rows and idx < len(self.saved_flash_rows):
                var_en.set(self.saved_flash_rows[idx].get("enabled", idx == 0))

            cb_en = ttk.Checkbutton(files_frame, variable=var_en)
            cb_en.grid(row=r_idx, column=0, padx=6, pady=2)

            lbl_num = ttk.Label(files_frame, text=f"File {idx + 1}:")
            lbl_num.grid(row=r_idx, column=1, padx=6, pady=2)

            entry_path = ttk.Entry(files_frame)
            entry_path.grid(row=r_idx, column=2, sticky="ew", padx=6, pady=2)

            saved_p = self.saved_flash_rows[idx].get("path", "") if self.saved_flash_rows and idx < len(self.saved_flash_rows) else ""
            if saved_p:
                entry_path.insert(0, saved_p)

            btn_browse = ttk.Button(files_frame, text="Chọn File...", width=11, command=lambda i=idx: self.on_browse_bin(i))
            btn_browse.grid(row=r_idx, column=3, padx=6, pady=2)

            entry_offset = ttk.Entry(files_frame, width=12)
            entry_offset.grid(row=r_idx, column=4, padx=6, pady=2)

            saved_off = self.saved_flash_rows[idx].get("offset", "") if self.saved_flash_rows and idx < len(self.saved_flash_rows) else ""
            entry_offset.insert(0, saved_off if saved_off else (default_offsets[idx] if idx < len(default_offsets) else "0x0"))

            lbl_size = ttk.Label(files_frame, text="-- KB", width=12)
            lbl_size.grid(row=r_idx, column=5, padx=6, pady=2)

            row_dict = {
                "var_enable": var_en,
                "check_btn": cb_en,
                "path_entry": entry_path,
                "browse_btn": btn_browse,
                "offset_entry": entry_offset,
                "size_label": lbl_size
            }
            self.flash_file_rows.append(row_dict)
            self._update_file_size_display(idx)

        # 3. Khung Tiến trình, Nút Bấm & Nhật ký Log
        log_frame = ttk.LabelFrame(self.flasher_tab, text=" Tiến trình & Nhật ký Nạp Flash ", padding=(10, 6))
        log_frame.grid(row=2, column=0, sticky="nsew", padx=6, pady=(2, 4))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(1, weight=1)

        # Hàng nút điều khiển & Progressbar
        ctrl_bar = ttk.Frame(log_frame)
        ctrl_bar.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ctrl_bar.columnconfigure(1, weight=1)

        self.btn_flash_write = ttk.Button(ctrl_bar, text="BẮT ĐẦU NẠP FLASH", style="Accent.TButton", command=self.on_flash_write_click)
        self.btn_flash_write.grid(row=0, column=0, padx=(0, 10))

        self.flash_prog = ttk.Progressbar(ctrl_bar, orient="horizontal", mode="determinate")
        self.flash_prog.grid(row=0, column=1, sticky="ew", padx=(0, 10))

        self.flash_pct_lbl = ttk.Label(ctrl_bar, text="0%", width=6, font=("Segoe UI", 9, "bold"))
        self.flash_pct_lbl.grid(row=0, column=2, padx=(0, 10))

        self.btn_clear_flasher_log = ttk.Button(ctrl_bar, text="Xóa Log", command=lambda: self.on_clear(self.flasher_txt))
        self.btn_clear_flasher_log.grid(row=0, column=3)

        # Ô Text hiển thị log esptool thời gian thực
        txt_container = ttk.Frame(log_frame)
        txt_container.grid(row=1, column=0, sticky="nsew")
        txt_container.columnconfigure(0, weight=1)
        txt_container.rowconfigure(0, weight=1)

        self.flasher_txt = tk.Text(txt_container, height=8, wrap="word", font=("Consolas", REPORT_FONT_SIZE), relief="flat", borderwidth=1, state="disabled")
        self.flasher_txt.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        vsb_flash = ttk.Scrollbar(txt_container, orient="vertical", command=self.flasher_txt.yview)
        vsb_flash.grid(row=0, column=1, sticky="ns")
        self.flasher_txt.configure(yscrollcommand=vsb_flash.set)
        self.flasher_txt.tag_configure('header', font=("Consolas", REPORT_FONT_SIZE, 'bold'))

    def _update_file_size_display(self, row_idx):
        """Cập nhật dung lượng hiển thị cho file .bin."""
        if row_idx < len(self.flash_file_rows):
            path = self.flash_file_rows[row_idx]["path_entry"].get().strip()
            lbl = self.flash_file_rows[row_idx]["size_label"]
            if path and os.path.isfile(path):
                try:
                    sz_kb = os.path.getsize(path) / 1024.0
                    if sz_kb < 1024:
                        lbl.config(text=f"{sz_kb:.1f} KB")
                    else:
                        lbl.config(text=f"{sz_kb/1024.0:.2f} MB")
                except Exception:
                    lbl.config(text="-- KB")
            else:
                lbl.config(text="-- KB")

    def on_browse_bin(self, row_idx):
        """Hộp thoại chọn file .bin."""
        curr_p = self.flash_file_rows[row_idx]["path_entry"].get().strip()
        init_dir = os.path.dirname(curr_p) if (curr_p and os.path.exists(os.path.dirname(curr_p))) else "."
        fpath = filedialog.askopenfilename(
            initialdir=init_dir,
            title=f"Chọn file Firmware Binary (File {row_idx + 1})",
            filetypes=[("Binary Firmware", "*.bin"), ("All Files", "*.*")]
        )
        if fpath:
            norm_p = os.path.normpath(fpath)
            self.flash_file_rows[row_idx]["path_entry"].delete(0, tk.END)
            self.flash_file_rows[row_idx]["path_entry"].insert(0, norm_p)
            self.flash_file_rows[row_idx]["var_enable"].set(True)
            self._update_file_size_display(row_idx)
            self.save_config()

    def log_flash(self, s, tag=None):
        """Ghi log vào màn hình của tab Nạp Flash."""
        if hasattr(self, 'flasher_txt') and self.flasher_txt.winfo_exists():
            self.flasher_txt.config(state="normal")
            self.flasher_txt.insert("end", s + "\n", tag)
            self.flasher_txt.see("end")
            self.flasher_txt.config(state="disabled")

    def on_erase_flash_click(self):
        """Xử lý sự kiện bấm nút Xóa Toàn Bộ Flash."""
        port = self.port_cb.get().strip()
        if not port:
            messagebox.showwarning("Thiếu Cổng", "Vui lòng chọn cổng COM trước khi xóa Flash.")
            return

        if self.is_flashing.is_set() or self.is_detecting.is_set() or getattr(self, "is_connecting", False):
            messagebox.showwarning("Bận", "Thiết bị đang bận xử lý tác vụ khác!")
            return

        if not messagebox.askyesno(
            "Xác nhận Xóa Toàn Bộ Flash",
            f"CẢNH BÁO NGUY HIỂM:\n\n"
            f"Thao tác này sẽ XÓA SẠCH toàn bộ bộ nhớ Flash trên {port}!\n"
            f"Toàn bộ Firmware (chương trình), Bootloader, Partition Table và Dữ liệu NVS sẽ bị xóa hoàn toàn.\n\n"
            f"Bạn có chắc chắn muốn xóa sạch Flash không?"
        ):
            return

        if self.serial_connection and self.serial_connection.is_open:
            self.on_serial_disconnect()
            self.is_flashing.set()
            self._set_flash_ui_state("disabled")
            self.root.after(400, lambda: self._start_erase_thread(port))
        else:
            self._start_erase_thread(port)

    def _start_erase_thread(self, port):
        self.is_flashing.set()
        self.on_clear(self.flasher_txt, clear_status=False)
        self.set_status(f"Đang xóa sạch Flash trên {port}...", "warning")
        self.flash_prog.config(value=0)
        self.flash_pct_lbl.config(text="0%")
        self._set_flash_ui_state("disabled")

        chip_target = self.flash_chip_cb.get().strip()
        baud = self.flash_baud_cb.get().strip()

        self.log_flash("=== BẮT ĐẦU XÓA SẠCH FLASH (ERASE FLASH) ===", 'header')
        self.log_flash(f"Cổng COM: {port} | Baudrate: {baud} | Chip: {chip_target}\n")
        threading.Thread(target=self._erase_worker, args=(port, baud, chip_target), daemon=True).start()

    def _erase_worker(self, port, baud, chip_target):
        args = ['--port', port, '--baud', str(baud)]
        if chip_target and chip_target != "auto":
            args.extend(['--chip', chip_target])
        args.append('erase-flash')

        def on_stream(line):
            self.root.after(0, self.log_flash, f"  {line}")

        try:
            res = run_esptool_command(args, progress_callback=on_stream)
            if esptool_command_succeeded(res):
                self.root.after(0, lambda: self.set_status("Đã xóa sạch Flash thành công!", "success"))
                self.root.after(0, self.log_flash, "\n>>> XÓA SẠCH FLASH THÀNH CÔNG!", 'green')
                self.root.after(0, lambda: self.flash_prog.config(value=100))
                self.root.after(0, lambda: self.flash_pct_lbl.config(text="100%"))
            else:
                self.root.after(0, lambda: self.set_status("Xóa Flash thất bại!", "error"))
                self.root.after(0, self.log_flash, "\n>>> LỖI KHI XÓA FLASH!", 'red')
        except Exception as e:
            error_message = f"Lỗi: {e}"
            self.root.after(0, lambda msg=error_message: self.set_status(msg, "error"))
            self.root.after(0, self.log_flash, f"\n>>> NGOẠI LỆ: {e}", 'red')
        finally:
            self.is_flashing.clear()
            self.root.after(0, lambda: self._set_flash_ui_state("normal"))

    def on_erase_nvs_click(self):
        """Xử lý sự kiện bấm nút Xóa vùng Flash."""
        port = self.port_cb.get().strip()
        if not port:
            messagebox.showwarning("Thiếu Cổng", "Vui lòng chọn cổng COM trước khi xóa vùng Flash.")
            return

        if self.is_flashing.is_set() or self.is_detecting.is_set() or getattr(self, "is_connecting", False):
            messagebox.showwarning("Bận", "Thiết bị đang bận xử lý tác vụ khác!")
            return

        self._show_erase_nvs_dialog(port)

    def _show_erase_nvs_dialog(self, port):
        """Hộp thoại cấu hình và xác nhận Xóa phân vùng bộ nhớ NVS."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Xác nhận Xóa Vùng Flash")
        set_window_icon_native(dialog)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        w, h = 480, 275
        self.root.update_idletasks()
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        x = rx + max(0, (rw - w) // 2)
        y = ry + max(0, (rh - h) // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        content = ttk.Frame(dialog, padding=16)
        content.pack(fill="both", expand=True)

        lbl_title = ttk.Label(content, text="XÓA VÙNG FLASH THEO ĐỊA CHỈ", font=("Segoe UI", 10, "bold"))
        lbl_title.pack(anchor="w", pady=(0, 6))

        lbl_desc = ttk.Label(
            content,
            text=f"Cổng kết nối: {port}\n"
                 "Vùng nhập bên dưới chưa được đối chiếu với bảng phân vùng trên chip.\n"
                 "Chọn sai địa chỉ có thể xóa firmware, bootloader hoặc dữ liệu. Hãy kiểm tra bảng phân vùng trước khi xóa.",
            wraplength=440,
            justify="left"
        )
        lbl_desc.pack(anchor="w", pady=(0, 10))

        grid_f = ttk.Frame(content)
        grid_f.pack(fill="x", pady=(0, 6))

        ttk.Label(grid_f, text="Địa chỉ bắt đầu (Hex):").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        entry_offset = ttk.Entry(grid_f, width=16)
        entry_offset.insert(0, "0x9000")
        entry_offset.grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(grid_f, text="Kích thước Vùng Xóa (Hex):").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
        entry_size = ttk.Entry(grid_f, width=16)
        entry_size.insert(0, "0x5000")
        entry_size.grid(row=1, column=1, sticky="w", pady=4)

        ttk.Label(
            grid_f,
            text="* Giá trị gợi ý, không xác nhận đây là NVS của thiết bị.",
            font=("Segoe UI", 8, "italic")
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        btn_bar = ttk.Frame(content)
        btn_bar.pack(fill="x", pady=(12, 0))

        def on_confirm():
            off_str = entry_offset.get().strip()
            sz_str = entry_size.get().strip()
            if not off_str or not sz_str:
                messagebox.showwarning("Thiếu thông tin", "Vui lòng nhập đầy đủ Offset và Size vùng xóa!", parent=dialog)
                return
            try:
                off_val = int(off_str, 16 if off_str.lower().startswith("0x") else 10)
                sz_val = int(sz_str, 16 if sz_str.lower().startswith("0x") else 10)
            except ValueError:
                messagebox.showerror("Dữ liệu không hợp lệ", "Offset hoặc Kích thước phải là số nguyên hoặc hex hợp lệ (vd: 0x9000, 0x5000)!", parent=dialog)
                return

            if off_val < 0:
                messagebox.showerror("Lỗi", "Offset vùng xóa không được là số âm!", parent=dialog)
                return

            if sz_val <= 0:
                messagebox.showerror("Lỗi", "Kích thước vùng xóa phải lớn hơn 0!", parent=dialog)
                return

            if off_val % 4096 != 0 or sz_val % 4096 != 0:
                messagebox.showerror(
                    "Lỗi Căn Sector",
                    "Offset và kích thước vùng xóa đều phải là bội số của sector 4 KB (0x1000).",
                    parent=dialog
                )
                return

            if self.is_flashing.is_set() or self.is_detecting.is_set() or getattr(self, "is_connecting", False):
                messagebox.showwarning("Thiết bị đang bận", "Hãy đợi tác vụ hiện tại hoàn tất.", parent=dialog)
                return
            if not messagebox.askyesno(
                "Xác nhận xóa vùng Flash",
                f"Sẽ xóa từ 0x{off_val:X} đến 0x{off_val + sz_val - 1:X} ({sz_val} byte).\n"
                "Chưa xác minh phân vùng nào nằm trong vùng này. Firmware và dữ liệu có thể bị mất.\nTiếp tục?",
                parent=dialog
            ):
                return
            dialog.destroy()
            if self.serial_connection and self.serial_connection.is_open:
                self.on_serial_disconnect()
                self.is_flashing.set()
                self._set_flash_ui_state("disabled")
                self.root.after(400, lambda: self._start_erase_nvs_thread(port, hex(off_val), hex(sz_val)))
            else:
                self._start_erase_nvs_thread(port, hex(off_val), hex(sz_val))

        btn_confirm = ttk.Button(btn_bar, text="Xác nhận Xóa vùng Flash", command=on_confirm)
        btn_confirm.pack(side="right", padx=(6, 0))

        btn_cancel = ttk.Button(btn_bar, text="Hủy", command=dialog.destroy)
        btn_cancel.pack(side="right")
        fit_dialog(dialog, self.root, 480, 320)

    def _start_erase_nvs_thread(self, port, offset_hex, size_hex):
        self.is_flashing.set()
        self.on_clear(self.flasher_txt, clear_status=False)
        self.set_status(f"Đang xóa vùng Flash ({offset_hex}, {size_hex}) trên {port}...", "warning")
        self.flash_prog.config(value=0)
        self.flash_pct_lbl.config(text="0%")
        self._set_flash_ui_state("disabled")

        chip_target = self.flash_chip_cb.get().strip()
        baud = self.flash_baud_cb.get().strip()

        sz_kb = int(size_hex, 16 if size_hex.lower().startswith("0x") else 10) / 1024.0
        self.log_flash("=== BẮT ĐẦU XÓA VÙNG FLASH THEO ĐỊA CHỈ ===", 'header')
        self.log_flash(f"Cổng COM: {port} | Baudrate: {baud} | Chip: {chip_target}")
        self.log_flash(f"Địa chỉ Offset: {offset_hex} | Kích thước: {size_hex} ({sz_kb:.1f} KB)")
        self.log_flash("-" * 65 + "\n")
        threading.Thread(target=self._erase_nvs_worker, args=(port, baud, chip_target, offset_hex, size_hex), daemon=True).start()

    def _erase_nvs_worker(self, port, baud, chip_target, offset_hex, size_hex):
        args = ['--port', port, '--baud', str(baud)]
        if chip_target and chip_target != "auto":
            args.extend(['--chip', chip_target])
        args.extend(['erase-region', offset_hex, size_hex])

        def on_stream(line):
            self.root.after(0, self.log_flash, f"  {line}")

        try:
            res = run_esptool_command(args, progress_callback=on_stream)
            if esptool_command_succeeded(res):
                self.root.after(0, lambda: self.set_status("Đã xóa vùng Flash thành công!", "success"))
                self.root.after(0, self.log_flash, "\n>>> XÓA VÙNG FLASH THÀNH CÔNG!", 'green')
                self.root.after(0, lambda: self.flash_prog.config(value=100))
                self.root.after(0, lambda: self.flash_pct_lbl.config(text="100%"))
            else:
                self.root.after(0, lambda: self.set_status("Xóa vùng Flash thất bại!", "error"))
                self.root.after(0, self.log_flash, "\n>>> LỖI KHI XÓA VÙNG FLASH!", 'red')
        except Exception as e:
            error_message = f"Lỗi: {e}"
            self.root.after(0, lambda msg=error_message: self.set_status(msg, "error"))
            self.root.after(0, self.log_flash, f"\n>>> NGOẠI LỆ: {e}", 'red')
        finally:
            self.is_flashing.clear()
            self.root.after(0, lambda: self._set_flash_ui_state("normal"))

    def on_flash_write_click(self):
        """Xử lý bắt đầu nạp firmware .bin."""
        port = self.port_cb.get().strip()
        if not port:
            messagebox.showwarning("Thiếu Cổng", "Vui lòng chọn cổng COM trước khi nạp Flash.")
            return

        if self.is_flashing.is_set() or self.is_detecting.is_set() or getattr(self, "is_connecting", False):
            messagebox.showwarning("Bận", "Thiết bị đang bận xử lý tác vụ khác!")
            return

        write_pairs = []
        for idx, row in enumerate(self.flash_file_rows):
            if row["var_enable"].get():
                path = row["path_entry"].get().strip()
                offset = row["offset_entry"].get().strip()
                if not path:
                    messagebox.showwarning("Thiếu File", f"Hàng File {idx + 1} đang được tích chọn nhưng chưa nhập đường dẫn file!")
                    return
                if not os.path.isfile(path):
                    messagebox.showerror("File không tồn tại", f"File tại hàng {idx + 1} không tồn tại:\n{path}")
                    return
                if not offset:
                    messagebox.showwarning("Thiếu Offset", f"Vui lòng nhập địa chỉ Offset cho File {idx + 1} (Ví dụ: 0x1000, 0x0)!")
                    return
                try:
                    int(offset, 16 if offset.lower().startswith("0x") else 10)
                except ValueError:
                    messagebox.showerror("Offset không hợp lệ", f"Địa chỉ Offset '{offset}' tại hàng {idx + 1} không hợp lệ!")
                    return
                write_pairs.append((offset, path))

        is_valid, validation_message, write_pairs, _max_end = validate_binary_segments(write_pairs)
        if not is_valid:
            messagebox.showerror("Dữ liệu Nạp Flash không hợp lệ", validation_message)
            return

        self.save_config()

        if self.serial_connection and self.serial_connection.is_open:
            self.on_serial_disconnect()
            self.is_flashing.set()
            self._set_flash_ui_state("disabled")
            self.root.after(400, lambda: self._start_flash_write_thread(port, write_pairs))
        else:
            self._start_flash_write_thread(port, write_pairs)

    def _start_flash_write_thread(self, port, write_pairs):
        self.is_flashing.set()
        self.on_clear(self.flasher_txt, clear_status=False)
        self.set_status(f"Đang nạp Flash vào {port}...", "warning")
        self.flash_prog.config(value=0)
        self.flash_pct_lbl.config(text="0%")
        self._set_flash_ui_state("disabled")

        chip_target = self.flash_chip_cb.get().strip()
        baud = self.flash_baud_cb.get().strip()
        erase_all = self.var_flash_erase.get()

        self.log_flash(f"=== BẮT ĐẦU NẠP FIRMWARE ESP ({len(write_pairs)} FILE) ===", 'header')
        self.log_flash(f"Cổng COM: {port} | Baudrate: {baud} | Chip: {chip_target}")
        if erase_all:
            self.log_flash("Tùy chọn: Xóa sạch Flash trước khi ghi (--erase-all)")
        for off, fpath in write_pairs:
            sz_kb = os.path.getsize(fpath) / 1024.0
            self.log_flash(f"  + Offset: {off:<10} | Kích thước: {sz_kb:8.1f} KB | File: {fpath}")
        self.log_flash("-" * 65 + "\n")
        threading.Thread(target=self._flash_write_worker, args=(port, baud, chip_target, erase_all, write_pairs), daemon=True).start()

    def _flash_write_worker(self, port, baud, chip_target, erase_all, write_pairs):
        args = ['--port', port, '--baud', str(baud)]
        if chip_target and chip_target != "auto":
            args.extend(['--chip', chip_target])
        args.extend(['write-flash', '-z'])
        if erase_all:
            args.append('--erase-all')

        for off, fpath in write_pairs:
            args.extend([off, fpath])

        def on_stream(line):
            self.root.after(0, self.log_flash, f"  {line}")
            m = re.search(r"\((\d+)\s*%\)", line)
            if m:
                pct = int(m.group(1))
                self.root.after(0, lambda p=pct: self._update_flash_progress(p))

        try:
            res = run_esptool_command(args, progress_callback=on_stream)
            if esptool_command_succeeded(res):
                self.root.after(0, lambda: self._update_flash_progress(100))
                self.root.after(0, lambda: self.set_status("Nạp Firmware thành công!", "success"))
                self.root.after(0, self.log_flash, "\n>>> NẠP FLASH THÀNH CÔNG! ESP ĐÃ SẴN SÀNG KHỞI ĐỘNG.", 'green')
            else:
                self.root.after(0, lambda: self.set_status("Nạp Flash thất bại!", "error"))
                self.root.after(0, self.log_flash, "\n>>> LỖI QUÁ TRÌNH NẠP FLASH!", 'red')
        except Exception as e:
            error_message = f"Lỗi: {e}"
            self.root.after(0, lambda msg=error_message: self.set_status(msg, "error"))
            self.root.after(0, self.log_flash, f"\n>>> NGOẠI LỆ: {e}", 'red')
        finally:
            self.is_flashing.clear()
            self.root.after(0, lambda: self._set_flash_ui_state("normal"))

    def _update_flash_progress(self, percent):
        """Cập nhật thanh tiến trình nạp Flash."""
        self.flash_prog.config(value=percent)
        self.flash_pct_lbl.config(text=f"{percent}%")

    def _set_flash_ui_state(self, state):
        """Bật/tắt các nút khi đang nạp Flash để chống bấm trùng."""
        self.btn_flash_write.config(state=state)
        if hasattr(self, 'btn_erase_flash'):
            self.btn_erase_flash.config(state=state)
        if hasattr(self, 'btn_erase_only'):
            self.btn_erase_only.config(state=state)
        if hasattr(self, 'btn_erase_nvs'):
            self.btn_erase_nvs.config(state=state)
        combo_state = "disabled" if state == "disabled" else "readonly"
        self.flash_chip_cb.config(state=combo_state)
        self.flash_baud_cb.config(state=combo_state)
        self.cb_flash_erase.config(state=state)
        if hasattr(self, 'detect_btn'):
            self.detect_btn.config(state=state)
        if hasattr(self, 'serial_toggle_btn'):
            self.serial_toggle_btn.config(state=state)
        if hasattr(self, 'flash_file_rows'):
            for row in self.flash_file_rows:
                row["path_entry"].config(state=state)
                row["offset_entry"].config(state=state)
                if "browse_btn" in row:
                    row["browse_btn"].config(state=state)
                if "check_btn" in row:
                    row["check_btn"].config(state=state)
