# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Tab 3: Firmware Flasher & Erase Tools Mixin
"""
import os
import re
import threading
from modules.ui.models import END
from modules.ui import dialogs_service as messagebox
from modules.ui import dialogs_service as filedialog
from modules.config import FLASH_BAUDS, FLASH_CHIP_TARGETS, REPORT_FONT_SIZE
from modules.binary_scanner import validate_binary_segments
from modules.esptool_util import (
    run_esptool_command,
    esptool_command_succeeded,
    parse_esptool_progress_percent,
)

class FlasherTabMixin:
    """Mixin cung cấp logic điều khiển Nạp Firmware & Công cụ Xóa Flash (Trang 3)."""
    flash_thread = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.flash_thread = None

    def create_flasher_tab(self):
        return

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
            self.flash_file_rows[row_idx]["path_entry"].delete(0, END)
            self.flash_file_rows[row_idx]["path_entry"].insert(0, norm_p)
            self.flash_file_rows[row_idx]["var_enable"].set(True)
            self._update_file_size_display(row_idx)
            self.save_config()

    def log_flash(self, s, tag=None):
        """Ghi log vào màn hình của tab Nạp Flash và phản chiếu sang sub-tab Log."""
        try:
            if hasattr(self, 'flasher_txt') and self.flasher_txt.winfo_exists():
                self.flasher_txt.config(state="normal")
                self.flasher_txt.insert("end", s + "\n", tag)
                self.flasher_txt.see("end")
                self.flasher_txt.config(state="disabled")
        except Exception:
            pass
        if hasattr(self, "append_tab_log"):
            self.append_tab_log("Nạp Firmware", s, level=tag)

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

        was_connected = bool(self.serial_connection and getattr(self.serial_connection, 'is_open', True))
        if was_connected:
            self.on_serial_disconnect()
            self.is_flashing.set()
            self._set_flash_ui_state("disabled")
            self.root.after(400, lambda: self._start_erase_thread(port, was_connected=True))
        else:
            self._start_erase_thread(port, was_connected=False)

    def _start_erase_thread(self, port, was_connected=False):
        self.is_flashing.set()
        self.on_clear(self.flasher_txt, clear_status=False)
        self.set_status(f"Đang xóa sạch Flash trên {port}...", "warning")
        self._update_flash_progress(0, task_label=f"Xóa toàn bộ Flash ({port})")
        if hasattr(self, 'set_global_busy_state'):
            self.set_global_busy_state(True, "xóa toàn bộ flash")
        else:
            self._set_flash_ui_state("disabled")

        chip_target = self.flash_chip_cb.get().strip()
        baud = self.flash_baud_cb.get().strip()

        self.log_flash("=== BẮT ĐẦU XÓA SẠCH FLASH (ERASE FLASH) ===", 'header')
        self.flash_thread = threading.Thread(target=self._erase_worker, args=(port, baud, chip_target, was_connected), daemon=True)
        self.flash_thread.start()

    def _erase_worker(self, port, baud, chip_target, was_connected=False):
        args = ['--port', port, '--baud', str(baud)]
        if chip_target and chip_target != "auto":
            args.extend(['--chip', chip_target])
        args.append('erase-flash')

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def on_stream(line):
            safe_after(lambda: self.log_flash(f"  {line}"))
            l_str = str(line)
            if "Connecting" in l_str:
                safe_after(lambda: self._update_flash_progress(15))
            elif "Stub flasher running" in l_str or "Running stub" in l_str:
                safe_after(lambda: self._update_flash_progress(35))
            elif "Erasing flash" in l_str:
                safe_after(lambda: self._update_flash_progress(65))
            elif "Chip erase completed" in l_str:
                safe_after(lambda: self._update_flash_progress(95))

        try:
            res = run_esptool_command(args, progress_callback=on_stream)
            if esptool_command_succeeded(res):
                safe_after(lambda: self.set_status("Đã xóa sạch Flash thành công!", "success", progress=100))
                safe_after(lambda: self.log_flash("\n>>> XÓA SẠCH FLASH THÀNH CÔNG!", 'green'))
                safe_after(lambda: self._update_flash_progress(100))
            else:
                safe_after(lambda: self.set_status("Xóa Flash thất bại!", "error", progress=0))
                safe_after(lambda: self.log_flash("\n>>> LỖI KHI XÓA FLASH!", 'red'))
                safe_after(lambda: self._update_flash_progress(0))
        except Exception as e:
            error_message = f"Lỗi: {e}"
            safe_after(lambda msg=error_message: self.set_status(msg, "error", progress=0))
            safe_after(lambda err=error_message: self.log_flash(f"\n>>> NGOẠI LỆ: {err}", 'red'))
            safe_after(lambda: self._update_flash_progress(0))
        finally:
            self.is_flashing.clear()
            if hasattr(self, 'set_global_busy_state'):
                safe_after(lambda: self.set_global_busy_state(False))
            else:
                safe_after(lambda: self._set_flash_ui_state("normal"))
            if was_connected and hasattr(self, 'on_serial_connect'):
                safe_after(self.on_serial_connect, 500)

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

        is_valid, validation_message, write_pairs, max_end = validate_binary_segments(write_pairs)
        if not is_valid:
            messagebox.showerror("Dữ liệu Nạp Flash không hợp lệ", validation_message)
            return

        flash_limit = getattr(getattr(self, 'table', None), 'flash_size', None)
        if flash_limit is None and hasattr(self, 'flash_size') and isinstance(self.flash_size, (int, float)):
            flash_limit = int(self.flash_size)
        if flash_limit is not None and max_end > flash_limit:
            messagebox.showerror(
                "Vượt quá dung lượng Flash",
                f"Vùng nhớ nạp ghi tới 0x{max_end:X} ({max_end / (1024*1024):.2f} MB), "
                f"vượt quá dung lượng Flash của chip ({flash_limit / (1024*1024):.1f} MB)!"
            )
            return

        self.save_config()

        was_connected = bool(self.serial_connection and getattr(self.serial_connection, 'is_open', True))
        if was_connected:
            self.on_serial_disconnect()
            self.is_flashing.set()
            self._set_flash_ui_state("disabled")
            self.root.after(400, lambda: self._start_flash_write_thread(port, write_pairs, was_connected=True))
        else:
            self._start_flash_write_thread(port, write_pairs, was_connected=False)

    def _start_flash_write_thread(self, port, write_pairs, was_connected=False):
        self.is_flashing.set()
        self.on_clear(self.flasher_txt, clear_status=False)
        self.set_status(f"Đang nạp Flash vào {port}...", "warning")
        self._update_flash_progress(0, task_label=f"Nạp Firmware ({port})")
        if hasattr(self, 'set_global_busy_state'):
            self.set_global_busy_state(True, "nạp firmware")
        else:
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
        self.flash_thread = threading.Thread(target=self._flash_write_worker, args=(port, baud, chip_target, erase_all, write_pairs, was_connected), daemon=True)
        self.flash_thread.start()

    def _flash_write_worker(self, port, baud, chip_target, erase_all, write_pairs, was_connected=False):
        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        try:
            args = ['--port', port, '--baud', str(baud)]
            if chip_target and chip_target != "auto":
                args.extend(['--chip', chip_target])
            args.extend(['write-flash', '-z'])
            if erase_all:
                args.append('--erase-all')

            for off, fpath in write_pairs:
                args.extend([off, fpath])

            current_file_idx = 0
            last_file_pct = 0
            file_finished = False
            file_sizes = []
            for _, fpath in write_pairs:
                try:
                    sz = os.path.getsize(fpath) if os.path.isfile(fpath) else 0
                except OSError:
                    sz = 0
                file_sizes.append(max(1, sz))
            total_bytes = max(1, sum(file_sizes))

            def on_stream(line):
                nonlocal current_file_idx, last_file_pct, file_finished
                safe_after(lambda: self.log_flash(f"  {line}"))

                if "Hash of data verified" in line or re.search(r"Wrote\s+\d+\s+bytes", line):
                    if not file_finished and current_file_idx < len(write_pairs) - 1:
                        current_file_idx += 1
                        last_file_pct = 0
                        file_finished = True

                if "Writing at" in line:
                    file_finished = False

                parsed_pct = parse_esptool_progress_percent(line)
                if parsed_pct is not None:
                    pct = float(parsed_pct)
                    if pct < last_file_pct and current_file_idx < len(write_pairs) - 1:
                        if not file_finished:
                            current_file_idx += 1
                            last_file_pct = 0
                    last_file_pct = pct
                    file_finished = False

                    completed_bytes = sum(file_sizes[:current_file_idx])
                    current_bytes = (pct / 100.0) * file_sizes[current_file_idx]
                    agg_pct = min(100, max(0, int(((completed_bytes + current_bytes) / total_bytes) * 100)))
                    safe_after(lambda p=agg_pct: self._update_flash_progress(p))

            res = run_esptool_command(args, progress_callback=on_stream)
            if esptool_command_succeeded(res):
                safe_after(lambda: self._update_flash_progress(100))
                safe_after(lambda: self.set_status("Nạp Firmware thành công!", "success", progress=100))
                safe_after(lambda: self.log_flash("\n>>> NẠP FLASH THÀNH CÔNG! ESP ĐÃ SẴN SÀNG KHỞI ĐỘNG.", 'green'))
            else:
                safe_after(lambda: self._update_flash_progress(0))
                safe_after(lambda: self.set_status("Nạp Flash thất bại!", "error", progress=0))
                safe_after(lambda: self.log_flash("\n>>> LỖI QUÁ TRÌNH NẠP FLASH!", 'red'))
        except Exception as e:
            error_message = f"Lỗi: {e}"
            safe_after(lambda: self._update_flash_progress(0))
            safe_after(lambda msg=error_message: self.set_status(msg, "error", progress=0))
            safe_after(lambda err=error_message: self.log_flash(f"\n>>> NGOẠI LỆ: {err}", 'red'))
        finally:
            self.is_flashing.clear()
            if hasattr(self, 'set_global_busy_state'):
                safe_after(lambda: self.set_global_busy_state(False))
            else:
                safe_after(lambda: self._set_flash_ui_state("normal"))
            if was_connected and hasattr(self, 'on_serial_connect'):
                safe_after(self.on_serial_connect, 500)

    def _update_flash_progress(self, percent, task_label=None):
        """Cập nhật thanh tiến trình chung ở dưới cùng cho mọi tác vụ Nạp / Xóa / Phân vùng."""
        try:
            pct_int = int(round(max(0, min(100, float(percent)))))
            if hasattr(self, 'update_global_progress') and callable(self.update_global_progress):
                self.update_global_progress(pct_int, task_label=task_label)
            else:
                if hasattr(self, 'global_progress_bar') and self.global_progress_bar.winfo_exists():
                    self.global_progress_bar.config(mode="determinate", value=pct_int)
                if hasattr(self, 'global_progress_pct_lbl') and self.global_progress_pct_lbl.winfo_exists():
                    self.global_progress_pct_lbl.config(text=f"{pct_int}%")
                if task_label and hasattr(self, 'global_progress_task_lbl') and self.global_progress_task_lbl.winfo_exists():
                    self.global_progress_task_lbl.config(text=str(task_label))
        except Exception:
            pass

    def _set_flash_ui_state(self, state):
        """Bật/tắt các nút khi đang nạp Flash để chống bấm trùng."""
        if isinstance(state, bool):
            state = "normal" if state else "disabled"
        self.btn_flash_write.config(state=state)
        if hasattr(self, 'btn_erase_flash'):
            self.btn_erase_flash.config(state=state)
        if hasattr(self, 'btn_erase_only'):
            self.btn_erase_only.config(state=state)
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
