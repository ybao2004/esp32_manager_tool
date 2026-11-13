# -*- coding: utf-8 -*-
"""
Trang Nạp Flash Firmware (FlasherPage - v1.5).
- Card 1: Cấu hình Nạp & Công cụ Xóa (1 hàng gọn gàng: Dòng Chip, Tốc độ Nạp, Xóa toàn bộ trước khi nạp | Bắt đầu nạp, Xóa Toàn Bộ Flash, Xóa nhật ký).
- Card 2: Danh sách 4 File Firmware (.bin) với phân bổ tỷ lệ cột chuẩn:
  [x] (50px) | File #N (55px) | Đường dẫn File .bin (stretch=1, ~65% chiều rộng) | [Chọn...] (85px) | Offset (100px Monospace) | Dung lượng (85px).
- Card 3: Thanh điều khiển Nạp Firmware + Progress Bar + Nhật ký Nạp thời gian thực.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QProgressBar, QFileDialog
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from modules.config import FLASH_CHIP_TARGETS, FLASH_BAUDS
from modules.ui.widgets.card import Card
from modules.ui.widgets.flow_layout import FlowLayout, make_group
from modules.ui.widgets.log_view import LogView
from modules.ui.icons import get_icon, bind_themed_icon


class _EntryCompat(QLineEdit):
    def get(self) -> str:
        return self.text()

    def delete(self, first, last=None):
        self.clear()

    def insert(self, index, val: str):
        self.setText(str(val))

    def config(self, **kwargs):
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")

    configure = config

    def cget(self, prop: str):
        if prop == "state":
            return "normal" if self.isEnabled() else "disabled"
        return ""

    def winfo_exists(self) -> bool:
        return True


class _ButtonCompat(QPushButton):
    def cget(self, prop: str):
        if prop == "text":
            return self.text()
        elif prop == "state":
            return "normal" if self.isEnabled() else "disabled"
        return ""

    def config(self, **kwargs):
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")

    configure = config

    def winfo_exists(self) -> bool:
        return True

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        if key == "text":
            self.setText(str(value))
        elif key == "state":
            self.setEnabled(value != "disabled")


class _ComboCompat(QComboBox):
    def __init__(self, parent=None, fit_to_content: bool = True, min_fit_width: int = 80):
        super().__init__(parent)
        self._fit_to_content = fit_to_content
        self._min_fit_width = min_fit_width
        if self._fit_to_content:
            self.currentTextChanged.connect(lambda _t: self._sync_fit_width())

    def _sync_fit_width(self):
        if not self._fit_to_content or self.isEditable():
            return
        self.ensurePolished()
        fm = self.fontMetrics()
        curr_txt = self.currentText() or ""
        target_w = max(self._min_fit_width, fm.horizontalAdvance(curr_txt) + 40)
        self.setFixedWidth(target_w)
        max_item_w = target_w
        for i in range(self.count()):
            iw = fm.horizontalAdvance(self.itemText(i)) + 44
            if iw > max_item_w:
                max_item_w = iw
        if self.view():
            self.view().setMinimumWidth(max_item_w)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_fit_width()

    def addItems(self, texts):
        super().addItems(texts)
        self._sync_fit_width()

    def setCurrentText(self, text: str):
        super().setCurrentText(text)
        self._sync_fit_width()

    def get(self) -> str:
        return self.currentText()

    def set(self, val: str):
        val_str = str(val)
        idx = self.findText(val_str)
        if idx >= 0:
            self.setCurrentIndex(idx)
        else:
            self.addItem(val_str)
            self.setCurrentIndex(self.count() - 1)
        self._sync_fit_width()

    def bind(self, event: str, callback):
        self.currentTextChanged.connect(lambda _: callback(None))

    def cget(self, prop: str):
        if prop == "state":
            return "readonly" if self.isEnabled() else "disabled"
        return ""

    def config(self, **kwargs):
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")

    configure = config

    def winfo_exists(self) -> bool:
        return True

    def __setitem__(self, key, value):
        if key == "values":
            curr = self.currentText()
            self.blockSignals(True)
            self.clear()
            super().addItems([str(v) for v in value])
            super().setCurrentText(curr)
            self.blockSignals(False)
            self._sync_fit_width()
        elif key == "state":
            self.setEnabled(value != "disabled")

    def __getitem__(self, key):
        if key == "values":
            return [self.itemText(i) for i in range(self.count())]
        elif key == "state":
            return "readonly" if self.isEnabled() else "disabled"
        return ""


class _CheckBoxCompat(QCheckBox):
    def config(self, **kwargs):
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")

    configure = config

    def winfo_exists(self) -> bool:
        return True

    def __getitem__(self, key):
        if key == "state":
            return "normal" if self.isEnabled() else "disabled"
        return ""

    def __setitem__(self, key, value):
        if key == "state":
            self.setEnabled(value != "disabled")

    def cget(self, prop: str):
        return self[prop]


class _TkVarCompat:
    def __init__(self, checkbox: QCheckBox, default: bool = False):
        self._cb = checkbox
        self._cb.setChecked(default)

    def get(self) -> bool:
        return self._cb.isChecked()

    def set(self, val: bool):
        self._cb.setChecked(bool(val))


class _LabelCompat(QLabel):
    def winfo_exists(self) -> bool:
        return True

    def __setitem__(self, key, value):
        if key == "text":
            self.setText(str(value))

    def __getitem__(self, key):
        if key == "text":
            return self.text()
        return ""

    def cget(self, prop: str):
        return self[prop]

    def config(self, **kwargs):
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))
        if "fg" in kwargs or "foreground" in kwargs:
            color = kwargs.get("fg") or kwargs.get("foreground")
            if color:
                self.setStyleSheet(f"color: {color};")

    configure = config


class _ProgressBarCompat(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._val = 0.0

    def winfo_exists(self) -> bool:
        return True

    def cget(self, key):
        if key == "mode":
            return "indeterminate" if (self.minimum() == 0 and self.maximum() == 0) else "determinate"
        elif key == "value":
            return self._val
        return ""

    def config(self, **kwargs):
        if "mode" in kwargs:
            if kwargs["mode"] == "indeterminate":
                self.setRange(0, 0)
            else:
                self.setRange(0, 100)
        if "value" in kwargs:
            try:
                self._val = float(kwargs["value"])
            except (ValueError, TypeError):
                self._val = 0.0
            self.setValue(int(round(max(0.0, min(100.0, self._val)))))

    configure = config

    def __getitem__(self, key):
        if key == "value":
            return self._val
        elif key == "mode":
            return self.cget("mode")
        return 0

    def __setitem__(self, key, value):
        if key == "value":
            try:
                self._val = float(value)
            except (ValueError, TypeError):
                self._val = 0.0
            self.setValue(int(round(max(0.0, min(100.0, self._val)))))


class FlasherPage(QWidget):
    """Trang Nạp Flash Firmware (.bin) - v1.7"""

    def __init__(
        self,
        saved_flash_chip: str = "auto",
        saved_flash_baud: str = "460800",
        saved_flash_erase: bool = False,
        saved_flash_rows: list = None,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.saved_flash_chip = saved_flash_chip
        self.saved_flash_baud = saved_flash_baud
        self.saved_flash_erase = saved_flash_erase
        self.saved_flash_rows = saved_flash_rows or []

        self.setAcceptDrops(True)
        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(6)

        # 1. Card Cấu hình Nạp & Thao tác chính (tự xuống dòng khi cửa sổ hẹp)
        card_cfg = Card("Cấu hình Nạp Firmware & Công cụ Xóa", icon_name="chip", parent=self)
        cfg_bar = FlowLayout(h_spacing=6, v_spacing=6)

        self.flash_chip_cb = _ComboCompat(card_cfg, min_fit_width=86)
        self.flash_chip_cb.addItems(FLASH_CHIP_TARGETS)
        self.flash_chip_cb.setCurrentText(
            self.saved_flash_chip if self.saved_flash_chip in FLASH_CHIP_TARGETS else "auto"
        )
        cfg_bar.addWidget(make_group(card_cfg, QLabel("Chip:", card_cfg), self.flash_chip_cb))

        self.flash_baud_cb = _ComboCompat(card_cfg, min_fit_width=82)
        self.flash_baud_cb.addItems(FLASH_BAUDS)
        self.flash_baud_cb.setCurrentText(
            self.saved_flash_baud if self.saved_flash_baud in FLASH_BAUDS else "460800"
        )
        cfg_bar.addWidget(make_group(card_cfg, QLabel("Baud:", card_cfg), self.flash_baud_cb))

        self.cb_flash_erase = _CheckBoxCompat(
            "Xóa toàn bộ trước khi nạp", card_cfg
        )
        self.cb_flash_erase.setToolTip("Thực thi --erase-all để xóa sạch Flash trước khi ghi Firmware mới")
        self.var_flash_erase = _TkVarCompat(self.cb_flash_erase, default=self.saved_flash_erase)
        cfg_bar.addWidget(self.cb_flash_erase)

        cfg_bar.addStretch(1)

        self.btn_flash_write = _ButtonCompat("Bắt đầu nạp", card_cfg)
        self.btn_flash_write.setProperty("accent", "true")
        bind_themed_icon(self.btn_flash_write, "flash", role="on_accent")
        self.btn_flash_write.setToolTip("Bắt đầu nạp các file Firmware đã chọn xuống ESP32")
        cfg_bar.addWidget(self.btn_flash_write)

        self.btn_erase_flash = _ButtonCompat("Xóa toàn bộ Flash", card_cfg)
        self.btn_erase_flash.setProperty("danger", "true")
        bind_themed_icon(self.btn_erase_flash, "delete", role="on_accent")
        self.btn_erase_only = self.btn_erase_flash
        cfg_bar.addWidget(self.btn_erase_flash)

        self.btn_clear_flasher_log = _ButtonCompat("Xóa nhật ký", card_cfg)
        bind_themed_icon(self.btn_clear_flasher_log, "delete")
        cfg_bar.addWidget(self.btn_clear_flasher_log)

        for cfg_btn in (
            self.btn_flash_write,
            self.btn_erase_flash,
            self.btn_clear_flasher_log,
        ):
            cfg_btn.setStyleSheet("padding: 0 10px;")

        card_cfg.body_layout.addLayout(cfg_bar)
        root_layout.addWidget(card_cfg)

        # 2. Card Danh sách File Firmware (.bin) & Offset nạp (tỷ lệ cột chuẩn)
        card_files = Card(
            "Danh sách File Firmware (.bin) & Offset nạp (Hỗ trợ kéo thả file .bin)",
            icon_name="folder",
            parent=self,
        )
        files_grid = QGridLayout()
        files_grid.setContentsMargins(0, 0, 0, 0)
        files_grid.setHorizontalSpacing(10)
        files_grid.setVerticalSpacing(6)

        headers = [
            ("Bật", Qt.AlignmentFlag.AlignCenter),
            ("Thứ tự", Qt.AlignmentFlag.AlignLeft),
            ("Đường dẫn File .bin", Qt.AlignmentFlag.AlignLeft),
            ("Chọn File", Qt.AlignmentFlag.AlignCenter),
            ("Offset (Hex)", Qt.AlignmentFlag.AlignLeft),
            ("Dung lượng", Qt.AlignmentFlag.AlignRight),
        ]
        for col_idx, (h_text, align) in enumerate(headers):
            lbl_hdr = QLabel(h_text, card_files)
            lbl_hdr.setProperty("role", "muted")
            lbl_hdr.setStyleSheet("font-weight: 600; font-size: 8.5pt;")
            files_grid.addWidget(lbl_hdr, 0, col_idx, align)

        default_offsets = ["0x1000", "0x8000", "0xe000", "0x10000"]
        self.flash_file_rows = []

        for idx in range(4):
            r_idx = idx + 1
            cb_en = _CheckBoxCompat(card_files)
            is_init_en = idx == 0
            if self.saved_flash_rows and idx < len(self.saved_flash_rows):
                is_init_en = self.saved_flash_rows[idx].get("enabled", idx == 0)
            var_en = _TkVarCompat(cb_en, default=is_init_en)
            files_grid.addWidget(cb_en, r_idx, 0, Qt.AlignmentFlag.AlignCenter)

            lbl_num = QLabel(f"File #{idx + 1}", card_files)
            lbl_num.setFixedWidth(55)
            files_grid.addWidget(lbl_num, r_idx, 1)

            entry_path = _EntryCompat(card_files)
            entry_path.setPlaceholderText(f"Chưa chọn file .bin cho vị trí #{idx + 1}...")
            saved_p = (
                self.saved_flash_rows[idx].get("path", "")
                if self.saved_flash_rows and idx < len(self.saved_flash_rows)
                else ""
            )
            if saved_p:
                entry_path.setText(saved_p)
            files_grid.addWidget(entry_path, r_idx, 2)

            btn_browse = _ButtonCompat("Chọn...", card_files)
            bind_themed_icon(btn_browse, "folder")
            btn_browse.setFixedWidth(88)
            btn_browse.clicked.connect(lambda _, i=idx: self._browse_file(i))
            files_grid.addWidget(btn_browse, r_idx, 3)

            entry_offset = _EntryCompat(card_files)
            entry_offset.setFixedWidth(100)
            entry_offset.setStyleSheet("font-family: Consolas; font-weight: 600;")
            saved_off = (
                self.saved_flash_rows[idx].get("offset", "")
                if self.saved_flash_rows and idx < len(self.saved_flash_rows)
                else ""
            )
            entry_offset.setText(
                saved_off
                if saved_off
                else (default_offsets[idx] if idx < len(default_offsets) else "0x0")
            )
            files_grid.addWidget(entry_offset, r_idx, 4)

            lbl_size = _LabelCompat("-- KB", card_files)
            lbl_size.setFixedWidth(85)
            lbl_size.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl_size.setStyleSheet("font-family: Consolas; font-size: 8.5pt;")
            files_grid.addWidget(lbl_size, r_idx, 5)

            row_dict = {
                "var_enable": var_en,
                "check_btn": cb_en,
                "path_entry": entry_path,
                "browse_btn": btn_browse,
                "offset_entry": entry_offset,
                "size_label": lbl_size,
            }
            self.flash_file_rows.append(row_dict)

            entry_path.textChanged.connect(lambda _, i=idx: self._update_file_size(i))
            self._update_file_size(idx)

        # Cột 2 (Đường dẫn file) giãn tối đa ~65% chiều rộng
        files_grid.setColumnStretch(2, 1)
        card_files.body_layout.addLayout(files_grid)
        root_layout.addWidget(card_files)

        # 3. Card Nhật ký Nạp Flash (Tiến trình dùng chung thanh dưới cùng)
        card_log = Card("Nhật ký Nạp Firmware & Xóa Flash", icon_name="window_console", parent=self)
        self.flasher_txt = LogView(card_log)
        card_log.body_layout.addWidget(self.flasher_txt, 1)

        root_layout.addWidget(card_log, 1)

    def _browse_file(self, row_idx: int):
        curr_p = self.flash_file_rows[row_idx]["path_entry"].text().strip()
        init_dir = (
            os.path.dirname(curr_p)
            if (curr_p and os.path.exists(os.path.dirname(curr_p)))
            else "."
        )
        fpath, _ = QFileDialog.getOpenFileName(
            self,
            f"Chọn file firmware (.bin) cho File #{row_idx + 1}",
            init_dir,
            "Firmware binary (*.bin);;Tất cả file (*.*)",
        )
        if fpath:
            self.flash_file_rows[row_idx]["path_entry"].setText(os.path.normpath(fpath))
            self.flash_file_rows[row_idx]["var_enable"].set(True)
            self._update_file_size(row_idx)

    def _update_file_size(self, row_idx: int):
        if row_idx < len(self.flash_file_rows):
            path = self.flash_file_rows[row_idx]["path_entry"].text().strip()
            lbl = self.flash_file_rows[row_idx]["size_label"]
            if path and os.path.isfile(path):
                try:
                    sz_kb = os.path.getsize(path) / 1024.0
                    if sz_kb < 1024:
                        lbl.setText(f"{sz_kb:.1f} KB")
                    else:
                        lbl.setText(f"{sz_kb / 1024.0:.2f} MB")
                except Exception:
                    lbl.setText("-- KB")
            else:
                lbl.setText("-- KB")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        bin_files = [u.toLocalFile() for u in urls if u.toLocalFile().lower().endswith(".bin")]
        if not bin_files:
            return

        for idx, fpath in enumerate(bin_files):
            if idx < len(self.flash_file_rows):
                self.flash_file_rows[idx]["path_entry"].setText(os.path.normpath(fpath))
                self.flash_file_rows[idx]["var_enable"].set(True)
                self._update_file_size(idx)
        event.acceptProposedAction()
