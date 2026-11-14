# -*- coding: utf-8 -*-
"""
Sơ đồ phân vùng Flash trực quan (DiskMapWidget) cho PyQt6.
Phong cách MiniTool Partition Wizard với thanh hiển thị theo tỷ lệ dung lượng,
hỗ trợ hover tooltip chi tiết chuẩn ESP-IDF, chọn khối và menu ngữ cảnh chuột phải.
"""
from html import escape
from PyQt6.QtWidgets import QWidget, QToolTip
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QRectF
from modules.partition.partition_model import PartitionEntry
from modules.partition.unit_formatter import (
    format_hex, format_bytes_human, sector_count, DisplayMode
)
from modules.ui.theme.tokens import ThemeTokens
from modules.ui.theme.manager import ThemeManager


def get_entry_color(entry: PartitionEntry, is_dark: bool = False) -> tuple[str, str]:
    """Trả về (màu nền, màu chữ) đạt chuẩn tương phản WCAG AA (>= 4.5:1)."""
    if entry.is_unallocated:
        return ("#374151" if is_dark else "#E2E8F0", "#D1D5DB" if is_dark else "#334155")
    if entry.is_system:
        if entry.type_str == "bootloader":
            return ("#475569", "#FFFFFF")
        return ("#334155", "#FFFFFF")

    t = entry.type_str.lower()
    st = entry.subtype_str.lower()

    if t == "app":
        if st == "factory":
            return ("#2563EB" if is_dark else "#1D4ED8", "#FFFFFF")
        elif st.startswith("ota_"):
            return ("#6D28D9", "#FFFFFF")
        return ("#4338CA", "#FFFFFF")
    else:  # data
        if st == "nvs":
            return ("#B45309", "#FFFFFF")
        elif st in ("ota", "otadata"):
            return ("#0F766E", "#FFFFFF")
        elif st in ("spiffs", "littlefs", "fat"):
            return ("#047857", "#FFFFFF")
        elif st == "phy":
            return ("#92400E", "#FFFFFF")
        elif st == "coredump":
            return ("#BE185D", "#FFFFFF")
        return ("#0E7490", "#FFFFFF")


def build_detailed_tooltip_text(entry: PartitionEntry, is_dark: bool | None = None) -> str:
    """Tạo nội dung tooltip Rich HTML hướng dẫn kỹ thuật chi tiết cho phân vùng."""
    if is_dark is None:
        try:
            is_dark = bool(ThemeManager.instance().is_dark)
        except Exception:
            is_dark = False

    hr_col = "#3E4452" if is_dark else "#D0D7DE"
    muted_col = "#9AA5B4" if is_dark else "#57606A"
    accent_app = "#60A5FA" if is_dark else "#0F6CBD"
    accent_data = "#34D399" if is_dark else "#0F7B6C"
    accent_sys = "#CBD5E1" if is_dark else "#475569"

    divider = f"<hr style='border:none; border-top:1px solid {hr_col}; margin:6px 0;'>"

    def _section(title: str, body_lines: list[str]) -> str:
        body_html = "<br>".join(body_lines)
        return (
            f"<div style='margin-top:2px;'>"
            f"<div style='font-weight:700; color:{muted_col}; font-size:8.5pt; margin-bottom:2px;'>{title}</div>"
            f"<div>{body_html}</div>"
            f"</div>"
        )

    if entry.is_unallocated:
        header = (
            f"<div style='font-size:10pt; font-weight:700; color:{accent_sys};'>"
            f"KHOẢNG TRỐNG CHƯA PHÂN BỔ"
            f" <span style='font-weight:500; color:{muted_col};'>(Unallocated Gap)</span></div>"
        )
        specs = [
            f"• Địa chỉ (Offset): <b>{format_hex(entry.offset)}</b> -> <b>{format_hex(entry.end_offset)}</b>",
            f"• Dung lượng trống: <b>{escape(format_bytes_human(entry.size))}</b>",
            f"• Số Sector vật lý: {sector_count(entry.size)} sectors (mỗi sector 4KB)",
        ]
        blocks = [
            header,
            f"<div style='margin-top:4px;'>{'<br>'.join(specs)}</div>",
            divider,
            _section("MỤC ĐÍCH SỬ DỤNG", [
                "Vùng nhớ Flash vật lý còn trống, chưa được cấp phát cho phân vùng nào.",
                "Có thể tận dụng để mở rộng phân vùng hoặc tạo phân vùng mới (LittleFS, SPIFFS, OTA).",
            ]),
            divider,
            _section("GỢI Ý THAO TÁC", [
                "Bấm chuột trái vào khối này để tạo phân vùng mới vừa vặn.",
            ]),
        ]
        return f"<div style='min-width:290px; max-width:440px; line-height:1.35;'>{''.join(blocks)}</div>"

    if entry.is_system:
        if entry.type_str == "bootloader":
            title_txt = f"PHÂN VÙNG HỆ THỐNG: {escape(entry.name.upper())}"
            purpose = [
                "Chương trình Second-Stage Bootloader do Espressif quản lý.",
                "Khởi tạo phần cứng (GPIO/PLL/Flash), đọc bảng phân vùng tại 0x8000 và nạp App.",
            ]
            recommend = [
                "• Mặc định: 28 KB - 32 KB (đặt tại 0x1000 trên ESP32 hoặc 0x0 trên S3/C3).",
                "• Phân vùng cố định, không được chỉnh sửa hoặc xóa.",
            ]
        else:
            title_txt = "BẢNG PHÂN VÙNG HỆ THỐNG (PARTITION TABLE)"
            purpose = [
                "Bản đồ lưu trữ toàn bộ các phân vùng của chip Flash.",
                "Chứa cấu trúc 32-byte định nghĩa Type, SubType, Offset, Size và MD5 Checksum.",
            ]
            recommend = [
                "• Chuẩn ESP-IDF: Cố định đúng 1 sector 4 KB (0x1000) tại offset 0x8000.",
            ]

        header = f"<div style='font-size:10pt; font-weight:700; color:{accent_sys};'>{title_txt}</div>"
        specs = [
            f"• Vị trí Offset: <b>{format_hex(entry.offset)}</b>",
            f"• Kích thước: <b>{escape(format_bytes_human(entry.size))}</b>",
        ]
        blocks = [
            header,
            f"<div style='margin-top:4px;'>{'<br>'.join(specs)}</div>",
            divider,
            _section("MỤC ĐÍCH SỬ DỤNG", purpose),
            divider,
            _section("KHUYẾN NGHỊ DUNG LƯỢNG", recommend),
        ]
        return f"<div style='min-width:290px; max-width:440px; line-height:1.35;'>{''.join(blocks)}</div>"

    # Phân vùng người dùng
    t = entry.type_str.lower()
    st = entry.subtype_str.lower()
    title_col = accent_app if t == "app" else accent_data
    header = (
        f"<div style='font-size:10pt; font-weight:700; color:{title_col};'>"
        f"{escape(entry.name)} "
        f"<span style='font-weight:500; color:{muted_col};'>(Type: {escape(entry.type_str)} | SubType: {escape(entry.subtype_str)})</span>"
        f"</div>"
    )
    align_rule = "Căn biên 64 KB (0x10000)" if t == "app" else "Căn biên 4 KB (0x1000)"
    specs = [
        f"• Offset: <b>{format_hex(entry.offset)}</b> ({entry.offset:,} B) | {align_rule}",
        f"• Dung lượng: <b>{escape(format_bytes_human(entry.size))}</b> | {sector_count(entry.size)} Sectors (4KB)",
    ]
    if entry.used_size > 0:
        specs.append(
            f"• Firmware chiếm: {escape(format_bytes_human(entry.used_size))} ({entry.usage_percent:.1f}%) "
            f"| Còn trống: {escape(format_bytes_human(entry.free_size))}"
        )
    if entry.flags_str:
        specs.append(f"• Cờ bảo mật: {escape(entry.flags_str)}")

    blocks = [
        header,
        f"<div style='margin-top:4px;'>{'<br>'.join(specs)}</div>",
        divider,
    ]
    if st == "nvs":
        blocks.append(_section("MỤC ĐÍCH SỬ DỤNG", [
            "Non-Volatile Storage. Lưu trữ cấu hình Wi-Fi (SSID, Password), khóa BLE,",
            "dữ liệu hiệu chuẩn RF (PHY calibration) và các biến Key-Value tùy biến.",
            "Dữ liệu được lưu vĩnh viễn, không bị mất khi reset hoặc tắt nguồn.",
        ]))
        blocks.append(divider)
        blocks.append(_section("KHUYẾN NGHỊ DUNG LƯỢNG", [
            "• Tối thiểu: 12 KB (0x3000 = 3 sectors)",
            "• Khuyến nghị: 16 KB - 24 KB (0x4000 - 0x6000)",
        ]))
    elif st == "factory":
        blocks.append(_section("MỤC ĐÍCH SỬ DỤNG", [
            "Bản firmware ứng dụng chính gốc xuất xưởng (Default Factory App).",
            "Bootloader sẽ nạp và thực thi mã tại phân vùng này khi khởi động.",
        ]))
        blocks.append(divider)
        blocks.append(_section("KHUYẾN NGHỊ DUNG LƯỢNG", [
            "• Căn biên 64 KB (0x10000). Dung lượng điển hình: 1 MB - 2 MB.",
        ]))
    else:
        blocks.append(_section("MỤC ĐÍCH SỬ DỤNG", [
            f"Phân vùng dữ liệu/ứng dụng {escape(st.upper())} chuẩn ESP-IDF.",
        ]))

    return f"<div style='min-width:290px; max-width:440px; line-height:1.35;'>{''.join(blocks)}</div>"


class DiskMapWidget(QWidget):
    entry_clicked = pyqtSignal(object)
    entry_double_clicked = pyqtSignal(object)
    unallocated_clicked = pyqtSignal(object)
    unallocated_double_clicked = pyqtSignal(object)
    entry_context_requested = pyqtSignal(object, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(42)
        self.setFixedHeight(42)
        self.setMouseTracking(True)

        self.layout_entries: list[PartitionEntry] = []
        self.flash_size = 4 * 1024 * 1024
        self.display_mode = None
        self.selected_entry: PartitionEntry | None = None
        self.checked_names: set[str] | None = None  # Dùng cho Tab 5 (mờ khối không chọn)
        self.on_select_entry = None
        self.on_double_click_entry = None
        self.on_unallocated_click = None
        self.on_unallocated_double_click = None
        self.on_context_action = None

        self._rendered_blocks: list[tuple[float, float, float, float, PartitionEntry]] = []
        self._current_tokens: ThemeTokens = ThemeManager.instance().tokens

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _build_detailed_tooltip_text(self, entry: PartitionEntry) -> str:
        """Helper tương thích với test suite cũ."""
        return build_detailed_tooltip_text(entry)

    def set_theme_mode(self, is_dark: bool):
        self._current_tokens = ThemeManager.instance().tokens
        self.update()

    def redraw(self):
        self.update()

    def set_data(self, layout_entries: list[PartitionEntry], flash_size: int, display_mode=None, selected_entry: PartitionEntry | None = None):
        self.layout_entries = layout_entries
        self.flash_size = max(1024, flash_size)
        self.display_mode = display_mode
        self.selected_entry = selected_entry
        self.update()

    def set_checked_names(self, names: set[str] | None):
        self.checked_names = names
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._rendered_blocks.clear()

        w = float(self.width())
        h = float(self.height())
        if w < 60 or h < 30:
            return

        is_dark = (self._current_tokens.mode == "dark")
        padding_x = 3.0
        padding_y = 3.0
        bar_w = w - (2 * padding_x)
        bar_h = h - (2 * padding_y)

        # Nền khung viền ngoài
        painter.setPen(QPen(QColor(self._current_tokens.border), 1))
        painter.setBrush(QBrush(QColor(self._current_tokens.surface)))
        painter.drawRoundedRect(QRectF(padding_x, padding_y, bar_w, bar_h), 5, 5)

        if not self.layout_entries or self.flash_size <= 0:
            painter.setPen(QColor(self._current_tokens.text_secondary))
            painter.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "Chưa có dữ liệu phân vùng")
            return

        # Tính toán bề rộng khối
        min_px = 32.0
        raw_widths = []
        for e in self.layout_entries:
            px = (e.size / self.flash_size) * bar_w
            raw_widths.append(max(px, min_px if e.size > 0 else 0))

        sum_w = sum(raw_widths)
        scale = bar_w / sum_w if sum_w > 0 else 1.0

        current_x = padding_x
        top_y = padding_y
        bot_y = padding_y + bar_h

        font_name = QFont("Segoe UI", 8, QFont.Weight.Bold)
        font_size = QFont("Segoe UI", 7)
        fm_name = QFontMetrics(font_name)

        line1_h = 15.0
        line2_h = 13.0
        line_gap = 1.0 if bar_h < 42 else 2.0
        total_txt_h = line1_h + line_gap + line2_h
        top_txt_y = top_y + max(2.0, (bar_h - total_txt_h) / 2.0 - 0.5)
        bot_txt_y = top_txt_y + line1_h + line_gap

        selected_rect: QRectF | None = None

        # Vòng 1: Vẽ toàn bộ khối phân vùng, vạch phân cách và chữ nhãn
        for idx, entry in enumerate(self.layout_entries):
            block_w = raw_widths[idx] * scale
            x1 = current_x
            x2 = current_x + block_w
            current_x = x2

            bg_hex, fg_hex = get_entry_color(entry, is_dark)
            bg_col = QColor(bg_hex)
            fg_col = QColor(fg_hex)

            # Nếu trong Tab 5 và khối này không được tích chọn, làm mờ
            if self.checked_names is not None and not entry.is_unallocated:
                if entry.name not in self.checked_names and entry.name.lower() not in self.checked_names:
                    bg_col.setAlpha(90)
                    fg_col.setAlpha(120)

            allow_system_highlight = self.checked_names is not None
            is_selected = (
                self.selected_entry is not None
                and not entry.is_unallocated
                and (allow_system_highlight or not entry.is_system)
                and self.selected_entry.name == entry.name
                and self.selected_entry.offset == entry.offset
            )

            rect = QRectF(x1, top_y, max(0.0, block_w), bar_h)

            pen = QPen(QColor(self._current_tokens.border), 1)
            if entry.is_unallocated:
                pen.setStyle(Qt.PenStyle.DashLine)

            painter.setPen(pen)
            painter.setBrush(QBrush(bg_col))
            painter.drawRect(rect)

            if is_selected:
                selected_rect = QRectF(rect)

            # Nhãn tên & kích thước căn giữa theo chiều dọc khối màu
            if block_w >= 28:
                painter.setPen(fg_col)
                painter.setFont(font_name)
                label_text = "Trống" if (entry.is_unallocated and block_w < 78) else entry.name
                elided_name = fm_name.elidedText(label_text, Qt.TextElideMode.ElideRight, int(block_w - 6))
                painter.drawText(QRectF(x1 + 3, top_txt_y, block_w - 6, line1_h), Qt.AlignmentFlag.AlignCenter, elided_name)

                painter.setFont(font_size)
                size_str = format_bytes_human(entry.size, compact=True)
                painter.drawText(QRectF(x1 + 3, bot_txt_y, block_w - 6, line2_h), Qt.AlignmentFlag.AlignCenter, size_str)

            self._rendered_blocks.append((x1, top_y, x2, bot_y, entry))

        # Vòng 2: Vẽ viền chọn kép tương phản cao lên trên cùng để các khối cạnh bên không che khuất cạnh phải
        if selected_rect is not None and selected_rect.width() >= 4.0:
            outer_col = QColor("#FFFFFF") if is_dark else QColor("#00FF04")
            inner_col = QColor("#00FF04") if is_dark else QColor("#FFFFFF")

            painter.setBrush(Qt.BrushStyle.NoBrush)

            outer_pen = QPen(outer_col, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)
            painter.setPen(outer_pen)
            painter.drawRect(selected_rect.adjusted(-0.5, -0.5, 0.5, 0.5))

            inner_pen = QPen(inner_col, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.SquareCap, Qt.PenJoinStyle.MiterJoin)
            painter.setPen(inner_pen)
            painter.drawRect(selected_rect.adjusted(1.5, 1.5, -1.5, -1.5))

    def _find_entry_at(self, pos: QPoint) -> PartitionEntry | None:
        x = float(pos.x())
        y = float(pos.y())
        for x1, top_y, x2, bot_y, entry in self._rendered_blocks:
            if x1 <= x <= x2 and top_y <= y <= bot_y:
                return entry
        return None

    def mouseMoveEvent(self, event):
        entry = self._find_entry_at(event.pos())
        if entry:
            is_dark = bool(getattr(self._current_tokens, "mode", "light") == "dark")
            tip = build_detailed_tooltip_text(entry, is_dark=is_dark)
            QToolTip.showText(event.globalPosition().toPoint(), tip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        entry = self._find_entry_at(event.pos())
        if entry:
            if event.button() == Qt.MouseButton.LeftButton:
                if entry.is_unallocated:
                    self.unallocated_clicked.emit(entry)
                    cb = getattr(self, "on_unallocated_click", None)
                    if callable(cb):
                        cb(entry.offset, entry.size)
                else:
                    if self.checked_names is not None:
                        self.selected_entry = entry
                    elif (
                        self.selected_entry is not None
                        and self.selected_entry.name == entry.name
                        and self.selected_entry.offset == entry.offset
                    ):
                        self.selected_entry = None
                    else:
                        self.selected_entry = entry
                    self.entry_clicked.emit(entry)
                    cb = getattr(self, "on_select_entry", None)
                    if callable(cb):
                        cb(entry)
                    self.update()
            elif event.button() == Qt.MouseButton.RightButton:
                global_pt = event.globalPosition().toPoint()
                self.entry_context_requested.emit(entry, global_pt)
                cb = getattr(self, "on_context_action", None)
                if callable(cb):
                    local_pt = event.pos()
                    compat_evt = type(
                        "_DiskMapEvent",
                        (),
                        {
                            "x": local_pt.x(),
                            "y": local_pt.y(),
                            "x_root": global_pt.x(),
                            "y_root": global_pt.y(),
                            "globalPos": lambda _s: global_pt,
                        },
                    )()
                    cb("full_context_menu", entry, compat_evt)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        entry = self._find_entry_at(event.pos())
        if entry and event.button() == Qt.MouseButton.LeftButton:
            if entry.is_unallocated:
                self.unallocated_double_clicked.emit(entry)
                cb = getattr(self, "on_unallocated_double_click", None)
                if callable(cb):
                    cb(entry.offset, entry.size)
            else:
                self.selected_entry = entry
                self.update()
                self.entry_double_clicked.emit(entry)
                cb = getattr(self, "on_double_click_entry", None)
                if callable(cb):
                    cb(entry)
        super().mouseDoubleClickEvent(event)

    def _on_theme_changed(self, tokens: ThemeTokens):
        self._current_tokens = tokens
        self.update()

    def _build_detailed_tooltip_text(self, entry: PartitionEntry) -> str:
        return build_detailed_tooltip_text(entry)
