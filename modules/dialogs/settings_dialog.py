# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.1 - Settings Dialog Mixin
Tinh gọn Hộp thoại Cài đặt (chỉ gồm Cài đặt chung và Nút chức năng F1-F12),
tách riêng Hộp thoại Giới thiệu (AboutDialog) và Kiểm tra Cập nhật (UpdateDialog).
"""
import os
import threading
from modules import qt_toolkit as tk
from modules.qt_toolkit import ttk, messagebox, filedialog

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None

from modules.config import (
    CONTROL_CONFIG, DARK_PALETTE, LIGHT_PALETTE,
    APP_NAME, APP_VERSION, APP_AUTHOR, APP_LICENSE, GITHUB_REPO
)
from modules.win32_util import set_window_icon_native
from modules.serial_util import is_bluetooth_port
from modules.help_content import about_features_text
from modules.update_util import check_for_updates, download_update_asset


class SettingsDialogMixin:
    """Mixin cung cấp chức năng mở hộp thoại cài đặt hệ thống, thông tin ứng dụng và cập nhật."""

    def open_settings_dialog(self, initial_tab_index: int = 0):
        """Mở Hộp thoại Cài đặt hệ thống tinh gọn gồm 2 Tab: Cài đặt chung và Nút chức năng."""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{APP_NAME} - Cài đặt hệ thống")
        set_window_icon_native(dialog)

        dialog.update_idletasks()
        width = 680
        height = 510
        x = max(0, self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2))
        y = max(0, self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2))
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        dialog.minsize(640, 440)
        dialog.transient(self.root)
        dialog.grab_set()

        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        dialog.configure(bg=p["bg"])

        # Tạo Notebook chia 2 tab cài đặt thuần túy
        settings_notebook = ttk.Notebook(dialog)
        settings_notebook.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        tab_general = ttk.Frame(settings_notebook, padding=10)
        tab_functions = ttk.Frame(settings_notebook, padding=10)

        settings_notebook.add(tab_general, text=" Cài đặt chung ")
        settings_notebook.add(tab_functions, text=f" Nút chức năng (F{min(CONTROL_CONFIG)}-F{max(CONTROL_CONFIG)}) ")

        tabs = [tab_general, tab_functions]
        if 0 <= initial_tab_index < len(tabs):
            settings_notebook.select(tabs[initial_tab_index])

        # =========================================================================
        # TAB 1: CÀI ĐẶT CHUNG
        # =========================================================================
        # --- 1. Frame Quản lý Cổng COM ---
        com_frame = ttk.LabelFrame(tab_general, text=" Quản lý Cổng COM ", padding=10)
        com_frame.pack(fill="x", pady=(0, 8))

        # Cấu hình tự động quét, ưu tiên cổng mới & ẩn cổng Bluetooth
        com_auto_frame = ttk.Frame(com_frame)
        com_auto_frame.pack(fill="x", pady=(0, 6))
        if hasattr(self, "var_auto_scan"):
            ttk.Checkbutton(
                com_auto_frame,
                text="Tự động quét cổng COM định kỳ (mỗi 2 giây)",
                variable=self.var_auto_scan
            ).pack(anchor="w", pady=1)
        if hasattr(self, "var_auto_select_new"):
            ttk.Checkbutton(
                com_auto_frame,
                text="Tự động ưu tiên chọn cổng COM mới cắm",
                variable=self.var_auto_select_new
            ).pack(anchor="w", pady=1)

        if not hasattr(self, "var_hide_bt_ports"):
            self.var_hide_bt_ports = tk.BooleanVar(value=getattr(self, "saved_hide_bluetooth_ports", True))

        com_checkbox_vars = {}
        com_list_frame = ttk.Frame(com_frame)
        custom_ignored_var = tk.StringVar()

        def populate_com_list():
            for widget in com_list_frame.winfo_children():
                widget.destroy()
            com_checkbox_vars.clear()

            hide_bt_active = bool(self.var_hide_bt_ports.get())
            raw_ports_info = []
            bt_port_names = set()
            if list_ports is not None:
                try:
                    for p_obj in list_ports.comports():
                        if is_bluetooth_port(p_obj):
                            bt_port_names.add(p_obj.device.upper())
                            if hide_bt_active:
                                continue
                        raw_ports_info.append((p_obj.device, p_obj.description))
                except Exception:
                    pass

            if not raw_ports_info:
                ttk.Label(com_list_frame, text="Không phát hiện cổng COM nào kết nối.", foreground=p["disabled_fg"]).pack(anchor="w", padx=5, pady=2)
            else:
                row_idx = 0
                for dev, desc in sorted(raw_ports_info, key=lambda x: x[0]):
                    is_ignored = dev.upper() in [x.upper() for x in self.ignored_com_ports]
                    var = tk.BooleanVar(value=is_ignored)
                    com_checkbox_vars[dev] = var

                    cb = ttk.Checkbutton(com_list_frame, text=f"{dev} ({desc})", variable=var)
                    cb.grid(row=row_idx // 2, column=row_idx % 2, sticky="w", padx=10, pady=2)
                    row_idx += 1

            visible_upper = {p_item[0].upper() for p_item in raw_ports_info}
            extra_ignored = [
                x for x in self.ignored_com_ports
                if x.upper() not in visible_upper and (not hide_bt_active or x.upper() not in bt_port_names)
            ]
            custom_ignored_var.set(", ".join(extra_ignored))

        def on_toggle_hide_bt():
            populate_com_list()
            self.refresh_ports_dropdown()

        ttk.Checkbutton(
            com_auto_frame,
            text="Tự động lọc / ẩn cổng COM của Bluetooth",
            variable=self.var_hide_bt_ports,
            command=on_toggle_hide_bt
        ).pack(anchor="w", pady=1)

        ttk.Separator(com_frame, orient="horizontal").pack(fill="x", pady=(2, 6))

        com_top_frame = ttk.Frame(com_frame)
        com_top_frame.pack(fill="x", pady=(0, 5))

        ttk.Label(com_top_frame, text="Tích chọn cổng COM cần ẨN / BỎ QUA:", font=("Segoe UI", 9, "bold")).pack(side="left")

        com_list_frame.pack(fill="x", pady=2)

        populate_com_list()

        ttk.Button(com_frame, text="Làm mới danh sách", command=populate_com_list).pack(anchor="w", pady=(4, 5))

        extra_frame = ttk.Frame(com_frame)
        extra_frame.pack(fill="x", pady=(5, 0))
        ttk.Label(extra_frame, text="Cổng COM ẩn khác (ngăn cách bằng dấu phẩy):").pack(anchor="w")
        ttk.Entry(extra_frame, textvariable=custom_ignored_var).pack(fill="x", pady=(2, 0))

        # --- 2. Frame Cấu hình Mạng mặc định ---
        network_frame = ttk.LabelFrame(tab_general, text=" Cấu hình Server Mặc định ", padding=10)
        network_frame.pack(fill="x", pady=5)

        net_grid = ttk.Frame(network_frame)
        net_grid.pack(fill="x")

        ttk.Label(net_grid, text="IP Server mặc định:").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=2)
        ip_var = tk.StringVar(value=self.default_ip)
        ttk.Entry(net_grid, textvariable=ip_var, width=25).grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(net_grid, text="Cổng (Port) mặc định:").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=2)
        port_var = tk.StringVar(value=self.default_port)
        ttk.Entry(net_grid, textvariable=port_var, width=10).grid(row=1, column=1, sticky="w", pady=2)

        # =========================================================================
        # TAB 2: NÚT CHỨC NĂNG (F1 -> F12)
        # =========================================================================
        ttk.Label(tab_functions, text="Tùy chỉnh Tên hiển thị và Chuỗi lệnh gửi đi cho từng nút trên Bảng điều khiển:", font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 8))

        canvas_frame = ttk.Frame(tab_functions)
        canvas_frame.pack(fill="both", expand=True)

        canvas = tk.Canvas(canvas_frame, bg=p["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except (tk.TclError, Exception):
                pass

        def _bind_mousewheel(event=None):
            canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(event=None):
            try:
                canvas.unbind_all("<MouseWheel>")
            except (tk.TclError, Exception):
                pass

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)
        scrollable_frame.bind("<Enter>", _bind_mousewheel)
        scrollable_frame.bind("<Leave>", _unbind_mousewheel)
        canvas_frame.bind("<Enter>", _bind_mousewheel)
        canvas_frame.bind("<Leave>", _unbind_mousewheel)

        dialog.bind("<Destroy>", lambda e: _unbind_mousewheel(e) if e.widget == dialog else None, add="+")

        btn_label_vars = {}
        btn_cmd_vars = {}

        for i in sorted(CONTROL_CONFIG):
            curr_label = self.control_labels.get(i, CONTROL_CONFIG[i][0])
            curr_cmd = self.control_commands.get(i, CONTROL_CONFIG[i][1])

            row_frame = ttk.Frame(scrollable_frame, padding=2)
            row_frame.pack(fill="x", pady=2)

            ttk.Label(row_frame, text=f"Nút {i} (F{i}):", width=12, font=("Segoe UI", 9, "bold")).pack(side="left")

            ttk.Label(row_frame, text="Tên:").pack(side="left", padx=(5, 2))
            lbl_var = tk.StringVar(value=curr_label)
            btn_label_vars[i] = lbl_var
            ttk.Entry(row_frame, textvariable=lbl_var, width=15).pack(side="left", padx=(0, 10))

            ttk.Label(row_frame, text="Lệnh:").pack(side="left", padx=(5, 2))
            cmd_var = tk.StringVar(value=curr_cmd)
            btn_cmd_vars[i] = cmd_var
            ttk.Entry(row_frame, textvariable=cmd_var, width=28).pack(side="left")

        # =========================================================================
        # FRAME NÚT TÁC VỤ Ở ĐÁY CỬA SỔ
        # =========================================================================
        action_frame = ttk.Frame(dialog)
        action_frame.pack(fill="x", padx=10, pady=(5, 10))

        def do_reset_from_dialog():
            if self.reset_config():
                populate_com_list()
                self.refresh_ports_dropdown()
                dialog.destroy()

        ttk.Button(action_frame, text="Khôi phục gốc", command=do_reset_from_dialog).pack(side="left")

        def save_and_close():
            self.default_ip = ip_var.get().strip()
            self.default_port = port_var.get().strip()

            checked_ports = [dev for dev, var in com_checkbox_vars.items() if var.get()]
            extra_ports = [x.strip() for x in custom_ignored_var.get().split(',') if x.strip()]

            combined_ignored = []
            seen_upper = set()
            for p_name in checked_ports + extra_ports:
                if p_name.upper() not in seen_upper:
                    combined_ignored.append(p_name)
                    seen_upper.add(p_name.upper())

            self.ignored_com_ports = combined_ignored
            self.refresh_ports_dropdown()

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
                self.control_labels[i] = btn_label_vars[i].get().strip()
                self.control_commands[i] = btn_cmd_vars[i].get().strip()
                self.f_buttons[index].config(text=self.control_labels[i])

            self.save_config()
            dialog.destroy()

        ttk.Button(action_frame, text="Hủy", command=dialog.destroy).pack(side="right", padx=(5, 0))
        ttk.Button(action_frame, text="Lưu Cài đặt", command=save_and_close, style="Accent.TButton").pack(side="right")

    def open_about_dialog(self):
        """Mở Hộp thoại Giới thiệu ứng dụng độc lập."""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{APP_NAME} - Giới thiệu")
        set_window_icon_native(dialog)

        dialog.update_idletasks()
        width = 580
        height = 440
        x = max(0, self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2))
        y = max(0, self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2))
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        dialog.minsize(520, 360)
        dialog.transient(self.root)
        dialog.grab_set()

        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        dialog.configure(bg=p["bg"])

        main_box = ttk.Frame(dialog, padding=16)
        main_box.pack(fill="both", expand=True)

        about_title_lbl = tk.Label(
            main_box,
            text=APP_NAME,
            font=("Segoe UI", 15, "bold"),
            fg=p["accent"],
            bg=p["bg"]
        )
        about_title_lbl.pack(anchor="w", pady=(0, 2))

        about_version_lbl = tk.Label(
            main_box,
            text=f"Phiên bản: v{APP_VERSION}  |  Tác giả: {APP_AUTHOR}  |  Bản quyền: {APP_LICENSE} License",
            font=("Segoe UI", 10, "bold"),
            fg=p["text_fg"],
            bg=p["bg"]
        )
        about_version_lbl.pack(anchor="w", pady=(2, 10))

        features_frame = ttk.LabelFrame(main_box, text=" Tính năng & Công nghệ ", padding=10)
        features_frame.pack(fill="both", expand=True, pady=(0, 10))

        features_text = about_features_text()
        features_txt = tk.Text(
            features_frame,
            wrap="word",
            font=("Segoe UI", 9),
            relief="flat",
            bg=p["text_bg"],
            fg=p["text_fg"],
            padx=8,
            pady=8
        )
        features_scroll = ttk.Scrollbar(features_frame, orient="vertical", command=features_txt.yview)
        features_txt.configure(yscrollcommand=features_scroll.set)
        features_txt.pack(side="left", fill="both", expand=True)
        features_scroll.pack(side="right", fill="y")

        features_txt.insert("1.0", features_text)
        features_txt.config(state="disabled")

        btn_row = ttk.Frame(main_box)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="Đóng", command=dialog.destroy, style="Accent.TButton").pack(side="right")

    def open_update_dialog(self):
        """Mở Hộp thoại Kiểm tra và Tải bản cập nhật mới từ GitHub Releases."""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{APP_NAME} - Kiểm tra cập nhật phần mềm")
        set_window_icon_native(dialog)

        dialog.update_idletasks()
        width = 680
        height = 480
        x = max(0, self.root.winfo_x() + (self.root.winfo_width() // 2) - (width // 2))
        y = max(0, self.root.winfo_y() + (self.root.winfo_height() // 2) - (height // 2))
        dialog.geometry(f"{width}x{height}+{x}+{y}")

        dialog.minsize(620, 400)
        dialog.transient(self.root)
        dialog.grab_set()

        p = DARK_PALETTE if self.is_dark_mode else LIGHT_PALETTE
        dialog.configure(bg=p["bg"])

        main_box = ttk.Frame(dialog, padding=14)
        main_box.pack(fill="both", expand=True)

        update_top_frame = ttk.LabelFrame(main_box, text=" Kiểm Tra Phiên Bản Mới ", padding=10)
        update_top_frame.pack(fill="x", pady=(0, 8))

        lbl_update_ver = ttk.Label(
            update_top_frame,
            text=f"Phiên bản hiện tại: v{APP_VERSION}  |  Kho lưu trữ: https://github.com/{GITHUB_REPO}",
            font=("Segoe UI", 9, "bold")
        )
        lbl_update_ver.pack(anchor="w", pady=(0, 6))

        check_row = ttk.Frame(update_top_frame)
        check_row.pack(fill="x", pady=2)

        lbl_check_status = ttk.Label(check_row, text="Nhấn nút bên dưới để kiểm tra bản phát hành mới nhất từ GitHub.", font=("Segoe UI", 9))
        lbl_check_status.pack(side="left", padx=(0, 10))

        # Khung hiển thị chi tiết bản cập nhật
        release_frame = ttk.LabelFrame(main_box, text=" Chi Tiết Bản Phát Hành (Release Notes) ", padding=10)
        release_frame.pack(fill="both", expand=True, pady=(0, 8))

        txt_release_notes = tk.Text(
            release_frame,
            wrap="word",
            font=("Segoe UI", 9),
            relief="solid",
            borderwidth=1,
            bg=p["text_bg"],
            fg=p["text_fg"]
        )
        txt_release_notes.pack(side="left", fill="both", expand=True)
        rel_scroll = ttk.Scrollbar(release_frame, orient="vertical", command=txt_release_notes.yview)
        rel_scroll.pack(side="right", fill="y")
        txt_release_notes.configure(yscrollcommand=rel_scroll.set)
        txt_release_notes.insert("1.0", "Chưa kiểm tra cập nhật.\nBấm 'Kiểm Tra Bản Cập Nhật' để lấy thông tin phát hành mới nhất.")
        txt_release_notes.config(state="disabled")

        # Khung tải bản cập nhật
        download_box = ttk.LabelFrame(main_box, text=" Tải Bản Cập Nhật ", padding=10)
        download_box.pack(fill="x", pady=(0, 8))

        pb_download = ttk.Progressbar(download_box, orient="horizontal", mode="determinate")
        pb_download.pack(fill="x", pady=(0, 6))

        down_bottom_row = ttk.Frame(download_box)
        down_bottom_row.pack(fill="x")

        lbl_download_status = ttk.Label(down_bottom_row, text="", font=("Segoe UI", 9))
        lbl_download_status.pack(side="left")

        latest_update_info = {}
        download_in_progress = threading.Event()

        def on_check_update_click():
            btn_check.config(state="disabled")
            lbl_check_status.config(text="Đang kết nối GitHub Releases API...")

            def worker():
                res = check_for_updates(current_version=APP_VERSION, repo=GITHUB_REPO)

                def update_ui():
                    btn_check.config(state="normal")
                    latest_update_info.clear()
                    latest_update_info.update(res)

                    txt_release_notes.config(state="normal")
                    txt_release_notes.delete("1.0", "end")

                    if res.get("status") == "success":
                        tag = res.get("latest_version", "")
                        has_up = res.get("has_update", False)
                        rel_name = res.get("release_name", tag)
                        pub_date = res.get("published_at", "")
                        notes = res.get("release_notes", "")
                        asset_name = res.get("asset_name", "")
                        asset_size = res.get("asset_size", 0)

                        if has_up:
                            lbl_check_status.config(text=f"Có bản cập nhật mới: {tag} (Hiện tại: v{APP_VERSION})")
                            btn_download.config(state="normal")
                        else:
                            lbl_check_status.config(text=f"Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION}).")
                            btn_download.config(state="normal" if res.get("download_url") else "disabled")

                        lines = [
                            f"【 BẢN PHÁT HÀNH: {rel_name} ({tag}) 】",
                            f"Ngày phát hành: {pub_date}",
                            f"File tải về: {asset_name if asset_name else 'Mã nguồn (.zip)'}" + (f" ({asset_size / (1024*1024):.1f} MB)" if asset_size > 0 else ""),
                            "--------------------------------------------------------------------------------",
                            "Nội dung cập nhật & cải tiến:",
                            notes if notes else "(Không có ghi chú phát hành)."
                        ]
                        txt_release_notes.insert("1.0", "\n".join(lines))

                    elif res.get("status") == "no_releases":
                        lbl_check_status.config(text="Kho GitHub chưa tạo Release chính thức.")
                        txt_release_notes.insert("1.0", res.get("message", ""))
                        btn_download.config(state="disabled")
                    else:
                        lbl_check_status.config(text="Lỗi khi kiểm tra cập nhật.")
                        txt_release_notes.insert("1.0", f"Lỗi: {res.get('message', 'Không xác định')}")
                        btn_download.config(state="disabled")

                    txt_release_notes.config(state="disabled")

                dialog.after(0, update_ui)

            threading.Thread(target=worker, daemon=True).start()

        def on_download_click():
            if download_in_progress.is_set():
                return

            download_url = latest_update_info.get("download_url")
            if not download_url:
                messagebox.showinfo("Thông báo", "Không tìm thấy đường dẫn tải file cập nhật trực tiếp.", parent=dialog)
                return

            default_name = latest_update_info.get("asset_name", "Esp32_manager_tool_update.exe")
            ext = os.path.splitext(default_name)[1] or ".exe"

            dest_path = filedialog.asksaveasfilename(
                title="Chọn vị trí lưu file cập nhật",
                defaultextension=ext,
                initialfile=default_name,
                filetypes=[("Update Files (*.exe;*.zip)", "*.exe;*.zip"), ("All Files (*.*)", "*.*")],
                parent=dialog
            )
            if not dest_path:
                return

            download_in_progress.set()
            btn_download.config(state="disabled")
            btn_check.config(state="disabled")
            lbl_download_status.config(text="Đang kết nối tải file...")
            pb_download.config(value=0)

            def worker():
                def progress_cb(percent, downloaded, total):
                    def update_progress():
                        pb_download.config(value=percent)
                        if total > 0:
                            lbl_download_status.config(text=f"Đang tải: {downloaded / (1024*1024):.2f} MB / {total / (1024*1024):.2f} MB ({percent:.1f}%)")
                        else:
                            lbl_download_status.config(text=f"Đang tải: {downloaded / (1024*1024):.2f} MB...")
                    dialog.after(0, update_progress)

                success, msg = download_update_asset(download_url, dest_path, progress_callback=progress_cb)

                def download_finished():
                    download_in_progress.clear()
                    btn_download.config(state="normal")
                    btn_check.config(state="normal")
                    if success:
                        pb_download.config(value=100)
                        lbl_download_status.config(text=f"Tải thành công: {os.path.basename(dest_path)}")
                        messagebox.showinfo(
                            "Tải hoàn tất",
                            f"Đã tải thành công bản cập nhật về máy:\n{dest_path}\n\nBạn có thể đóng ứng dụng và chạy file này để cài đặt/sử dụng bản mới.",
                            parent=dialog
                        )
                    else:
                        lbl_download_status.config(text="Lỗi khi tải bản cập nhật.")
                        messagebox.showerror("Lỗi tải file", f"Không thể tải bản cập nhật:\n{msg}", parent=dialog)

                dialog.after(0, download_finished)

            threading.Thread(target=worker, daemon=True).start()

        btn_check = ttk.Button(check_row, text="Kiểm Tra Bản Cập Nhật", command=on_check_update_click)
        btn_check.pack(side="right")

        btn_download = ttk.Button(down_bottom_row, text="Tải Bản Cập Nhật Về Máy", command=on_download_click, state="disabled")
        btn_download.pack(side="right")

        btn_bottom_row = ttk.Frame(main_box)
        btn_bottom_row.pack(fill="x", pady=(6, 0))
        ttk.Button(btn_bottom_row, text="Đóng", command=dialog.destroy).pack(side="right")
