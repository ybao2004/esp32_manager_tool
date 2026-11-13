# -*- coding: utf-8 -*-
"""
Trang 1: Kiểm tra Phần cứng (Chip Inspector Page) - Thiết kế Hybrid v1.6.
- Hàng trên: Thanh công cụ gọn gàng + Nút chuyển đổi nhanh 2 chế độ xem.
- Hàng giữa: 4 Thẻ KPI nổi bật (Vi xử lý, Flash, PSRAM, Địa chỉ MAC).
- Hàng dưới (QStackedWidget):
  + Chế độ 1 (Mặc định): Báo cáo văn bản định dạng liền mạch (dễ theo dõi tiến trình & copy).
  + Chế độ 2: Bảng thông số 2 cột kiểu CPU-Z (không cuộn con lồng nhau).
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QPushButton,
    QCheckBox, QLineEdit, QScrollArea, QFrame, QLabel, QStackedWidget,
    QButtonGroup, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from modules.ui.text import qt_text
from modules.ui.icons import get_icon
from modules.mac_database import is_espressif_oui
from modules.ui.theme.manager import ThemeManager
from modules.ui.widgets.card import Card
from modules.ui.widgets.flow_layout import FlowLayout
from modules.ui.widgets.key_value_table import KeyValueTable
from modules.ui.widgets.log_view import LogView


class _ButtonCompat(QPushButton):
    def winfo_exists(self) -> bool:
        return True

    def cget(self, key: str):
        if key == "state":
            return "normal" if self.isEnabled() else "disabled"
        if key == "text":
            return self.text()
        return ""

    def config(self, **kwargs):
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))

    configure = config

    def __getitem__(self, key: str):
        return self.cget(key)

    def __setitem__(self, key: str, value):
        self.config(**{key: value})


class _CheckVar:
    def __init__(self, cb: QCheckBox):
        self._cb = cb

    def get(self) -> bool:
        return self._cb.isChecked()

    def set(self, val: bool):
        self._cb.setChecked(bool(val))


class KpiStatCard(QFrame):
    """Thẻ hiển thị chỉ số phần cứng quan trọng (KPI Stat Card)."""

    def __init__(self, title: str, default_val: str = "Chưa có dữ liệu", default_sub: str = "---", parent=None):
        super().__init__(parent)
        self.setProperty("role", "kpi_card")
        self.setMinimumHeight(66)
        self.setMaximumHeight(76)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)

        self.lbl_title = QLabel(str(title), self)
        self.lbl_title.setProperty("role", "kpi_title")

        self.lbl_value = QLabel(str(default_val), self)
        self.lbl_value.setProperty("role", "kpi_value")

        self.lbl_sub = QLabel(str(default_sub), self)
        self.lbl_sub.setProperty("role", "kpi_sub")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)
        layout.addWidget(self.lbl_sub)

    def set_metrics(self, value: str, subtitle: str = ""):
        self.lbl_value.setText(str(value))
        self.lbl_sub.setText(str(subtitle))


class InspectorPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._report_rows_cache: list[tuple[str, str, str | None]] = []
        self._build_ui()
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _build_ui(self):
        tokens = ThemeManager.instance().tokens

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(6)

        # =====================================================================
        # 1. THANH CÔNG CỤ TRÊN CÙNG (ACTION BAR - RESPONSIVE FLOWLAYOUT)
        # =====================================================================
        top_bar = FlowLayout(h_spacing=6, v_spacing=6)

        self.detect_btn = _ButtonCompat(qt_text("Kiểm tra Chip"), self)
        self.detect_btn.setProperty("accent", "true")
        self.detect_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.detect_btn.setIcon(get_icon("chip", tokens.on_accent, 16))
        self.detect_btn.setIconSize(QSize(16, 16))
        self.detect_btn.setMinimumWidth(122)

        self.save_report_btn = _ButtonCompat(qt_text("Lưu Báo Cáo"), self)
        self.save_report_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_report_btn.setIcon(get_icon("save", tokens.text, 16))
        self.save_report_btn.setIconSize(QSize(16, 16))
        self.save_btn = self.save_report_btn

        self.clear_inspector_btn = _ButtonCompat(qt_text("Xóa"), self)
        self.clear_inspector_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_inspector_btn.setIcon(get_icon("trash", tokens.text, 16))
        self.clear_inspector_btn.setIconSize(QSize(16, 16))

        self.cb_raw_log = QCheckBox(qt_text("Xem log thô esptool"), self)
        self.chk_debug = self.cb_raw_log
        self.var_debug = _CheckVar(self.cb_raw_log)

        self.cb_extra_log = QCheckBox(qt_text("Ghi thêm thông tin phụ"), self)
        self.cb_extra_log.setChecked(True)
        self.var_extra_log = _CheckVar(self.cb_extra_log)

        self.search_entry = QLineEdit(self)
        self.search_entry.setPlaceholderText("Tìm nhanh thông số...")
        self.search_entry.setClearButtonEnabled(True)
        self.search_entry.setFixedWidth(160)
        self.search_entry.textChanged.connect(self._on_filter_changed)

        # Nút gạt chuyển đổi nhanh giữa 2 chế độ xem (Hybrid View Switcher)
        self.btn_view_report = QPushButton(qt_text("Báo cáo Liền mạch"), self)
        self.btn_view_report.setCheckable(True)
        self.btn_view_report.setChecked(True)
        self.btn_view_report.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_view_grid = QPushButton(qt_text("Bảng Thông số"), self)
        self.btn_view_grid.setCheckable(True)
        self.btn_view_grid.setCursor(Qt.CursorShape.PointingHandCursor)

        self.view_group = QButtonGroup(self)
        self.view_group.setExclusive(True)
        self.view_group.addButton(self.btn_view_report, 0)
        self.view_group.addButton(self.btn_view_grid, 1)
        self.view_group.idClicked.connect(self._on_switch_view_mode)

        top_bar.addWidget(self.detect_btn)
        top_bar.addWidget(self.save_report_btn)
        top_bar.addWidget(self.clear_inspector_btn)
        top_bar.addSpacing(6)
        top_bar.addWidget(self.cb_raw_log)
        top_bar.addWidget(self.cb_extra_log)
        top_bar.addStretch(1)
        top_bar.addWidget(self.search_entry)
        top_bar.addWidget(self.btn_view_report)
        top_bar.addWidget(self.btn_view_grid)
        main_layout.addLayout(top_bar)

        # =====================================================================
        # 2. HÀNG 4 THẺ KPI TÓM TẮT PHẦN CỨNG NỔI BẬT
        # =====================================================================
        kpi_row = QHBoxLayout()
        kpi_row.setContentsMargins(0, 0, 0, 0)
        kpi_row.setSpacing(6)

        self.kpi_chip = KpiStatCard("VI XỬ LÝ (CHIP MODEL)", "Chưa kiểm tra", "Chọn cổng COM & bấm Kiểm tra Chip", self)
        self.kpi_flash = KpiStatCard("BỘ NHỚ FLASH", "N/A", "Dung lượng & Nhà sản xuất JEDEC", self)
        self.kpi_psram = KpiStatCard("BỘ NHỚ PSRAM", "N/A", "Tốc độ & Chế độ giao tiếp Bus", self)
        self.kpi_mac = KpiStatCard("ĐỊA CHỈ MAC & HÃNG", "N/A", "Định danh eFuse & Tiền tố OUI", self)

        kpi_row.addWidget(self.kpi_chip, 1)
        kpi_row.addWidget(self.kpi_flash, 1)
        kpi_row.addWidget(self.kpi_psram, 1)
        kpi_row.addWidget(self.kpi_mac, 1)
        main_layout.addLayout(kpi_row)

        # =====================================================================
        # 3. VÙNG NỘI DUNG CHÍNH (HYBRID STACK: BÁO CÁO LIỀN MẠCH / BẢNG 2 CỘT)
        # =====================================================================
        self.view_stack = QStackedWidget(self)

        # --- Chế độ 0: Khung Báo cáo văn bản định dạng liền mạch (Mặc định) ---
        self.report_card = Card("Báo Cáo Chẩn Đoán Phần Cứng & Tiến Trình Trực Tiếp", "chip", self)
        self.inspector_txt = LogView(self.report_card)
        self.raw_log_view = self.inspector_txt
        self.report_card.content_layout.addWidget(self.inspector_txt, 1)
        self.view_stack.addWidget(self.report_card)

        # --- Chế độ 1: Bảng thông số 2 cột kiểu CPU-Z ---
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QFrame.Shape.NoFrame)

        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("PageScrollCanvas")
        cols_layout = QHBoxLayout(self.scroll_content)
        cols_layout.setContentsMargins(0, 0, 4, 0)
        cols_layout.setSpacing(10)

        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(10)

        right_col = QVBoxLayout()
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(10)

        # Cột trái
        self.card_dynamic = Card("1. Định danh Silicon & Động (Đọc từ Chip)", "chip", self.scroll_content)
        self.table_dynamic = KeyValueTable(self.card_dynamic)
        self.card_dynamic.content_layout.addWidget(self.table_dynamic)

        self.card_memory = Card("2. Bộ nhớ Flash & PSRAM", "save", self.scroll_content)
        self.table_memory = KeyValueTable(self.card_memory)
        self.card_memory.content_layout.addWidget(self.table_memory)

        self.card_specs = Card("3. Thông số Kỹ thuật (CSDL)", "info", self.scroll_content)
        self.table_specs = KeyValueTable(self.card_specs)
        self.card_specs.content_layout.addWidget(self.table_specs)

        # Cột phải
        self.card_network = Card("4. Mạng & Kết nối (MAC / Wi-Fi / BT)", "wifi", self.scroll_content)
        self.table_network = KeyValueTable(self.card_network)
        self.card_network.content_layout.addWidget(self.table_network)

        self.card_origin = Card("5. Firmware, Phân vùng & Nguồn gốc", "search", self.scroll_content)
        self.table_origin = KeyValueTable(self.card_origin)
        self.card_origin.content_layout.addWidget(self.table_origin)

        left_col.addWidget(self.card_dynamic)
        left_col.addWidget(self.card_memory)
        left_col.addWidget(self.card_specs)
        left_col.addStretch(1)

        right_col.addWidget(self.card_network)
        right_col.addWidget(self.card_origin)
        right_col.addStretch(1)

        cols_layout.addLayout(left_col, 1)
        cols_layout.addLayout(right_col, 1)

        self.scroll_area.setWidget(self.scroll_content)
        self.view_stack.addWidget(self.scroll_area)

        main_layout.addWidget(self.view_stack, 1)

        # Khởi tạo dữ liệu mặc định cho bảng
        self.reset_kpi_and_tables()

    def _on_switch_view_mode(self, idx: int):
        self.view_stack.setCurrentIndex(idx)

    def reset_kpi_and_tables(self):
        self.kpi_chip.set_metrics("Chưa kiểm tra", "Chọn cổng COM & bấm Kiểm tra Chip")
        self.kpi_flash.set_metrics("N/A", "Dung lượng & Nhà sản xuất JEDEC")
        self.kpi_psram.set_metrics("N/A", "Tốc độ & Chế độ giao tiếp Bus")
        self.kpi_mac.set_metrics("N/A", "Định danh eFuse & Tiền tố OUI")

        self.table_dynamic.populate([
            ("Tên chip đầy đủ", "Chưa kiểm tra"),
            ("Các tính năng", "N/A"),
            ("Phiên bản Silicon", "N/A"),
            ("Tần số thạch anh", "N/A"),
        ])
        self.table_memory.populate([
            ("Nhà sản xuất Flash", "N/A"),
            ("ID Thiết bị Flash", "N/A"),
            ("Kích thước Flash", "N/A"),
            ("Kích thước PSRAM", "N/A"),
        ])
        self.table_specs.populate([
            ("Loại chip", "N/A"),
            ("Kiến trúc CPU", "N/A"),
            ("Số nhân & Tần số", "N/A"),
            ("Năng lực tính toán", "N/A"),
            ("SRAM / ROM", "N/A"),
        ])
        self.table_network.populate([
            ("Chuẩn Wi-Fi", "N/A"),
            ("Chuẩn Bluetooth", "N/A"),
            ("Địa chỉ Base MAC", "N/A"),
        ])
        self.table_origin.populate([
            ("Nguồn gốc MAC (OUI)", "N/A"),
            ("Chip nhớ Flash", "N/A"),
            ("Firmware / Phân vùng", "N/A"),
        ])

    def update_from_parsed_info(
        self,
        info: dict,
        chip_data: dict | None,
        man_display: str,
        psram_str: str,
        base_mac_formatted: str | None,
        report_data: list[tuple[str, str | None, str | None]]
    ):
        """Cập nhật trực tiếp 4 thẻ KPI và 5 bảng thông số khi đọc chip hoàn tất."""
        # 1. KPI Chip
        chip_title = info.get("chip_line") or info.get("chip_name_key") or "Không xác định"
        chip_sub = info.get("features_line") or (chip_data.get("architecture", "") if chip_data else "")
        self.kpi_chip.set_metrics(str(chip_title), str(chip_sub))

        # 2. KPI Flash
        flash_mb = f"{info.get('flash_mb', 0):.2f} MB" if "flash_mb" in info else "N/A"
        flash_sub = f"{man_display} · ID: {info.get('flash_device', 'N/A')}"
        self.kpi_flash.set_metrics(flash_mb, flash_sub)

        # 3. KPI PSRAM
        if "psram_mb" in info:
            ps_val = f"{info['psram_mb']} MB"
            ps_sub = " · ".join(p for p in [info.get("psram_speed"), info.get("psram_mode"), info.get("psram_vendor")] if p) or "Đã kích hoạt"
        else:
            ps_val = "Không phát hiện"
            ps_sub = info.get("fw_psram_driver") or "Không có PSRAM ngoài"
        self.kpi_psram.set_metrics(ps_val, ps_sub)

        # 4. KPI MAC
        if base_mac_formatted:
            mac_val = base_mac_formatted.upper()
            mac_sub = (
                "Espressif Systems (OUI hợp lệ)"
                if is_espressif_oui(base_mac_formatted)
                else "OUI ngoại lệ / Không thuộc Espressif"
            )
        else:
            mac_val = "Không rõ"
            mac_sub = "Chưa đọc được MAC"
        self.kpi_mac.set_metrics(mac_val, mac_sub)

        # 5. Phân nhóm dữ liệu cho 5 bảng ở Chế độ Bảng Thông số
        sec_map: dict[int, list[tuple[str, str]]] = {1: [], 2: [], 3: [], 4: [], 5: []}
        current_bucket = 1
        for k, v, _tag in report_data:
            if v is None:
                hdr = (k or "").lower()
                if "động" in hdr or "silicon" in hdr:
                    current_bucket = 1
                elif "flash" in hdr and "psram" in hdr:
                    current_bucket = 2
                elif "kỹ thuật" in hdr:
                    current_bucket = 3
                elif "mạng" in hdr or "kết nối" in hdr:
                    current_bucket = 4
                else:
                    current_bucket = 5
            else:
                clean_k = k.strip() if k and k.strip() else "Ghi chú"
                sec_map[current_bucket].append((clean_k, str(v)))

        if sec_map[1]:
            self.table_dynamic.populate(sec_map[1])
        if sec_map[2]:
            self.table_memory.populate(sec_map[2])
        if sec_map[3]:
            self.table_specs.populate(sec_map[3])
        if sec_map[4]:
            self.table_network.populate(sec_map[4])
        if sec_map[5]:
            self.table_origin.populate(sec_map[5])

    def _on_filter_changed(self, text: str):
        query = text.strip().lower()
        for tbl in (
            self.table_dynamic,
            self.table_memory,
            self.table_specs,
            self.table_network,
            self.table_origin,
        ):
            for r in range(tbl.rowCount()):
                k_item = tbl.item(r, 0)
                v_item = tbl.item(r, 1)
                k_txt = k_item.text().lower() if k_item else ""
                v_txt = v_item.text().lower() if v_item else ""
                match = (not query) or (query in k_txt) or (query in v_txt)
                tbl.setRowHidden(r, not match)

    def _on_theme_changed(self, tokens):
        self.detect_btn.setIcon(get_icon("chip", tokens.on_accent, 16))
        self.save_report_btn.setIcon(get_icon("save", tokens.text, 16))
        self.clear_inspector_btn.setIcon(get_icon("trash", tokens.text, 16))
