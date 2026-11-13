# -*- coding: utf-8 -*-
"""
Trang Quản Lý Phân Vùng Bộ Nhớ ESP32 (PartitionPage - v1.6).
- Tách thanh công cụ thành 2 nhóm rõ ràng (không bị cắt chữ bất kỳ nút nào):
  + Card trên (Cấu hình & Tệp): Chip, Flash, Đơn vị, [x] Tự căn 4K/64K | [Mẫu Chuẩn], [Quét Dự Án], [Mở CSV/BIN], [Xuất CSV], [Xuất BIN], [Dồn & Căn], [Hoàn tác], [Làm lại], [Hướng Dẫn]
  + Card giữa: Sơ đồ ổ đĩa trực quan DiskMapWidget + Thống kê dung lượng & kiểm tra hợp lệ ESP-IDF
  + Card chính: Bảng phân vùng tương tác cao (cột Tên co giãn stretch=1) + Thanh thao tác 2 bên:
    Trái: [+ Thêm dòng], [Sửa dòng], [Xóa dòng], [Xóa tất cả]
    Phải: [Đọc bảng từ Chip], [Nạp bảng vào Chip], [Dump vùng], [Ghi vùng], [Xóa vùng]
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QFrame, QProgressBar
)
from PyQt6.QtCore import Qt, QPoint
from modules.config import FLASH_SIZE_OPTIONS
from modules.partition.chip_database import CHIP_FAMILY_DATABASE
from modules.ui.widgets.card import Card
from modules.ui.widgets.disk_map import DiskMapWidget
from modules.ui.widgets.log_view import LogView
from modules.ui.widgets.collapsible import CollapsiblePanel
from modules.ui.widgets.flow_layout import FlowLayout, make_group
from modules.ui.icons import get_icon, bind_themed_icon


class _EntryCompat(QLineEdit):
    def get(self) -> str:
        return self.text()

    def set(self, val: str):
        self.setText(str(val))

    def winfo_exists(self) -> bool:
        return True

    def __setitem__(self, key, value):
        if key == "state":
            self.setEnabled(value != "disabled")

    def __getitem__(self, key):
        if key == "state":
            return "normal" if self.isEnabled() else "disabled"
        return ""

    def cget(self, prop: str):
        if prop == "state":
            return "readonly" if self.isEnabled() else "disabled"
        return ""

    def config(self, **kwargs):
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")

    configure = config


class _ButtonCompat(QPushButton):
    def config(self, **kwargs):
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))

    configure = config

    def winfo_exists(self) -> bool:
        return True

    def __setitem__(self, key, value):
        if key == "state":
            self.setEnabled(value != "disabled")
        elif key == "text":
            self.setText(str(value))

    def __getitem__(self, key):
        if key == "state":
            return "normal" if self.isEnabled() else "disabled"
        elif key == "text":
            return self.text()
        return ""

    def cget(self, key):
        return self[key]


class _ComboCompat(QComboBox):
    def __init__(self, parent=None, fit_to_content: bool = True, min_fit_width: int = 76):
        super().__init__(parent)
        self._fit_to_content = fit_to_content
        self._min_fit_width = min_fit_width
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        if self._fit_to_content:
            self.currentTextChanged.connect(lambda _t: self._sync_fit_width())

    def _sync_fit_width(self):
        if not self._fit_to_content or self.isEditable():
            return
        self.ensurePolished()
        fm = self.fontMetrics()
        curr_txt = self.currentText() or ""
        # 8px padding trái + 18px drop-down + khoảng thở đầy đủ để không cắt tên chip dài (ví dụ ESP32-P4)
        target_w = max(self._min_fit_width, fm.horizontalAdvance(curr_txt) + 42)
        self.setFixedWidth(target_w)
        max_item_w = target_w
        for i in range(self.count()):
            iw = fm.horizontalAdvance(self.itemText(i)) + 38
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
            was_blocked = self.signalsBlocked()
            self.blockSignals(True)
            try:
                self.clear()
                super().addItems([str(v) for v in value])
                super().setCurrentText(curr)
            finally:
                self.blockSignals(was_blocked)
            self._sync_fit_width()
        elif key == "state":
            self.setEnabled(value != "disabled")

    def __getitem__(self, key):
        if key == "values":
            return [self.itemText(i) for i in range(self.count())]
        elif key == "state":
            return "normal" if self.isEnabled() else "disabled"
        return ""


class _TkVarCompat:
    def __init__(self, checkbox: QCheckBox, default: bool = True):
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
        if prop == "state":
            return "readonly" if self.isEnabled() else "disabled"
        return ""

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

    def cget(self, prop: str):
        if prop == "state":
            return "readonly" if self.isEnabled() else "disabled"
        elif prop == "value":
            return self._val
        elif prop == "mode":
            return "indeterminate" if (self.minimum() == 0 and self.maximum() == 0) else "determinate"
        return ""

    def config(self, **kwargs):
        if "value" in kwargs:
            try:
                self._val = float(kwargs["value"])
            except (ValueError, TypeError):
                self._val = 0.0
            self.setValue(int(round(max(0.0, min(100.0, self._val)))))
        if "maximum" in kwargs:
            self.setMaximum(int(kwargs["maximum"]))

    configure = config

    def winfo_exists(self) -> bool:
        return True

    def __setitem__(self, key, value):
        if key == "value":
            try:
                self._val = float(value)
            except (ValueError, TypeError):
                self._val = 0.0
            self.setValue(int(round(max(0.0, min(100.0, self._val)))))
        elif key == "maximum":
            self.setMaximum(int(value))

    def __getitem__(self, key):
        if key == "value":
            return self._val
        elif key == "maximum":
            return self.maximum()
        elif key == "mode":
            return self.cget("mode")
        return 0


class _EventShim:
    def __init__(self, x: int = 0, y: int = 0, x_root: int = 0, y_root: int = 0):
        self.x = x
        self.y = y
        self.x_root = x_root
        self.y_root = y_root


class _TreeviewCompat(QTreeWidget):
    """Lớp bọc Treeview PyQt6 tương thích 100% với giao thức gọi của Partition Wizard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRootIsDecorated(False)
        self.setAlternatingRowColors(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._items_by_iid: dict[str, QTreeWidgetItem] = {}
        self._iids_by_item_id: dict[int, str] = {}
        self._auto_id = 0
        self._cols: list[str] = []

    def winfo_exists(self) -> bool:
        return True

    def __setitem__(self, key, value):
        if key in ("columns", "displaycolumns"):
            self.set_columns(list(value))

    def __getitem__(self, key):
        if key in ("columns", "displaycolumns"):
            return list(self._cols)
        return ""

    def winfo_children(self) -> list:
        return []

    def set_columns(self, cols: list[str]):
        self._cols = list(cols)
        self.setColumnCount(len(cols))

    def heading(self, col: str, text: str = ""):
        if col in self._cols:
            idx = self._cols.index(col)
            header_item = self.headerItem()
            if not header_item:
                header_item = QTreeWidgetItem()
                self.setHeaderItem(header_item)
            header_item.setText(idx, text)

    def column(self, col: str, width: int = 100, anchor: str = "w"):
        if col in self._cols:
            idx = self._cols.index(col)
            self.setColumnWidth(idx, width)

    def get_children(self, item: str = "") -> list[str]:
        if not item:
            return list(self._items_by_iid.keys())
        return []

    def delete(self, *items):
        for iid in items:
            item = self._items_by_iid.pop(str(iid), None)
            if item:
                self._iids_by_item_id.pop(id(item), None)
                idx = self.indexOfTopLevelItem(item)
                if idx >= 0:
                    self.takeTopLevelItem(idx)

    def insert(
        self,
        parent: str,
        index,
        iid: str = None,
        values: tuple = (),
        tags: tuple = (),
    ) -> str:
        if not iid:
            self._auto_id += 1
            iid = f"item_{self._auto_id}"
        else:
            iid = str(iid)

        item = QTreeWidgetItem()
        item.setData(0, Qt.ItemDataRole.UserRole, iid)
        for col_idx, val in enumerate(values):
            item.setText(col_idx, str(val))
            if col_idx in (0, 2, 3, 6, 7):
                item.setTextAlignment(col_idx, Qt.AlignmentFlag.AlignCenter)
            elif col_idx in (4, 5, 8):
                item.setTextAlignment(
                    col_idx, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                )
            else:
                item.setTextAlignment(
                    col_idx, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                )

        if index == "end" or index >= self.topLevelItemCount():
            self.addTopLevelItem(item)
        else:
            self.insertTopLevelItem(int(index), item)

        self._items_by_iid[iid] = item
        self._iids_by_item_id[id(item)] = iid
        return iid

    def selection(self) -> tuple[str, ...]:
        sel = self.selectedItems()
        if not sel:
            return ()
        iid = self._iids_by_item_id.get(id(sel[0])) or sel[0].data(0, Qt.ItemDataRole.UserRole)
        return (iid,) if iid else ()

    def selection_set(self, iid: str):
        item = self._items_by_iid.get(str(iid))
        if item:
            self.setCurrentItem(item)

    def exists(self, iid: str) -> bool:
        return str(iid) in self._items_by_iid

    def see(self, iid: str):
        item = self._items_by_iid.get(str(iid))
        if item:
            self.scrollToItem(item)

    def item(self, iid: str, option: str = None):
        item = self._items_by_iid.get(str(iid))
        if not item:
            return () if option == "values" else {"values": ()}
        vals = tuple(item.text(c) for c in range(self.columnCount()))
        if option == "values":
            return vals
        return {"values": vals}

    def set(self, iid: str, col: str, val: str):
        item = self._items_by_iid.get(str(iid))
        if item and col in self._cols:
            idx = self._cols.index(col)
            item.setText(idx, str(val))

    def identify_row(self, y: int) -> str:
        item = self.itemAt(QPoint(10, int(y)))
        if item:
            return self._iids_by_item_id.get(id(item)) or item.data(0, Qt.ItemDataRole.UserRole) or ""
        return ""

    def identify_column(self, x: int) -> str:
        col_idx = self.columnAt(int(x))
        if col_idx < 0:
            col_idx = 0
        return f"#{col_idx + 1}"

    def tag_configure(self, tag, **kwargs):
        pass

    def tag_bind(self, tag, event, callback):
        pass

    def cget(self, prop: str):
        if prop == "state":
            return "readonly" if self.isEnabled() else "disabled"
        return ""

    def config(self, **kwargs):
        pass

    configure = config

    def yview(self, *args):
        pass

    def yview_scroll(self, number: int, what: str = "units"):
        sb = self.verticalScrollBar()
        if sb:
            sb.setValue(sb.value() + int(number) * sb.singleStep())

    def bind(self, event: str, callback):
        if "TreeviewSelect" in event:
            self.itemSelectionChanged.connect(lambda: callback(None))
        elif "<Button-1>" in event:
            self.itemClicked.connect(
                lambda item, col: callback(
                    _EventShim(x=10, y=self.visualItemRect(item).center().y())
                )
            )
        elif "<Double-1>" in event:
            self.itemDoubleClicked.connect(
                lambda item, col: callback(
                    _EventShim(x=10, y=self.visualItemRect(item).center().y())
                )
            )
        elif "<Button-3>" in event:
            def _on_ctx(pt: QPoint):
                gpos = self.viewport().mapToGlobal(pt)
                callback(_EventShim(x=pt.x(), y=pt.y(), x_root=gpos.x(), y_root=gpos.y()))
            self.customContextMenuRequested.connect(_on_ctx)


class PartitionPage(QWidget):
    """Trang Quản Lý Phân Vùng Bộ Nhớ ESP32 (Partition Wizard - v1.7)"""

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(6)

        # 1. Card Cấu hình & Công cụ Tệp / Bảng Phân Vùng
        header_card = Card("Cấu hình & Quản Lý Tệp Bảng Phân Vùng", icon_name="chip", parent=self)
        h_vbox = QVBoxLayout()
        h_vbox.setContentsMargins(0, 0, 0, 0)
        h_vbox.setSpacing(6)

        # Dòng 1: Cấu hình Chip, Flash, Đơn vị, Tự căn chỉnh + Hoàn tác / Làm lại / Hướng dẫn
        # FlowLayout: tự xuống dòng khi cửa sổ hẹp thay vì cắt chữ / chồng nút
        row_top = FlowLayout(h_spacing=6, v_spacing=6)

        self.cb_part_chip = _ComboCompat(header_card, min_fit_width=95)
        chip_names = ["(Chưa chọn)"] + [c.name for c in CHIP_FAMILY_DATABASE.values()]
        self.cb_part_chip.addItems(chip_names)
        row_top.addWidget(make_group(header_card, QLabel("Chip:", header_card), self.cb_part_chip))

        self.cb_part_flash = _ComboCompat(header_card, min_fit_width=76)
        self.cb_part_flash.addItems([opt[0] for opt in FLASH_SIZE_OPTIONS])
        self.cb_part_flash.setCurrentText("4 MB (Chuẩn)")
        row_top.addWidget(make_group(header_card, QLabel("Flash:", header_card), self.cb_part_flash))

        self.cb_part_mode = _ComboCompat(header_card, min_fit_width=115)
        self.cb_part_mode.addItems(["Thập phân (KB/MB)", "Hệ HEX (0x...)", "Song song (HEX + KB)"])
        row_top.addWidget(make_group(header_card, QLabel("Đơn vị:", header_card), self.cb_part_mode))

        self.chk_auto_align = QCheckBox("Tự căn 4K/64K", header_card)
        self.var_auto_align = _TkVarCompat(self.chk_auto_align, default=True)
        row_top.addWidget(self.chk_auto_align)

        row_top.addStretch(1)

        # Nút công cụ nhỏ dạng biểu tượng (có tooltip) để tiết kiệm chiều ngang khi cửa sổ hẹp
        self.btn_part_help = _ButtonCompat("", header_card)
        bind_themed_icon(self.btn_part_help, "info")
        self.btn_part_help.setToolTip("Sổ tay hướng dẫn & tra cứu bảng phân vùng")
        self.btn_part_help.setAccessibleName("Sổ tay")
        row_top.addWidget(self.btn_part_help)

        h_vbox.addLayout(row_top)

        # Dòng 2: Các công cụ Mẫu, Dự án, Mở/Lưu CSV, Dồn và Căn | Hoàn tác / Làm lại
        row_tools = FlowLayout(h_spacing=6, v_spacing=6)

        self.btn_presets = _ButtonCompat("Mẫu Chuẩn...", header_card)
        bind_themed_icon(self.btn_presets, "folder")
        row_tools.addWidget(self.btn_presets)

        self.btn_part_scan = _ButtonCompat("Quét Dự Án", header_card)
        bind_themed_icon(self.btn_part_scan, "search")
        row_tools.addWidget(self.btn_part_scan)

        self.btn_open_csv = _ButtonCompat("Mở CSV/BIN", header_card)
        bind_themed_icon(self.btn_open_csv, "folder")
        row_tools.addWidget(self.btn_open_csv)

        self.btn_save_csv = _ButtonCompat("Lưu CSV", header_card)
        bind_themed_icon(self.btn_save_csv, "save")
        self.btn_save_csv.setToolTip("Lưu toàn bộ bảng phân vùng ra file CSV chuẩn ESP-IDF")
        row_tools.addWidget(self.btn_save_csv)

        self.btn_autopack = _ButtonCompat("Dồn và Căn 4K/64K", header_card)
        bind_themed_icon(self.btn_autopack, "checkmark")
        row_tools.addWidget(self.btn_autopack)

        row_tools.addStretch(1)

        self.btn_part_undo = _ButtonCompat("", header_card)
        bind_themed_icon(self.btn_part_undo, "arrow_undo")
        self.btn_part_undo.setToolTip("Hoàn tác (Ctrl+Z)")
        self.btn_part_undo.setAccessibleName("Hoàn tác")
        self.btn_part_undo.setEnabled(False)
        row_tools.addWidget(self.btn_part_undo)

        self.btn_part_redo = _ButtonCompat("", header_card)
        bind_themed_icon(self.btn_part_redo, "arrow_redo")
        self.btn_part_redo.setToolTip("Làm lại (Ctrl+Y)")
        self.btn_part_redo.setAccessibleName("Làm lại")
        self.btn_part_redo.setEnabled(False)
        row_tools.addWidget(self.btn_part_redo)

        for hdr_btn in (
            self.btn_presets,
            self.btn_part_scan,
            self.btn_open_csv,
            self.btn_save_csv,
            self.btn_autopack,
        ):
            hdr_btn.setStyleSheet("padding: 0 10px;")
        for icon_btn in (self.btn_part_undo, self.btn_part_redo, self.btn_part_help):
            icon_btn.setStyleSheet("padding: 0 8px;")

        h_vbox.addLayout(row_tools)

        header_card.body_layout.addLayout(h_vbox)
        root_layout.addWidget(header_card)

        # 2. Card Sơ đồ ổ đĩa trực quan (MiniTool Partition Map)
        map_card = Card("Sơ Đồ Thanh Ổ Đĩa Flash (MiniTool Partition Map)", icon_name="save", parent=self)
        self.disk_map = DiskMapWidget(map_card)
        map_card.body_layout.addWidget(self.disk_map)

        self.lbl_flash_stats = _LabelCompat("", map_card)
        self.lbl_flash_stats.setProperty("role", "muted")
        map_card.body_layout.addWidget(self.lbl_flash_stats)
        root_layout.addWidget(map_card)

        # 3. Card Bảng Phân Vùng Chi Tiết & Thao tác Phần cứng
        table_card = Card("Danh Sách Bảng Phân Vùng Chi Tiết", icon_name="folder", parent=self)
        t_layout = QVBoxLayout()
        t_layout.setContentsMargins(0, 0, 0, 0)
        t_layout.setSpacing(6)

        columns = ("stt", "name", "type", "subtype", "offset", "size", "flags", "used", "free")
        self.part_tree = _TreeviewCompat(table_card)
        self.part_tree.set_columns(columns)

        headers = [
            ("stt", "STT", 48),
            ("name", "Tên Phân Vùng (Name)", 150),
            ("type", "Kiểu (Type)", 95),
            ("subtype", "Phân loại (SubType)", 135),
            ("offset", "Offset", 130),
            ("size", "Dung lượng (Size)", 135),
            ("flags", "Cờ (Flags)", 85),
            ("used", "Đã dùng (%)", 105),
            ("free", "Còn trống", 105),
        ]
        for col_id, col_text, col_w in headers:
            self.part_tree.heading(col_id, col_text)
            self.part_tree.column(col_id, col_w)

        hdr_view = self.part_tree.header()
        if hdr_view:
            hdr_view.setStretchLastSection(False)
            for c_idx in (0, 2, 3, 4, 5, 6, 7, 8):
                hdr_view.setSectionResizeMode(c_idx, QHeaderView.ResizeMode.ResizeToContents)
            hdr_view.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)

        t_layout.addWidget(self.part_tree, 1)

        # Thanh nút dưới bảng: Chia 2 nhóm Trái (Chỉnh sửa bảng) | Phải (Thao tác Phần cứng Chip)
        tbl_actions = FlowLayout(h_spacing=4, v_spacing=4)

        self.btn_add_part = _ButtonCompat("Thêm dòng", table_card)
        bind_themed_icon(self.btn_add_part, "add")
        tbl_actions.addWidget(self.btn_add_part)

        self.btn_edit_part = _ButtonCompat("Sửa dòng", table_card)
        bind_themed_icon(self.btn_edit_part, "edit")
        tbl_actions.addWidget(self.btn_edit_part)

        self.btn_del_part = _ButtonCompat("Xóa dòng", table_card)
        bind_themed_icon(self.btn_del_part, "delete")
        tbl_actions.addWidget(self.btn_del_part)

        self.btn_part_clear = _ButtonCompat("Xóa tất cả", table_card)
        bind_themed_icon(self.btn_part_clear, "delete")
        tbl_actions.addWidget(self.btn_part_clear)

        tbl_actions.addStretch(1)

        self.btn_part_read_hw = _ButtonCompat("Đọc bảng từ Chip", table_card)
        self.btn_part_read_hw.setProperty("accent", "true")
        bind_themed_icon(self.btn_part_read_hw, "chip", role="on_accent")
        tbl_actions.addWidget(self.btn_part_read_hw)

        self.btn_part_flash_hw = _ButtonCompat("Nạp bảng vào Chip", table_card)
        bind_themed_icon(self.btn_part_flash_hw, "flash")
        tbl_actions.addWidget(self.btn_part_flash_hw)

        self.btn_part_dump_hw = _ButtonCompat("Dump vùng", table_card)
        bind_themed_icon(self.btn_part_dump_hw, "save")
        tbl_actions.addWidget(self.btn_part_dump_hw)

        self.btn_part_write_hw = _ButtonCompat("Ghi vùng", table_card)
        bind_themed_icon(self.btn_part_write_hw, "folder")
        tbl_actions.addWidget(self.btn_part_write_hw)

        self.btn_part_erase_hw = _ButtonCompat("Xóa vùng", table_card)
        bind_themed_icon(self.btn_part_erase_hw, "delete")
        tbl_actions.addWidget(self.btn_part_erase_hw)

        for action_btn in (
            self.btn_add_part,
            self.btn_edit_part,
            self.btn_del_part,
            self.btn_part_clear,
            self.btn_part_read_hw,
            self.btn_part_flash_hw,
            self.btn_part_dump_hw,
            self.btn_part_write_hw,
            self.btn_part_erase_hw,
        ):
            action_btn.setStyleSheet("padding: 0 10px;")

        t_layout.addLayout(tbl_actions)

        table_card.body_layout.addLayout(t_layout)
        root_layout.addWidget(table_card, 1)

        # 4. Panel Nhật ký phần cứng thu gọn
        self.log_panel = CollapsiblePanel(
            "Nhật Ký Thao Tác Phần Cứng Phân Vùng", collapsed=True, parent=self
        )
        self.part_log_txt = LogView(self.log_panel)
        self.log_panel.add_widget(self.part_log_txt)
        root_layout.addWidget(self.log_panel)
