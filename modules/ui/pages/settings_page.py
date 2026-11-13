# -*- coding: utf-8 -*-
"""
Trang Cài Đặt Hệ Thống (SettingsPage - v1.6).
- Bố cục QTabWidget gồm 2 sub-tab gọn gàng, loại bỏ hiện tượng cuộn-lồng-cuộn:
  1. Sub-tab 1 ("Cài đặt Chung & Cổng COM"): Chia 2 cột cân đối:
     - Cột Trái: Giao diện & Chủ đề (tự động áp dụng trực tiếp khi chọn), Cấu hình Server Mặc định, Thông tin Bản quyền v1.6 (GPL-3.0, @ybao04).
     - Cột Phải: Quản lý Cổng COM (tự động quét, lọc Bluetooth, tích chọn cổng ẩn, nút [Làm mới danh sách] rộng vừa đủ 165px).
  2. Sub-tab 2 ("Phím chức năng F1-F15"): Bảng 15 dòng chiếm trọn chiều cao, dễ nhìn và dễ chỉnh sửa.
- Hàng nút dưới cùng cố định: [Khôi phục mặc định] (155px) và [Lưu Cài Đặt] (155px Primary) căn phải.
"""
import os
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QRadioButton, QTabWidget,
    QPlainTextEdit, QProgressBar, QApplication, QSizePolicy, QScrollArea
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from serial.tools import list_ports
from modules.config import CONTROL_CONFIG, APP_VERSION, GITHUB_REPO
from modules.serial_util import is_bluetooth_port
from modules.update_util import (
    check_for_updates,
    download_update_asset,
    get_running_executable_path,
    get_staged_update_path,
    is_running_frozen,
    is_same_target_as_running_exe,
    launch_windows_self_updater,
)
from modules.ui.dispatch import UiDispatcher
from modules.ui.theme.manager import ThemeManager
from modules.ui.widgets.card import Card
from modules.ui.widgets.update_badge import UpdateDotBadge, get_update_dot_icon
from modules.ui.icons import get_icon, bind_themed_icon
from modules.ui import dialogs_service as dlg


class SettingsPage(QWidget):
    """Trang Cài Đặt Hệ Thống ESP32 Manager Tool (v1.2)"""

    def __init__(self, core_app=None, parent: QWidget = None):
        super().__init__(parent)
        self.core = core_app
        self._com_checkboxes: dict[str, QCheckBox] = {}
        self._f_entries: list[tuple[QLineEdit, QLineEdit]] = []
        self._syncing_theme_controls = False
        self._syncing_update_prefs = False
        self._dispatcher = UiDispatcher.instance()
        self.latest_update_info: dict = {}
        self._update_check_in_progress = False
        self._update_download_in_progress = False
        self._update_cancel_event = threading.Event()
        self._has_available_update = False
        self._build_ui()
        ThemeManager.instance().theme_changed.connect(self._on_external_theme_changed)

    def _build_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(6)

        self.tabs = QTabWidget(self)
        root_layout.addWidget(self.tabs, 1)

        # =====================================================================
        # SUB-TAB 1: CÀI ĐẶT CHUNG & CỔNG COM (Chia 2 cột cân đối)
        # =====================================================================
        tab_general = QWidget()
        gen_hbox = QHBoxLayout(tab_general)
        gen_hbox.setContentsMargins(10, 10, 10, 10)
        gen_hbox.setSpacing(12)

        # --- CỘT TRÁI: Giao diện & Chủ đề + Cấu hình Server TCP ---
        left_col = QVBoxLayout()
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(10)

        # 1. Card Giao diện & Chủ đề (Tự động áp dụng tức thì - Chỉ phong cách Kỹ thuật)
        card_theme = Card("Giao diện Kỹ thuật (Tự động áp dụng)", icon_name="edit", parent=tab_general)
        t_grid = QGridLayout()
        t_grid.setContentsMargins(0, 0, 0, 0)
        t_grid.setHorizontalSpacing(10)
        t_grid.setVerticalSpacing(8)

        t_grid.addWidget(QLabel("Phong cách thiết kế:", card_theme), 0, 0)
        self.lbl_theme_style = QLabel("Kỹ thuật Chuyên sâu (Engineering)", card_theme)
        self.lbl_theme_style.setStyleSheet("font-weight: 600;")
        t_grid.addWidget(self.lbl_theme_style, 0, 1)

        t_grid.addWidget(QLabel("Chế độ màu:", card_theme), 1, 0)
        mode_box = QHBoxLayout()
        mode_box.setSpacing(14)
        self.rb_dark = QRadioButton("Giao diện Tối (Dark)", card_theme)
        self.rb_light = QRadioButton("Giao diện Sáng (Light)", card_theme)
        if ThemeManager.instance().is_dark:
            self.rb_dark.setChecked(True)
        else:
            self.rb_light.setChecked(True)
        mode_box.addWidget(self.rb_dark)
        mode_box.addWidget(self.rb_light)
        mode_box.addStretch(1)
        t_grid.addLayout(mode_box, 1, 1)

        lbl_live_hint = QLabel(
            "Chế độ Sáng / Tối được áp dụng ngay lập tức trên toàn bộ giao diện.",
            card_theme,
        )
        lbl_live_hint.setProperty("role", "muted")
        t_grid.addWidget(lbl_live_hint, 2, 0, 1, 2)

        t_grid.setColumnStretch(1, 1)
        card_theme.body_layout.addLayout(t_grid)
        left_col.addWidget(card_theme)

        self.rb_dark.toggled.connect(self._on_live_theme_changed)

        # 2. Card Cấu hình Server TCP Mặc định
        card_server = Card("Cấu hình Server TCP Mặc định", icon_name="wifi", parent=tab_general)
        srv_grid = QGridLayout()
        srv_grid.setContentsMargins(0, 0, 0, 0)
        srv_grid.setHorizontalSpacing(10)
        srv_grid.setVerticalSpacing(8)

        srv_grid.addWidget(QLabel("IP Server mặc định:", card_server), 0, 0)
        self.entry_default_ip = QLineEdit(
            getattr(self.core, "default_ip", "192.168.4.1") if self.core else "192.168.4.1",
            card_server,
        )
        srv_grid.addWidget(self.entry_default_ip, 0, 1)

        srv_grid.addWidget(QLabel("Cổng (Port) mặc định:", card_server), 1, 0)
        self.entry_default_port = QLineEdit(
            getattr(self.core, "default_port", "100") if self.core else "100",
            card_server,
        )
        srv_grid.addWidget(self.entry_default_port, 1, 1)
        srv_grid.setColumnStretch(1, 1)

        card_server.body_layout.addLayout(srv_grid)
        left_col.addWidget(card_server)
        left_col.addStretch(1)

        gen_hbox.addLayout(left_col, 1)

        # --- CỘT PHẢI: Quản lý Cổng COM & Bộ lọc Bluetooth ---
        right_col = QVBoxLayout()
        right_col.setSpacing(10)

        card_com = Card("Quản lý Cổng COM & Bộ lọc Thiết bị", icon_name="router", parent=tab_general)
        com_layout = QVBoxLayout()
        com_layout.setContentsMargins(0, 0, 0, 0)
        com_layout.setSpacing(8)

        self.chk_auto_scan = QCheckBox("Tự động quét cổng COM định kỳ (mỗi 2 giây)", card_com)
        self.chk_auto_scan.setChecked(
            getattr(self.core, "saved_auto_scan", True) if self.core else True
        )
        com_layout.addWidget(self.chk_auto_scan)

        self.chk_auto_select = QCheckBox("Tự động ưu tiên chọn cổng COM mới cắm", card_com)
        self.chk_auto_select.setChecked(
            getattr(self.core, "saved_auto_select_new", True) if self.core else True
        )
        com_layout.addWidget(self.chk_auto_select)

        self.chk_hide_bt = QCheckBox("Tự động lọc / ẩn cổng COM của Bluetooth", card_com)
        self.chk_hide_bt.setChecked(
            getattr(self.core, "saved_hide_bluetooth_ports", True) if self.core else True
        )
        self.chk_hide_bt.toggled.connect(self._populate_com_list)
        com_layout.addWidget(self.chk_hide_bt)

        sep = QFrame(card_com)
        sep.setFrameShape(QFrame.Shape.HLine)
        com_layout.addWidget(sep)

        hdr_com_row = QHBoxLayout()
        lbl_com_hint = QLabel("Tích chọn cổng COM cần ẨN / BỎ QUA:", card_com)
        lbl_com_hint.setStyleSheet("font-weight: 600;")
        hdr_com_row.addWidget(lbl_com_hint)
        hdr_com_row.addStretch(1)

        btn_refresh_ports = QPushButton("Làm mới danh sách", card_com)
        bind_themed_icon(btn_refresh_ports, "refresh")
        btn_refresh_ports.setFixedWidth(160)
        btn_refresh_ports.clicked.connect(self._populate_com_list)
        hdr_com_row.addWidget(btn_refresh_ports)
        com_layout.addLayout(hdr_com_row)

        self.com_list_widget = QWidget(card_com)
        self.com_list_layout = QGridLayout(self.com_list_widget)
        self.com_list_layout.setContentsMargins(0, 4, 0, 4)
        self.com_list_layout.setSpacing(6)
        com_layout.addWidget(self.com_list_widget)

        extra_layout = QVBoxLayout()
        extra_layout.setSpacing(4)
        extra_layout.addWidget(QLabel("Cổng COM ẩn khác (ngăn cách bằng dấu phẩy):", card_com))
        self.entry_extra_ignored = QLineEdit(card_com)
        self.entry_extra_ignored.setPlaceholderText("Ví dụ: COM3, COM4")
        extra_layout.addWidget(self.entry_extra_ignored)
        com_layout.addLayout(extra_layout)

        sep_adv = QFrame(card_com)
        sep_adv.setFrameShape(QFrame.Shape.HLine)
        com_layout.addWidget(sep_adv)

        lbl_adv = QLabel("Tùy chọn ẩn (Tab 5 - Sao lưu & Nhân bản):", card_com)
        lbl_adv.setStyleSheet("font-weight: 600;")
        com_layout.addWidget(lbl_adv)

        self.chk_tab5_led_blink = QCheckBox(
            "Bật nháy LED 5s nhận diện Board Gốc và nút 'Nháy LED' (chỉ khi ở Tab 5)",
            card_com,
        )
        self.chk_tab5_led_blink.setToolTip(
            "Khi bật: chọn Board Gốc trong Tab 5 sẽ tự gửi xung UART/TX 5 giây để làm chớp đèn nhận diện board, kèm nút 'Nháy LED'."
        )
        self.chk_tab5_led_blink.setChecked(
            bool(getattr(self.core, "tab5_led_blink_enabled", False)) if self.core else False
        )
        self.chk_tab5_led_blink.toggled.connect(self._on_tab5_led_blink_toggled)
        com_layout.addWidget(self.chk_tab5_led_blink)

        com_layout.addStretch(1)
        card_com.body_layout.addLayout(com_layout)
        right_col.addWidget(card_com, 1)

        gen_hbox.addLayout(right_col, 1)
        self.tabs.addTab(tab_general, "Cài đặt Chung và Cổng COM")

        # =====================================================================
        # SUB-TAB 2: PHÍM CHỨC NĂNG F1 - F15 (Toàn chiều cao, không cuộn lồng)
        # =====================================================================
        tab_fkeys = QWidget()
        f_vbox = QVBoxLayout(tab_fkeys)
        f_vbox.setContentsMargins(10, 10, 10, 10)
        f_vbox.setSpacing(8)

        card_f = Card(
            "Tùy chỉnh 15 Nút Chức Năng Nhanh (F1 - F15) trên Bảng Điều Khiển",
            icon_name="chip",
            parent=tab_fkeys,
        )
        f_layout = QVBoxLayout()
        f_layout.setContentsMargins(0, 0, 0, 0)
        f_layout.setSpacing(6)

        self.table_f = QTableWidget(15, 3, card_f)
        self.table_f.verticalHeader().setVisible(False)
        self.table_f.setHorizontalHeaderLabels(
            ["Phím", "Tên Hiển Thị Trên Nút (Label)", "Chuỗi Lệnh Gửi Qua Serial (Command)"]
        )
        self.table_f.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table_f.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_f.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        ctrl_cmds = getattr(self.core, "control_commands", None) if self.core else None
        ctrl_cfg = (
            ctrl_cmds
            if isinstance(ctrl_cmds, dict) and ctrl_cmds
            else (getattr(self.core, "control_config", CONTROL_CONFIG) if self.core else CONTROL_CONFIG)
        )
        ctrl_lbls = getattr(self.core, "control_labels", {}) if self.core else {}

        self._f_entries.clear()
        for idx in range(15):
            key_num = idx + 1
            item_key = QTableWidgetItem(f"F{key_num}")
            item_key.setFlags(item_key.flags() ^ Qt.ItemFlag.ItemIsEditable)
            item_key.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_f.setItem(idx, 0, item_key)

            cfg_val = ctrl_cfg.get(key_num, "")
            if isinstance(cfg_val, (tuple, list)):
                init_label = str(cfg_val[0]) if len(cfg_val) > 0 else f"F{key_num}"
                init_cmd = str(cfg_val[1]) if len(cfg_val) > 1 else ""
            else:
                default_pair = CONTROL_CONFIG.get(key_num, (f"F{key_num}", ""))
                init_label = str(ctrl_lbls.get(key_num, default_pair[0]))
                init_cmd = str(cfg_val)

            edit_label = QLineEdit(init_label)
            self.table_f.setCellWidget(idx, 1, edit_label)

            edit_cmd = QLineEdit(init_cmd)
            self.table_f.setCellWidget(idx, 2, edit_cmd)

            self._f_entries.append((edit_label, edit_cmd))

        f_layout.addWidget(self.table_f, 1)
        card_f.body_layout.addLayout(f_layout)
        f_vbox.addWidget(card_f, 1)

        self.tabs.addTab(tab_fkeys, "Phím chức năng F1 - F15")

        # =====================================================================
        # SUB-TAB 3: CẬP NHẬT PHẦN MỀM (Trực tiếp, không hỏi vị trí lưu)
        # =====================================================================
        tab_update = QWidget()
        upd_vbox = QVBoxLayout(tab_update)
        upd_vbox.setContentsMargins(10, 10, 10, 10)
        upd_vbox.setSpacing(8)

        card_update = Card(
            "Cập nhật Phần mềm & Nhật ký Phát hành",
            icon_name="arrow_download",
            parent=tab_update,
        )
        upd_card_layout = QVBoxLayout()
        upd_card_layout.setContentsMargins(0, 0, 0, 0)
        upd_card_layout.setSpacing(8)

        self.chk_auto_check_update = QCheckBox(
            "Tự động kiểm tra cập nhật khi mở ứng dụng", card_update
        )
        self.chk_auto_check_update.setChecked(
            bool(getattr(self.core, "saved_auto_check_updates", False)) if self.core else False
        )
        self.chk_auto_check_update.toggled.connect(self._on_auto_check_update_toggled)
        upd_card_layout.addWidget(self.chk_auto_check_update)

        self.lbl_update_status = QLabel(
            f"Phiên bản hiện tại: v{APP_VERSION}. Nhấn 'Kiểm Tra Cập Nhật' để kiểm tra bản phát hành mới từ GitHub.",
            card_update,
        )
        self.lbl_update_status.setProperty("role", "muted")
        self.lbl_update_status.setWordWrap(True)
        upd_card_layout.addWidget(self.lbl_update_status)

        upd_btn_row = QHBoxLayout()
        upd_btn_row.setSpacing(10)

        self.btn_chk_update = QPushButton("Kiểm Tra Cập Nhật", card_update)
        bind_themed_icon(self.btn_chk_update, "refresh")
        self.btn_chk_update.setMinimumWidth(160)
        self.btn_chk_update.clicked.connect(self._on_check_update)
        upd_btn_row.addWidget(self.btn_chk_update)

        self.btn_update_now = QPushButton("Cập nhật ngay", card_update)
        self.btn_update_now.setProperty("accent", "true")
        bind_themed_icon(self.btn_update_now, "arrow_download", role="on_accent")
        self.btn_update_now.setMinimumWidth(150)
        self.btn_update_now.clicked.connect(self._on_update_now_click)
        self.btn_update_now.setVisible(False)
        upd_btn_row.addWidget(self.btn_update_now)

        self.btn_cancel_update = QPushButton("Hủy tải", card_update)
        self.btn_cancel_update.setProperty("danger_outline", "true")
        bind_themed_icon(self.btn_cancel_update, "stop", role="danger")
        self.btn_cancel_update.setMinimumWidth(100)
        self.btn_cancel_update.clicked.connect(self._on_cancel_update_click)
        self.btn_cancel_update.setVisible(False)
        upd_btn_row.addWidget(self.btn_cancel_update)

        upd_btn_row.addStretch(1)
        upd_card_layout.addLayout(upd_btn_row)

        # Thanh tiến trình tải (chỉ hiện khi đang tải)
        self.update_progress_box = QWidget(card_update)
        upd_prog_layout = QVBoxLayout(self.update_progress_box)
        upd_prog_layout.setContentsMargins(0, 2, 0, 2)
        upd_prog_layout.setSpacing(6)

        self.lbl_download_status = QLabel("", self.update_progress_box)
        self.lbl_download_status.setProperty("role", "muted")
        self.lbl_download_status.setWordWrap(True)
        upd_prog_layout.addWidget(self.lbl_download_status)

        self.pb_update_download = QProgressBar(self.update_progress_box)
        self.pb_update_download.setRange(0, 100)
        self.pb_update_download.setValue(0)
        self.pb_update_download.setTextVisible(False)
        self.pb_update_download.setFixedHeight(10)
        upd_prog_layout.addWidget(self.pb_update_download)

        self.update_progress_box.setVisible(False)
        upd_card_layout.addWidget(self.update_progress_box)

        lbl_notes_hdr = QLabel("Chi tiết bản phát hành (Release Notes):", card_update)
        lbl_notes_hdr.setProperty("role", "section")
        upd_card_layout.addWidget(lbl_notes_hdr)

        self.txt_release_notes = QPlainTextEdit(card_update)
        self.txt_release_notes.setReadOnly(True)
        self.txt_release_notes.setProperty("role", "log")
        upd_card_layout.addWidget(self.txt_release_notes, 1)

        card_update.body_layout.addLayout(upd_card_layout)
        upd_vbox.addWidget(card_update, 1)

        self.tabs.addTab(tab_update, "Cập nhật Phần mềm")

        self._btn_chk_badge = UpdateDotBadge(self.btn_chk_update, margin_right=5, margin_top=4)
        self._btn_update_now_badge = UpdateDotBadge(self.btn_update_now, margin_right=5, margin_top=4)

        # =====================================================================
        # THANH HÀNH ĐỘNG DƯỚI CÙNG (Cố định, nút rộng chuẩn 155px)
        # =====================================================================
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 0, 0, 0)
        btn_bar.setSpacing(10)
        btn_bar.addStretch(1)

        btn_reset = QPushButton("Khôi phục mặc định", self)
        bind_themed_icon(btn_reset, "delete")
        btn_reset.setFixedWidth(160)
        btn_reset.clicked.connect(self._on_restore_defaults)
        btn_bar.addWidget(btn_reset)

        btn_save = QPushButton("Lưu Cài Đặt", self)
        btn_save.setProperty("accent", "true")
        bind_themed_icon(btn_save, "save", role="on_accent")
        btn_save.setFixedWidth(155)
        btn_save.clicked.connect(self._on_save_settings)
        btn_bar.addWidget(btn_save)

        root_layout.addLayout(btn_bar)

        self._populate_com_list()

    def _on_live_theme_changed(self, *args):
        if self._syncing_theme_controls:
            return
        preset = "engineering"
        is_dark = self.rb_dark.isChecked()
        ThemeManager.instance().apply_theme(preset, is_dark)
        if self.core is not None:
            self.core.saved_theme_preset = preset
            self.core.is_dark_mode = is_dark
            if hasattr(self.core, "disk_map") and hasattr(self.core.disk_map, "set_theme_mode"):
                self.core.disk_map.set_theme_mode(is_dark)
            if hasattr(self.core, "backup_disk_map") and hasattr(self.core.backup_disk_map, "set_theme_mode"):
                self.core.backup_disk_map.set_theme_mode(is_dark)

    def _on_external_theme_changed(self, tokens):
        self._syncing_theme_controls = True
        try:
            if tokens.is_dark:
                self.rb_dark.setChecked(True)
            else:
                self.rb_light.setChecked(True)
        finally:
            self._syncing_theme_controls = False

    def _on_apply_theme(self):
        self._on_live_theme_changed()

    def _on_tab5_led_blink_toggled(self, checked: bool):
        if self.core is not None:
            self.core.tab5_led_blink_enabled = bool(checked)
            if hasattr(self.core, "update_tab5_led_blink_visibility"):
                self.core.update_tab5_led_blink_visibility()

    def _populate_com_list(self):
        while self.com_list_layout.count():
            item = self.com_list_layout.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for child in list(self.com_list_widget.findChildren(QWidget)):
            child.hide()
            child.setParent(None)
            child.deleteLater()
        self._com_checkboxes.clear()

        hide_bt = self.chk_hide_bt.isChecked()
        ports_info = []
        ignored = [
            x.upper() for x in (getattr(self.core, "ignored_com_ports", []) if self.core else [])
        ]

        try:
            for p_obj in list_ports.comports():
                if hide_bt and is_bluetooth_port(p_obj):
                    continue
                ports_info.append((p_obj.device, p_obj.description))
        except Exception:
            pass

        if not ports_info:
            lbl_none = QLabel("Không phát hiện cổng COM nào đang kết nối.", self.com_list_widget)
            lbl_none.setProperty("role", "muted")
            self.com_list_layout.addWidget(lbl_none, 0, 0)
        else:
            for idx, (dev, desc) in enumerate(sorted(ports_info, key=lambda x: x[0])):
                cb = QCheckBox(f"{dev} ({desc})", self.com_list_widget)
                cb.setChecked(dev.upper() in ignored)
                self.com_list_layout.addWidget(cb, idx, 0)
                self._com_checkboxes[dev] = cb

    def _is_widget_alive(self) -> bool:
        if self.core is not None and getattr(self.core, "_closing", False):
            return False
        try:
            _ = self.isVisible()
            return True
        except RuntimeError:
            return False

    def _on_auto_check_update_toggled(self, checked: bool):
        if self._syncing_update_prefs:
            return
        enabled = bool(checked)
        if self.core is not None:
            self.core.saved_auto_check_updates = enabled
            if hasattr(self.core, "save_config"):
                self.core.save_config()
        if enabled:
            self.start_update_check(silent=True)

    def select_sub_tab(self, index: int):
        """Chuyển đổi sub-tab theo chỉ số index (0: Chung & COM, 1: Phím F, 2: Cập nhật)."""
        if hasattr(self, "tabs") and 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def _sync_update_badge_targets(self):
        active = bool(self._has_available_update)
        if hasattr(self, "tabs") and self.tabs.count() > 2:
            self.tabs.tabBar().setTabIcon(2, get_update_dot_icon(10) if active else QIcon())

        show_now = active and hasattr(self, "btn_update_now") and not self.btn_update_now.isHidden()
        show_chk = active and not show_now

        if hasattr(self, "_btn_update_now_badge"):
            self._btn_update_now_badge.set_active(show_now)
        if hasattr(self, "_btn_chk_badge"):
            self._btn_chk_badge.set_active(show_chk)

    def set_update_badge(self, active: bool):
        """Hiển thị hoặc ẩn dấu chấm đỏ hướng dẫn đến nút cập nhật trên tab Cài đặt."""
        self._has_available_update = bool(active)
        self._sync_update_badge_targets()

    def _notify_update_availability(self, has_update: bool, info: dict | None = None):
        if self.core is not None and hasattr(self.core, "set_update_available"):
            self.core.set_update_available(bool(has_update), info)
        else:
            self.set_update_badge(bool(has_update))

    def _on_check_update(self):
        self.start_update_check(silent=False)

    def start_update_check(self, silent: bool = False):
        """Kiểm tra bản cập nhật trực tiếp trong trang Cài đặt (không mở cửa sổ khác)."""
        if self._update_check_in_progress or self._update_download_in_progress:
            return

        self._update_check_in_progress = True
        if not silent:
            self.btn_chk_update.setEnabled(False)
            self.lbl_update_status.setText("Đang kết nối GitHub Releases API...")

        def worker():
            res = check_for_updates(current_version=APP_VERSION, repo=GITHUB_REPO)

            def apply_result():
                if not self._is_widget_alive():
                    return
                self._update_check_in_progress = False
                self.btn_chk_update.setEnabled(not self._update_download_in_progress)
                self._apply_update_check_result(res, silent=silent)

            self._dispatcher.post(apply_result)

        threading.Thread(target=worker, daemon=True).start()

    def _apply_update_check_result(self, res: dict, silent: bool = False):
        status = res.get("status")
        if status == "error" and silent:
            # Kiểm tra ngầm lúc khởi động/mở lại: offline hoặc lỗi API thì bỏ qua im lặng
            return

        self.latest_update_info.clear()
        self.latest_update_info.update(res)
        if self.core is not None:
            self.core.latest_update_info = dict(res)

        if status == "success":
            tag = res.get("latest_version", "")
            has_up = bool(res.get("has_update", False))
            rel_name = res.get("release_name", tag)
            pub_date = res.get("published_at", "")
            notes = res.get("release_notes", "")
            asset_name = res.get("asset_name", "")
            asset_size = res.get("asset_size", 0)
            download_url = res.get("download_url", "")

            size_str = f" ({asset_size / (1024 * 1024):.1f} MB)" if asset_size > 0 else ""
            lines = [
                f"[ BẢN PHÁT HÀNH: {rel_name} ({tag}) ]",
                f"Ngày phát hành: {pub_date}",
                f"File tải về: {asset_name if asset_name else 'Mã nguồn (.zip)'}{size_str}",
                "-" * 36,
                "Nội dung cập nhật & cải tiến:",
                notes if notes else "(Không có ghi chú phát hành).",
            ]
            self.txt_release_notes.setPlainText("\n".join(lines))

            if has_up:
                self.lbl_update_status.setText(
                    f"Có bản cập nhật mới: {tag} (Hiện tại: v{APP_VERSION})"
                )
                self.btn_update_now.setVisible(bool(download_url))
                self.btn_update_now.setEnabled(bool(download_url))
            else:
                self.lbl_update_status.setText(
                    f"Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION})."
                )
                self.btn_update_now.setVisible(False)

            self._notify_update_availability(has_up, res)
        elif status == "no_releases":
            if not silent:
                self.lbl_update_status.setText("Kho GitHub chưa tạo Release chính thức.")
                self.txt_release_notes.setPlainText(res.get("message", ""))
            self.btn_update_now.setVisible(False)
            self._notify_update_availability(False, res)
        else:
            self.lbl_update_status.setText("Lỗi khi kiểm tra cập nhật.")
            self.txt_release_notes.setPlainText(
                f"Lỗi: {res.get('message', 'Không xác định')}"
            )
            self.btn_update_now.setVisible(False)

    def _on_update_now_click(self):
        if self._update_download_in_progress:
            return
        download_url = self.latest_update_info.get("download_url", "")
        if not download_url:
            dlg.show_info("Thông báo", "Không tìm thấy đường dẫn tải file cập nhật trực tiếp.", self)
            return

        running_exe = get_running_executable_path()
        asset_name = self.latest_update_info.get("asset_name", "Esp32_manager_tool.exe")
        staged_path = get_staged_update_path(asset_name)

        if running_exe and os.name == "nt":
            # Tự động tải vào %TEMP% và thay thế file .exe đang chạy khi đóng (không mở File Dialog)
            self._start_update_download(download_url, staged_path, self_update_target=running_exe)
        else:
            # Chạy từ mã nguồn / Python: tải trực tiếp về file .exe cùng thư mục gốc mà không mở File Dialog
            target_path = os.path.join(os.path.abspath(os.getcwd()), asset_name)
            self._start_update_download(download_url, target_path, self_update_target=None)

    def _on_save_update_click(self):
        """Tương thích ngược: chuyển thẳng sang tải cập nhật một chạm, không hỏi vị trí lưu."""
        self._on_update_now_click()

    def _on_cancel_update_click(self):
        if self._update_download_in_progress:
            self._update_cancel_event.set()
            self.lbl_download_status.setText("Đang hủy quá trình tải...")
            self.btn_cancel_update.setEnabled(False)

    def _start_update_download(
        self,
        download_url: str,
        dest_path: str,
        self_update_target: str | None = None,
    ):
        self._update_cancel_event.clear()
        self._update_download_in_progress = True

        self.btn_chk_update.setEnabled(False)
        self.btn_update_now.setEnabled(False)
        self.btn_cancel_update.setVisible(True)
        self.btn_cancel_update.setEnabled(True)

        self.update_progress_box.setVisible(True)
        self.pb_update_download.setValue(0)
        self.lbl_download_status.setText("Đang kết nối tải bản cập nhật...")

        def worker():
            def progress_cb(percent, downloaded, total):
                if self._update_cancel_event.is_set():
                    return

                def update_progress():
                    if not self._is_widget_alive():
                        return
                    self.pb_update_download.setValue(int(round(percent)))
                    if total > 0:
                        self.lbl_download_status.setText(
                            f"Đang tải: {downloaded / (1024 * 1024):.2f} MB / {total / (1024 * 1024):.2f} MB ({percent:.1f}%)"
                        )
                    else:
                        self.lbl_download_status.setText(
                            f"Đang tải: {downloaded / (1024 * 1024):.2f} MB..."
                        )

                self._dispatcher.post(update_progress)

            success, msg = download_update_asset(
                download_url,
                dest_path,
                progress_callback=progress_cb,
                cancel_event=self._update_cancel_event,
            )

            def download_finished():
                if not self._is_widget_alive():
                    return
                self._update_download_in_progress = False
                self.btn_cancel_update.setVisible(False)
                self.btn_chk_update.setEnabled(True)
                self.btn_update_now.setEnabled(not self.btn_update_now.isHidden())

                if self._update_cancel_event.is_set():
                    self.pb_update_download.setValue(0)
                    self.lbl_download_status.setText("Đã hủy tải bản cập nhật.")
                    return

                if success:
                    self.pb_update_download.setValue(100)
                    if self_update_target:
                        self._handle_staged_self_update_ready(dest_path, self_update_target)
                    else:
                        self.lbl_download_status.setText(
                            f"Tải thành công: {os.path.basename(dest_path)}"
                        )
                        dlg.show_info(
                            "Tải hoàn tất",
                            f"Đã tải thành công bản cập nhật về máy:\n{dest_path}\n\n"
                            "Bạn có thể chạy file này để sử dụng phiên bản mới.",
                            parent=self,
                        )
                else:
                    self.lbl_download_status.setText("Lỗi khi tải bản cập nhật.")
                    dlg.show_error(
                        "Lỗi tải file",
                        f"Không thể tải bản cập nhật:\n{msg}",
                        parent=self,
                    )

            self._dispatcher.post(download_finished)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_staged_self_update_ready(self, staged_path: str, target_exe_path: str):
        self.lbl_download_status.setText("Đã tải xong bản cập nhật. Sẵn sàng cài đặt.")
        if self.core is not None and hasattr(self.core, "is_device_busy") and self.core.is_device_busy():
            dlg.show_warning(
                "Thiết bị đang bận",
                f"Đã tải xong bản cập nhật tạm tại:\n{staged_path}\n\n"
                "Thiết bị đang thực hiện tác vụ phần cứng. Vui lòng đợi tác vụ hoàn tất rồi bấm 'Cập nhật ngay' lại.",
                parent=self,
            )
            return

        if not dlg.ask_yes_no(
            "Sẵn sàng cập nhật",
            f"Đã tải xong bản cập nhật mới.\n\n"
            f"Ứng dụng sẽ đóng lại, thay thế file:\n{target_exe_path}\n"
            "và tự động khởi động lại phiên bản mới.\n\n"
            "Bạn có muốn cập nhật ngay bây giờ không?",
            parent=self,
        ):
            self.lbl_download_status.setText(f"Đã tải tạm bản cập nhật tại: {staged_path}")
            return

        ok, info_msg = launch_windows_self_updater(
            staged_exe_path=staged_path,
            target_exe_path=target_exe_path,
            current_pid=os.getpid(),
            relaunch=True,
        )
        if not ok:
            dlg.show_error("Lỗi tự cập nhật", info_msg, parent=self)
            return

        self._notify_update_availability(False, None)
        if self.core is not None and hasattr(self.core, "on_closing"):
            self.core.on_closing()
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.quit()

    def cancel_pending_update_tasks(self):
        """Hủy tiến trình tải cập nhật đang chạy khi đóng ứng dụng."""
        self._update_cancel_event.set()

    def load_from_core(self):
        """Đồng bộ lại toàn bộ ô nhập liệu trên trang Cài đặt từ trạng thái của cửa sổ chính."""
        if not self.core:
            return

        self._on_external_theme_changed(ThemeManager.instance().tokens)
        self.entry_default_ip.setText(str(getattr(self.core, "default_ip", "192.168.4.1")))
        self.entry_default_port.setText(str(getattr(self.core, "default_port", "100")))
        self.chk_auto_scan.setChecked(bool(getattr(self.core, "saved_auto_scan", True)))
        self.chk_auto_select.setChecked(bool(getattr(self.core, "saved_auto_select_new", True)))
        self.chk_hide_bt.setChecked(bool(getattr(self.core, "saved_hide_bluetooth_ports", True)))
        if hasattr(self, "chk_auto_check_update"):
            self._syncing_update_prefs = True
            try:
                self.chk_auto_check_update.setChecked(
                    bool(getattr(self.core, "saved_auto_check_updates", False))
                )
            finally:
                self._syncing_update_prefs = False
        if hasattr(self, "chk_tab5_led_blink"):
            self.chk_tab5_led_blink.setChecked(bool(getattr(self.core, "tab5_led_blink_enabled", False)))

        self._populate_com_list()
        attached_upper = {dev.upper() for dev in self._com_checkboxes}
        extra_ignored = [
            p for p in (getattr(self.core, "ignored_com_ports", []) or [])
            if p and p.strip().upper() not in attached_upper
        ]
        self.entry_extra_ignored.setText(", ".join(extra_ignored))

        ctrl_cmds = getattr(self.core, "control_commands", {}) or {}
        ctrl_lbls = getattr(self.core, "control_labels", {}) or {}
        for idx, (edit_label, edit_cmd) in enumerate(self._f_entries):
            key_num = idx + 1
            default_pair = CONTROL_CONFIG.get(key_num, (f"F{key_num}", ""))
            edit_label.setText(str(ctrl_lbls.get(key_num, default_pair[0])))
            edit_cmd.setText(str(ctrl_cmds.get(key_num, default_pair[1])))

    def _on_restore_defaults(self):
        if dlg.ask_yes_no(
            "Khôi phục mặc định",
            "Bạn có chắc chắn muốn đặt lại tất cả cài đặt về mặc định ban đầu?",
            parent=self,
        ):
            if self.core:
                if hasattr(self.core, "reset_settings_to_default"):
                    self.core.reset_settings_to_default()
                    self.load_from_core()
                    dlg.show_info("Hoàn tất", "Đã khôi phục cài đặt mặc định.", self)
                elif hasattr(self.core, "reset_config"):
                    self.core.reset_config(confirm=False)
                    self.load_from_core()
            else:
                dlg.show_info("Hoàn tất", "Đã khôi phục cài đặt mặc định.", self)

    def _on_save_settings(self):
        if not self.core:
            dlg.show_info("Lưu cài đặt", "Đã lưu cài đặt tạm thời trong phiên làm việc.", self)
            return

        self.core.saved_auto_scan = self.chk_auto_scan.isChecked()
        self.core.saved_auto_select_new = self.chk_auto_select.isChecked()
        self.core.saved_hide_bluetooth_ports = self.chk_hide_bt.isChecked()
        if hasattr(self, "chk_auto_check_update"):
            self.core.saved_auto_check_updates = bool(self.chk_auto_check_update.isChecked())

        if hasattr(self.core, "var_auto_scan"):
            self.core.var_auto_scan.set(self.core.saved_auto_scan)
        if hasattr(self.core, "var_auto_select_new"):
            self.core.var_auto_select_new.set(self.core.saved_auto_select_new)
        if hasattr(self.core, "var_hide_bt_ports"):
            self.core.var_hide_bt_ports.set(self.core.saved_hide_bluetooth_ports)

        ignored = []
        for dev, cb in self._com_checkboxes.items():
            if cb.isChecked():
                ignored.append(dev)
        extra = [x.strip() for x in self.entry_extra_ignored.text().split(",") if x.strip()]
        for x in extra:
            if x.upper() not in [i.upper() for i in ignored]:
                ignored.append(x)
        self.core.ignored_com_ports = ignored

        self.core.default_ip = self.entry_default_ip.text().strip() or "192.168.4.1"
        self.core.default_port = self.entry_default_port.text().strip() or "100"

        if hasattr(self.core, "ip_entry"):
            self.core.ip_entry.setText(self.core.default_ip)
        if hasattr(self.core, "port_entry"):
            self.core.port_entry.setText(self.core.default_port)

        new_labels = {}
        new_cmds = {}
        f_buttons = getattr(self.core, "f_buttons", []) or []
        for idx, (lbl_edit, cmd_edit) in enumerate(self._f_entries):
            num = idx + 1
            lbl_val = lbl_edit.text().strip() or f"F{num}"
            cmd_val = cmd_edit.text().strip()
            new_labels[num] = lbl_val
            new_cmds[num] = cmd_val
            if idx < len(f_buttons):
                f_buttons[idx].setText(lbl_val)
        self.core.control_labels = new_labels
        self.core.control_commands = new_cmds
        self.core.control_config = new_cmds

        self.core.saved_theme_preset = "engineering"
        self.core.is_dark_mode = self.rb_dark.isChecked()
        if hasattr(self, "chk_tab5_led_blink"):
            self.core.tab5_led_blink_enabled = bool(self.chk_tab5_led_blink.isChecked())
        if hasattr(self.core, "update_tab5_led_blink_visibility"):
            self.core.update_tab5_led_blink_visibility()

        if hasattr(self.core, "refresh_ports_dropdown"):
            self.core.refresh_ports_dropdown()

        if hasattr(self.core, "save_user_settings"):
            self.core.save_user_settings()
        elif hasattr(self.core, "save_config"):
            self.core.save_config()

        dlg.show_info("Thành công", "Đã lưu toàn bộ cài đặt hệ thống thành công.", self)
