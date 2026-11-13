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
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QRadioButton, QTabWidget
)
from PyQt6.QtCore import Qt
from serial.tools import list_ports
from modules.config import CONTROL_CONFIG, APP_VERSION
from modules.serial_util import is_bluetooth_port
from modules.ui.theme.manager import ThemeManager
from modules.ui.widgets.card import Card
from modules.ui.icons import get_icon, bind_themed_icon
from modules.ui import dialogs_service as dlg


class SettingsPage(QWidget):
    """Trang Cài Đặt Hệ Thống ESP32 Manager Tool (v1.6)"""

    def __init__(self, core_app=None, parent: QWidget = None):
        super().__init__(parent)
        self.core = core_app
        self._com_checkboxes: dict[str, QCheckBox] = {}
        self._f_entries: list[tuple[QLineEdit, QLineEdit]] = []
        self._syncing_theme_controls = False
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

        # --- CỘT TRÁI: Giao diện & Chủ đề + Cấu hình Server + Bản quyền ---
        left_col = QVBoxLayout()
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

        # 3. Card Thông tin Phiên bản & Bản quyền
        card_about = Card("Thông tin Phiên bản & Bản quyền", icon_name="info", parent=tab_general)
        abt_layout = QVBoxLayout()
        abt_layout.setContentsMargins(0, 0, 0, 0)
        abt_layout.setSpacing(5)

        lbl_app = QLabel(f"ESP32 Manager Tool - Phiên bản v{APP_VERSION}", card_about)
        lbl_app.setStyleSheet("font-size: 10.5pt; font-weight: 700;")
        abt_layout.addWidget(lbl_app)

        abt_layout.addWidget(QLabel("Tác giả: @ybao04", card_about))
        abt_layout.addWidget(QLabel("Giấy phép: GNU General Public License v3.0 (GPL-3.0)", card_about))
        abt_layout.addWidget(
            QLabel("Mã nguồn: https://github.com/ybao2004/esp32_manager_tool.git", card_about)
        )

        abt_btn_row = QHBoxLayout()
        self.btn_chk_update = QPushButton("Kiểm Tra Cập Nhật", card_about)
        bind_themed_icon(self.btn_chk_update, "refresh")
        self.btn_chk_update.setFixedWidth(165)
        self.btn_chk_update.clicked.connect(self._on_check_update)
        abt_btn_row.addWidget(self.btn_chk_update)
        abt_btn_row.addStretch(1)
        abt_layout.addLayout(abt_btn_row)

        card_about.body_layout.addLayout(abt_layout)
        left_col.addWidget(card_about)
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
        btn_save.setIcon(get_icon("save", color="#ffffff"))
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

    def _on_check_update(self):
        if self.core and hasattr(self.core, "open_update_dialog"):
            self.core.open_update_dialog()
        else:
            dlg.show_info(
                "Cập nhật", f"Phiên bản hiện tại là v{APP_VERSION} mới nhất.", self
            )

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
