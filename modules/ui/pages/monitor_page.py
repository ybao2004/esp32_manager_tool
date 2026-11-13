# -*- coding: utf-8 -*-
"""
Trang Serial Monitor & Log (MonitorPage - v1.6).
- Chia 2 sub-tab trong QTabWidget:
  + Serial: Terminal thời gian thực, thanh công cụ, dòng nhập lệnh và Bảng điều khiển Wi-Fi / F1-F15.
  + Log: Nhật ký hoạt động tập trung từ Tab 1, 3, 4, 5 kèm tiền tố [Tên Tab], bộ lọc, timestamp, Lưu & Xóa.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QComboBox, QCheckBox, QFrame, QTabWidget
)
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtGui import QKeyEvent
from modules.config import CONTROL_CONFIG
from modules.ui.widgets.card import Card
from modules.ui.widgets.flow_layout import FlowLayout, make_group
from modules.ui.widgets.log_view import LogView
from modules.ui.icons import get_icon, bind_themed_icon


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

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        if key == "text":
            self.setText(str(value))
        elif key == "state":
            self.setEnabled(value != "disabled")


class _EntryCompat(QLineEdit):
    def get(self, *args) -> str:
        return self.text()

    def delete(self, first=0, last=None):
        self.clear()

    def insert_text(self, index, val: str):
        self.setText(str(val))

    def insert(self, index, val: str):
        self.setText(str(val))

    def config(self, **kwargs):
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")
        if "show" in kwargs:
            show_val = kwargs["show"]
            self.setEchoMode(
                QLineEdit.EchoMode.Password if show_val == "*" else QLineEdit.EchoMode.Normal
            )

    configure = config

    def cget(self, prop: str):
        if prop == "state":
            return "normal" if self.isEnabled() else "disabled"
        return ""

    def winfo_exists(self) -> bool:
        return True

    def bind(self, event: str, callback):
        pass


class _ComboCompat(QComboBox):
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

    def bind(self, event: str, callback):
        if "Selected" in event:
            self.currentTextChanged.connect(lambda txt: callback(None))

    def config(self, **kwargs):
        if "values" in kwargs:
            curr = self.currentText()
            self.blockSignals(True)
            self.clear()
            self.addItems([str(v) for v in kwargs["values"]])
            self.setCurrentText(curr)
            self.blockSignals(False)
        if "state" in kwargs:
            self.setEnabled(kwargs["state"] != "disabled")

    configure = config

    def winfo_exists(self) -> bool:
        return True

    def __setitem__(self, key, value):
        if key == "values":
            self.config(values=value)
        elif key == "state":
            self.config(state=value)

    def __getitem__(self, key):
        if key == "values":
            return [self.itemText(i) for i in range(self.count())]
        elif key == "state":
            return "normal" if self.isEnabled() else "disabled"
        return ""


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

    def cget(self, prop: str) -> str:
        if prop == "text":
            return self.text()
        return ""

    def __getitem__(self, key: str) -> str:
        return self.cget(key)

    def __setitem__(self, key: str, val):
        if key == "text":
            self.setText(str(val))

    def config(self, **kwargs):
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))
        if "fg" in kwargs or "foreground" in kwargs:
            color = kwargs.get("fg") or kwargs.get("foreground")
            if color:
                self.setStyleSheet(f"color: {color}; font-weight: 600;")

    configure = config


class MonitorPage(QWidget):
    """Trang Serial Monitor & Bảng Điều Khiển IoT (v1.6)"""

    def __init__(
        self,
        default_ip: str = "192.168.4.1",
        default_port: str = "100",
        control_labels: dict | None = None,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self.default_ip = default_ip
        self.default_port = default_port
        self.control_labels = control_labels or {}
        self.cmd_history: list[str] = []
        self.cmd_history_idx = -1

        self._build_ui()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.sub_tabs = QTabWidget(self)
        self.sub_tabs.setObjectName("monitorSubTabs")
        outer_layout.addWidget(self.sub_tabs, 1)

        # =====================================================================
        # SUB-TAB 1: SERIAL MONITOR & BẢNG ĐIỀU KHIỂN IOT
        # =====================================================================
        self.serial_tab_widget = QWidget(self.sub_tabs)
        root_layout = QHBoxLayout(self.serial_tab_widget)
        root_layout.setContentsMargins(4, 6, 4, 4)
        root_layout.setSpacing(6)

        # --- CỘT TRÁI: Card Terminal & Thanh nhập lệnh đồng bộ chiều cao với cột phải ---
        left_card = Card("Giao tiếp Serial Monitor & Gửi Lệnh", icon_name="monitor", parent=self.serial_tab_widget)
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        # Hàng 1: Thanh công cụ phía trên Terminal (tự xuống dòng khi hẹp)
        top_bar = FlowLayout(h_spacing=8, v_spacing=6)

        self.cb_autoscroll = QCheckBox("Tự động cuộn", left_card)
        self.var_autoscroll = _TkVarCompat(self.cb_autoscroll, default=True)
        top_bar.addWidget(self.cb_autoscroll)

        self.cb_timestamp = QCheckBox("Thêm dấu thời gian", left_card)
        self.var_timestamp = _TkVarCompat(self.cb_timestamp, default=False)
        top_bar.addWidget(self.cb_timestamp)

        top_bar.addStretch(1)

        self.clear_monitor_btn = _ButtonCompat("Xóa màn hình", left_card)
        bind_themed_icon(self.clear_monitor_btn, "delete")
        top_bar.addWidget(self.clear_monitor_btn)

        self.reset_btn = _ButtonCompat("Reset ESP", left_card)
        bind_themed_icon(self.reset_btn, "refresh")
        top_bar.addWidget(self.reset_btn)

        self.btn_toggle_right_panel = QPushButton("Ẩn Bảng Điều Khiển", left_card)
        self.btn_toggle_right_panel.setCheckable(True)
        self.btn_toggle_right_panel.setChecked(True)
        self.btn_toggle_right_panel.setMinimumWidth(136)
        self.btn_toggle_right_panel.toggled.connect(self._on_toggle_right_panel)
        top_bar.addWidget(self.btn_toggle_right_panel)

        left_layout.addLayout(top_bar)

        # Hàng 2: Khung Terminal hiển thị dữ liệu Serial (stretch=1)
        self.monitor_txt = LogView(left_card)
        left_layout.addWidget(self.monitor_txt, 1)

        # Hàng 3: Dòng nhập lệnh 100% chiều rộng cột trái
        cmd_bar = QHBoxLayout()
        cmd_bar.setContentsMargins(0, 0, 0, 0)
        cmd_bar.setSpacing(8)

        self.serial_input = _EntryCompat(left_card)
        self.serial_input.setPlaceholderText(
            "Nhập lệnh Serial gửi tới chip ESP (Nhấn Enter để gửi, Up/Down xem lịch sử)..."
        )
        self.serial_input.installEventFilter(self)
        cmd_bar.addWidget(self.serial_input, 1)

        self.cb_crlf = QCheckBox("Thêm \\r\\n", left_card)
        self.var_crlf = _TkVarCompat(self.cb_crlf, default=True)
        cmd_bar.addWidget(self.cb_crlf)

        self.send_btn = _ButtonCompat("Gửi", left_card)
        self.send_btn.setProperty("accent", "true")
        bind_themed_icon(self.send_btn, "send", role="on_accent")
        self.send_btn.setMinimumWidth(85)
        cmd_bar.addWidget(self.send_btn)

        left_layout.addLayout(cmd_bar)

        # Giữ req_status_lbl ẩn để tương thích mixin/test nhưng không lặp chữ "Sẵn sàng." phía trên thanh trạng thái
        self.req_status_lbl = _LabelCompat("Sẵn sàng.", left_card)
        self.req_status_lbl.setProperty("role", "muted")
        self.req_status_lbl.hide()

        left_card.body_layout.addLayout(left_layout, 1)
        root_layout.addWidget(left_card, 1)

        # --- CỘT PHẢI: Bảng Mạng Wi-Fi & 15 Phím chức năng F1-F15 (rộng cố định 320px) ---
        self.right_panel = QWidget(self.serial_tab_widget)
        self.right_panel.setFixedWidth(320)
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        # 1. Card Cấu hình Mạng (Wi-Fi & Server)
        card_wifi = Card("Cấu hình Mạng (Wi-Fi & Server)", icon_name="wifi", parent=self.right_panel)
        w_grid = QGridLayout()
        w_grid.setContentsMargins(0, 0, 0, 0)
        w_grid.setHorizontalSpacing(6)
        w_grid.setVerticalSpacing(6)

        w_grid.addWidget(QLabel("WiFi:", card_wifi), 0, 0)
        self.wifi_cb = _ComboCompat(card_wifi)
        self.wifi_cb.setEditable(True)
        w_grid.addWidget(self.wifi_cb, 0, 1, 1, 2)

        w_grid.addWidget(QLabel("Mật khẩu:", card_wifi), 1, 0)
        self.wifi_pass_entry = _EntryCompat(card_wifi)
        self.wifi_pass_entry.setEchoMode(QLineEdit.EchoMode.Password)
        w_grid.addWidget(self.wifi_pass_entry, 1, 1)

        self.cb_show_pwd = QCheckBox("Hiện", card_wifi)
        self.var_show_pwd = _TkVarCompat(self.cb_show_pwd, default=False)
        self.cb_show_pwd.toggled.connect(self._toggle_pwd)
        w_grid.addWidget(self.cb_show_pwd, 1, 2)

        w_grid.addWidget(QLabel("IP Server:", card_wifi), 2, 0)
        self.ip_entry = _EntryCompat(card_wifi)
        self.ip_entry.setText(self.default_ip)
        w_grid.addWidget(self.ip_entry, 2, 1)

        self.cb_auto_server = QCheckBox("Tự nối", card_wifi)
        self.var_auto_connect_server = _TkVarCompat(self.cb_auto_server, default=True)
        w_grid.addWidget(self.cb_auto_server, 2, 2)

        w_grid.addWidget(QLabel("Cổng TCP:", card_wifi), 3, 0)
        self.port_entry = _EntryCompat(card_wifi)
        self.port_entry.setText(self.default_port)
        w_grid.addWidget(self.port_entry, 3, 1, 1, 2)

        w_grid.setColumnStretch(1, 1)
        card_wifi.body_layout.addLayout(w_grid)

        # Hàng 3 nút Mạng vừa khít 310px
        net_btn_box = QHBoxLayout()
        net_btn_box.setContentsMargins(0, 2, 0, 0)
        net_btn_box.setSpacing(4)
        self.btn_scan_wifi = _ButtonCompat("Quét WiFi", card_wifi)
        self.btn_connect_wifi = _ButtonCompat("Kết nối WiFi", card_wifi)
        self.btn_connect_server = _ButtonCompat("Nối Server", card_wifi)
        for b in (self.btn_scan_wifi, self.btn_connect_wifi, self.btn_connect_server):
            b.setStyleSheet("padding: 4px 6px; font-size: 8.5pt;")
            net_btn_box.addWidget(b, 1)
        card_wifi.body_layout.addLayout(net_btn_box)

        self.wifi_status_lbl = _LabelCompat("Chưa kết nối", card_wifi)
        self.wifi_status_lbl.setProperty("role", "muted")
        card_wifi.body_layout.addWidget(self.wifi_status_lbl)

        right_layout.addWidget(card_wifi)

        # 2. Card Bảng Điều Khiển (F1 - F15) lưới 5x3 cân đối
        card_ctrl = Card("Bảng Điều Khiển (F1 - F15)", icon_name="chip", parent=self.right_panel)
        f_grid = QGridLayout()
        f_grid.setContentsMargins(0, 0, 0, 0)
        f_grid.setSpacing(5)
        self.f_buttons = []
        for index, i in enumerate(sorted(CONTROL_CONFIG)):
            btn_text = self.control_labels.get(i, f"F{i}")
            btn = _ButtonCompat(btn_text, card_ctrl)
            btn.setMinimumHeight(28)
            btn.setStyleSheet("padding: 3px 4px; font-size: 8.5pt;")
            f_grid.addWidget(btn, index // 3, index % 3)
            self.f_buttons.append(btn)
        for col in range(3):
            f_grid.setColumnStretch(col, 1)
        card_ctrl.body_layout.addLayout(f_grid)
        right_layout.addWidget(card_ctrl)

        right_layout.addStretch(1)
        root_layout.addWidget(self.right_panel, 0)

        self.sub_tabs.addTab(self.serial_tab_widget, "Serial")

        # =====================================================================
        # SUB-TAB 2: NHẬT KÝ HOẠT ĐỘNG TỔNG HỢP (TAB 1, 3, 4, 5)
        # =====================================================================
        self.log_tab_widget = QWidget(self.sub_tabs)
        log_root_layout = QVBoxLayout(self.log_tab_widget)
        log_root_layout.setContentsMargins(4, 6, 4, 4)
        log_root_layout.setSpacing(6)

        log_card = Card("Nhật Ký Hoạt Động Tổng Hợp (Tab 1, 3, 4, 5)", icon_name="info", parent=self.log_tab_widget)
        log_inner = QVBoxLayout()
        log_inner.setContentsMargins(0, 0, 0, 0)
        log_inner.setSpacing(6)

        log_toolbar = FlowLayout(h_spacing=8, v_spacing=6)

        lbl_source = QLabel("Nguồn tab:", log_card)
        self.cb_log_source_filter = _ComboCompat(log_card)
        self.cb_log_source_filter.addItems([
            "Tất cả",
            "Kiểm tra Chip",
            "Nạp Firmware",
            "Phân vùng",
            "Sao lưu & Chép",
        ])
        self.cb_log_source_filter.setFixedWidth(156)
        self.cb_log_source_filter.setFixedHeight(30)
        log_toolbar.addWidget(make_group(log_card, lbl_source, self.cb_log_source_filter))

        self.cb_log_autoscroll = QCheckBox("Tự động cuộn", log_card)
        self.var_log_autoscroll = _TkVarCompat(self.cb_log_autoscroll, default=True)
        log_toolbar.addWidget(self.cb_log_autoscroll)

        self.cb_log_timestamp = QCheckBox("Thêm dấu thời gian", log_card)
        self.var_log_timestamp = _TkVarCompat(self.cb_log_timestamp, default=True)
        log_toolbar.addWidget(self.cb_log_timestamp)

        log_toolbar.addStretch(1)

        self.btn_save_central_log = _ButtonCompat("Lưu Log (.txt)", log_card)
        bind_themed_icon(self.btn_save_central_log, "save")
        log_toolbar.addWidget(self.btn_save_central_log)

        self.btn_clear_central_log = _ButtonCompat("Xóa Log", log_card)
        bind_themed_icon(self.btn_clear_central_log, "delete")
        log_toolbar.addWidget(self.btn_clear_central_log)

        log_inner.addLayout(log_toolbar)

        self.central_log_txt = LogView(log_card)
        self.central_log_txt.timestamps = False
        self.central_log_txt.autoscroll = True
        log_inner.addWidget(self.central_log_txt, 1)

        log_card.body_layout.addLayout(log_inner, 1)
        log_root_layout.addWidget(log_card, 1)

        self.sub_tabs.addTab(self.log_tab_widget, "Log")

    def _on_toggle_right_panel(self, visible: bool):
        self.right_panel.setVisible(visible)
        self.btn_toggle_right_panel.setText(
            "Ẩn Bảng Điều Khiển" if visible else "Hiện Bảng Điều Khiển"
        )

    def _toggle_pwd(self, checked: bool):
        self.wifi_pass_entry.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def eventFilter(self, obj, event):
        if obj == self.serial_input and event.type() == QEvent.Type.KeyPress:
            key_event: QKeyEvent = event
            if key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.send_btn.click()
                return True
            elif key_event.key() == Qt.Key.Key_Up:
                if self.cmd_history and self.cmd_history_idx < len(self.cmd_history) - 1:
                    self.cmd_history_idx += 1
                    cmd = self.cmd_history[-(self.cmd_history_idx + 1)]
                    self.serial_input.setText(cmd)
                return True
            elif key_event.key() == Qt.Key.Key_Down:
                if self.cmd_history_idx > 0:
                    self.cmd_history_idx -= 1
                    cmd = self.cmd_history[-(self.cmd_history_idx + 1)]
                    self.serial_input.setText(cmd)
                elif self.cmd_history_idx == 0:
                    self.cmd_history_idx = -1
                    self.serial_input.clear()
                return True
        return super().eventFilter(obj, event)

    def push_command_history(self, cmd: str):
        if cmd and (not self.cmd_history or self.cmd_history[-1] != cmd):
            self.cmd_history.append(cmd)
        self.cmd_history_idx = -1
