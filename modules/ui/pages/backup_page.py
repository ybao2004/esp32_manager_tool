# -*- coding: utf-8 -*-
"""
Trang Sao Lưu & Nhân Bản Đa Bo Mạch (BackupPage - v1.5).
- Thanh trên cùng: Board Gốc, Làm mới COM, Baudrate, [Đọc chip nguồn] | [Chọn Tất Cả], [Bỏ Chọn], [Chỉ Chọn Firmware], [x] Cắt trống 0xFF
- Giữa: Sơ đồ phân vùng trên Chip gốc (DiskMapWidget 42px) + Thống kê MAC / Dung lượng
- Dưới (Chia đôi 60% Trái / 40% Phải):
  + Trái (60%): Bảng phân vùng tối ưu độ rộng cột + thanh nút Sao lưu & Thao tác dữ liệu Non-Firmware + Menu chuột phải
  + Phải (40%): Card Sao Chép Trực Tiếp Đa Mạch (COM đích căn trái gọn gàng) + Card Nhật ký Sao lưu & Nhân bản
"""
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
    QPushButton, QCheckBox, QRadioButton, QSplitter, QFrame, QHeaderView,
    QScrollArea, QStyle, QStyleOptionButton, QStyleOptionViewItem, QStyledItemDelegate
)
from PyQt6.QtCore import Qt, QRect, pyqtSignal
from modules.config import FLASH_BAUDS
from modules.ui.widgets.card import Card
from modules.ui.widgets.disk_map import DiskMapWidget
from modules.ui.widgets.flow_layout import FlowLayout, make_group
from modules.ui.widgets.log_view import LogView
from modules.ui.pages.partition_page import (
    _TreeviewCompat, _ComboCompat, _TkVarCompat, _LabelCompat, _ButtonCompat
)
from modules.ui.icons import get_icon, bind_themed_icon


class _BackupCheckDelegate(QStyledItemDelegate):
    """Vẽ hộp kiểm vector căn giữa ô ở cột Chọn (thay cho text thô '[x]' / '[ ]')."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        checked = "[x]" in str(opt.text or "").lower()
        opt.text = ""
        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget)

        cb_opt = QStyleOptionButton()
        cb_opt.state = QStyle.StateFlag.State_Enabled if (opt.state & QStyle.StateFlag.State_Enabled) else QStyle.StateFlag.State_None
        if opt.state & QStyle.StateFlag.State_MouseOver:
            cb_opt.state |= QStyle.StateFlag.State_MouseOver
        cb_opt.state |= QStyle.StateFlag.State_On if checked else QStyle.StateFlag.State_Off

        pm = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, cb_opt, opt.widget)
        if pm <= 0:
            pm = 18
        x = opt.rect.x() + max(0, (opt.rect.width() - pm) // 2)
        y = opt.rect.y() + max(0, (opt.rect.height() - pm) // 2)
        cb_opt.rect = QRect(x, y, pm, pm)
        style.drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox, cb_opt, painter, opt.widget)


class _TkVarStringCompat:
    def __init__(self, default: str = ""):
        self._val = str(default)

    def get(self) -> str:
        return self._val

    def set(self, val: str):
        self._val = str(val)


class _TargetContainer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._vbox = QVBoxLayout(self)
        self._vbox.setContentsMargins(0, 0, 0, 0)
        self._vbox.setSpacing(4)
        self._hint_box = QVBoxLayout()
        self._hint_box.setContentsMargins(0, 0, 0, 0)
        self._hint_box.setSpacing(2)
        self._flow = FlowLayout(h_spacing=16, v_spacing=6)
        self._vbox.addLayout(self._hint_box)
        self._vbox.addLayout(self._flow)

    def set_hint_widget(self, widget: QWidget):
        self._hint_box.addWidget(widget)

    def add_target_widget(self, widget: QWidget):
        self._flow.addWidget(widget)

    def winfo_children(self):
        return [c for c in self.children() if isinstance(c, QWidget)]

    def clear_children(self):
        """Gỡ hoàn toàn toàn bộ widget con khỏi FlowLayout và hint box."""
        for lay in (self._hint_box, self._flow):
            while lay.count():
                item = lay.takeAt(0)
                w = item.widget() if item else None
                if w is not None:
                    w.hide()
                    w.setParent(None)
                    w.deleteLater()
        for child in list(self.winfo_children()):
            child.hide()
            child.setParent(None)
            child.deleteLater()

    def winfo_exists(self) -> bool:
        return True


class BackupPage(QWidget):
    """Trang Sao Lưu Phân Vùng & Nhân Bản Đa Bo Mạch Trực Tiếp (v1.5)"""

    source_mode_changed = pyqtSignal(str)

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setProperty("role", "transparent")

        content = QWidget(scroll)
        content.setProperty("role", "transparent")
        root_layout = QVBoxLayout(content)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(6)

        # 1. Top Card: Cấu hình Chip Nguồn & Bộ lọc Sao Lưu (gom gọn 1 hàng ngang)
        top_card = Card("Cấu hình Chip Nguồn & Bộ lọc Sao Lưu", icon_name="chip", parent=content)
        row_src = FlowLayout(h_spacing=6, v_spacing=6)

        self.backup_src_port_var = _TkVarStringCompat("")
        self.lbl_backup_src_port = QLabel("Chưa chọn", top_card)
        self.lbl_backup_src_port.setObjectName("backupSourceBadge")
        self.lbl_backup_src_port.setToolTip(
            "Board Gốc dùng chung Cổng COM ở thanh điều khiển trên cùng"
        )
        row_src.addWidget(make_group(top_card, QLabel("Board Gốc:", top_card), self.lbl_backup_src_port))

        self.btn_backup_blink_led = _ButtonCompat("Nháy LED", top_card)
        bind_themed_icon(self.btn_backup_blink_led, "flash")
        self.btn_backup_blink_led.setToolTip(
            "Nháy đèn TX/UART trên Board Gốc trong 5 giây để nhận diện đúng mạch đang cắm"
        )
        self.btn_backup_blink_led.setStyleSheet("padding: 0 8px;")
        self.btn_backup_blink_led.setVisible(False)
        row_src.addWidget(self.btn_backup_blink_led)

        self.cb_backup_baud = _ComboCompat(top_card, min_fit_width=78)
        self.cb_backup_baud.addItems(FLASH_BAUDS)
        self.cb_backup_baud.setCurrentText("460800")
        self.backup_baud_var = _TkVarStringCompat("460800")
        self.cb_backup_baud.currentTextChanged.connect(
            lambda txt: self.backup_baud_var.set(txt)
        )
        self.cb_backup_baud.setToolTip(
            "Tốc độ Baudrate riêng cho sao lưu & nhân bản ở Tab 5 (độc lập với Baudrate trên cùng)"
        )
        row_src.addWidget(make_group(top_card, QLabel("Baud:", top_card), self.cb_backup_baud))

        self.btn_backup_read_chip = _ButtonCompat("Đọc chip nguồn", top_card)
        self.btn_backup_read_chip.setProperty("accent", "true")
        bind_themed_icon(self.btn_backup_read_chip, "search", role="on_accent")
        self.btn_backup_read_chip.setStyleSheet("padding: 0 10px;")
        row_src.addWidget(self.btn_backup_read_chip)

        self.btn_backup_sel_all = _ButtonCompat("Chọn Tất Cả", top_card)
        self.btn_backup_sel_all.setStyleSheet("padding: 0 8px;")
        row_src.addWidget(self.btn_backup_sel_all)

        self.btn_backup_unsel_all = _ButtonCompat("Bỏ Chọn", top_card)
        self.btn_backup_unsel_all.setStyleSheet("padding: 0 8px;")
        row_src.addWidget(self.btn_backup_unsel_all)

        self.btn_backup_sel_fw = _ButtonCompat("Chỉ Chọn Firmware", top_card)
        self.btn_backup_sel_fw.setStyleSheet("padding: 0 8px;")
        row_src.addWidget(self.btn_backup_sel_fw)

        self.chk_backup_trim = QCheckBox("Cắt trống 0xFF", top_card)
        self.var_backup_smart_trim = _TkVarCompat(self.chk_backup_trim, default=True)
        row_src.addWidget(self.chk_backup_trim)
        row_src.addStretch(1)

        top_card.body_layout.addLayout(row_src)
        root_layout.addWidget(top_card)

        # 2. Visual Disk Map
        map_card = Card(
            "Sơ Đồ Phân Vùng Trên Chip Nguồn (Nhấp khối để chỉ định dòng)",
            icon_name="save",
            parent=content,
        )
        self.backup_disk_map = DiskMapWidget(map_card)
        self.backup_disk_map.setFixedHeight(42)
        map_card.body_layout.addWidget(self.backup_disk_map)

        self.lbl_backup_chip_summary = _LabelCompat("", map_card)
        self.lbl_backup_chip_summary.setProperty("role", "muted")
        self.lbl_backup_chip_summary.setWordWrap(True)
        map_card.body_layout.addWidget(self.lbl_backup_chip_summary)
        root_layout.addWidget(map_card)

        # 3. Chia đôi 60% Trái / 40% Phải
        splitter = QSplitter(Qt.Orientation.Horizontal, content)
        splitter.setMinimumHeight(255)

        # --- CỘT TRÁI (60%): Bảng chọn phân vùng & Nút Sao lưu ---
        left_widget = QWidget(splitter)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 4, 0)
        left_layout.setSpacing(6)

        left_card = Card(
            "Danh Sách Phân Vùng Cần Sao Lưu (Bấm cột Chọn để tích / bỏ tích)",
            icon_name="folder",
            parent=left_widget,
        )
        cols = ("checked", "stt", "name", "type", "subtype", "offset", "size")
        self.backup_tree = _TreeviewCompat(left_card)
        self.backup_tree.set_columns(cols)
        self.backup_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.backup_tree.setMouseTracking(True)
        if self.backup_tree.viewport():
            self.backup_tree.viewport().setMouseTracking(True)
        self.backup_tree.setItemDelegateForColumn(0, _BackupCheckDelegate(self.backup_tree))

        headers = [
            ("checked", "Chọn", 50),
            ("stt", "STT", 38),
            ("name", "Tên Vùng", 120),
            ("type", "Kiểu", 56),
            ("subtype", "Phân loại", 76),
            ("offset", "Offset", 84),
            ("size", "Dung lượng", 110),
        ]
        for col_id, col_text, col_w in headers:
            self.backup_tree.heading(col_id, col_text)
            self.backup_tree.column(col_id, col_w)

        b_hdr = self.backup_tree.header()
        if b_hdr:
            b_hdr.setStretchLastSection(True)
            for c_idx in (0, 1, 3, 4, 5, 6):
                b_hdr.setSectionResizeMode(c_idx, QHeaderView.ResizeMode.ResizeToContents)
            b_hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
            b_hdr.resizeSection(2, 120)

        self.backup_tree.setMinimumHeight(60)
        left_card.body_layout.addWidget(self.backup_tree, 1)

        btn_bar = FlowLayout(h_spacing=4, v_spacing=6)

        self.btn_backup_to_folder = _ButtonCompat("Sao lưu vùng", left_card)
        self.btn_backup_to_folder.setProperty("accent", "true")
        bind_themed_icon(self.btn_backup_to_folder, "save", role="on_accent")
        self.btn_backup_to_folder.setToolTip("Sao lưu các phân vùng đã tick [x] ra thư mục")
        btn_bar.addWidget(self.btn_backup_to_folder)

        self.btn_backup_full_chip = _ButtonCompat("Sao lưu Full Flash", left_card)
        bind_themed_icon(self.btn_backup_full_chip, "save")
        self.btn_backup_full_chip.setToolTip("Sao lưu toàn bộ Flash (0x0 -> hết dung lượng chip)")
        btn_bar.addWidget(self.btn_backup_full_chip)

        self.btn_backup_to_flasher = _ButtonCompat("Sang Nạp Flash", left_card)
        bind_themed_icon(self.btn_backup_to_flasher, "flash")
        self.btn_backup_to_flasher.setToolTip("Đẩy tệp/thư mục vừa sao lưu sang Tab Nạp Firmware")
        btn_bar.addWidget(self.btn_backup_to_flasher)

        self.btn_backup_edit_data = _ButtonCompat("Đọc/Sửa dữ liệu", left_card)
        bind_themed_icon(self.btn_backup_edit_data, "edit")
        self.btn_backup_edit_data.setToolTip(
            "Chỉ áp dụng cho phân vùng dữ liệu (NVS, SPIFFS, LittleFS, FATFS...); khóa đối với Bootloader và Firmware App."
        )
        btn_bar.addWidget(self.btn_backup_edit_data)

        self.btn_backup_erase_data = _ButtonCompat("Xóa dữ liệu", left_card)
        self.btn_backup_erase_data.setProperty("danger_outline", "true")
        bind_themed_icon(self.btn_backup_erase_data, "delete", role="danger")
        self.btn_backup_erase_data.setToolTip(
            "Xóa sạch dữ liệu trong phân vùng Non-Firmware đã chọn (không xóa Bootloader hoặc Firmware App)."
        )
        btn_bar.addWidget(self.btn_backup_erase_data)

        for b_btn in (
            self.btn_backup_to_folder,
            self.btn_backup_full_chip,
            self.btn_backup_to_flasher,
            self.btn_backup_edit_data,
            self.btn_backup_erase_data,
        ):
            b_btn.setStyleSheet("padding: 0 7px;")

        btn_bar.addStretch(1)
        left_card.body_layout.addLayout(btn_bar)
        left_layout.addWidget(left_card, 1)
        splitter.addWidget(left_widget)

        # --- CỘT PHẢI (40%): Nhân bản đa mạch & Nhật ký ---
        right_widget = QWidget(splitter)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 0, 0, 0)
        right_layout.setSpacing(8)

        clone_card = Card(
            "Sao Chép Trực Tiếp (1 Board Gốc -> Nhiều Board Đích)",
            icon_name="copy",
            parent=right_widget,
        )
        c_layout = QVBoxLayout()
        c_layout.setContentsMargins(0, 0, 0, 0)
        c_layout.setSpacing(4)

        mode_row = FlowLayout(h_spacing=6, v_spacing=4)
        mode_row.addWidget(QLabel("Nguồn:", clone_card))
        self.rb_live = QRadioButton("Board Gốc trực tiếp", clone_card)
        self.rb_live.setChecked(True)
        self.rb_folder = QRadioButton("Thư mục đã lưu", clone_card)
        mode_row.addWidget(self.rb_live)
        mode_row.addWidget(self.rb_folder)
        mode_row.addStretch(1)
        c_layout.addLayout(mode_row)

        self.var_clone_source_mode = _TkVarStringCompat("live_board")
        self._syncing_source_mode = False

        def _on_source_mode_var_set(val: str):
            norm = "live_board" if str(val) == "live_board" else "saved_folder"
            self.var_clone_source_mode._val = norm
            if not self._syncing_source_mode:
                self._syncing_source_mode = True
                try:
                    self.rb_live.setChecked(norm == "live_board")
                    self.rb_folder.setChecked(norm != "live_board")
                finally:
                    self._syncing_source_mode = False
            self.source_mode_changed.emit(norm)

        self.var_clone_source_mode.set = _on_source_mode_var_set

        def _on_rb_live_toggled(chk: bool):
            norm = "live_board" if chk else "saved_folder"
            if not self._syncing_source_mode:
                self._syncing_source_mode = True
                try:
                    self.var_clone_source_mode._val = norm
                finally:
                    self._syncing_source_mode = False
                self.source_mode_changed.emit(norm)

        self.rb_live.toggled.connect(_on_rb_live_toggled)

        tgt_hdr = QHBoxLayout()
        tgt_hdr.setContentsMargins(0, 0, 0, 0)
        tgt_hdr.setSpacing(6)
        tgt_hdr.addWidget(QLabel("Cổng COM Đích:", clone_card))
        tgt_hdr.addStretch(1)
        self.btn_sel_all_targets = _ButtonCompat("Chọn tất cả đích", clone_card)
        self.btn_sel_all_targets.setStyleSheet("padding: 2px 8px; min-height: 24px;")
        tgt_hdr.addWidget(self.btn_sel_all_targets)
        c_layout.addLayout(tgt_hdr)

        self.clone_target_ports_frame = _TargetContainer(clone_card)
        c_layout.addWidget(self.clone_target_ports_frame)

        self.chk_clone_erase = QCheckBox(
            "Xóa sạch Flash board đích trước khi chép (--erase-all)", clone_card
        )
        self.var_clone_erase_first = _TkVarCompat(self.chk_clone_erase, default=False)
        c_layout.addWidget(self.chk_clone_erase)

        self.btn_direct_clone = _ButtonCompat("Sao chép đến board mạch đích", clone_card)
        self.btn_direct_clone.setProperty("accent", "true")
        self.btn_direct_clone.setMinimumHeight(30)
        bind_themed_icon(self.btn_direct_clone, "copy", role="on_accent")
        c_layout.addWidget(self.btn_direct_clone)

        clone_card.body_layout.addLayout(c_layout)
        right_layout.addWidget(clone_card)

        log_card = Card(
            "Nhật Ký Sao Lưu & Tiến Trình Nhân Bản",
            icon_name="window_console",
            parent=right_widget,
        )
        self.backup_log_txt = LogView(log_card)
        self.backup_log_txt.setMinimumHeight(44)
        log_card.body_layout.addWidget(self.backup_log_txt, 1)
        right_layout.addWidget(log_card, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 13)
        splitter.setStretchFactor(1, 7)
        splitter.setSizes([720, 390])

        for card_w in (top_card, map_card, left_card, clone_card, log_card):
            if card_w.layout() is not None:
                card_w.layout().setContentsMargins(12, 8, 12, 8)
            card_w.body_layout.setSpacing(4)

        root_layout.addWidget(splitter, 1)
        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)
