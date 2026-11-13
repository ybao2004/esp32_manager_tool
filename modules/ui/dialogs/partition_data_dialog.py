# -*- coding: utf-8 -*-
"""
Hộp thoại Đọc / Xem / Chỉnh Sửa & Xóa Dữ Liệu Phân Vùng Non-Firmware (v1.5).
Hỗ trợ:
- NVS (Key-Value Parser/Encoder thuần Python v1/v2, lọc namespace/key, thêm/sửa/xóa, xuất JSON/CSV)
- Phân vùng dữ liệu khác (SPIFFS, LittleFS, FATFS, CoreDump, OTA Data, PHY...):
  + Trình xem/sửa Hex phân trang 16 KB/trang (nhanh mượt cho cả vùng nhiều MB)
  + Trình xem/sửa Văn bản UTF-8
  + Đọc lại từ chip, Lấy dữ liệu (.bin), Nạp file .bin ngoài, Xóa dữ liệu vùng, Ghi đè xuống chip.
"""
from __future__ import annotations

import csv
import json
import math
import os
from typing import Callable, Optional

from PyQt6.QtCore import QEvent, Qt
from PyQt6.QtGui import QFont, QFontMetricsF
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from modules.backup_utils import (
    format_partition_backup_filename,
    is_non_firmware_data_region,
)
from modules.nvs_util import (
    INT_TYPE_RANGES,
    NVS_MAX_KEY_LEN,
    NVS_TYPE_BLOB,
    NVS_TYPE_BLOB_DATA,
    NVS_TYPE_SZ,
    TYPE_NAME_TO_CODE,
    NvsEntry,
    NvsParseResult,
    encode_nvs_binary,
    parse_nvs_binary,
)
from modules.partition.unit_formatter import format_bytes_human, format_hex
from modules.ui import dialogs_service as dlg
from modules.ui.icons import bind_themed_icon
from modules.ui.text import qt_text


HEX_PAGE_SIZE = 16 * 1024  # 16 KB/trang để mở SPIFFS/LittleFS nhiều MB không đơ UI

NVS_EDITABLE_TYPES = [
    ("SZ", "Chuỗi ký tự (SZ)"),
    ("U8", "Số nguyên 8-bit không dấu (U8)"),
    ("I8", "Số nguyên 8-bit có dấu (I8)"),
    ("U16", "Số nguyên 16-bit không dấu (U16)"),
    ("I16", "Số nguyên 16-bit có dấu (I16)"),
    ("U32", "Số nguyên 32-bit không dấu (U32)"),
    ("I32", "Số nguyên 32-bit có dấu (I32)"),
    ("U64", "Số nguyên 64-bit không dấu (U64)"),
    ("I64", "Số nguyên 64-bit có dấu (I64)"),
    ("BLOB", "Mảng Byte Hex (BLOB)"),
]


def _ascii_char(b: int) -> str:
    return chr(b) if 32 <= b <= 126 else "."


def _format_hex_chunk_with_offsets(chunk: bytes, base_offset: int) -> tuple[str, str, str]:
    """Trả về 3 chuỗi đồng bộ từng dòng (offsets_txt, pure_hex_txt, ascii_txt) cho 1 trang <= 16 KB."""
    off_lines: list[str] = []
    hex_lines: list[str] = []
    asc_lines: list[str] = []
    for pos in range(0, len(chunk), 16):
        slice_b = chunk[pos : pos + 16]
        off_lines.append(f"0x{base_offset + pos:08X}")
        hex_lines.append(" ".join(f"{b:02X}" for b in slice_b))
        asc_lines.append("".join(_ascii_char(b) for b in slice_b))
    return "\n".join(off_lines), "\n".join(hex_lines), "\n".join(asc_lines)


def _parse_hex_text_to_bytes(text: str) -> bytes:
    """Chuyển chuỗi hex (có khoảng trắng/xuống dòng) thành bytes, hỗ trợ bỏ qua tiền tố 0xOFFSET: nếu người dùng dán vào."""
    cleaned_tokens: list[str] = []
    for line in (text or "").splitlines():
        part = line.strip()
        if not part:
            continue
        if "|" in part:
            part = part.split("|", 1)[0].strip()
        if ":" in part:
            left, right = part.split(":", 1)
            if left.strip().lower().startswith("0x") or len(left.strip()) >= 6:
                part = right.strip()
        for tok in part.replace(",", " ").replace("\t", " ").split():
            if tok.lower().startswith("0x"):
                tok = tok[2:]
            cleaned_tokens.append(tok)
    joined = "".join(cleaned_tokens)
    if len(joined) % 2 != 0:
        raise ValueError("Số ký tự Hex phải là số chẵn (mỗi byte gồm 2 ký tự 0-9, A-F).")
    try:
        return bytes.fromhex(joined)
    except ValueError as exc:
        raise ValueError(f"Chuỗi Hex chứa ký tự không hợp lệ: {exc}") from exc


class NvsEntryEditorDialog(QDialog):
    """Hộp thoại Thêm hoặc Chỉnh Sửa một cặp Key-Value trong phân vùng NVS."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        entry: Optional[NvsEntry] = None,
        namespaces: Optional[list[str]] = None,
    ):
        if parent is not None and not isinstance(parent, QWidget):
            parent = None
        super().__init__(parent)
        self._orig_entry = entry
        self._result: Optional[NvsEntry] = None
        self.setWindowTitle("Sửa mục NVS" if entry else "Thêm mục NVS mới")
        self.resize(520, 360)
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        grid = QGridLayout()
        grid.setSpacing(8)

        lbl_ns = QLabel("Namespace:", self)
        lbl_ns.setStyleSheet("font-weight: 600;")
        self.cb_ns = QComboBox(self)
        self.cb_ns.setEditable(True)
        ns_candidates = list(dict.fromkeys([n for n in (namespaces or []) if n] + ["storage", "wifi", "nvs"]))
        self.cb_ns.addItems(ns_candidates)
        if entry:
            self.cb_ns.setCurrentText(entry.namespace)
        elif namespaces:
            self.cb_ns.setCurrentText(namespaces[0])
        grid.addWidget(lbl_ns, 0, 0)
        grid.addWidget(self.cb_ns, 0, 1)
        grid.addWidget(QLabel("(Tối đa 15 ký tự ASCII)", self), 0, 2)

        lbl_key = QLabel("Key:", self)
        lbl_key.setStyleSheet("font-weight: 600;")
        self.txt_key = QLineEdit(entry.key if entry else "", self)
        self.txt_key.setMaxLength(NVS_MAX_KEY_LEN)
        self.txt_key.setPlaceholderText("Ví dụ: wifi_ssid, device_id...")
        grid.addWidget(lbl_key, 1, 0)
        grid.addWidget(self.txt_key, 1, 1)
        grid.addWidget(QLabel("(Tối đa 15 ký tự ASCII)", self), 1, 2)

        lbl_type = QLabel("Kiểu dữ liệu:", self)
        lbl_type.setStyleSheet("font-weight: 600;")
        self.cb_type = QComboBox(self)
        for code, desc in NVS_EDITABLE_TYPES:
            self.cb_type.addItem(desc, userData=code)
        if entry:
            tn = entry.type_name.upper()
            if tn in ("BLOB_DATA", "BLOB_IDX"):
                tn = "BLOB"
            idx = self.cb_type.findData(tn)
            if idx >= 0:
                self.cb_type.setCurrentIndex(idx)
        self.cb_type.currentIndexChanged.connect(self._update_value_hint)
        grid.addWidget(lbl_type, 2, 0)
        grid.addWidget(self.cb_type, 2, 1, 1, 2)
        grid.setColumnStretch(1, 1)
        layout.addLayout(grid)

        lbl_val = QLabel("Giá trị (Value):", self)
        lbl_val.setStyleSheet("font-weight: 600;")
        layout.addWidget(lbl_val)

        self.lbl_val_hint = QLabel("", self)
        self.lbl_val_hint.setProperty("role", "muted")
        self.lbl_val_hint.setWordWrap(True)
        layout.addWidget(self.lbl_val_hint)

        self.txt_val = QPlainTextEdit(self)
        mono = QFont("Consolas", 10)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self.txt_val.setFont(mono)
        self.txt_val.setProperty("role", "mono")
        self.txt_val.document().setDocumentMargin(4)
        if entry:
            if entry.type_name.upper() in ("BLOB", "BLOB_DATA", "BLOB_IDX") and isinstance(
                entry.value, (bytes, bytearray)
            ):
                self.txt_val.setPlainText(" ".join(f"{b:02X}" for b in entry.value))
            else:
                self.txt_val.setPlainText(str(entry.value if entry.value is not None else ""))
        layout.addWidget(self.txt_val, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("Hủy", self)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("Lưu mục NVS", self)
        btn_ok.setProperty("accent", "true")
        bind_themed_icon(btn_ok, "save", size=16, role="on_accent")
        btn_ok.clicked.connect(self._on_accept)
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        self._update_value_hint()

    def _update_value_hint(self):
        tname = str(self.cb_type.currentData() or "SZ").upper()
        tcode = TYPE_NAME_TO_CODE.get(tname, NVS_TYPE_SZ)
        if tcode in INT_TYPE_RANGES:
            _, min_v, max_v = INT_TYPE_RANGES[tcode]
            self.lbl_val_hint.setText(
                f"Nhập số nguyên thập phân hoặc hệ 0x Hex trong khoảng [{min_v} .. {max_v}]."
            )
        elif tname == "BLOB":
            self.lbl_val_hint.setText(
                "Nhập các cặp byte Hex cách nhau bởi dấu cách hoặc xuống dòng (ví dụ: 01 A4 FF 00)."
            )
        else:
            self.lbl_val_hint.setText("Nhập chuỗi văn bản UTF-8 (tối đa khoảng 4000 byte khi mã hóa UTF-8).")

    def _on_accept(self):
        ns = self.cb_ns.currentText().strip()
        key = self.txt_key.text().strip()
        tname = str(self.cb_type.currentData() or "SZ").upper()
        tcode = TYPE_NAME_TO_CODE.get(tname, NVS_TYPE_SZ)
        raw_text = self.txt_val.toPlainText()

        try:
            ns_b = ns.encode("ascii")
            key_b = key.encode("ascii")
        except UnicodeEncodeError:
            dlg.showerror("Lỗi dữ liệu", "Namespace và Key NVS chỉ hỗ trợ ký tự ASCII không dấu.", parent=self)
            return

        if not (1 <= len(ns_b) <= NVS_MAX_KEY_LEN):
            dlg.showerror("Lỗi dữ liệu", "Namespace không được rỗng và tối đa 15 ký tự.", parent=self)
            return
        if not (1 <= len(key_b) <= NVS_MAX_KEY_LEN):
            dlg.showerror("Lỗi dữ liệu", "Key không được rỗng và tối đa 15 ký tự.", parent=self)
            return

        if tcode in INT_TYPE_RANGES:
            _, min_v, max_v = INT_TYPE_RANGES[tcode]
            s = raw_text.strip()
            try:
                val = int(s, 0)
            except ValueError:
                dlg.showerror("Lỗi giá trị số", f"'{s}' không phải là số nguyên hợp lệ.", parent=self)
                return
            if not (min_v <= val <= max_v):
                dlg.showerror(
                    "Vượt giới hạn kiểu số",
                    f"Kiểu {tname} chỉ nhận giá trị từ {min_v} đến {max_v}.",
                    parent=self,
                )
                return
            parsed_val = val
            out_type = tname
        elif tname == "BLOB":
            try:
                parsed_val = _parse_hex_text_to_bytes(raw_text)
            except ValueError as exc:
                dlg.showerror("Lỗi dữ liệu Hex", str(exc), parent=self)
                return
            out_type = "BLOB"
            tcode = NVS_TYPE_BLOB_DATA
        else:
            encoded = raw_text.encode("utf-8") + b"\x00"
            if len(encoded) > 4000:
                dlg.showerror(
                    "Chuỗi quá dài",
                    f"Độ dài chuỗi UTF-8 ({len(encoded)} byte) vượt quá giới hạn 4000 byte của 1 trang NVS.",
                    parent=self,
                )
                return
            parsed_val = raw_text
            out_type = "SZ"
            tcode = NVS_TYPE_SZ

        self._result = NvsEntry(
            namespace=ns,
            key=key,
            type_name=out_type,
            value=parsed_val,
            type_code=tcode,
        )
        self.accept()

    def get_entry(self) -> Optional[NvsEntry]:
        return self._result


class PartitionDataDialog(QDialog):
    """Hộp thoại Đọc / Xem / Chỉnh sửa / Ghi đè / Xóa dữ liệu phân vùng Non-Firmware (v1.5)."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        region: Optional[dict] = None,
        raw_data: bytes = b"",
        chip_name: str = "ESP32",
        mac: str = "",
        port: str = "",
        on_read_from_chip: Optional[Callable[[Callable[[Optional[bytes], str], None]], None]] = None,
        on_write_to_chip: Optional[Callable[[bytes, Callable[[bool, str], None]], None]] = None,
        on_erase_on_chip: Optional[Callable[[Callable[[bool, str], None]], None]] = None,
    ):
        if parent is not None and not isinstance(parent, QWidget):
            parent = None
        super().__init__(parent)

        self._region = dict(region or {})
        self._part_name = str(self._region.get("name", "data_part") or "data_part")
        self._part_type = str(self._region.get("type", "data") or "data").lower()
        self._part_subtype = str(self._region.get("subtype", "undefined") or "undefined").lower()
        self._offset_int = int(self._region.get("offset_int", self._region.get("offset", 0)) or 0)
        self._size_int = int(
            self._region.get("size_int", self._region.get("size", len(raw_data) or 0x1000)) or 0x1000
        )

        self._chip_name = str(chip_name or "ESP32")
        self._mac = str(mac or "")
        self._port = str(port or "")
        self._on_read_from_chip = on_read_from_chip
        self._on_write_to_chip = on_write_to_chip
        self._on_erase_on_chip = on_erase_on_chip

        _, self._access_level = is_non_firmware_data_region(self._region)
        self._is_busy = False
        self._is_dirty = False
        self._page_dirty = False
        self._current_page = 0
        self._total_pages = max(1, (self._size_int + HEX_PAGE_SIZE - 1) // HEX_PAGE_SIZE)

        self._nvs_result: Optional[NvsParseResult] = None
        self._nvs_entries: list[NvsEntry] = []
        self._nvs_editable = False
        self._filtered_indices: list[int] = []

        self._buffer = self._normalize_buffer(raw_data)

        self.setWindowTitle(
            f"Dữ liệu phân vùng: {self._part_name} ({self._part_type}/{self._part_subtype}) - {format_hex(self._offset_int)}"
        )
        self.resize(980, 680)
        self.setMinimumSize(780, 520)

        self._build_ui()
        self.set_buffer(self._buffer, mark_dirty=False)

    def _normalize_buffer(self, data: bytes) -> bytes:
        raw = bytes(data or b"")
        if len(raw) < self._size_int:
            raw = raw + (b"\xFF" * (self._size_int - len(raw)))
        elif len(raw) > self._size_int:
            raw = raw[: self._size_int]
        return raw

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Header metadata + cảnh báo phân vùng nhạy cảm
        header_box = QFrame(self)
        header_box.setProperty("role", "card")
        hl = QVBoxLayout(header_box)
        hl.setContentsMargins(12, 8, 12, 8)
        hl.setSpacing(4)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(12)
        self.lbl_meta = QLabel(
            f"Phân vùng: <b>{self._part_name}</b>  |  Loại: <b>{self._part_type}/{self._part_subtype}</b>"
            f"  |  Offset: <b>{format_hex(self._offset_int)}</b>"
            f"  |  Kích thước: <b>{format_bytes_human(self._size_int)}</b> ({self._size_int:,} B)"
            f"  |  Cổng: <b>{self._port or 'Chưa kết nối'}</b>",
            header_box,
        )
        self.lbl_meta.setTextFormat(Qt.TextFormat.RichText)
        meta_row.addWidget(self.lbl_meta, 1)

        self.lbl_dirty_badge = QLabel("Đã đồng bộ", header_box)
        self.lbl_dirty_badge.setProperty("role", "muted")
        meta_row.addWidget(self.lbl_dirty_badge)
        hl.addLayout(meta_row)

        if self._access_level == "sensitive":
            self.lbl_sensitivity = QLabel(
                f"Lưu ý an toàn: Phân vùng '{self._part_name}' ({self._part_subtype}) chứa dữ liệu hệ thống nhạy cảm "
                "(OTA/PHY/Keys). Hãy sao lưu (.bin) trước khi ghi đè hoặc xóa.",
                header_box,
            )
            self.lbl_sensitivity.setProperty("role", "warning")
            self.lbl_sensitivity.setWordWrap(True)
            hl.addWidget(self.lbl_sensitivity)

        root.addWidget(header_box)

        # TabWidget: NVS Key-Value & Hex/Text
        self.tabs = QTabWidget(self)

        # --- Tab 1: NVS Key-Value ---
        self.nvs_tab = QWidget(self.tabs)
        nvs_lay = QVBoxLayout(self.nvs_tab)
        nvs_lay.setContentsMargins(8, 8, 8, 8)
        nvs_lay.setSpacing(8)

        self.lbl_nvs_status = QLabel("", self.nvs_tab)
        self.lbl_nvs_status.setWordWrap(True)
        nvs_lay.addWidget(self.lbl_nvs_status)

        nvs_top = QHBoxLayout()
        nvs_top.setSpacing(8)
        nvs_top.addWidget(QLabel("Namespace:", self.nvs_tab))
        self.cb_ns_filter = QComboBox(self.nvs_tab)
        self.cb_ns_filter.addItem("(Tất cả Namespace)", userData="")
        self.cb_ns_filter.currentIndexChanged.connect(lambda _: self._refresh_nvs_table())
        nvs_top.addWidget(self.cb_ns_filter)

        nvs_top.addWidget(QLabel("Tìm Key/Giá trị:", self.nvs_tab))
        self.txt_nvs_filter = QLineEdit(self.nvs_tab)
        self.txt_nvs_filter.setPlaceholderText("Lọc theo key hoặc nội dung...")
        self.txt_nvs_filter.textChanged.connect(lambda _: self._refresh_nvs_table())
        nvs_top.addWidget(self.txt_nvs_filter, 1)

        self.btn_nvs_add = QPushButton("Thêm Key", self.nvs_tab)
        bind_themed_icon(self.btn_nvs_add, "add", size=15)
        self.btn_nvs_add.clicked.connect(self._on_nvs_add)
        nvs_top.addWidget(self.btn_nvs_add)

        self.btn_nvs_edit = QPushButton("Sửa", self.nvs_tab)
        bind_themed_icon(self.btn_nvs_edit, "edit", size=15)
        self.btn_nvs_edit.clicked.connect(self._on_nvs_edit)
        nvs_top.addWidget(self.btn_nvs_edit)

        self.btn_nvs_del = QPushButton("Xóa", self.nvs_tab)
        bind_themed_icon(self.btn_nvs_del, "delete", size=15)
        self.btn_nvs_del.clicked.connect(self._on_nvs_delete)
        nvs_top.addWidget(self.btn_nvs_del)

        self.btn_nvs_export = QPushButton("Xuất JSON/CSV", self.nvs_tab)
        bind_themed_icon(self.btn_nvs_export, "document", size=15)
        self.btn_nvs_export.clicked.connect(self._on_nvs_export)
        nvs_top.addWidget(self.btn_nvs_export)
        nvs_lay.addLayout(nvs_top)

        self.nvs_table = QTableWidget(0, 4, self.nvs_tab)
        self.nvs_table.setHorizontalHeaderLabels(["Namespace", "Key", "Kiểu", "Giá trị (Value)"])
        self.nvs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.nvs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.nvs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.nvs_table.setAlternatingRowColors(True)
        self.nvs_table.verticalHeader().setVisible(False)
        hdr = self.nvs_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.nvs_table.itemDoubleClicked.connect(lambda _: self._on_nvs_edit())
        nvs_lay.addWidget(self.nvs_table, 1)

        # --- Tab 2: Hex & UTF-8 Editor (16KB/trang) ---
        self.hex_tab = QWidget(self.tabs)
        hex_lay = QVBoxLayout(self.hex_tab)
        hex_lay.setContentsMargins(8, 8, 8, 8)
        hex_lay.setSpacing(8)

        page_bar = QHBoxLayout()
        page_bar.setSpacing(6)

        self.btn_prev_page = QPushButton("< Trang trước", self.hex_tab)
        self.btn_prev_page.clicked.connect(lambda: self._go_to_page(self._current_page - 1))
        page_bar.addWidget(self.btn_prev_page)

        self.lbl_page_info = QLabel("Trang 1 / 1", self.hex_tab)
        self.lbl_page_info.setStyleSheet("font-weight: 600;")
        page_bar.addWidget(self.lbl_page_info)

        self.btn_next_page = QPushButton("Trang sau >", self.hex_tab)
        self.btn_next_page.clicked.connect(lambda: self._go_to_page(self._current_page + 1))
        page_bar.addWidget(self.btn_next_page)

        page_bar.addSpacing(8)
        page_bar.addWidget(QLabel("Chế độ:", self.hex_tab))
        self.cb_editor_mode = QComboBox(self.hex_tab)
        self.cb_editor_mode.addItems(["Sửa Hex (16 byte/dòng)", "Sửa Văn bản (UTF-8)"])
        self.cb_editor_mode.currentIndexChanged.connect(self._on_editor_mode_changed)
        page_bar.addWidget(self.cb_editor_mode)

        page_bar.addSpacing(8)
        self.txt_hex_search = QLineEdit(self.hex_tab)
        self.txt_hex_search.setPlaceholderText("Tìm chuỗi UTF-8 hoặc Hex (vd: 57 69 46 69)...")
        self.txt_hex_search.returnPressed.connect(self._on_hex_search)
        page_bar.addWidget(self.txt_hex_search, 1)

        self.btn_hex_search = QPushButton("Tìm", self.hex_tab)
        bind_themed_icon(self.btn_hex_search, "search", size=14)
        self.btn_hex_search.clicked.connect(self._on_hex_search)
        page_bar.addWidget(self.btn_hex_search)

        self.btn_apply_page = QPushButton("Áp dụng trang vào đệm", self.hex_tab)
        bind_themed_icon(self.btn_apply_page, "edit", size=14)
        self.btn_apply_page.clicked.connect(self._apply_current_editor_page)
        page_bar.addWidget(self.btn_apply_page)
        hex_lay.addLayout(page_bar)

        self.lbl_hex_status = QLabel("", self.hex_tab)
        self.lbl_hex_status.setProperty("role", "muted")
        hex_lay.addWidget(self.lbl_hex_status)

        mono_font = QFont("Consolas", 10)
        mono_font.setStyleHint(QFont.StyleHint.Monospace)
        fm = QFontMetricsF(mono_font)
        offset_w = max(106, math.ceil(fm.horizontalAdvance("0x00009000")) + 20)
        ascii_w = max(168, math.ceil(fm.horizontalAdvance("W" * 16)) + 20)

        self.editor_stack = QStackedWidget(self.hex_tab)

        # Page 0: Header + Hex + Offset + ASCII synced layout
        hex_page_w = QWidget(self.editor_stack)
        hex_page_vbox = QVBoxLayout(hex_page_w)
        hex_page_vbox.setContentsMargins(0, 0, 0, 0)
        hex_page_vbox.setSpacing(2)

        hex_hdr_lay = QHBoxLayout()
        hex_hdr_lay.setContentsMargins(0, 0, 0, 0)
        hex_hdr_lay.setSpacing(6)

        self.lbl_col_offset = QLabel("Offset", hex_page_w)
        self.lbl_col_offset.setFont(mono_font)
        self.lbl_col_offset.setProperty("role", "mono_header")
        self.lbl_col_offset.setFixedWidth(offset_w)

        hex_col_title = " ".join(f"{b:02X}" for b in range(16))
        self.lbl_col_hex = QLabel(hex_col_title, hex_page_w)
        self.lbl_col_hex.setFont(mono_font)
        self.lbl_col_hex.setProperty("role", "mono_header")

        self.lbl_col_ascii = QLabel("ASCII", hex_page_w)
        self.lbl_col_ascii.setFont(mono_font)
        self.lbl_col_ascii.setProperty("role", "mono_header")
        self.lbl_col_ascii.setFixedWidth(ascii_w)

        hex_hdr_lay.addWidget(self.lbl_col_offset, 0)
        hex_hdr_lay.addWidget(self.lbl_col_hex, 1)
        hex_hdr_lay.addWidget(self.lbl_col_ascii, 0)
        hex_page_vbox.addLayout(hex_hdr_lay)

        hex_page_lay = QHBoxLayout()
        hex_page_lay.setContentsMargins(0, 0, 0, 0)
        hex_page_lay.setSpacing(6)

        self.offset_view = QPlainTextEdit(hex_page_w)
        self.offset_view.setFont(mono_font)
        self.offset_view.setProperty("role", "mono_readonly")
        self.offset_view.setReadOnly(True)
        self.offset_view.setFixedWidth(offset_w)
        self.offset_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.offset_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.offset_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.offset_view.document().setDocumentMargin(4)
        self.offset_view.installEventFilter(self)
        self.offset_view.viewport().installEventFilter(self)

        self.hex_edit = QPlainTextEdit(hex_page_w)
        self.hex_edit.setFont(mono_font)
        self.hex_edit.setProperty("role", "mono")
        self.hex_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.hex_edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hex_edit.document().setDocumentMargin(4)
        self.hex_edit.textChanged.connect(self._on_page_text_modified)

        self.ascii_view = QPlainTextEdit(hex_page_w)
        self.ascii_view.setFont(mono_font)
        self.ascii_view.setProperty("role", "mono_readonly")
        self.ascii_view.setReadOnly(True)
        self.ascii_view.setFixedWidth(ascii_w)
        self.ascii_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.ascii_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.ascii_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.ascii_view.document().setDocumentMargin(4)
        self.ascii_view.installEventFilter(self)
        self.ascii_view.viewport().installEventFilter(self)

        # Đồng bộ thanh cuộn dọc duy nhất từ Hex tới Offset & ASCII
        self.hex_edit.verticalScrollBar().valueChanged.connect(self.offset_view.verticalScrollBar().setValue)
        self.hex_edit.verticalScrollBar().valueChanged.connect(self.ascii_view.verticalScrollBar().setValue)

        hex_page_lay.addWidget(self.offset_view, 0)
        hex_page_lay.addWidget(self.hex_edit, 1)
        hex_page_lay.addWidget(self.ascii_view, 0)
        hex_page_vbox.addLayout(hex_page_lay, 1)
        self.editor_stack.addWidget(hex_page_w)

        # Page 1: UTF-8 Text Editor cho trang hiện tại
        self.utf8_edit = QPlainTextEdit(self.editor_stack)
        self.utf8_edit.setFont(mono_font)
        self.utf8_edit.setProperty("role", "mono")
        self.utf8_edit.document().setDocumentMargin(4)
        self.utf8_edit.textChanged.connect(self._on_page_text_modified)
        self.editor_stack.addWidget(self.utf8_edit)

        hex_lay.addWidget(self.editor_stack, 1)

        if self._part_subtype == "nvs":
            self.tabs.addTab(self.nvs_tab, "Bảng NVS (Key-Value)")
            self.tabs.addTab(self.hex_tab, qt_text("Trình xem / sửa Hex & Văn bản (UTF-8)"))
        else:
            self.tabs.addTab(self.hex_tab, qt_text("Trình xem / sửa Hex & Văn bản (UTF-8)"))
            self.tabs.addTab(self.nvs_tab, "Phân tích cấu trúc NVS (Nếu có)")

        root.addWidget(self.tabs, 1)

        # Footer action bar
        footer = QHBoxLayout()
        footer.setSpacing(8)

        self.btn_read_chip = QPushButton("Đọc lại từ chip", self)
        bind_themed_icon(self.btn_read_chip, "refresh", size=16)
        self.btn_read_chip.clicked.connect(self._handle_read_chip)
        self.btn_read_chip.setEnabled(self._on_read_from_chip is not None)
        footer.addWidget(self.btn_read_chip)

        self.btn_export_bin = QPushButton("Lấy dữ liệu (.bin)", self)
        bind_themed_icon(self.btn_export_bin, "save", size=16)
        self.btn_export_bin.clicked.connect(self._handle_export_bin)
        footer.addWidget(self.btn_export_bin)

        self.btn_import_bin = QPushButton("Nạp file .bin ngoài...", self)
        bind_themed_icon(self.btn_import_bin, "open", size=16)
        self.btn_import_bin.clicked.connect(self._handle_import_bin)
        footer.addWidget(self.btn_import_bin)

        self.btn_erase_chip = QPushButton("Xóa dữ liệu vùng", self)
        self.btn_erase_chip.setProperty("danger", "true")
        bind_themed_icon(self.btn_erase_chip, "delete", size=16, role="on_accent")
        self.btn_erase_chip.clicked.connect(self._handle_erase_chip)
        self.btn_erase_chip.setEnabled(self._on_erase_on_chip is not None)
        footer.addWidget(self.btn_erase_chip)

        footer.addStretch(1)

        self.btn_write_chip = QPushButton("Ghi đè xuống chip", self)
        self.btn_write_chip.setProperty("accent", "true")
        bind_themed_icon(self.btn_write_chip, "flash", size=16, role="on_accent")
        self.btn_write_chip.clicked.connect(self._handle_write_chip)
        self.btn_write_chip.setEnabled(self._on_write_to_chip is not None)
        footer.addWidget(self.btn_write_chip)

        self.btn_close = QPushButton("Đóng", self)
        self.btn_close.clicked.connect(self.accept)
        footer.addWidget(self.btn_close)

        root.addLayout(footer)

    def eventFilter(self, obj, event):
        if (
            event is not None
            and event.type() == QEvent.Type.Wheel
            and hasattr(self, "hex_edit")
            and obj in (
                getattr(self, "offset_view", None),
                self.offset_view.viewport() if hasattr(self, "offset_view") else None,
                getattr(self, "ascii_view", None),
                self.ascii_view.viewport() if hasattr(self, "ascii_view") else None,
            )
        ):
            sb = self.hex_edit.verticalScrollBar()
            delta_y = event.angleDelta().y()
            if delta_y:
                sb.setValue(sb.value() - int(round(delta_y / 40.0)))
            return True
        return super().eventFilter(obj, event)

    def get_buffer(self) -> bytes:
        return self._buffer

    def set_buffer(self, data: bytes, mark_dirty: bool = False):
        self._buffer = self._normalize_buffer(data)
        self._page_dirty = False
        self._set_dirty(mark_dirty)
        self._parse_and_refresh_nvs()
        self._load_page_into_editor(self._current_page)

    def _set_dirty(self, dirty: bool):
        self._is_dirty = bool(dirty)
        if self._is_dirty or self._page_dirty:
            self.lbl_dirty_badge.setText("Có thay đổi chưa ghi chip")
            self.lbl_dirty_badge.setProperty("role", "warning")
        else:
            self.lbl_dirty_badge.setText("Đã đồng bộ bộ nhớ đệm")
            self.lbl_dirty_badge.setProperty("role", "muted")
        self.lbl_dirty_badge.style().unpolish(self.lbl_dirty_badge)
        self.lbl_dirty_badge.style().polish(self.lbl_dirty_badge)

    def _set_busy(self, busy: bool, message: str = ""):
        self._is_busy = busy
        for b in (
            self.btn_export_bin,
            self.btn_import_bin,
            self.btn_apply_page,
            self.btn_close,
        ):
            b.setEnabled(not busy)
        self.btn_read_chip.setEnabled((not busy) and (self._on_read_from_chip is not None))
        self.btn_write_chip.setEnabled((not busy) and (self._on_write_to_chip is not None))
        self.btn_erase_chip.setEnabled((not busy) and (self._on_erase_on_chip is not None))
        self._update_nvs_buttons_state()
        if message:
            self.lbl_dirty_badge.setText(message)

    def _parse_and_refresh_nvs(self):
        res = parse_nvs_binary(self._buffer)
        self._nvs_result = res
        self._nvs_entries = list(res.entries)
        self._nvs_editable = (not res.is_encrypted_or_unknown) and (
            self._part_subtype == "nvs" or len(res.entries) > 0 or res.is_all_erased
        )

        if res.is_encrypted_or_unknown:
            self.lbl_nvs_status.setText(
                "Cảnh báo: Không nhận dạng được cấu trúc NVS chuẩn (có thể NVS đã được mã hóa hoặc vùng nhớ không chứa NVS). "
                "Đã khóa chỉnh sửa Key-Value; bạn vẫn có thể xem/nạp Hex hoặc file .bin."
            )
            self.lbl_nvs_status.setProperty("role", "warning")
        elif res.is_all_erased:
            self.lbl_nvs_status.setText(
                f"Phân vùng đang trống (toàn bộ 0xFF, {self._size_int // 4096} pages). "
                "Bạn có thể bấm 'Thêm Key' để khởi tạo dữ liệu NVS v2 mới."
            )
            self.lbl_nvs_status.setProperty("role", "muted")
        else:
            ver_str = f"v{res.version}" if res.version in (1, 2) else "NVS"
            warn_note = f" | Cảnh báo CRC/Header: {len(res.warnings)}" if res.warnings else ""
            self.lbl_nvs_status.setText(
                f"Đã giải mã NVS {ver_str}: {len(res.entries)} key trong {len(res.namespaces)} namespace "
                f"({res.active_pages}/{res.page_count} page đang sử dụng){warn_note}."
            )
            self.lbl_nvs_status.setProperty("role", "muted")

        cur_ns = self.cb_ns_filter.currentData() or ""
        self.cb_ns_filter.blockSignals(True)
        self.cb_ns_filter.clear()
        self.cb_ns_filter.addItem("(Tất cả Namespace)", userData="")
        seen_ns: list[str] = []
        for e in self._nvs_entries:
            if e.namespace not in seen_ns:
                seen_ns.append(e.namespace)
        for ns in seen_ns:
            self.cb_ns_filter.addItem(ns, userData=ns)
        idx = self.cb_ns_filter.findData(cur_ns)
        if idx >= 0:
            self.cb_ns_filter.setCurrentIndex(idx)
        self.cb_ns_filter.blockSignals(False)

        self._refresh_nvs_table()
        self._update_nvs_buttons_state()

    def _update_nvs_buttons_state(self):
        can_edit = (not self._is_busy) and self._nvs_editable
        self.btn_nvs_add.setEnabled(can_edit)
        self.btn_nvs_edit.setEnabled(can_edit and len(self._nvs_entries) > 0)
        self.btn_nvs_del.setEnabled(can_edit and len(self._nvs_entries) > 0)
        self.btn_nvs_export.setEnabled((not self._is_busy) and len(self._nvs_entries) > 0)

    def _refresh_nvs_table(self):
        ns_filter = str(self.cb_ns_filter.currentData() or "")
        q = self.txt_nvs_filter.text().strip().lower()
        self._filtered_indices = []
        rows: list[NvsEntry] = []
        for idx, entry in enumerate(self._nvs_entries):
            if ns_filter and entry.namespace != ns_filter:
                continue
            val_disp = entry.format_value_display()
            if q:
                hay = f"{entry.namespace} {entry.key} {entry.type_name} {val_disp}".lower()
                if q not in hay:
                    continue
            self._filtered_indices.append(idx)
            rows.append(entry)

        self.nvs_table.setRowCount(len(rows))
        for r, entry in enumerate(rows):
            self.nvs_table.setItem(r, 0, QTableWidgetItem(entry.namespace))
            self.nvs_table.setItem(r, 1, QTableWidgetItem(entry.key))
            self.nvs_table.setItem(r, 2, QTableWidgetItem(entry.type_name))
            self.nvs_table.setItem(r, 3, QTableWidgetItem(entry.format_value_display(160)))

    def _commit_nvs_entries_to_buffer(self):
        ver = 2
        if self._nvs_result and self._nvs_result.version in (1, 2):
            ver = self._nvs_result.version
        try:
            encoded = encode_nvs_binary(self._nvs_entries, self._size_int, version=ver)
        except Exception as exc:
            dlg.showerror("Lỗi đóng gói NVS", str(exc), parent=self)
            return False
        self._buffer = self._normalize_buffer(encoded)
        self._page_dirty = False
        self._set_dirty(True)
        self._parse_and_refresh_nvs()
        self._load_page_into_editor(self._current_page)
        return True

    def _selected_nvs_entry_index(self) -> Optional[int]:
        row = self.nvs_table.currentRow()
        if row < 0 or row >= len(self._filtered_indices):
            return None
        return self._filtered_indices[row]

    def _on_nvs_add(self):
        if not self._nvs_editable:
            return
        namespaces = sorted({e.namespace for e in self._nvs_entries})
        ed = NvsEntryEditorDialog(self, entry=None, namespaces=namespaces)
        if ed.exec() == QDialog.DialogCode.Accepted:
            new_entry = ed.get_entry()
            if new_entry:
                # Ghi đè nếu trùng (namespace, key)
                replaced = False
                for i, cur in enumerate(self._nvs_entries):
                    if cur.namespace == new_entry.namespace and cur.key == new_entry.key:
                        self._nvs_entries[i] = new_entry
                        replaced = True
                        break
                if not replaced:
                    self._nvs_entries.append(new_entry)
                self._commit_nvs_entries_to_buffer()

    def _on_nvs_edit(self):
        if not self._nvs_editable:
            return
        real_idx = self._selected_nvs_entry_index()
        if real_idx is None:
            dlg.showinfo("Chưa chọn dòng", "Vui lòng chọn một mục Key-Value trong bảng NVS để sửa.", parent=self)
            return
        cur = self._nvs_entries[real_idx]
        namespaces = sorted({e.namespace for e in self._nvs_entries})
        ed = NvsEntryEditorDialog(self, entry=cur, namespaces=namespaces)
        if ed.exec() == QDialog.DialogCode.Accepted:
            updated = ed.get_entry()
            if updated:
                self._nvs_entries[real_idx] = updated
                self._commit_nvs_entries_to_buffer()

    def _on_nvs_delete(self):
        if not self._nvs_editable:
            return
        real_idx = self._selected_nvs_entry_index()
        if real_idx is None:
            dlg.showinfo("Chưa chọn dòng", "Vui lòng chọn một mục Key-Value để xóa.", parent=self)
            return
        cur = self._nvs_entries[real_idx]
        if not dlg.askyesno(
            "Xóa khóa NVS",
            f"Xóa khóa '{cur.namespace}:{cur.key}' khỏi bộ nhớ đệm NVS?",
            parent=self,
        ):
            return
        self._nvs_entries.pop(real_idx)
        self._commit_nvs_entries_to_buffer()

    def _on_nvs_export(self):
        if not self._nvs_entries:
            return
        default_name = f"{self._part_name}_nvs.json"
        out_path = dlg.asksaveasfilename(
            parent=self,
            title="Xuất bảng NVS Key-Value (JSON hoặc CSV)",
            defaultextension=".json",
            initialfile=default_name,
            filetypes=[("JSON files", "*.json"), ("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if not out_path:
            return
        try:
            if out_path.lower().endswith(".csv"):
                with open(out_path, "w", encoding="utf-8-sig", newline="") as fp:
                    writer = csv.writer(fp)
                    writer.writerow(["Namespace", "Key", "Type", "Value"])
                    for e in self._nvs_entries:
                        writer.writerow([e.namespace, e.key, e.type_name, e.format_value_display(10000)])
            else:
                payload = {
                    "partition": self._part_name,
                    "offset": format_hex(self._offset_int),
                    "size": self._size_int,
                    "entries": [e.to_serializable() for e in self._nvs_entries],
                }
                with open(out_path, "w", encoding="utf-8") as fp:
                    json.dump(payload, fp, ensure_ascii=False, indent=2)
            dlg.showinfo("Đã xuất NVS", f"Đã lưu {len(self._nvs_entries)} mục NVS ra:\n{out_path}", parent=self)
        except Exception as exc:
            dlg.showerror("Lỗi xuất tệp", str(exc), parent=self)

    # --- Hex / UTF-8 Page Editor ---
    def _page_bounds(self, page_idx: int) -> tuple[int, int]:
        start = page_idx * HEX_PAGE_SIZE
        end = min(self._size_int, start + HEX_PAGE_SIZE)
        return start, end

    def _load_page_into_editor(self, page_idx: int):
        self._current_page = max(0, min(page_idx, self._total_pages - 1))
        start, end = self._page_bounds(self._current_page)
        chunk = self._buffer[start:end]

        self.lbl_page_info.setText(f"Trang {self._current_page + 1} / {self._total_pages}")
        self.btn_prev_page.setEnabled(self._current_page > 0)
        self.btn_next_page.setEnabled(self._current_page < self._total_pages - 1)

        abs_start = self._offset_int + start
        abs_end = self._offset_int + max(start, end - 1)
        self.lbl_hex_status.setText(
            f"Dải trang hiện tại: offset tương đối {format_hex(start)}..{format_hex(max(start, end - 1))} "
            f"(Flash thực: {format_hex(abs_start)}..{format_hex(abs_end)}, {len(chunk)} bytes)"
        )

        off_txt, hex_txt, asc_txt = _format_hex_chunk_with_offsets(chunk, abs_start)
        self.hex_edit.blockSignals(True)
        self.offset_view.setPlainText(off_txt)
        self.hex_edit.setPlainText(hex_txt)
        self.ascii_view.setPlainText(asc_txt)
        v_pos = self.hex_edit.verticalScrollBar().value()
        self.offset_view.verticalScrollBar().setValue(v_pos)
        self.ascii_view.verticalScrollBar().setValue(v_pos)
        self.hex_edit.blockSignals(False)

        trimmed = chunk.rstrip(b"\xFF")
        utf8_txt = trimmed.decode("utf-8", errors="replace")
        self.utf8_edit.blockSignals(True)
        self.utf8_edit.setPlainText(utf8_txt)
        self.utf8_edit.blockSignals(False)
        self._page_dirty = False
        self._set_dirty(self._is_dirty)

    def _on_page_text_modified(self):
        self._page_dirty = True
        self._set_dirty(self._is_dirty)

    def _on_editor_mode_changed(self, idx: int):
        if self._page_dirty:
            if not self._apply_current_editor_page(silent=True):
                # Giữ nguyên hoặc nạp lại trang nếu không hợp lệ
                pass
        self.editor_stack.setCurrentIndex(1 if idx == 1 else 0)
        self._load_page_into_editor(self._current_page)

    def _go_to_page(self, target_page: int):
        if target_page < 0 or target_page >= self._total_pages:
            return
        if self._page_dirty:
            if not self._apply_current_editor_page():
                return
        self._load_page_into_editor(target_page)

    def _apply_current_editor_page(self, silent: bool = False) -> bool:
        start, end = self._page_bounds(self._current_page)
        page_len = end - start
        mode_idx = self.editor_stack.currentIndex()

        if mode_idx == 0:
            try:
                parsed = _parse_hex_text_to_bytes(self.hex_edit.toPlainText())
            except ValueError as exc:
                if not silent:
                    dlg.showerror("Lỗi cú pháp Hex", str(exc), parent=self)
                return False
            if len(parsed) > page_len:
                if not silent:
                    dlg.showerror(
                        "Vượt dung lượng trang",
                        f"Dữ liệu Hex đang có {len(parsed)} bytes, vượt quá dung lượng trang ({page_len} bytes).",
                        parent=self,
                    )
                return False
            if len(parsed) < page_len:
                parsed = parsed + (b"\xFF" * (page_len - len(parsed)))
            new_chunk = parsed
        else:
            raw_utf8 = self.utf8_edit.toPlainText().encode("utf-8")
            if len(raw_utf8) > page_len:
                if not silent:
                    dlg.showerror(
                        "Vượt dung lượng trang",
                        f"Văn bản UTF-8 chiếm {len(raw_utf8)} bytes, vượt quá trang hiện tại ({page_len} bytes).",
                        parent=self,
                    )
                return False
            new_chunk = raw_utf8 + (b"\xFF" * (page_len - len(raw_utf8)))

        buf = bytearray(self._buffer)
        buf[start:end] = new_chunk
        self._buffer = bytes(buf)
        self._page_dirty = False
        self._set_dirty(True)
        self._parse_and_refresh_nvs()
        self._load_page_into_editor(self._current_page)
        return True

    def _on_hex_search(self):
        q = self.txt_hex_search.text().strip()
        if not q:
            return
        needle_bytes: Optional[bytes] = None
        if q.lower().startswith("0x") or (all(c in "0123456789abcdefABCDEF " for c in q) and len(q.replace(" ", "")) >= 2 and " " in q):
            try:
                needle_bytes = _parse_hex_text_to_bytes(q)
            except ValueError:
                needle_bytes = None
        if not needle_bytes:
            needle_bytes = q.encode("utf-8")

        start_search = min(len(self._buffer), (self._current_page * HEX_PAGE_SIZE) + 1)
        pos = self._buffer.find(needle_bytes, start_search)
        if pos < 0:
            pos = self._buffer.find(needle_bytes, 0)
        if pos < 0:
            dlg.showinfo("Không tìm thấy", f"Không tìm thấy '{q}' trong dữ liệu phân vùng.", parent=self)
            return

        target_page = pos // HEX_PAGE_SIZE
        if target_page != self._current_page:
            if self._page_dirty and not self._apply_current_editor_page():
                return
            self._load_page_into_editor(target_page)

        abs_pos = self._offset_int + pos
        self.lbl_hex_status.setText(
            f"Tìm thấy tại offset tương đối {format_hex(pos)} (Flash thực: {format_hex(abs_pos)}) — Trang {target_page + 1}"
        )

    # --- Chip / File Footer Actions ---
    def _ensure_buffer_current(self) -> bool:
        if self._page_dirty:
            return self._apply_current_editor_page()
        return True

    def _handle_read_chip(self):
        if self._is_busy or self._on_read_from_chip is None:
            return
        if (self._is_dirty or self._page_dirty) and not dlg.askyesno(
            "Đọc lại từ chip",
            "Bộ nhớ đệm đang có sửa đổi chưa ghi xuống chip.\nĐọc lại từ chip sẽ ghi đè bản đang sửa. Tiếp tục?",
            parent=self,
        ):
            return
        self._set_busy(True, "Đang đọc lại dữ liệu từ chip...")

        def _done(data: Optional[bytes], err: str):
            self._set_busy(False)
            if data is None:
                dlg.showerror("Lỗi đọc phân vùng", err or "Không thể đọc dữ liệu từ chip.", parent=self)
                return
            self.set_buffer(data, mark_dirty=False)

        self._on_read_from_chip(_done)

    def _handle_export_bin(self):
        if not self._ensure_buffer_current():
            return
        default_name = format_partition_backup_filename(
            self._chip_name, self._mac, self._part_name, self._offset_int
        )
        out_path = dlg.asksaveasfilename(
            parent=self,
            title=f"Lưu dữ liệu phân vùng '{self._part_name}' (.bin)",
            defaultextension=".bin",
            initialfile=default_name,
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
        )
        if not out_path:
            return
        try:
            with open(out_path, "wb") as fp:
                fp.write(self._buffer)
            dlg.showinfo(
                "Đã lưu tệp .bin",
                f"Đã xuất {format_bytes_human(len(self._buffer))} dữ liệu phân vùng '{self._part_name}' ra:\n{out_path}",
                parent=self,
            )
        except Exception as exc:
            dlg.showerror("Lỗi lưu tệp", str(exc), parent=self)

    def _handle_import_bin(self):
        in_path = dlg.askopenfilename(
            parent=self,
            title=f"Chọn tệp .bin nạp vào bộ nhớ đệm vùng '{self._part_name}'",
            filetypes=[("Binary files", "*.bin"), ("All files", "*.*")],
        )
        if not in_path:
            return
        try:
            with open(in_path, "rb") as fp:
                raw = fp.read()
        except Exception as exc:
            dlg.showerror("Lỗi đọc tệp", str(exc), parent=self)
            return

        if len(raw) > self._size_int:
            dlg.showerror(
                "Tệp quá kích thước phân vùng",
                f"Tệp '{os.path.basename(in_path)}' có dung lượng {len(raw):,} bytes, "
                f"lớn hơn kích thước phân vùng '{self._part_name}' ({self._size_int:,} bytes).\n"
                "Không thể nạp đè vì sẽ tràn sang phân vùng kế tiếp.",
                parent=self,
            )
            return

        self.set_buffer(raw, mark_dirty=True)
        dlg.showinfo(
            "Đã nạp vào bộ nhớ đệm",
            f"Đã nạp {len(raw):,} bytes từ '{os.path.basename(in_path)}' (tự đệm 0xFF phần còn lại đến {self._size_int:,} bytes).\n"
            "Kiểm tra lại dữ liệu rồi bấm 'Ghi đè xuống chip' để nạp vào ESP32.",
            parent=self,
        )

    def _confirm_sensitive_action(self, action_verb: str) -> bool:
        if self._access_level == "sensitive":
            return dlg.askyesno(
                "Cảnh báo phân vùng hệ thống nhạy cảm",
                f"Phân vùng '{self._part_name}' ({self._part_subtype}) chứa thông số hệ thống nhạy cảm (OTA / PHY / Keys).\n"
                f"Bạn có chắc chắn muốn {action_verb} không?",
                parent=self,
            )
        return True

    def _handle_erase_chip(self):
        if self._is_busy or self._on_erase_on_chip is None:
            return
        if not self._confirm_sensitive_action(f"xóa trắng hoàn toàn vùng '{self._part_name}' về 0xFF"):
            return
        if not dlg.askyesno(
            "Xác nhận xóa dữ liệu phân vùng",
            f"Sẽ xóa toàn bộ dữ liệu trong phân vùng '{self._part_name}'\n"
            f"(Offset {format_hex(self._offset_int)}, Kích thước {format_bytes_human(self._size_int)}).\n"
            "Hành động này không ảnh hưởng bootloader hay ứng dụng. Tiếp tục?",
            parent=self,
        ):
            return

        self._set_busy(True, "Đang xóa dữ liệu phân vùng trên chip...")

        def _done(ok: bool, msg: str):
            self._set_busy(False)
            if ok:
                self.set_buffer(b"\xFF" * self._size_int, mark_dirty=False)
                dlg.showinfo(
                    "Xóa vùng thành công",
                    msg or f"Đã xóa trắng phân vùng '{self._part_name}' về 0xFF.",
                    parent=self,
                )
            else:
                dlg.showerror("Lỗi xóa phân vùng", msg or "Không thể xóa dữ liệu phân vùng.", parent=self)

        self._on_erase_on_chip(_done)

    def _handle_write_chip(self):
        if self._is_busy or self._on_write_to_chip is None:
            return
        if not self._ensure_buffer_current():
            return
        if not self._confirm_sensitive_action(f"ghi đè dữ liệu xuống phân vùng '{self._part_name}'"):
            return
        if not dlg.askyesno(
            "Xác nhận ghi đè xuống chip",
            f"Ghi đè {format_bytes_human(len(self._buffer))} ({len(self._buffer):,} bytes) xuống phân vùng '{self._part_name}'\n"
            f"tại địa chỉ {format_hex(self._offset_int)} trên cổng {self._port or 'hiện tại'}?",
            parent=self,
        ):
            return

        self._set_busy(True, "Đang ghi đè dữ liệu xuống chip...")

        def _done(ok: bool, msg: str):
            self._set_busy(False)
            if ok:
                self._set_dirty(False)
                dlg.showinfo(
                    "Ghi đè thành công",
                    msg or f"Đã ghi đè dữ liệu xuống phân vùng '{self._part_name}' thành công!",
                    parent=self,
                )
            else:
                dlg.showerror("Lỗi ghi đè phân vùng", msg or "Không thể ghi dữ liệu xuống chip.", parent=self)

        self._on_write_to_chip(self._buffer, _done)
