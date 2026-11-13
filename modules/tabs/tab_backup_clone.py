# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.3 - Tab 5: Backup & Direct Multi-Board Clone Mixin
Sao lưu phân vùng / toàn bộ Flash từ chip kèm hồ sơ băm (MD5, SHA-256, MAC gốc, tên chip, thời gian, địa chỉ, dung lượng)
và Sao chép trực tiếp (Direct Clone) từ 1 Board gốc sang 1 hoặc nhiều Board đích cùng lúc.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from modules.ui.models import BooleanVar as _BooleanVar, StringVar as _StringVar, END
from modules.ui import dialogs_service as messagebox
from modules.ui import dialogs_service as filedialog
from modules.backup_utils import (
    compute_bytes_hashes, smart_trim_trailing_ff,
    infer_bootloader_offset_for_chip, build_backup_metadata_report
)

from modules.config import (
    DARK_PALETTE, LIGHT_PALETTE, FLASH_BAUDS, REPORT_FONT_SIZE,
    APP_NAME, APP_VERSION
)
from modules.esptool_util import (
    run_esptool_command,
    esptool_command_succeeded,
    parse_esptool_output,
    parse_esptool_progress_percent,
)
from modules.serial_util import list_com_ports_local
from modules.partition.unit_formatter import (
    DisplayMode, format_bytes_human, format_hex, align_up
)
from modules.partition.chip_database import (
    CHIP_FAMILY_DATABASE, get_chip_info
)
from modules.partition.partition_model import (
    PartitionTable, PartitionEntry
)
from modules.tabs.tab_partition import DiskMapCanvas


class _TkCompat:
    BooleanVar = _BooleanVar
    StringVar = _StringVar
    END = END


tk = _TkCompat


class BackupCloneTabMixin:
    """
    Mixin quản lý Tab 5: Sao lưu & Nhân bản Trực tiếp (Backup & Direct Multi-Board Clone).
    """
    backup_hw_thread = None

    def create_backup_tab(self):
        """Khởi tạo giao diện Tab 5 bên trong self.backup_tab."""
        self.backup_hw_thread = None
        self._is_backup_hw_running = False
        self._backup_has_loaded_source = False
        self._syncing_backup_ports = False
        self._led_blink_thread = None
        self._led_blink_stop_event = threading.Event()
        self._is_led_blinking = False
        self._last_blink_port = ""
        self.backup_source_info = {
            "chip_name": "Chưa xác định",
            "chip_line": "Chưa đọc từ chip",
            "revision": "N/A",
            "crystal": "N/A",
            "mac": "Chưa xác định",
            "flash_size": 4 * 1024 * 1024,
            "bootloader_offset": 0x1000,
            "part_table_offset": 0x8000,
        }
        self.backup_last_saved_dir = ""
        self.backup_last_manifest: dict | None = None

        if not hasattr(self, "var_backup_smart_trim") or self.var_backup_smart_trim is None:
            self.var_backup_smart_trim = tk.BooleanVar(value=True)
        if not hasattr(self, "var_clone_erase_first") or self.var_clone_erase_first is None:
            self.var_clone_erase_first = tk.BooleanVar(value=False)
        if not hasattr(self, "var_clone_source_mode") or self.var_clone_source_mode is None:
            self.var_clone_source_mode = tk.StringVar(value="live_board")
        self.backup_selected_keys: set[str] = set()
        self.backup_region_hashes: dict[str, str] = {}
        self.clone_target_vars: dict[str, tk.BooleanVar] = {}

        # Khởi tạo bảng phân vùng trống hoàn toàn cho tới khi đọc cấu trúc từ chip nguồn
        self.backup_table = PartitionTable(flash_size=4 * 1024 * 1024, target_chip="esp32")

        if hasattr(self, 'backup_tree') and self.backup_tree is not None:
            if hasattr(self, 'backup_disk_map') and self.backup_disk_map is not None:
                self.backup_disk_map.on_select_entry = self._on_backup_map_click_entry
                self.backup_disk_map.set_theme_mode(getattr(self, "is_dark_mode", False))
            self.backup_tree.bind("<Button-1>", self._on_backup_tree_click)
            self.refresh_backup_views()
            return

    def log_backup(self, text: str, tag: str | None = None):
        """Ghi nhật ký vào khung log của Tab 5."""
        try:
            if hasattr(self, "backup_log_txt") and self.backup_log_txt.winfo_exists():
                self.backup_log_txt.config(state="normal")
                self.backup_log_txt.insert("end", text + "\n", tag)
                self.backup_log_txt.see("end")
                self.backup_log_txt.config(state="disabled")
        except Exception:
            pass

    def _get_all_backup_regions(self) -> list[dict]:
        """
        Trả về danh sách toàn bộ các phân vùng có thể sao lưu trên chip gốc:
        Bao gồm Bootloader, Partition Table và tất cả các phân vùng trong self.backup_table.entries.
        Trả về danh sách rỗng nếu chưa đọc từ chip và chưa có phân vùng nào.
        """
        if not getattr(self, "_backup_has_loaded_source", False) and not self.backup_table.entries:
            return []

        boot_off = int(self.backup_source_info.get("bootloader_offset", 0x1000))
        part_off = int(self.backup_source_info.get("part_table_offset", 0x8000))
        boot_size = max(0x1000, part_off - boot_off) if part_off > boot_off else 0x7000

        regions = [
            {
                "key": f"sys_bootloader_{boot_off:X}",
                "name": "bootloader",
                "type": "system",
                "subtype": "bootloader",
                "offset": boot_off,
                "size": boot_size,
                "is_system": True,
            },
            {
                "key": f"sys_parttable_{part_off:X}",
                "name": "partition_table",
                "type": "system",
                "subtype": "part_table",
                "offset": part_off,
                "size": 0x1000,
                "is_system": True,
            },
        ]

        for entry in sorted(self.backup_table.entries, key=lambda e: e.offset):
            regions.append({
                "key": f"part_{entry.name}_{entry.offset:X}",
                "name": entry.name,
                "type": entry.type_str,
                "subtype": entry.subtype_str,
                "offset": entry.offset,
                "size": entry.size,
                "is_system": False,
            })
        return regions

    def _get_backup_src_port(self) -> str:
        """Lấy cổng COM Board Gốc đồng bộ từ thanh chọn COM trên cùng."""
        port = ""
        if hasattr(self, "port_cb") and self.port_cb is not None:
            try:
                port = self.port_cb.get().strip()
            except Exception:
                port = ""
        if (not port or port == "Không có cổng COM") and hasattr(self, "port_var"):
            try:
                port = str(self.port_var.get()).strip()
            except Exception:
                port = ""
        if (not port or port == "Không có cổng COM") and hasattr(self, "backup_src_port_var"):
            try:
                port = str(self.backup_src_port_var.get()).strip()
            except Exception:
                port = ""
        if port == "Không có cổng COM":
            return ""
        return port

    def _sync_backup_source_port_ui(self, port_text: str | None = None) -> str:
        """Đồng bộ nhãn hiển thị Board Gốc ở Tab 5 theo Cổng COM trên cùng."""
        src = (port_text if port_text is not None else self._get_backup_src_port()).strip()
        if src == "Không có cổng COM":
            src = ""
        if hasattr(self, "backup_src_port_var") and self.backup_src_port_var is not None:
            if self.backup_src_port_var.get().strip() != src:
                self.backup_src_port_var.set(src)
        lbl = getattr(self, "lbl_backup_src_port", None)
        if lbl is not None:
            lbl.setText(src if src else "Chưa chọn")
            active_val = "true" if src else "false"
            if lbl.property("active") != active_val:
                lbl.setProperty("active", active_val)
                st = lbl.style()
                if st is not None:
                    st.unpolish(lbl)
                    st.polish(lbl)
        return src

    def _refresh_backup_ports(self):
        """Đồng bộ cổng Board Gốc từ thanh trên cùng và lọc danh sách Board Đích."""
        raw_ports = list_com_ports_local()
        filtered = self.filter_ignored_ports(raw_ports) if hasattr(self, "filter_ignored_ports") else raw_ports
        self._sync_backup_source_port_ui()
        self._refresh_clone_target_checkboxes(filtered)

    def _is_on_backup_tab(self) -> bool:
        """Kiểm tra người dùng có đang đứng ở Tab 5 (Backup & Clone) hay không."""
        if hasattr(self, "stack") and hasattr(self, "page_backup"):
            return self.stack.currentWidget() is self.page_backup
        if hasattr(self, "notebook") and hasattr(self, "backup_tab"):
            try:
                return self.notebook.stack.currentWidget() is self.backup_tab
            except Exception:
                pass
        return False

    def update_tab5_led_blink_visibility(self):
        """Ẩn/hiện nút Nháy LED trên Tab 5 theo tùy chọn ẩn trong Cài đặt."""
        enabled = bool(getattr(self, "tab5_led_blink_enabled", False))
        btn = getattr(self, "btn_backup_blink_led", None)
        if btn is not None and hasattr(btn, "setVisible"):
            btn.setVisible(enabled)
        if not enabled:
            self._stop_board_led_blink()

    def _stop_board_led_blink(self, join_timeout: float = 0.25):
        """Dừng ngay tiến trình nháy LED Board Gốc và giải phóng cổng COM an toàn."""
        stop_ev = getattr(self, "_led_blink_stop_event", None)
        if stop_ev is not None:
            stop_ev.set()
        t = getattr(self, "_led_blink_thread", None)
        if t is not None and t.is_alive() and threading.current_thread() is not t:
            try:
                t.join(timeout=join_timeout)
            except Exception:
                pass
        self._is_led_blinking = False
        btn = getattr(self, "btn_backup_blink_led", None)
        if btn is not None:
            try:
                btn.setText("Nháy LED")
            except Exception:
                pass

    def _start_board_led_blink(self, port: str, duration: float = 5.0) -> bool:
        """
        Gửi burst dữ liệu UART TX định kỳ (khoảng 10 Hz trong `duration` giây)
        mà không tạo xung DTR/RTS reset chip, giúp nháy LED TX/RX nhận diện Board Gốc an toàn.
        Chỉ hoạt động khi đang ở Tab 5 và tùy chọn ẩn đã được bật.
        """
        port = str(port or "").strip()
        if not port or port == "Không có cổng COM":
            return False
        if not bool(getattr(self, "tab5_led_blink_enabled", False)):
            return False
        if not self._is_on_backup_tab():
            return False
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            return False
        # Nếu Serial Monitor đang mở đúng cổng đó, không tranh chấp mở lại cổng
        cur_ser = getattr(self, "serial_connection", None)
        if cur_ser is not None and getattr(cur_ser, "is_open", False):
            ser_port = str(getattr(cur_ser, "port", "") or "").strip().upper()
            if ser_port == port.upper():
                self.log_backup(f">> [NHÁY LED] Cổng {port} đang mở ở Serial Monitor, bỏ qua nháy LED.", tag=None)
                return False

        self._stop_board_led_blink()
        self._led_blink_stop_event = threading.Event()
        stop_ev = self._led_blink_stop_event
        self._is_led_blinking = True
        self._last_blink_port = port

        btn = getattr(self, "btn_backup_blink_led", None)
        if btn is not None:
            try:
                btn.setText("Dừng nháy (5s)")
            except Exception:
                pass

        def safe_ui(fn):
            try:
                if hasattr(self, "ui_call") and callable(self.ui_call):
                    self.ui_call(fn)
                elif getattr(self, "root", None) and hasattr(self.root, "after"):
                    self.root.after(0, fn)
            except Exception:
                pass

        safe_ui(lambda p=port, d=int(round(duration)): self.set_status(
            f"Đang nháy LED nhận diện Board Gốc {p} trong {d}s...", "info"
        ))

        def worker():
            import serial
            ser = None
            try:
                ser = serial.Serial()
                ser.port = port
                ser.baudrate = 115200
                ser.timeout = 0.05
                ser.write_timeout = 0.05
                ser.rtscts = False
                ser.dsrdtr = False
                # Giữ DTR/RTS ở trạng thái thụ động để tránh reset ESP32 khi mở cổng
                ser.dtr = False
                ser.rts = False
                ser.open()

                start_t = time.monotonic()
                while not stop_ev.is_set() and (time.monotonic() - start_t) < duration:
                    if not self._is_on_backup_tab() or not getattr(self, "tab5_led_blink_enabled", False):
                        break
                    try:
                        ser.write(b"\n")
                        ser.flush()
                    except Exception:
                        break
                    if stop_ev.wait(0.1):
                        break
            except Exception as ex:
                err_msg = str(ex)
                safe_ui(lambda p=port, m=err_msg: self.log_backup(
                    f">> [NHÁY LED] Không thể mở {p}: {m}"
                ))
            finally:
                if ser is not None:
                    try:
                        if getattr(ser, "is_open", False):
                            ser.close()
                    except Exception:
                        pass

                def _cleanup_ui():
                    self._is_led_blinking = False
                    b = getattr(self, "btn_backup_blink_led", None)
                    if b is not None:
                        try:
                            b.setText("Nháy LED")
                        except Exception:
                            pass

                safe_ui(_cleanup_ui)

        self._led_blink_thread = threading.Thread(target=worker, daemon=True)
        self._led_blink_thread.start()
        return True

    def _on_backup_src_port_selected_by_user(self, port_text: str = ""):
        """Đồng bộ khi Cổng COM trên cùng đổi và nháy LED 5s nhận diện Board Gốc (nếu đang ở Tab 5)."""
        if getattr(self, "_syncing_backup_ports", False):
            return
        chosen = self._sync_backup_source_port_ui(port_text)
        self._refresh_clone_target_checkboxes()
        if chosen and self._is_on_backup_tab() and bool(getattr(self, "tab5_led_blink_enabled", False)):
            if not getattr(self, "_is_backup_hw_running", False):
                self._start_board_led_blink(chosen, duration=5.0)
        else:
            self._stop_board_led_blink()

    def _on_toggle_board_led_blink(self):
        """Bấm nút 'Nháy LED' bên cạnh Board Gốc để nháy 5 giây hoặc dừng sớm."""
        if getattr(self, "_is_led_blinking", False):
            self._stop_board_led_blink()
            self.set_status("Đã dừng nháy LED nhận diện Board Gốc.", "info")
            return
        port = self._sync_backup_source_port_ui()
        if not port:
            messagebox.showwarning(
                "Chưa chọn Board Gốc",
                "Vui lòng chọn cổng COM trên thanh điều khiển ở trên cùng trước khi nháy LED.",
                parent=self.root,
            )
            return
        self._start_board_led_blink(port, duration=5.0)

    def _refresh_clone_target_checkboxes(self, available_ports: list[str] | None = None):
        """Hiển thị danh sách các cổng COM Đích (loại trừ cổng COM đang làm Board Gốc ở chế độ Board Gốc trực tiếp)."""
        if not hasattr(self, "clone_target_ports_frame") or not self.clone_target_ports_frame.winfo_exists():
            return

        if available_ports is None:
            raw_ports = list_com_ports_local()
            available_ports = self.filter_ignored_ports(raw_ports) if hasattr(self, "filter_ignored_ports") else raw_ports

        # Lấy Board Gốc đồng bộ từ thanh Cổng COM trên cùng
        effective_src = self._sync_backup_source_port_ui()
        src_port = effective_src.upper()

        source_mode = "live_board"
        if hasattr(self, "var_clone_source_mode") and self.var_clone_source_mode is not None:
            source_mode = str(self.var_clone_source_mode.get() or "live_board").strip()

        prev_states = {k: v.get() for k, v in self.clone_target_vars.items()}
        if src_port and source_mode == "live_board":
            prev_states = {k: v for k, v in prev_states.items() if k.strip().upper() != src_port}

        if hasattr(self.clone_target_ports_frame, "clear_children"):
            self.clone_target_ports_frame.clear_children()
        else:
            for w in self.clone_target_ports_frame.winfo_children():
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self.clone_target_vars.clear()

        if source_mode == "live_board":
            target_candidates = [p for p in available_ports if p.strip() and p.strip().upper() != src_port]
        else:
            target_candidates = [p for p in available_ports if p.strip()]

        if not target_candidates:
            from PyQt6.QtWidgets import QLabel
            hint = (
                "(Chưa phát hiện thêm cổng COM đích nào khác ngoài cổng Board gốc. Hãy cắm thêm mạch đích và bấm 'Quét COM')"
                if source_mode == "live_board"
                else "(Chưa phát hiện cổng COM mạch đích nào đang cắm trên máy tính.)"
            )
            lbl = QLabel(hint, self.clone_target_ports_frame)
            lbl.setWordWrap(True)
            lbl.setProperty("role", "subtitle")
            lbl.setStyleSheet("font-style: italic;")
            if hasattr(self.clone_target_ports_frame, "_grid"):
                self.clone_target_ports_frame._grid.addWidget(lbl, 0, 0)
            return

        from PyQt6.QtWidgets import QCheckBox
        for idx, p_name in enumerate(target_candidates):
            var = _BooleanVar(value=prev_states.get(p_name, True))
            self.clone_target_vars[p_name] = var
            cb = QCheckBox(f"Board Đích: {p_name}", self.clone_target_ports_frame)
            cb.setChecked(var.get())
            cb.stateChanged.connect(lambda state, v=var: v.set(state == 2))
            if hasattr(self.clone_target_ports_frame, "_grid"):
                self.clone_target_ports_frame._grid.addWidget(cb, idx // 3, idx % 3)

    def _select_all_clone_targets(self, select: bool = True):
        for var in self.clone_target_vars.values():
            var.set(select)
        if hasattr(self, "clone_target_ports_frame"):
            for w in self.clone_target_ports_frame.winfo_children():
                if hasattr(w, "setChecked"):
                    w.setChecked(select)

    def refresh_backup_views(self):
        """Cập nhật thanh sơ đồ phân vùng DiskMapCanvas và bảng Treeview của Tab 5."""
        if not hasattr(self, "backup_tree") or not self.backup_tree.winfo_exists():
            return

        self._refresh_backup_ports()

        regions = self._get_all_backup_regions()
        for r in regions:
            r["selected"] = r["key"] in self.backup_selected_keys
        self.backup_regions = regions

        if not regions:
            self.backup_disk_map.set_checked_names(None)
            self.backup_disk_map.set_data(
                layout_entries=[],
                flash_size=self.backup_table.flash_size,
                display_mode=DisplayMode.DECIMAL,
                selected_entry=None
            )
            was_blocked = self.backup_tree.blockSignals(True)
            try:
                for item in self.backup_tree.get_children():
                    self.backup_tree.delete(item)
                self.backup_tree.clearSelection()
                self.backup_tree.setCurrentItem(None)
            finally:
                self.backup_tree.blockSignals(was_blocked)
            self.lbl_backup_chip_summary.config(
                text="Chưa đọc dữ liệu phân vùng từ chip nguồn (Chọn cổng Board Gốc và bấm 'Đọc Cấu Trúc Từ Chip Nguồn')."
            )
            return

        # Cập nhật thanh sơ đồ phân vùng (sử dụng checked_names, không đóng khung dính chọn cứng)
        layout_entries = self.backup_table.get_layout_with_unallocated()
        checked_names: set[str] = set()
        for r in regions:
            if r["key"] in self.backup_selected_keys:
                checked_names.add(r["name"])
                if r["name"] == "bootloader":
                    checked_names.add("Bootloader")
                elif r["name"] == "partition_table":
                    checked_names.add("Partition Table")

        self.backup_disk_map.set_checked_names(checked_names)
        self.backup_disk_map.set_data(
            layout_entries=layout_entries,
            flash_size=self.backup_table.flash_size,
            display_mode=DisplayMode.DECIMAL,
            selected_entry=None
        )

        # Cập nhật bảng Treeview
        selected_count = 0
        selected_bytes = 0
        was_blocked = self.backup_tree.blockSignals(True)
        try:
            for item in self.backup_tree.get_children():
                self.backup_tree.delete(item)

            for idx, reg in enumerate(regions, 1):
                key = reg["key"]
                is_checked = key in self.backup_selected_keys
                if is_checked:
                    selected_count += 1
                    selected_bytes += reg["size"]

                chk_symbol = "[x]" if is_checked else "[ ]"
                hash_info = self.backup_region_hashes.get(key, "Sẵn sàng sao lưu" if is_checked else "Bỏ qua")
                self.backup_tree.insert(
                    "",
                    "end",
                    iid=key,
                    values=(
                        chk_symbol,
                        idx,
                        reg["name"],
                        reg["type"],
                        reg["subtype"],
                        format_hex(reg["offset"]),
                        format_bytes_human(reg["size"]),
                        hash_info,
                    )
                )
            self.backup_tree.clearSelection()
            self.backup_tree.setCurrentItem(None)
        finally:
            self.backup_tree.blockSignals(was_blocked)

        chip_lbl = self.backup_source_info.get("chip_line", "Chưa đọc từ chip")
        mac_lbl = self.backup_source_info.get("mac", "N/A")
        flash_lbl = format_bytes_human(self.backup_table.flash_size)
        self.lbl_backup_chip_summary.config(
            text=(
                f"Chip gốc: {chip_lbl}  |  MAC gốc: {mac_lbl}  |  Flash: {flash_lbl}  |  "
                f"Đang chọn: {selected_count}/{len(regions)} phân vùng ({format_bytes_human(selected_bytes)})"
            )
        )

    def _on_backup_map_click_entry(self, entry: PartitionEntry):
        """Khi click vào một khối phân vùng trên thanh sơ đồ DiskMapCanvas -> Đảo chọn phân vùng đó."""
        if entry.is_unallocated:
            return
        if entry.is_system:
            boot_off = int(self.backup_source_info.get("bootloader_offset", 0x1000))
            part_off = int(self.backup_source_info.get("part_table_offset", 0x8000))
            if entry.type_str == "bootloader" or entry.name.lower() == "bootloader":
                key = f"sys_bootloader_{boot_off:X}"
            else:
                key = f"sys_parttable_{part_off:X}"
        else:
            key = f"part_{entry.name}_{entry.offset:X}"

        if key in self.backup_selected_keys:
            self.backup_selected_keys.remove(key)
        else:
            self.backup_selected_keys.add(key)
        self.refresh_backup_views()

    def _on_backup_tree_click(self, event):
        iid = self.backup_tree.identify_row(event.y)
        if not iid:
            return
        if iid in self.backup_selected_keys:
            self.backup_selected_keys.remove(iid)
        else:
            self.backup_selected_keys.add(iid)
        self.refresh_backup_views()
        if self.backup_tree.exists(iid):
            self.backup_tree.selection_set(iid)

    def _on_backup_tree_space(self, event):
        sel = self.backup_tree.selection()
        if not sel:
            return
        iid = sel[0]
        if iid in self.backup_selected_keys:
            self.backup_selected_keys.remove(iid)
        else:
            self.backup_selected_keys.add(iid)
        self.refresh_backup_views()
        if self.backup_tree.exists(iid):
            self.backup_tree.selection_set(iid)

    def _backup_select_all(self, select: bool = True):
        self.backup_selected_keys.clear()
        if select:
            for reg in self._get_all_backup_regions():
                self.backup_selected_keys.add(reg["key"])
        self.refresh_backup_views()

    def _action_backup_select_all(self, select: bool = True):
        self._backup_select_all(select)

    def _backup_select_firmware_only(self):
        """Chỉ tích chọn Bootloader, Partition Table và các phân vùng Firmware (app / otadata)."""
        self.backup_selected_keys.clear()
        for reg in self._get_all_backup_regions():
            if reg["is_system"] or reg["type"] == "app" or reg["subtype"] in ("ota", "otadata", "phy"):
                self.backup_selected_keys.add(reg["key"])
        self.refresh_backup_views()

    def _action_backup_select_firmware_only(self):
        self._backup_select_firmware_only()

    def _set_backup_ui_state(self, state):
        if isinstance(state, bool):
            state = "normal" if state else "disabled"
        for attr in (
            "btn_backup_blink_led", "cb_backup_baud",
            "btn_backup_read_chip", "btn_backup_sel_all", "btn_backup_unsel_all",
            "btn_backup_sel_fw", "chk_backup_trim", "btn_backup_to_folder",
            "btn_backup_full_chip", "btn_backup_to_flasher", "btn_direct_clone",
            "chk_clone_erase"
        ):
            w = getattr(self, attr, None)
            if w and hasattr(w, "config"):
                try:
                    w.config(state=state)
                except Exception:
                    pass

    def _prepare_backup_source_port(self) -> tuple[str, int] | None:
        if hasattr(self, "_stop_board_led_blink"):
            self._stop_board_led_blink()
        port = self._sync_backup_source_port_ui()
        if not port:
            messagebox.showwarning(
                "Thiếu Cổng COM",
                "Vui lòng chọn cổng COM trên thanh điều khiển ở trên cùng trước khi thao tác!",
                parent=self.root,
            )
            return None

        baud_str = self.backup_baud_var.get().strip()
        baud = int(baud_str) if baud_str.isdigit() else 460800

        if getattr(self, "serial_connection", None) and getattr(self.serial_connection, "is_open", False):
            self.on_serial_disconnect()
            self.log_backup(">> [HỆ THỐNG] Đã tự động tạm ngắt Serial Monitor để thực thi tác vụ Sao lưu / Nhân bản.")
        return port, baud

    def _probe_chip_and_partition_sync(self, port: str, baud: int, safe_after) -> bool:
        """
        Đọc thông tin định danh chip (Tên chip, Revision, Crystal, MAC gốc, Dung lượng Flash)
        và đọc bảng phân vùng 0x8000 từ Board Gốc.
        """
        safe_after(lambda: self.log_backup(f"\n=== ĐỌC THÔNG TIN CHIP & BẢNG PHÂN VÙNG TỪ BOARD GỐC ({port}) ===", "header"))
        safe_after(lambda: self.set_status(f"Đang nhận diện chip và đọc MAC gốc trên {port}...", "info", progress=15))

        fid_out = run_esptool_command(["--port", port, "--baud", str(baud), "flash-id"])
        if not esptool_command_succeeded(fid_out):
            safe_after(lambda: self.log_backup(">>> [LỖI] Không thể kết nối với chip trên cổng " + port, "red"))
            return False

        parsed = parse_esptool_output({"flash_id": fid_out})
        chip_key = parsed.get("chip_name_key") or "ESP32"
        chip_line = parsed.get("chip_line") or chip_key
        rev = parsed.get("revision") or "N/A"
        crystal = parsed.get("crystal") or "N/A"
        mac_hex = parsed.get("mac")
        mac_fmt = ":".join(mac_hex[i:i+2] for i in range(0, 12, 2)).upper() if mac_hex and len(mac_hex) == 12 else "N/A"
        flash_mb = parsed.get("flash_mb") or 4.0
        flash_bytes = int(flash_mb * 1024 * 1024)
        boot_off = infer_bootloader_offset_for_chip(chip_key)

        self.backup_source_info.update({
            "source_port": port,
            "chip_name": chip_key,
            "chip_line": chip_line,
            "revision": rev,
            "crystal": crystal,
            "mac": mac_fmt,
            "flash_size": flash_bytes,
            "bootloader_offset": boot_off,
            "part_table_offset": 0x8000,
        })

        safe_after(lambda: self.log_backup(
            f"  + Chip gốc: {chip_line} | MAC gốc: {mac_fmt} | Flash: {flash_mb:.1f} MB | Bootloader @ 0x{boot_off:X}"
        ))
        safe_after(
            lambda: self.set_status(
                f"Đang đọc bảng phân vùng (0x8000) từ {chip_key}...",
                "info",
                progress=45,
                task_label=f"Đọc bảng phân vùng ({port})",
            )
        )

        with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            def on_pt_stream(line):
                pct_val = parse_esptool_progress_percent(line)
                if pct_val is not None:
                    prog = 45.0 + (pct_val / 100.0) * 45.0
                    safe_after(
                        lambda p=prog, pt=port: self.set_status(
                            f"Đang đọc bảng phân vùng ({int(round(pct_val))}%)...",
                            "info",
                            progress=p,
                            task_label=f"Đọc bảng phân vùng ({pt})",
                        )
                    )

            read_out = run_esptool_command(
                ["--port", port, "--baud", str(baud), "read-flash", "0x8000", "0x1000", tmp_path],
                progress_callback=on_pt_stream,
            )
            if esptool_command_succeeded(read_out) and os.path.isfile(tmp_path) and os.path.getsize(tmp_path) > 0:
                with open(tmp_path, "rb") as f:
                    pt_bytes = f.read()
                new_table = PartitionTable(flash_size=flash_bytes, target_chip=chip_key.lower().replace("-", ""))
                new_table.bootloader_offset = boot_off
                new_table.from_binary(pt_bytes)
                if new_table.entries:
                    self.backup_table = new_table
                    safe_after(lambda n=len(new_table.entries): self.log_backup(
                        f"  + Đã giải mã thành công {n} phân vùng từ bảng phân vùng trên chip.", "green"
                    ))
                else:
                    self.backup_table.flash_size = flash_bytes
                    self.backup_table.bootloader_offset = boot_off
                    safe_after(lambda: self.log_backup(
                        "  ! Không tìm thấy cấu trúc phân vùng chuẩn tại 0x8000, giữ danh sách phân vùng hiện tại."
                    ))
            else:
                return False
        finally:
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        self._backup_has_loaded_source = True
        return True

    def _hw_probe_source_chip_for_backup(self):
        """Sự kiện bấm nút 'ĐỌC CẤU TRÚC & MAC TỪ CHIP GỐC'."""
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            messagebox.showwarning("Thiết bị đang bận", "Vui lòng đợi tác vụ phần cứng hiện tại hoàn tất!", parent=self.root)
            return

        prep = self._prepare_backup_source_port()
        if not prep:
            return
        port, baud = prep

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_backup_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, "đọc cấu trúc phân vùng & MAC từ chip gốc"))
            else:
                safe_after(lambda: self._set_backup_ui_state("disabled"))

            ok = False
            try:
                ok = self._probe_chip_and_partition_sync(port, baud, safe_after)
                if ok:
                    def _on_ok():
                        self.backup_selected_keys = {r["key"] for r in self._get_all_backup_regions()}
                        self.backup_region_hashes.clear()
                        self.refresh_backup_views()
                        self.set_status(
                            "Đã đọc thông tin chip, địa chỉ MAC và bảng phân vùng thành công!",
                            "success",
                            progress=100,
                            task_label="Đọc chip nguồn hoàn tất",
                        )
                    safe_after(_on_ok)
                else:
                    safe_after(
                        lambda: self.set_status(
                            "Không thể đọc cấu trúc từ chip gốc!",
                            "error",
                            progress=0,
                            task_label="Lỗi đọc chip nguồn",
                        )
                    )
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda m=err_msg: self.log_backup(f">>> [NGOẠI LỆ] {m}", "red"))
                safe_after(
                    lambda: self.set_status(
                        "Lỗi khi đọc chip gốc!",
                        "error",
                        progress=0,
                        task_label="Lỗi đọc chip nguồn",
                    )
                )
            finally:
                self._is_backup_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))
                else:
                    safe_after(lambda: self._set_backup_ui_state("normal"))

        self.backup_hw_thread = threading.Thread(target=worker, daemon=True)
        self.backup_hw_thread.start()

    def _dump_selected_regions_to_dir_sync(
        self, port: str, baud: int, out_dir: str, regions: list[dict], smart_trim: bool, safe_after,
        progress_start: float = 15.0, progress_end: float = 95.0, stage_label: str = "Sao lưu"
    ) -> dict | None:
        """
        Thực thi đọc tuần tự các phân vùng đã chọn từ cổng `port` ra thư mục `out_dir`,
        tính toán mã băm MD5 & SHA-256, xuất `partitions.csv`, `backup_manifest.json` và `backup_info.txt`.
        """
        os.makedirs(out_dir, exist_ok=True)
        total_bytes = max(1, sum(r["size"] for r in regions))
        completed_bytes = 0
        saved_regions_meta = []

        for idx, reg in enumerate(regions, 1):
            r_name = reg["name"]
            r_off = reg["offset"]
            r_size = reg["size"]
            safe_filename = f"{idx:02d}_{r_name}_{format_hex(r_off)}.bin"
            dest_path = os.path.join(out_dir, safe_filename)

            reg_start_prog = progress_start + ((completed_bytes / total_bytes) * (progress_end - progress_start))
            reg_task = f"{stage_label} [{idx}/{len(regions)}]: {r_name}"

            safe_after(lambda n=r_name, o=r_off, s=r_size, i=idx, tot=len(regions): self.log_backup(
                f"  [{i}/{tot}] Đang sao lưu '{n}' tại {format_hex(o)} ({format_bytes_human(s)})..."
            ))
            safe_after(
                lambda p=reg_start_prog, n=r_name, i=idx, tot=len(regions), tl=reg_task: self.set_status(
                    f"{stage_label} [{i}/{tot}] '{n}'...", "warning", progress=p, task_label=tl
                )
            )

            def on_stream(
                line,
                base_done=completed_bytes,
                cur_sz=r_size,
                reg_name=r_name,
                reg_idx=idx,
                reg_tot=len(regions),
                tl=reg_task,
            ):
                pct_val = parse_esptool_progress_percent(line)
                if pct_val is not None:
                    cur_done = base_done + (pct_val / 100.0) * cur_sz
                    overall = progress_start + ((cur_done / total_bytes) * (progress_end - progress_start))
                    safe_after(
                        lambda p=overall, n=reg_name, pc=int(round(pct_val)), i=reg_idx, tot=reg_tot, t_lbl=tl: self.set_status(
                            f"{stage_label} [{i}/{tot}] '{n}' ({pc}%)...",
                            "warning",
                            progress=p,
                            task_label=t_lbl,
                        )
                    )

            args = ["--port", port, "--baud", str(baud), "read-flash", format_hex(r_off), format_hex(r_size), dest_path]
            res = run_esptool_command(args, progress_callback=on_stream)
            if not esptool_command_succeeded(res) or not os.path.isfile(dest_path):
                safe_after(lambda n=r_name: self.log_backup(f">>> [LỖI] Sao lưu phân vùng '{n}' thất bại!", "red"))
                return None

            with open(dest_path, "rb") as f:
                raw_data = f.read()

            if smart_trim and not reg.get("is_system", False):
                final_data = smart_trim_trailing_ff(raw_data, min_size=4096, align_bytes=4096)
                if len(final_data) != len(raw_data):
                    with open(dest_path, "wb") as f:
                        f.write(final_data)
            else:
                final_data = raw_data

            hashes = compute_bytes_hashes(final_data)
            short_sha = f"SHA256: {hashes['sha256'][:16]}..."
            reg_key = reg["key"]
            self.backup_region_hashes[reg_key] = short_sha

            saved_regions_meta.append({
                "key": reg_key,
                "name": r_name,
                "type": reg["type"],
                "subtype": reg["subtype"],
                "offset": r_off,
                "offset_hex": format_hex(r_off),
                "partition_size": r_size,
                "partition_size_human": format_bytes_human(r_size),
                "saved_size": len(final_data),
                "saved_size_human": format_bytes_human(len(final_data)),
                "filename": safe_filename,
                "filepath": dest_path,
                "md5": hashes["md5"],
                "sha256": hashes["sha256"],
            })

            safe_after(
                lambda n=r_name, sz=len(final_data), md5=hashes["md5"], sha=hashes["sha256"]: self.log_backup(
                    f"      -> Đã lưu: {format_bytes_human(sz)} | MD5: {md5} | SHA256: {sha[:24]}...", "green"
                )
            )
            completed_bytes += r_size

        # Xuất thêm file partitions.csv chuẩn ESP-IDF
        try:
            csv_path = os.path.join(out_dir, "partitions.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write(self.backup_table.to_csv())
        except Exception:
            pass

        manifest = {
            "app_name": APP_NAME,
            "app_version": APP_VERSION,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_port": port,
            "baudrate": baud,
            "source_chip": self.backup_source_info.get("chip_line", "ESP32"),
            "source_chip_key": self.backup_source_info.get("chip_name", "ESP32"),
            "source_revision": self.backup_source_info.get("revision", "N/A"),
            "source_crystal": self.backup_source_info.get("crystal", "N/A"),
            "source_mac": self.backup_source_info.get("mac", "N/A"),
            "flash_size_bytes": self.backup_table.flash_size,
            "flash_size_human": format_bytes_human(self.backup_table.flash_size),
            "smart_trim": smart_trim,
            "regions": saved_regions_meta,
        }

        manifest_json_path = os.path.join(out_dir, "backup_manifest.json")
        with open(manifest_json_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        info_txt_path = os.path.join(out_dir, "backup_info.txt")
        report_txt = build_backup_metadata_report(manifest)
        with open(info_txt_path, "w", encoding="utf-8") as f:
            f.write(report_txt)

        safe_after(lambda p=info_txt_path: self.log_backup(f"  + Đã ghi hồ sơ băm & thông tin gốc: {p}", "blue"))
        return manifest

    def _hw_backup_selected_to_folder(self):
        """Sao lưu các phân vùng đang được tích chọn ra thư mục trên máy tính kèm file backup_info.txt."""
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            messagebox.showwarning("Thiết bị đang bận", "Vui lòng đợi tác vụ hiện tại hoàn tất!", parent=self.root)
            return

        selected_regions = [r for r in self._get_all_backup_regions() if r["key"] in self.backup_selected_keys]
        if not selected_regions:
            messagebox.showwarning("Chưa chọn phân vùng", "Vui lòng tích chọn ít nhất 1 phân vùng trong danh sách để sao lưu!", parent=self.root)
            return

        prep = self._prepare_backup_source_port()
        if not prep:
            return
        port, baud = prep

        parent_dir = filedialog.askdirectory(
            title="Chọn thư mục chứa bản sao lưu Firmware & Phân vùng",
            parent=self.root
        )
        if not parent_dir:
            return

        chip_tag = (self.backup_source_info.get("chip_name") or "ESP").replace(" ", "_")
        ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(parent_dir, f"Backup_{chip_tag}_{ts_tag}")
        smart_trim = bool(self.var_backup_smart_trim.get())

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_backup_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, "sao lưu phân vùng từ chip ra máy tính"))
            else:
                safe_after(lambda: self._set_backup_ui_state("disabled"))

            try:
                # Nếu chưa đọc thông tin MAC/chip thực tế từ cổng này, tự động đọc trước khi sao lưu
                if (
                    self.backup_source_info.get("mac") in (None, "Chưa xác định", "N/A")
                    or self.backup_source_info.get("source_port") != port
                ):
                    self._probe_chip_and_partition_sync(port, baud, safe_after)

                manifest = self._dump_selected_regions_to_dir_sync(
                    port, baud, out_dir, selected_regions, smart_trim, safe_after,
                    progress_start=20.0, progress_end=98.0, stage_label="Sao lưu"
                )
                if manifest:
                    self.backup_last_saved_dir = out_dir
                    self.backup_last_manifest = manifest
                    safe_after(self.refresh_backup_views)
                    safe_after(
                        lambda: self.set_status(
                            "Đã sao lưu thành công kèm hồ sơ SHA-256 & MAC gốc!",
                            "success",
                            progress=100,
                            task_label="Hoàn tất sao lưu",
                        )
                    )
                    safe_after(lambda: self.log_backup(f"\n>>> HOÀN TẤT SAO LƯU VÀO THƯ MỤC:\n    {out_dir}", "green"))
                    safe_after(lambda: messagebox.showinfo(
                        "Sao lưu thành công",
                        f"Đã sao lưu {len(selected_regions)} phân vùng kèm hồ sơ mã băm (MD5/SHA-256), địa chỉ MAC gốc và thông tin chip tại:\n\n{out_dir}",
                        parent=self.root
                    ))
                else:
                    safe_after(
                        lambda: self.set_status(
                            "Sao lưu phân vùng thất bại!",
                            "error",
                            progress=0,
                            task_label="Lỗi sao lưu",
                        )
                    )
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda m=err_msg: self.log_backup(f">>> [NGOẠI LỆ] {m}", "red"))
                safe_after(
                    lambda: self.set_status(
                        "Lỗi trong quá trình sao lưu!",
                        "error",
                        progress=0,
                        task_label="Lỗi sao lưu",
                    )
                )
            finally:
                self._is_backup_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))
                else:
                    safe_after(lambda: self._set_backup_ui_state("normal"))

        self.backup_hw_thread = threading.Thread(target=worker, daemon=True)
        self.backup_hw_thread.start()

    def _hw_backup_full_flash_single_file(self):
        """Sao lưu toàn bộ bộ nhớ Flash từ 0x0 đến hết dung lượng Flash ra 1 file .bin duy nhất kèm file .txt thông tin."""
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            messagebox.showwarning("Thiết bị đang bận", "Vui lòng đợi tác vụ hiện tại hoàn tất!", parent=self.root)
            return

        prep = self._prepare_backup_source_port()
        if not prep:
            return
        port, baud = prep

        chip_tag = (self.backup_source_info.get("chip_name") or "ESP32").replace(" ", "_")
        ts_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = filedialog.asksaveasfilename(
            title="Lưu bản sao lưu Toàn Bộ Flash (0x0 -> Hết Flash)",
            defaultextension=".bin",
            initialfile=f"FullFlash_{chip_tag}_{ts_tag}.bin",
            filetypes=[("Binary Flash Dump (*.bin)", "*.bin"), ("All Files (*.*)", "*.*")],
            parent=self.root
        )
        if not save_path:
            return

        smart_trim = bool(self.var_backup_smart_trim.get())

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_backup_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, "sao lưu toàn bộ Flash (0x0)"))
            else:
                safe_after(lambda: self._set_backup_ui_state("disabled"))

            try:
                if (
                    self.backup_source_info.get("mac") in (None, "Chưa xác định", "N/A")
                    or self.backup_source_info.get("source_port") != port
                ):
                    self._probe_chip_and_partition_sync(port, baud, safe_after)

                flash_sz = int(self.backup_table.flash_size)
                safe_after(lambda: self.log_backup(
                    f"\n=== BẮT ĐẦU SAO LƯU TOÀN BỘ FLASH (0x0 -> {format_hex(flash_sz)}, {format_bytes_human(flash_sz)}) ===",
                    "header"
                ))
                safe_after(
                    lambda pt=port: self.set_status(
                        f"Đang đọc toàn bộ Flash từ {pt}...",
                        "warning",
                        progress=15,
                        task_label=f"Xuất toàn bộ Flash ({pt})",
                    )
                )

                def on_stream(line):
                    pct_val = parse_esptool_progress_percent(line)
                    if pct_val is not None:
                        prog = 15.0 + (pct_val / 100.0) * 80.0
                        safe_after(
                            lambda p=prog, pc=int(round(pct_val)), pt=port: self.set_status(
                                f"Đang đọc toàn bộ Flash ({pc}%)...",
                                "warning",
                                progress=p,
                                task_label=f"Xuất toàn bộ Flash ({pt})",
                            )
                        )

                res = run_esptool_command(
                    ["--port", port, "--baud", str(baud), "read-flash", "0x0", format_hex(flash_sz), save_path],
                    progress_callback=on_stream
                )
                if esptool_command_succeeded(res) and os.path.isfile(save_path):
                    with open(save_path, "rb") as f:
                        raw_data = f.read()
                    if smart_trim:
                        final_data = smart_trim_trailing_ff(raw_data, min_size=65536, align_bytes=4096)
                        if len(final_data) != len(raw_data):
                            with open(save_path, "wb") as f:
                                f.write(final_data)
                    else:
                        final_data = raw_data

                    hashes = compute_bytes_hashes(final_data)
                    manifest = {
                        "app_name": APP_NAME,
                        "app_version": APP_VERSION,
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "source_port": port,
                        "baudrate": baud,
                        "source_chip": self.backup_source_info.get("chip_line", "ESP32"),
                        "source_revision": self.backup_source_info.get("revision", "N/A"),
                        "source_crystal": self.backup_source_info.get("crystal", "N/A"),
                        "source_mac": self.backup_source_info.get("mac", "N/A"),
                        "flash_size_bytes": flash_sz,
                        "flash_size_human": format_bytes_human(flash_sz),
                        "smart_trim": smart_trim,
                        "regions": [{
                            "name": "full_flash",
                            "type": "image",
                            "subtype": "full_dump",
                            "offset": 0,
                            "offset_hex": "0x0",
                            "partition_size": flash_sz,
                            "partition_size_human": format_bytes_human(flash_sz),
                            "saved_size": len(final_data),
                            "saved_size_human": format_bytes_human(len(final_data)),
                            "filename": os.path.basename(save_path),
                            "filepath": save_path,
                            "md5": hashes["md5"],
                            "sha256": hashes["sha256"],
                        }],
                    }
                    info_path = os.path.splitext(save_path)[0] + "_backup_info.txt"
                    with open(info_path, "w", encoding="utf-8") as f:
                        f.write(build_backup_metadata_report(manifest))

                    self.backup_last_manifest = manifest
                    safe_after(
                        lambda: self.set_status(
                            "Đã sao lưu toàn bộ Flash kèm file thông tin thành công!",
                            "success",
                            progress=100,
                            task_label="Hoàn tất xuất Flash",
                        )
                    )
                    safe_after(lambda: self.log_backup(
                        f">>> ĐÃ LƯU FULL FLASH: {save_path}\n"
                        f"    Dung lượng lưu: {format_bytes_human(len(final_data))} | MD5: {hashes['md5']}\n"
                        f"    SHA-256: {hashes['sha256']}\n"
                        f"    File thông tin: {info_path}",
                        "green"
                    ))
                    safe_after(lambda: messagebox.showinfo(
                        "Sao lưu Toàn bộ Flash thành công",
                        f"Đã lưu ảnh nhị phân toàn bộ Flash tại:\n{save_path}\n\n"
                        f"Kèm hồ sơ mã băm SHA-256 & MAC gốc tại:\n{info_path}",
                        parent=self.root
                    ))
                else:
                    safe_after(
                        lambda: self.set_status(
                            "Sao lưu toàn bộ Flash thất bại!",
                            "error",
                            progress=0,
                            task_label="Lỗi xuất Flash",
                        )
                    )
                    safe_after(lambda: self.log_backup(">>> [LỖI] Không thể đọc toàn bộ Flash từ chip!", "red"))
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda m=err_msg: self.log_backup(f">>> [NGOẠI LỆ] {m}", "red"))
                safe_after(
                    lambda: self.set_status(
                        "Lỗi khi sao lưu toàn bộ Flash!",
                        "error",
                        progress=0,
                        task_label="Lỗi xuất Flash",
                    )
                )
            finally:
                self._is_backup_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))
                else:
                    safe_after(lambda: self._set_backup_ui_state("normal"))

        self.backup_hw_thread = threading.Thread(target=worker, daemon=True)
        self.backup_hw_thread.start()

    def _action_send_backup_to_flasher_tab(self):
        """Đẩy tự động các file .bin và địa chỉ Offset từ bản sao lưu gần nhất sang 4 hàng của Tab 3 (Nạp Flash)."""
        if not self.backup_last_manifest or not self.backup_last_manifest.get("regions"):
            messagebox.showinfo(
                "Chưa có bản sao lưu",
                "Hãy thực hiện Sao lưu ra thư mục (hoặc Sao lưu Toàn bộ Flash) trước khi đẩy sang Tab Nạp Flash!",
                parent=self.root
            )
            return

        regions = self.backup_last_manifest["regions"][:4]
        if hasattr(self, "flash_file_rows"):
            for idx, row in enumerate(self.flash_file_rows):
                if idx < len(regions):
                    reg = regions[idx]
                    row["var_enable"].set(True)
                    row["path_entry"].delete(0, tk.END)
                    row["path_entry"].insert(0, reg["filepath"])
                    row["offset_entry"].delete(0, tk.END)
                    row["offset_entry"].insert(0, reg["offset_hex"])
                    if hasattr(self, "_update_file_size_display"):
                        self._update_file_size_display(idx)
                else:
                    row["var_enable"].set(False)

        if hasattr(self, "notebook") and hasattr(self, "flasher_tab"):
            self.notebook.select(self.flasher_tab)
        self.set_status(f"Đã nạp {len(regions)} file từ bản sao lưu sang Tab Nạp Flash!", "success")

    def _hw_start_direct_multi_board_clone(self):
        """
        Sao chép trực tiếp từ 1 Board Gốc (hoặc thư mục sao lưu) sang 1 hoặc nhiều Board Đích đang cắm trên máy tính.
        """
        if self._is_backup_hw_running or (hasattr(self, "is_device_busy") and self.is_device_busy()):
            messagebox.showwarning("Thiết bị đang bận", "Vui lòng đợi tác vụ hiện tại hoàn tất!", parent=self.root)
            return

        target_ports = [p for p, var in self.clone_target_vars.items() if var.get()]
        if not target_ports:
            messagebox.showwarning(
                "Chưa chọn Board Đích",
                "Vui lòng cắm thêm ít nhất 1 mạch ESP đích vào máy tính, bấm 'Làm mới COM' và tích chọn các cổng COM Đích cần nhận sao chép!",
                parent=self.root
            )
            return

        source_mode = self.var_clone_source_mode.get()
        baud_str = self.backup_baud_var.get().strip()
        baud = int(baud_str) if baud_str.isdigit() else 460800
        erase_first = bool(self.var_clone_erase_first.get())
        smart_trim = bool(self.var_backup_smart_trim.get())

        selected_regions = [r for r in self._get_all_backup_regions() if r["key"] in self.backup_selected_keys]
        src_port = ""
        saved_folder_dir = ""

        if source_mode == "live_board":
            if not selected_regions:
                messagebox.showwarning("Chưa chọn phân vùng", "Vui lòng tích chọn các phân vùng cần sao chép ở bảng bên trái!", parent=self.root)
                return
            prep = self._prepare_backup_source_port()
            if not prep:
                return
            src_port, baud = prep
            if src_port.upper() in [t.upper() for t in target_ports]:
                messagebox.showerror("Trùng cổng COM", "Cổng COM Nguồn không được nằm trong danh sách Cổng COM Đích!", parent=self.root)
                return
        else:
            init_dir = self.backup_last_saved_dir if (self.backup_last_saved_dir and os.path.isdir(self.backup_last_saved_dir)) else "."
            saved_folder_dir = filedialog.askdirectory(
                initialdir=init_dir,
                title="Chọn thư mục chứa bản sao lưu (có file backup_manifest.json)",
                parent=self.root
            )
            if not saved_folder_dir:
                return
            manifest_file = os.path.join(saved_folder_dir, "backup_manifest.json")
            if not os.path.isfile(manifest_file):
                messagebox.showerror(
                    "Thiếu hồ sơ sao lưu",
                    f"Không tìm thấy file 'backup_manifest.json' trong thư mục:\n{saved_folder_dir}",
                    parent=self.root
                )
                return

        targets_str = ", ".join(target_ports)
        src_desc = f"Board Gốc ({src_port})" if source_mode == "live_board" else f"Thư mục ({os.path.basename(saved_folder_dir)})"
        if not messagebox.askyesno(
            "Xác nhận Sao chép Trực tiếp (Direct Clone)",
            f"Nguồn sao chép: {src_desc}\n"
            f"Các Board Đích nhận dữ liệu ({len(target_ports)} mạch): {targets_str}\n"
            f"Tốc độ Baud: {baud} bps\n\n"
            f"Bạn có chắc chắn muốn bắt đầu sao chép đồng loạt sang {len(target_ports)} mạch đích không?",
            parent=self.root
        ):
            return

        def safe_after(fn, delay=0):
            try:
                if getattr(self, "root", None) and self.root.winfo_exists():
                    self.root.after(delay, fn)
            except Exception:
                pass

        def worker():
            self._is_backup_hw_running = True
            if hasattr(self, "set_global_busy_state"):
                safe_after(lambda: self.set_global_busy_state(True, f"nhân bản sang {len(target_ports)} board đích"))
            else:
                safe_after(lambda: self._set_backup_ui_state("disabled"))

            temp_clone_dir = None
            try:
                if source_mode == "live_board":
                    temp_clone_dir = tempfile.mkdtemp(prefix="esp32_direct_clone_")
                    safe_after(lambda: self.log_backup(
                        f"\n=== BƯỚC 1/2: HÚT DỮ LIỆU TỪ BOARD GỐC ({src_port}) ===", "header"
                    ))
                    safe_after(
                        lambda pt=src_port: self.set_status(
                            f"Bước 1/2: chuẩn bị đọc dữ liệu từ Board Gốc {pt}...",
                            "info",
                            progress=5,
                            task_label=f"Bước 1/2 - Đọc nguồn ({pt})",
                        )
                    )
                    if (
                        self.backup_source_info.get("mac") in (None, "Chưa xác định", "N/A")
                        or self.backup_source_info.get("source_port") != src_port
                    ):
                        self._probe_chip_and_partition_sync(src_port, baud, safe_after)

                    manifest = self._dump_selected_regions_to_dir_sync(
                        src_port, baud, temp_clone_dir, selected_regions, smart_trim, safe_after,
                        progress_start=10.0, progress_end=50.0, stage_label="Bước 1/2 - Đọc nguồn"
                    )
                    if not manifest or not manifest.get("regions"):
                        safe_after(
                            lambda: self.set_status(
                                "Lỗi khi đọc dữ liệu từ Board Gốc! Đã dừng sao chép.",
                                "error",
                                progress=0,
                                task_label="Lỗi đọc Board Gốc",
                            )
                        )
                        return
                else:
                    manifest_file = os.path.join(saved_folder_dir, "backup_manifest.json")
                    with open(manifest_file, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    for reg in manifest.get("regions", []):
                        reg["filepath"] = os.path.join(saved_folder_dir, reg["filename"])

                write_pairs = []
                for reg in manifest.get("regions", []):
                    fpath = reg.get("filepath")
                    off_hex = reg.get("offset_hex")
                    if fpath and os.path.isfile(fpath) and off_hex:
                        write_pairs.append((off_hex, fpath))

                if not write_pairs:
                    safe_after(
                        lambda: self.set_status(
                            "Không có dữ liệu phân vùng hợp lệ để ghi!",
                            "error",
                            progress=0,
                            task_label="Thiếu dữ liệu nguồn",
                        )
                    )
                    return

                step_label = "BƯỚC 2/2" if source_mode == "live_board" else "BƯỚC 1/1"
                step_short = "Bước 2/2" if source_mode == "live_board" else "Nạp đích"
                step_start_pct = 50.0 if source_mode == "live_board" else 10.0
                step_span_pct = 98.0 - step_start_pct

                safe_after(lambda sl=step_label: self.log_backup(
                    f"\n=== {sl}: SAO CHÉP SANG {len(target_ports)} BOARD ĐÍCH ({targets_str}) ===", "header"
                ))

                success_ports = []
                failed_ports = []
                total_targets = len(target_ports)
                pair_sizes = [max(1, os.path.getsize(fp)) for _, fp in write_pairs]
                total_write_bytes = sum(pair_sizes) or 1

                for t_idx, t_port in enumerate(target_ports, 1):
                    base_prog = step_start_pct + ((t_idx - 1) / total_targets) * step_span_pct
                    span_prog = step_span_pct / total_targets
                    target_task = f"{step_short} -> {t_port} ({t_idx}/{total_targets})"

                    safe_after(lambda tp=t_port, ti=t_idx, tt=total_targets: self.log_backup(
                        f"\n  >>> [{ti}/{tt}] Đang nạp nhân bản vào Board Đích: {tp}..."
                    ))
                    safe_after(
                        lambda tp=t_port, ti=t_idx, tt=total_targets, bp=base_prog, tl=target_task: self.set_status(
                            f"{step_short}: đang kết nối Board Đích {tp} ({ti}/{tt})...",
                            "warning",
                            progress=bp,
                            task_label=tl,
                        )
                    )

                    args = ["--port", t_port, "--baud", str(baud), "write-flash", "-z"]
                    if erase_first:
                        args.append("--erase-all")
                    for off_hex, fpath in write_pairs:
                        args.extend([off_hex, fpath])

                    current_file_idx = 0
                    last_raw_pct = 0.0
                    file_finished = False

                    def on_target_stream(
                        line,
                        bp=base_prog,
                        sp=span_prog,
                        tp=t_port,
                        ti=t_idx,
                        tt=total_targets,
                        tl=target_task,
                    ):
                        nonlocal current_file_idx, last_raw_pct, file_finished
                        l_str = str(line)
                        if "Hash of data verified" in l_str or re.search(r"Wrote\s+\d+\s+bytes", l_str):
                            if not file_finished and current_file_idx < len(pair_sizes) - 1:
                                current_file_idx += 1
                                last_raw_pct = 0.0
                                file_finished = True
                        if "Writing at " in l_str:
                            file_finished = False

                        pct_val = parse_esptool_progress_percent(l_str)
                        if pct_val is not None:
                            if pct_val < last_raw_pct - 20.0 and current_file_idx < len(pair_sizes) - 1:
                                if not file_finished:
                                    current_file_idx += 1
                            last_raw_pct = pct_val
                            file_finished = False
                            done_bytes = sum(pair_sizes[:current_file_idx]) + (pct_val / 100.0) * pair_sizes[current_file_idx]
                            frac = min(1.0, max(0.0, done_bytes / total_write_bytes))
                            board_pct = int(round(frac * 100))
                            cur_p = bp + frac * sp
                            safe_after(
                                lambda p=cur_p, port_lbl=tp, pc=board_pct, i=ti, tot=tt, t_lbl=tl: self.set_status(
                                    f"{step_short}: đang nạp {port_lbl} [{i}/{tot}] ({pc}%)...",
                                    "warning",
                                    progress=p,
                                    task_label=t_lbl,
                                )
                            )

                    port_err_msg = ""
                    port_ok = False
                    try:
                        res = run_esptool_command(args, progress_callback=on_target_stream)
                        port_ok = esptool_command_succeeded(res)
                        if not port_ok:
                            port_err_msg = str(res or "")
                    except Exception as port_ex:
                        port_err_msg = str(port_ex)
                        safe_after(lambda tp=t_port, err=port_err_msg: self.log_backup(
                            f">>> [NGOẠI LỆ] {tp}: {err}", "red"
                        ))

                    if port_ok:
                        success_ports.append(t_port)
                        done_prog = base_prog + span_prog
                        safe_after(
                            lambda tp=t_port, ti=t_idx, tt=total_targets, dp=done_prog, tl=target_task: (
                                self.log_backup(
                                    f"      [THÀNH CÔNG] Board {tp} đã nhận đầy đủ Firmware & Phân vùng!", "green"
                                ),
                                self.set_status(
                                    f"Đã nạp xong {tp} ({ti}/{tt}).",
                                    "success",
                                    progress=dp,
                                    task_label=tl,
                                ),
                            )
                        )
                    else:
                        failed_ports.append(t_port)
                        lower_err = port_err_msg.lower()
                        if "is not an" in lower_err and "image" in lower_err:
                            safe_after(lambda tp=t_port: self.log_backup(
                                f"      [LỖI KHÁC CHIP] Dữ liệu nguồn không tương thích với Board Đích {tp} "
                                f"(ví dụ nhân bản ESP32-S3 sang ESP32 thường). Hai board phải cùng dòng chip!",
                                "red",
                            ))
                        else:
                            safe_after(lambda tp=t_port: self.log_backup(
                                f"      [THẤT BẠI] Không thể ghi dữ liệu vào Board {tp}!", "red"
                            ))

                summary_msg = (
                    f"Hoàn tất nhân bản: Thành công {len(success_ports)}/{total_targets} board"
                    + (f" ({', '.join(success_ports)})" if success_ports else "")
                    + (f" | Lỗi: {', '.join(failed_ports)}" if failed_ports else "")
                )
                final_level = "success" if not failed_ports else ("warning" if success_ports else "error")
                final_prog = 100 if success_ports else 0
                final_task = (
                    f"Hoàn tất nhân bản ({len(success_ports)}/{total_targets})"
                    if not failed_ports
                    else (
                        f"Nhân bản xong {len(success_ports)}/{total_targets} board"
                        if success_ports
                        else f"Nhân bản thất bại (0/{total_targets})"
                    )
                )
                safe_after(
                    lambda m=summary_msg, lv=final_level, p=final_prog, tl=final_task: self.set_status(
                        m, lv, progress=p, task_label=tl
                    )
                )
                safe_after(lambda m=summary_msg: self.log_backup(f"\n=== KẾT QUẢ NHÂN BẢN ĐA MẠCH: {m} ===", "header"))
                safe_after(lambda m=summary_msg: messagebox.showinfo("Kết quả Sao chép Trực tiếp", m, parent=self.root))
            except Exception as ex:
                err_msg = str(ex)
                safe_after(lambda m=err_msg: self.log_backup(f">>> [NGOẠI LỆ] {m}", "red"))
                safe_after(
                    lambda: self.set_status(
                        "Lỗi trong quá trình sao chép trực tiếp!",
                        "error",
                        progress=0,
                        task_label="Lỗi nhân bản",
                    )
                )
            finally:
                if temp_clone_dir and os.path.isdir(temp_clone_dir):
                    try:
                        import shutil
                        shutil.rmtree(temp_clone_dir, ignore_errors=True)
                    except Exception:
                        pass
                self._is_backup_hw_running = False
                if hasattr(self, "set_global_busy_state"):
                    safe_after(lambda: self.set_global_busy_state(False))
                else:
                    safe_after(lambda: self._set_backup_ui_state("normal"))

        self.backup_hw_thread = threading.Thread(target=worker, daemon=True)
        self.backup_hw_thread.start()
