# -*- coding: utf-8 -*-
"""
Cửa sổ chính của ứng dụng ESP32 Manager Tool (MainWindow) v1.8.
Kiến trúc thuần PyQt6 với Sidebar điều hướng thu gọn, Thanh kết nối toàn cục ConnectionBar,
QStackedWidget chứa 6 trang giao diện Kỹ thuật (Sáng/Tối) và hệ thống quản lý tiến trình thống nhất.
"""
import sys
import os
import json
import re
import threading
import codecs
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QProgressBar, QMenuBar, QMenu, QStatusBar, QApplication,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon, QShortcut, QCloseEvent, QKeySequence

from modules.config import (
    CONFIG_FILE, DEFAULT_GEOMETRY, CONTROL_CONFIG,
    COMMON_BAUDS, APP_NAME, APP_VERSION,
    Tu_dong_cuon, Them_dau_thoi_gian
)
from modules.ui.dispatch import UiDispatcher
from modules.ui.theme.tokens import ThemeTokens
from modules.ui.theme.manager import ThemeManager
from modules.ui.icons import get_icon
from modules.ui.widgets.sidebar import Sidebar
from modules.ui.widgets.connection_bar import ConnectionBar
from modules.ui.pages.inspector_page import InspectorPage
from modules.ui.pages.monitor_page import MonitorPage
from modules.ui.pages.flasher_page import FlasherPage
from modules.ui.pages.partition_page import PartitionPage
from modules.ui.pages.backup_page import BackupPage
from modules.ui.pages.settings_page import SettingsPage
from modules.ui import dialogs_service as dlg

# Import mixins
from modules.tabs.tab_inspector import InspectorTabMixin
from modules.tabs.tab_monitor import MonitorTabMixin
from modules.tabs.tab_flasher import FlasherTabMixin
from modules.tabs.tab_partition import PartitionTabMixin
from modules.tabs.tab_backup_clone import BackupCloneTabMixin
from modules.ui.dialogs.about_update_dialogs import AboutUpdateMixin
from modules.ui.models import BooleanVar as _BooleanVar


class _NotebookCompat:
    """Đối tượng giả lập Tkinter Notebook cho phép chọn tab mượt mà."""

    _TAB_NAMES = [
        'Kiểm tra Phần cứng',
        'Serial Monitor & Điều khiển',
        'Nạp Flash Firmware (.bin)',
        'Phân vùng Bộ nhớ (Partition Wizard)',
        'Sao lưu & Nhân bản (Backup / Clone)',
        'Cài đặt Hệ thống'
    ]

    def __init__(self, sidebar: Sidebar, stack: QStackedWidget, tab_pages: list):
        self._sidebar = sidebar
        self._stack = stack
        self._tabs = tab_pages

    @property
    def sidebar_frame(self):
        return self._sidebar

    @property
    def btn_toggle_sidebar(self):
        return self._sidebar.btn_toggle_sidebar

    @property
    def stack(self):
        return self._stack

    @property
    def is_sidebar_collapsed(self):
        return self._sidebar._is_collapsed

    def toggle_sidebar(self):
        self._sidebar.toggle_collapse()

    def select(self, target):
        if isinstance(target, int):
            self._sidebar.select(target)
            self._stack.setCurrentIndex(target)
        elif target in self._tabs:
            idx = self._tabs.index(target)
            self._sidebar.select(idx)
            self._stack.setCurrentIndex(idx)

    def tabs(self):
        return self._tabs

    def index(self, target):
        if target == "end":
            return 5
        if isinstance(target, int):
            return target
        if target in self._tabs:
            return self._tabs.index(target)
        return -1

    def tab(self, i, option=None):
        idx = int(i)
        name = self._TAB_NAMES[idx] if idx < len(self._TAB_NAMES) else ""
        if option == 'text':
            return name
        return {"text": name}


class _SubMenuCompat:
    def __init__(self, labels: list[str], commands: dict = None):
        self._items = labels
        self._commands = commands or {}

    def index(self, which):
        if which == "end":
            return len(self._items) - 1
        return int(which)

    def entrycget(self, idx, opt):
        if opt == "label":
            return self._items[idx]
        if opt == "command":
            return self._commands.get(self._items[idx], lambda: None)
        return ""

    def type(self, idx):
        if idx < len(self._items) and self._items[idx] in ("---", "separator"):
            return "separator"
        return "command"


class _MainMenuCompat:
    def __init__(self, main_win):
        self._win = main_win
        self._file_menu = _SubMenuCompat(
            ["Tạo mới", "Mở...", "Nhập...", "Lưu", "Lưu như...", "---", "Thoát"],
            {"Thoát": main_win.on_closing}
        )
        self._tools_menu = _SubMenuCompat(
            ["Kiểm tra chip ESP", "Reset ESP", "Xóa toàn bộ Flash (Erase Chip)", "Kiểm tra cập nhật phần mềm..."]
        )
        self._theme_menu = _SubMenuCompat(
            ["Giao diện Tối (Dark)", "Giao diện Sáng (Light)"]
        )
        self._settings_menu = _SubMenuCompat(["Cài đặt hệ thống"])
        self._about_menu = _SubMenuCompat(["Giới thiệu"])

        self._top_items = [
            ("Tệp", self._file_menu, "file_menu"),
            ("Công cụ", self._tools_menu, "tools_menu"),
            ("Theme", self._theme_menu, "theme_menu"),
            ("Cài đặt", self._settings_menu, "settings_menu"),
            ("Giới thiệu", self._about_menu, "about_menu"),
        ]
        self._widget_map = {
            "file_menu": self._file_menu,
            "tools_menu": self._tools_menu,
            "theme_menu": self._theme_menu,
            "settings_menu": self._settings_menu,
            "about_menu": self._about_menu,
        }

    def index(self, which):
        if which == "end":
            return len(self._top_items) - 1
        return int(which)

    def entrycget(self, idx, opt):
        if opt == "label":
            return self._top_items[idx][0]
        elif opt == "menu":
            return self._top_items[idx][2]
        return ""

    def type(self, idx):
        return "cascade"

    def nametowidget(self, name):
        return self._widget_map.get(str(name), self._file_menu)


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


class _StatusLabelCompat(QLabel):
    def winfo_exists(self) -> bool:
        return True

    def cget(self, key):
        if key == "text":
            return self.text()
        return ""

    def config(self, **kwargs):
        if "text" in kwargs:
            self.setText(str(kwargs["text"]))

    configure = config

    def __getitem__(self, key):
        return self.cget(key)

    def __setitem__(self, key, value):
        if key == "text":
            self.setText(str(value))


class MainWindow(
    QMainWindow,
    InspectorTabMixin,
    MonitorTabMixin,
    FlasherTabMixin,
    PartitionTabMixin,
    BackupCloneTabMixin,
    AboutUpdateMixin
):
    """Cửa sổ chính ứng dụng ESP32 Manager Tool v1.8"""

    def __init__(self, root=None, auto_start: bool = True, parent: Optional[QWidget] = None):
        QMainWindow.__init__(self, parent)
        self.root = root if root is not None else self
        self._closing = False
        self._resources_cleaned = False
        self._native_icon_applied = False
        self._native_hicons = []
        self._scan_thread = None
        self._auto_start = False if root is not None else auto_start

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")

        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            min_w = min(960, max(800, int(avail.width() * 0.80)))
            min_h = min(580, max(520, int(avail.height() * 0.80)))
            self.setMinimumSize(min_w, min_h)
        else:
            self.setMinimumSize(960, 580)

        # Thiết lập Icon cho cửa sổ & QApplication (hỗ trợ cả chạy source & PyInstaller _MEIPASS)
        from modules.app_core import resolve_app_icon_path
        self._resolved_icon_path = resolve_app_icon_path()
        if self._resolved_icon_path:
            app_icon = QIcon(self._resolved_icon_path)
            self.setWindowIcon(app_icon)
            qapp = QApplication.instance()
            if qapp is not None:
                qapp.setWindowIcon(app_icon)

        # Khởi tạo Dispatcher chuyển luồng thread-safe (bảo đảm nhận lệnh mới kể cả sau khi đóng cửa sổ test trước đó)
        self._dispatcher = UiDispatcher.instance()
        if hasattr(self._dispatcher, "reset"):
            self._dispatcher.reset()

        # Luồng & Biến điều khiển phần cứng
        self.stop_scan = threading.Event()
        self.is_detecting = threading.Event()
        self.stop_serial_thread = threading.Event()
        self.is_flashing = threading.Event()

        self.serial_connection = None
        self.decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        self.is_new_line = True
        self.feedback_buffer = ""

        self.scanned_networks = []
        self.is_wifi_connected = False
        self.is_server_connected = False
        self.current_status_level = "info"
        self.main_menu = _MainMenuCompat(self)

        # Cấu hình lưu trữ
        self.is_dark_mode = False
        self.saved_theme_preset = "engineering"
        self.tab5_led_blink_enabled = False
        self.saved_wifi_credentials = {}
        self.saved_geometry = DEFAULT_GEOMETRY
        self.saved_is_zoomed = False
        self.saved_com_port = ""
        self.saved_baudrate = "Tự động"
        self.ignored_com_ports = []
        self.saved_hide_bluetooth_ports = True
        self.saved_auto_scan = True
        self.saved_auto_select_new = True
        self._previous_ports = set()

        self.default_ip = "192.168.4.1"
        self.default_port = "100"
        self.control_labels = {i: CONTROL_CONFIG.get(i, (f"F{i}", f"CMD_{i}"))[0] for i in sorted(CONTROL_CONFIG)}
        self.control_commands = {i: CONTROL_CONFIG.get(i, (f"F{i}", f"CMD_{i}"))[1] for i in sorted(CONTROL_CONFIG)}

        self.saved_flash_rows = []
        self.saved_flash_baud = "460800"
        self.saved_flash_chip = "auto"
        self.saved_flash_erase = False

        # Đọc cấu hình từ file
        self.load_config()

        # Áp dụng Theme theo cấu hình
        ThemeManager.instance().apply_theme(self.saved_theme_preset, self.is_dark_mode)

        # Dựng giao diện Qt
        self._build_ui()

        # Dựng Menu Bar
        self._create_main_menu()

        # Phục hồi kích thước cửa sổ tương thích mọi độ phân giải và mặc định mở toàn màn hình
        screen = QApplication.primaryScreen()
        if screen is not None:
            avail = screen.availableGeometry()
            def_w = min(1366, max(self.minimumWidth(), int(avail.width() * 0.90)))
            def_h = min(820, max(self.minimumHeight(), int(avail.height() * 0.88)))
            self.resize(def_w, def_h)
            frame_geo = self.frameGeometry()
            frame_geo.moveCenter(avail.center())
            self.move(frame_geo.topLeft())
        else:
            self.resize(1366, 820)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

        # Phím tắt toàn cục
        shortcut_side = QShortcut(QKeySequence("Ctrl+B"), self)
        shortcut_side.activated.connect(self.sidebar.toggle_collapse)

        # Khởi chạy luồng nền quét COM
        if self._auto_start:
            QTimer.singleShot(150, self.start_background_tasks)

    def _build_ui(self):
        central_widget = QWidget(self)
        central_layout = QHBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # 1. Sidebar bên trái
        self.sidebar = Sidebar(central_widget)
        central_layout.addWidget(self.sidebar)

        # 2. Vùng làm việc chính bên phải
        workspace_widget = QWidget(central_widget)
        workspace_widget.setObjectName("CentralWorkspace")
        workspace_layout = QVBoxLayout(workspace_widget)
        workspace_layout.setContentsMargins(8, 8, 8, 8)
        workspace_layout.setSpacing(6)

        # Thanh kết nối toàn cục ConnectionBar
        self.conn_bar = ConnectionBar(workspace_widget)
        workspace_layout.addWidget(self.conn_bar)

        # QStackedWidget chứa 6 trang
        self.stack = QStackedWidget(workspace_widget)

        self.page_inspector = InspectorPage(self.stack)
        self.page_monitor = MonitorPage(
            default_ip=self.default_ip,
            default_port=self.default_port,
            control_labels=self.control_labels,
            parent=self.stack
        )
        self.page_flasher = FlasherPage(
            saved_flash_chip=self.saved_flash_chip,
            saved_flash_baud=self.saved_flash_baud,
            saved_flash_erase=self.saved_flash_erase,
            saved_flash_rows=self.saved_flash_rows,
            parent=self.stack
        )
        self.page_partition = PartitionPage(self.stack)
        self.page_backup = BackupPage(self.stack)
        self.page_settings = SettingsPage(core_app=self, parent=self.stack)

        self.stack.addWidget(self.page_inspector)  # 0
        self.stack.addWidget(self.page_monitor)    # 1
        self.stack.addWidget(self.page_flasher)    # 2
        self.stack.addWidget(self.page_partition)  # 3
        self.stack.addWidget(self.page_backup)     # 4
        self.stack.addWidget(self.page_settings)   # 5

        workspace_layout.addWidget(self.stack, 1)
        central_layout.addWidget(workspace_widget, 1)

        self.setCentralWidget(central_widget)

        # 3. Thanh trạng thái StatusBar dưới cùng (Dùng chung tiến trình cho Tab 1, 3, 4, 5)
        status_bar = self.statusBar()
        self.lbl_status = _StatusLabelCompat("Sẵn sàng.", self)
        status_bar.addWidget(self.lbl_status, 1)

        self.lbl_conn = _StatusLabelCompat("Chưa kết nối", self)
        status_bar.addPermanentWidget(self.lbl_conn)

        self.lbl_progress_task = _StatusLabelCompat("Tiến trình: Sẵn sàng", self)
        status_bar.addPermanentWidget(self.lbl_progress_task)

        self.status_prog = _ProgressBarCompat(self)
        self.status_prog.setRange(0, 100)
        self.status_prog.setValue(0)
        self.status_prog.setFixedWidth(160)
        self.status_prog.setFixedHeight(12)
        self.status_prog.setTextVisible(False)
        status_bar.addPermanentWidget(self.status_prog)

        self.lbl_progress_pct = _StatusLabelCompat("0%", self)
        self.lbl_progress_pct.setFixedWidth(38)
        self.lbl_progress_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        status_bar.addPermanentWidget(self.lbl_progress_pct)

        # 4. Gắn kết nối chuyển trang
        self.sidebar.page_selected.connect(self._on_page_selected)

        # 5. Gán thuộc tính ủy quyền tương thích 100% với Controllers & Tests
        self._setup_attribute_delegations()

        # 6. Khởi tạo nghiệp vụ Tab 4 (Partition Table)
        if hasattr(self, "create_partition_tab"):
            self.create_partition_tab()
        if hasattr(self, "create_backup_tab"):
            self.create_backup_tab()

        # 7. Gắn đồng bộ Theme cho StatusBar & các widget vẽ trực tiếp
        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)
        self._refresh_status_bar_theme(ThemeManager.instance().tokens)

    def _setup_attribute_delegations(self):
        # Tabs
        self.inspector_tab = self.page_inspector
        self.monitor_tab = self.page_monitor
        self.flasher_tab = self.page_flasher
        self.partition_tab = self.page_partition
        self.backup_tab = self.page_backup
        self.settings_tab = self.page_settings

        self.notebook = _NotebookCompat(
            self.sidebar,
            self.stack,
            [self.inspector_tab, self.monitor_tab, self.flasher_tab, self.partition_tab, self.backup_tab, self.settings_tab]
        )

        # Top connection bar
        self.port_cb = self.conn_bar.port_cb
        self.baud_cb = self.conn_bar.baud_cb
        self.serial_toggle_btn = self.conn_bar.serial_toggle_btn
        self.refresh_btn = self.conn_bar.refresh_btn
        self.chip_badge = self.conn_bar.chip_badge

        # Kết nối sự kiện ConnectionBar
        self.conn_bar.serial_toggle_btn.clicked.connect(self.toggle_serial_connection)
        self.conn_bar.refresh_btn.clicked.connect(self.refresh_ports_dropdown)
        self.conn_bar.port_cb.currentTextChanged.connect(self.on_port_selected)
        self.conn_bar.baud_cb.currentTextChanged.connect(self.on_baud_selected)

        # Inspector
        self.detect_btn = self.page_inspector.detect_btn
        self.save_btn = self.page_inspector.save_btn
        self.clear_inspector_btn = self.page_inspector.clear_inspector_btn
        self.var_debug = self.page_inspector.var_debug
        self.chk_debug = self.page_inspector.chk_debug
        self.inspector_txt = self.page_inspector.inspector_txt
        self.raw_log_view = self.page_inspector.raw_log_view

        self.detect_btn.clicked.connect(self.on_detect)
        self.save_btn.clicked.connect(self.on_save)
        self.clear_inspector_btn.clicked.connect(lambda: self.on_clear(self.inspector_txt))
        self.page_inspector.cb_raw_log.toggled.connect(lambda _chk: self._rerender_inspector_report())
        self.page_inspector.cb_extra_log.toggled.connect(lambda _chk: self._rerender_inspector_report())

        # Monitor
        self.monitor_txt = self.page_monitor.monitor_txt
        self.serial_input = self.page_monitor.serial_input
        self.send_btn = self.page_monitor.send_btn
        self.clear_monitor_btn = self.page_monitor.clear_monitor_btn
        self.reset_btn = self.page_monitor.reset_btn
        self.cb_crlf = self.page_monitor.cb_crlf
        self.var_crlf = self.page_monitor.var_crlf
        self.cb_autoscroll = self.page_monitor.cb_autoscroll
        self.var_autoscroll = self.page_monitor.var_autoscroll
        self.cb_timestamp = self.page_monitor.cb_timestamp
        self.var_timestamp = self.page_monitor.var_timestamp
        self.var_timestamps = self.page_monitor.var_timestamp
        self.req_status_lbl = self.page_monitor.req_status_lbl
        self.wifi_cb = self.page_monitor.wifi_cb
        self.wifi_pass_entry = self.page_monitor.wifi_pass_entry
        self.cb_show_pwd = self.page_monitor.cb_show_pwd
        self.var_show_pwd = self.page_monitor.var_show_pwd
        self.ip_entry = self.page_monitor.ip_entry
        self.cb_auto_server = self.page_monitor.cb_auto_server
        self.var_auto_connect_server = self.page_monitor.var_auto_connect_server
        self.port_entry = self.page_monitor.port_entry
        self.btn_scan_wifi = self.page_monitor.btn_scan_wifi
        self.btn_connect_wifi = self.page_monitor.btn_connect_wifi
        self.btn_connect_server = self.page_monitor.btn_connect_server
        self.wifi_status_lbl = self.page_monitor.wifi_status_lbl
        self.f_buttons = self.page_monitor.f_buttons

        self.send_btn.clicked.connect(self.on_serial_send)
        self.clear_monitor_btn.clicked.connect(lambda: self.on_clear(self.monitor_txt))
        self.reset_btn.clicked.connect(self.on_reset_esp)
        self.wifi_cb.currentTextChanged.connect(lambda _t: self.on_wifi_selected())
        self.btn_scan_wifi.clicked.connect(self.on_wifi_scan)
        self.btn_connect_wifi.clicked.connect(self.toggle_wifi_connection)
        self.btn_connect_server.clicked.connect(self.toggle_server_connection)
        for index, i in enumerate(sorted(CONTROL_CONFIG)):
            if index < len(self.f_buttons):
                self.f_buttons[index].clicked.connect(lambda _=False, x=i: self.on_control_click(x))

        # Flasher
        self.flash_chip_cb = self.page_flasher.flash_chip_cb
        self.flash_baud_cb = self.page_flasher.flash_baud_cb
        self.cb_flash_erase = self.page_flasher.cb_flash_erase
        self.var_flash_erase = self.page_flasher.var_flash_erase
        self.btn_erase_flash = self.page_flasher.btn_erase_flash
        self.btn_erase_only = self.page_flasher.btn_erase_flash
        self.btn_erase_nvs = self.page_flasher.btn_erase_nvs
        self.flash_file_rows = self.page_flasher.flash_file_rows
        self.btn_flash_write = self.page_flasher.btn_flash_write
        self.flash_prog = self.status_prog
        self.flash_pct_lbl = self.lbl_progress_pct
        self.btn_clear_flasher_log = self.page_flasher.btn_clear_flasher_log
        self.flasher_txt = self.page_flasher.flasher_txt

        self.btn_erase_flash.clicked.connect(self.on_erase_flash_click)
        self.btn_erase_nvs.clicked.connect(self.on_erase_nvs_click)
        self.btn_flash_write.clicked.connect(self.on_flash_write_click)
        self.btn_clear_flasher_log.clicked.connect(lambda: self.on_clear(self.flasher_txt))

        # Partition
        self.cb_part_chip = self.page_partition.cb_part_chip
        self.part_chip_var = self.page_partition.cb_part_chip
        self.cb_part_flash = self.page_partition.cb_part_flash
        self.part_flash_var = self.page_partition.cb_part_flash
        self.cb_part_mode = self.page_partition.cb_part_mode
        self.part_mode_var = self.page_partition.cb_part_mode
        self.chk_auto_align = self.page_partition.chk_auto_align
        self.var_auto_align = self.page_partition.var_auto_align
        self.btn_part_read_hw = self.page_partition.btn_part_read_hw
        self.btn_part_flash_hw = self.page_partition.btn_part_flash_hw
        self.btn_part_dump_hw = self.page_partition.btn_part_dump_hw
        self.btn_part_write_hw = self.page_partition.btn_part_write_hw
        self.btn_part_erase_hw = self.page_partition.btn_part_erase_hw
        self.btn_part_scan = self.page_partition.btn_part_scan
        self.btn_part_clear = self.page_partition.btn_part_clear
        self.btn_part_help = self.page_partition.btn_part_help
        self.btn_part_undo = self.page_partition.btn_part_undo
        self.btn_part_redo = self.page_partition.btn_part_redo
        self.disk_map = self.page_partition.disk_map
        self.lbl_flash_stats = self.page_partition.lbl_flash_stats
        self.part_tree = self.page_partition.part_tree
        self.btn_add_part = self.page_partition.btn_add_part
        self.btn_edit_part = self.page_partition.btn_edit_part
        self.btn_del_part = self.page_partition.btn_del_part
        self.btn_autopack = self.page_partition.btn_autopack
        self.btn_presets = self.page_partition.btn_presets
        self.btn_open_csv = self.page_partition.btn_open_csv
        self.btn_save_csv = self.page_partition.btn_save_csv
        self.part_log_txt = self.page_partition.part_log_txt

        self.cb_part_chip.currentTextChanged.connect(lambda _: self._on_chip_changed())
        self.cb_part_chip.activated.connect(lambda _: self._on_chip_changed())
        self.cb_part_flash.currentTextChanged.connect(lambda _: self._on_flash_size_changed())
        self.cb_part_mode.currentTextChanged.connect(lambda _: self._on_display_mode_changed())
        self.chk_auto_align.toggled.connect(lambda _: self._on_toggle_auto_align())

        self.btn_part_read_hw.clicked.connect(self._hw_read_partition_table)
        self.btn_part_flash_hw.clicked.connect(self._hw_flash_partition_table)
        self.btn_part_dump_hw.clicked.connect(self._hw_dump_selected_partition)
        self.btn_part_write_hw.clicked.connect(self._hw_write_selected_partition)
        self.btn_part_erase_hw.clicked.connect(self._hw_erase_selected_partition)
        self.btn_part_scan.clicked.connect(self._action_scan_project)
        self.btn_part_clear.clicked.connect(self._action_clear_all_partitions)
        self.btn_part_help.clicked.connect(self._open_handbook_dialog)
        self.btn_part_undo.clicked.connect(self._action_undo)
        self.btn_part_redo.clicked.connect(self._action_redo)
        self.btn_add_part.clicked.connect(lambda: self._action_add_partition())
        self.btn_edit_part.clicked.connect(self._action_edit_selected)
        self.btn_del_part.clicked.connect(self._action_delete_selected)
        self.btn_autopack.clicked.connect(self._action_auto_pack)
        self.btn_presets.clicked.connect(self._action_presets)
        self.btn_open_csv.clicked.connect(self._action_open_file)
        self.btn_save_csv.clicked.connect(self._action_save_csv)

        # Backup
        self.cb_backup_src_port = self.page_backup.cb_backup_src_port
        self.backup_src_port_var = self.page_backup.backup_src_port_var
        self.btn_backup_blink_led = self.page_backup.btn_backup_blink_led
        self.btn_backup_refresh_com = self.page_backup.btn_backup_refresh_com
        self.cb_backup_baud = self.page_backup.cb_backup_baud
        self.backup_baud_var = self.page_backup.backup_baud_var
        self.btn_backup_read_chip = self.page_backup.btn_backup_read_chip
        self.btn_backup_sel_all = self.page_backup.btn_backup_sel_all
        self.btn_backup_unsel_all = self.page_backup.btn_backup_unsel_all
        self.btn_backup_sel_fw = self.page_backup.btn_backup_sel_fw
        self.chk_backup_trim = self.page_backup.chk_backup_trim
        self.var_backup_smart_trim = self.page_backup.var_backup_smart_trim
        self.backup_disk_map = self.page_backup.backup_disk_map
        self.lbl_backup_chip_summary = self.page_backup.lbl_backup_chip_summary
        self.backup_tree = self.page_backup.backup_tree
        self.btn_backup_to_folder = self.page_backup.btn_backup_to_folder
        self.btn_backup_full_chip = self.page_backup.btn_backup_full_chip
        self.btn_backup_to_flasher = self.page_backup.btn_backup_to_flasher
        self.var_clone_source_mode = self.page_backup.var_clone_source_mode
        self.btn_sel_all_targets = self.page_backup.btn_sel_all_targets
        self.clone_target_ports_frame = self.page_backup.clone_target_ports_frame
        self.chk_clone_erase = self.page_backup.chk_clone_erase
        self.var_clone_erase_first = self.page_backup.var_clone_erase_first
        self.btn_direct_clone = self.page_backup.btn_direct_clone
        self.backup_log_txt = self.page_backup.backup_log_txt

        # Kết nối đồng bộ chế độ nguồn (Board Gốc trực tiếp / Thư mục đã lưu) với danh sách Board Đích
        if hasattr(self.page_backup, "source_mode_changed"):
            self.page_backup.source_mode_changed.connect(
                lambda _m: self._refresh_clone_target_checkboxes()
            )
        self.cb_backup_src_port.currentTextChanged.connect(self._on_backup_src_port_selected_by_user)
        self.cb_backup_src_port.activated.connect(
            lambda _idx: self._on_backup_src_port_selected_by_user(self.cb_backup_src_port.currentText())
        )
        self.btn_backup_blink_led.clicked.connect(self._on_toggle_board_led_blink)
        self.btn_backup_refresh_com.clicked.connect(self._refresh_backup_ports)
        self.btn_backup_read_chip.clicked.connect(self._hw_probe_source_chip_for_backup)
        self.btn_backup_sel_all.clicked.connect(lambda: self._backup_select_all(True))
        self.btn_backup_unsel_all.clicked.connect(lambda: self._backup_select_all(False))
        self.btn_backup_sel_fw.clicked.connect(self._backup_select_firmware_only)
        self.btn_backup_to_folder.clicked.connect(self._hw_backup_selected_to_folder)
        self.btn_backup_full_chip.clicked.connect(self._hw_backup_full_flash_single_file)
        self.btn_backup_to_flasher.clicked.connect(self._action_send_backup_to_flasher_tab)
        self.btn_sel_all_targets.clicked.connect(lambda: self._select_all_clone_targets(True))
        self.btn_direct_clone.clicked.connect(self._hw_start_direct_multi_board_clone)

        # Global status mappings
        self.global_status_lbl = self.lbl_status
        self.global_progress_task_lbl = self.lbl_progress_task
        self.global_progress_bar = self.status_prog
        self.global_progress_pct_lbl = self.lbl_progress_pct
        self.clear_monitor_btn = self.page_monitor.clear_monitor_btn
        self.controls_frame = self.conn_bar
        self.var_hide_bt_ports = _BooleanVar(value=bool(getattr(self, "saved_hide_bluetooth_ports", True)))
        self.var_auto_scan = _BooleanVar(value=bool(getattr(self, "saved_auto_scan", True)))
        self.var_auto_select_new = _BooleanVar(value=bool(getattr(self, "saved_auto_select_new", True)))
        if not hasattr(self, "ignored_com_ports") or self.ignored_com_ports is None:
            self.ignored_com_ports = []
        if hasattr(self.page_settings, "load_from_core"):
            self.page_settings.load_from_core()
        if hasattr(self, "update_tab5_led_blink_visibility"):
            self.update_tab5_led_blink_visibility()

    def _action_copy_partition_config(self):
        if hasattr(self.page_partition, "_action_copy_partition_config"):
            self.page_partition._action_copy_partition_config()

    def _action_clear_all_partitions(self):
        if hasattr(self.page_partition, "_action_clear_all_partitions"):
            self.page_partition._action_clear_all_partitions()

    def _action_new_table(self):
        if hasattr(self.page_partition, "_action_new_table"):
            self.page_partition._action_new_table()

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_native_icon_applied", False):
            self._native_icon_applied = True
            icon_path = getattr(self, "_resolved_icon_path", "")
            if icon_path:
                try:
                    from modules.app_core import set_window_icon_native
                    set_window_icon_native(self, icon_path)
                except Exception:
                    pass

    def _on_page_selected(self, index: int):
        self.stack.setCurrentIndex(index)
        if index != 4 and hasattr(self, "_stop_board_led_blink"):
            self._stop_board_led_blink()
        if index == 4 and hasattr(self, "update_tab5_led_blink_visibility"):
            self.update_tab5_led_blink_visibility()
        if index == 5 and hasattr(self.page_settings, "load_from_core"):
            self.page_settings.load_from_core()

    def _create_main_menu(self):
        menubar = self.menuBar()

        # Menu Tệp
        menu_file = menubar.addMenu("Tệp")
        act_open = menu_file.addAction("Mở Bảng Phân Vùng...")
        act_open.triggered.connect(lambda: (self.notebook.select(self.partition_tab), self._action_open_file()))
        act_save = menu_file.addAction("Lưu CSV")
        act_save.triggered.connect(lambda: (self.notebook.select(self.partition_tab), self._action_save_csv()))
        menu_file.addSeparator()
        act_exit = menu_file.addAction("Thoát")
        act_exit.triggered.connect(self.close)

        # Menu Công cụ
        menu_tools = menubar.addMenu("Công cụ")
        act_inspect = menu_tools.addAction("Kiểm tra Chip ESP")
        act_inspect.triggered.connect(lambda: (self.notebook.select(self.inspector_tab), self.on_detect()))
        act_reset = menu_tools.addAction("Reset ESP")
        act_reset.triggered.connect(self.on_reset_esp)
        act_erase = menu_tools.addAction("Xóa Toàn Bộ Flash")
        act_erase.triggered.connect(self.on_erase_flash_click)

        # Menu Theme (Chỉ giữ phong cách Kỹ thuật Sáng/Tối)
        menu_theme = menubar.addMenu("Chủ đề")
        act_e_dark = menu_theme.addAction("Kỹ thuật Chuyên sâu (Tối)")
        act_e_dark.triggered.connect(lambda: self._apply_theme_selection("engineering", True))
        act_e_light = menu_theme.addAction("Kỹ thuật Chuyên sâu (Sáng)")
        act_e_light.triggered.connect(lambda: self._apply_theme_selection("engineering", False))

        # Menu Cài đặt
        menu_settings = menubar.addMenu("Cài đặt")
        act_settings = menu_settings.addAction("Cài đặt Hệ thống...")
        act_settings.triggered.connect(lambda: self.notebook.select(self.settings_tab))

        # Menu Giới thiệu
        menu_about = menubar.addMenu("Giới thiệu")
        act_about = menu_about.addAction("Thông tin Phần mềm...")
        act_about.triggered.connect(self.open_about_dialog)

    # Dispatcher Thread-safe Call
    def ui_call(self, fn, *args, delay_ms: int = 0):
        self._dispatcher.post(fn, *args, delay_ms=delay_ms)

    def safe_after(self, fn, delay_ms: int = 0):
        self.ui_call(fn, delay_ms=delay_ms)

    def after(self, delay_ms: int, fn, *args):
        self.ui_call(fn, *args, delay_ms=delay_ms)

    # Status Bar Management
    def update_global_progress(self, progress: float, task_label: Optional[str] = None):
        """Cập nhật thanh tiến trình dùng chung ở dưới cùng cho Tabs 1, 3, 4, 5 kèm tên tác vụ và %."""
        try:
            p = float(progress)
            self.status_prog.config(mode="determinate")
            self.status_prog["value"] = p
            pct = int(round(max(0.0, min(100.0, p))))
            self.lbl_progress_pct.setText(f"{pct}%")
        except (ValueError, TypeError):
            pass
        if task_label is not None and hasattr(self, "lbl_progress_task"):
            txt = str(task_label).strip()
            self.lbl_progress_task.setText(txt if txt else "Tiến trình: Sẵn sàng")

    def set_status(self, message: str, level: str = "info", progress: Optional[float] = None, task_label: Optional[str] = None):
        self.current_status_level = level
        self.lbl_status.setText(message)
        if hasattr(self, "req_status_lbl") and self.req_status_lbl is not None:
            self.req_status_lbl.setText(message)
        if progress is not None:
            self.update_global_progress(progress, task_label=task_label)
        elif task_label is not None and hasattr(self, "lbl_progress_task"):
            txt = str(task_label).strip()
            self.lbl_progress_task.setText(txt if txt else "Tiến trình: Sẵn sàng")
        self._apply_status_colors(tokens=ThemeManager.instance().tokens)

    def _apply_status_colors(self, tokens: Optional[ThemeTokens] = None):
        """Đồng bộ màu chữ thanh StatusBar và nhãn trạng thái theo theme Sáng/Tối hiện tại."""
        tokens = tokens or ThemeManager.instance().tokens
        level = getattr(self, "current_status_level", "info")
        color_map = {
            "error": tokens.danger,
            "warning": tokens.warning,
            "success": tokens.success,
            "info": tokens.text,
        }
        col = color_map.get(level, tokens.text)
        if hasattr(self, "lbl_status") and self.lbl_status is not None:
            self.lbl_status.setStyleSheet(f"font-size: 9pt; color: {col}; background-color: transparent;")
        if hasattr(self, "req_status_lbl") and self.req_status_lbl is not None:
            self.req_status_lbl.setStyleSheet(f"font-size: 8.5pt; color: {col}; font-style: italic; background-color: transparent;")

    def _refresh_status_bar_theme(self, tokens: Optional[ThemeTokens] = None):
        """Làm mới màu chữ tất cả thành phần trên StatusBar khi chuyển Sáng/Tối."""
        tokens = tokens or ThemeManager.instance().tokens
        self._apply_status_colors(tokens=tokens)
        if hasattr(self, "lbl_conn") and self.lbl_conn is not None:
            self.lbl_conn.setStyleSheet(
                f"font-size: 8.5pt; color: {tokens.text_secondary}; padding-right: 10px; background-color: transparent;"
            )
        if hasattr(self, "lbl_progress_task") and self.lbl_progress_task is not None:
            self.lbl_progress_task.setStyleSheet(
                f"font-size: 8.5pt; color: {tokens.text}; padding-right: 6px; background-color: transparent;"
            )
        if hasattr(self, "lbl_progress_pct") and self.lbl_progress_pct is not None:
            self.lbl_progress_pct.setStyleSheet(
                f"font-size: 8.5pt; font-weight: 700; font-family: Consolas; color: {tokens.text}; padding-right: 6px; background-color: transparent;"
            )

    def _on_theme_changed(self, tokens: Optional[ThemeTokens] = None):
        """Cập nhật toàn bộ nhãn StatusBar & DiskMap khi Theme thay đổi từ bất kỳ nguồn nào."""
        if getattr(self, "_closing", False):
            return
        tok = tokens or ThemeManager.instance().tokens
        self.is_dark_mode = bool(tok.is_dark)
        self._refresh_status_bar_theme(tok)
        if hasattr(self, "disk_map") and hasattr(self.disk_map, "set_theme_mode"):
            self.disk_map.set_theme_mode(self.is_dark_mode)
        if hasattr(self, "backup_disk_map") and hasattr(self.backup_disk_map, "set_theme_mode"):
            self.backup_disk_map.set_theme_mode(self.is_dark_mode)

    def update_global_status(self, text: str, is_active: bool = False, progress: Optional[float] = None, task_label: Optional[str] = None):
        prog_num = None
        if progress is not None:
            try:
                prog_num = float(progress)
            except (ValueError, TypeError):
                pass
        elif is_active:
            prog_num = 0.0
        level = "warning" if is_active else ("info" if prog_num is None or prog_num < 100 else "success")
        self.set_status(text, level=level, progress=prog_num, task_label=task_label)

    def set_connection_status(self, text: str, is_active: bool = False):
        self.lbl_conn.setText(text)
        self.conn_bar.set_chip_badge_info(text, is_active=is_active)

    # Tkinter compatibility shims
    def winfo_exists(self) -> bool:
        return not self._closing

    def winfo_children(self) -> list:
        return []

    def update_idletasks(self):
        QApplication.processEvents()

    def update(self):
        QApplication.processEvents()

    def withdraw(self):
        self.hide()

    def deiconify(self):
        self.show()

    def config(self, **kwargs):
        pass

    def configure(self, **kwargs):
        pass

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    if isinstance(config, dict):
                        self.saved_wifi_credentials = config.get("wifi_credentials", {})
                        self.is_dark_mode = config.get("is_dark_mode", False) is True
                        self.saved_theme_preset = "engineering"
                        self.tab5_led_blink_enabled = config.get("tab5_led_blink_enabled", False) is True
                        self.saved_com_port = str(config.get("last_com_port", "") or "")
                        self.saved_baudrate = str(config.get("last_baudrate", "Tự động") or "Tự động")
                        self.saved_hide_bluetooth_ports = config.get("hide_bluetooth_ports", True) is not False
                        self.ignored_com_ports = config.get("ignored_com_ports", [])
                        self.saved_auto_scan = config.get("auto_scan", True) is not False
                        self.saved_auto_select_new = config.get("auto_select_new_port", True) is not False
                        self.default_ip = str(config.get("default_ip", "192.168.4.1") or "192.168.4.1")
                        self.default_port = str(config.get("default_port", "100") or "100")
                        self.saved_flash_baud = str(config.get("flash_baud", "460800") or "460800")
                        self.saved_flash_chip = str(config.get("flash_chip", "auto") or "auto")
                        self.saved_flash_erase = config.get("flash_erase", False) is True

                        loaded_labels = config.get("control_labels", {})
                        if isinstance(loaded_labels, dict):
                            for k, v in loaded_labels.items():
                                if str(k).isdigit() and int(k) in CONTROL_CONFIG:
                                    self.control_labels[int(k)] = str(v)

                        loaded_cmds = config.get("control_commands", {})
                        if isinstance(loaded_cmds, dict):
                            for k, v in loaded_cmds.items():
                                if str(k).isdigit() and int(k) in CONTROL_CONFIG:
                                    self.control_commands[int(k)] = str(v)

                        flash_rows = config.get("flash_rows", [])
                        if isinstance(flash_rows, list):
                            self.saved_flash_rows = flash_rows[:4]
            except Exception as e:
                print(f"Lỗi đọc file cấu hình: {e}")

    def save_config(self):
        current_port = self.port_cb.currentText().strip() if hasattr(self, 'port_cb') else ""
        current_baud = self.baud_cb.currentText().strip() if hasattr(self, 'baud_cb') else ""
        last_port = current_port or self.saved_com_port
        last_baud = current_baud or self.saved_baudrate or "Tự động"
        self.saved_com_port = last_port
        self.saved_baudrate = last_baud

        flash_rows_data = []
        if hasattr(self, 'flash_file_rows'):
            for row in self.flash_file_rows:
                flash_rows_data.append({
                    "enabled": row["var_enable"].get(),
                    "path": row["path_entry"].text().strip(),
                    "offset": row["offset_entry"].text().strip()
                })
        else:
            flash_rows_data = self.saved_flash_rows

        flash_baud_val = self.flash_baud_cb.currentText().strip() if hasattr(self, 'flash_baud_cb') else self.saved_flash_baud
        flash_chip_val = self.flash_chip_cb.currentText().strip() if hasattr(self, 'flash_chip_cb') else self.saved_flash_chip
        flash_erase_val = self.var_flash_erase.get() if hasattr(self, 'var_flash_erase') else self.saved_flash_erase

        config = {
            "wifi_credentials": self.saved_wifi_credentials,
            "is_dark_mode": self.is_dark_mode,
            "theme_preset": "engineering",
            "tab5_led_blink_enabled": bool(getattr(self, "tab5_led_blink_enabled", False)),
            "last_com_port": last_port,
            "last_baudrate": last_baud,
            "ignored_com_ports": self.ignored_com_ports,
            "hide_bluetooth_ports": self.saved_hide_bluetooth_ports,
            "auto_scan": getattr(self, "saved_auto_scan", True),
            "auto_select_new_port": self.saved_auto_select_new,
            "default_ip": self.default_ip,
            "default_port": self.default_port,
            "control_labels": self.control_labels,
            "control_commands": self.control_commands,
            "flash_rows": flash_rows_data,
            "flash_baud": flash_baud_val,
            "flash_chip": flash_chip_val,
            "flash_erase": flash_erase_val
        }
        temp_config = f"{CONFIG_FILE}.{os.getpid()}.tmp"
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(temp_config, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_config, CONFIG_FILE)
        except Exception as e:
            print(f"Lỗi lưu file cấu hình: {e}")
            try:
                if os.path.exists(temp_config):
                    os.remove(temp_config)
            except OSError:
                pass

    def reset_config(self, confirm: bool = True):
        if (not confirm) or dlg.ask_yes_no("Xác nhận", "Bạn có chắc chắn muốn khôi phục cài đặt gốc?\n(Mật khẩu WiFi đã lưu, cấu hình và màu nền sẽ bị xóa)", parent=self):
            if os.path.exists(CONFIG_FILE):
                try:
                    os.remove(CONFIG_FILE)
                except Exception:
                    pass
            self.saved_wifi_credentials = {}
            self.is_dark_mode = False
            self.saved_theme_preset = "engineering"
            self.tab5_led_blink_enabled = False
            self.saved_com_port = ""
            self.saved_baudrate = "Tự động"
            self.ignored_com_ports = []
            self.saved_hide_bluetooth_ports = True
            self.saved_auto_scan = True
            self.saved_auto_select_new = True
            if hasattr(self, "var_hide_bt_ports"):
                self.var_hide_bt_ports.set(True)
            if hasattr(self, "var_auto_scan"):
                self.var_auto_scan.set(True)
            if hasattr(self, "var_auto_select_new"):
                self.var_auto_select_new.set(True)

            self.default_ip = "192.168.4.1"
            self.default_port = "100"
            self.control_labels = {i: CONTROL_CONFIG.get(i, (f"F{i}", f"CMD_{i}"))[0] for i in sorted(CONTROL_CONFIG)}
            self.control_commands = {i: CONTROL_CONFIG.get(i, (f"F{i}", f"CMD_{i}"))[1] for i in sorted(CONTROL_CONFIG)}
            if hasattr(self, "f_buttons"):
                for idx, key_num in enumerate(sorted(CONTROL_CONFIG)):
                    if idx < len(self.f_buttons):
                        self.f_buttons[idx].setText(self.control_labels.get(key_num, f"F{key_num}"))
            if hasattr(self, "ip_entry"):
                self.ip_entry.setText(self.default_ip)
            if hasattr(self, "port_entry"):
                self.port_entry.setText(self.default_port)

            self._apply_theme_selection("engineering", False)
            if hasattr(self, "update_tab5_led_blink_visibility"):
                self.update_tab5_led_blink_visibility()
            if hasattr(self, "page_settings") and hasattr(self.page_settings, "load_from_core"):
                self.page_settings.load_from_core()
            if hasattr(self, "refresh_ports_dropdown"):
                self.refresh_ports_dropdown()
            self.save_config()
            dlg.show_info("Thành công", "Đã khôi phục cài đặt mặc định.", self)
            return True
        return False

    def start_background_tasks(self):
        if hasattr(self, "stop_scan") and self.stop_scan.is_set():
            return
        if self._scan_thread is not None and self._scan_thread.is_alive():
            return
        self._scan_thread = threading.Thread(target=self._auto_scan_ports, daemon=True)
        self._scan_thread.start()
        self.set_status("Sẵn sàng.", "info", progress=0)

    def _auto_scan_ports(self):
        from modules.serial_util import list_com_ports_local
        while not self.stop_scan.is_set() and not self._closing:
            try:
                if getattr(self, "saved_auto_scan", True):
                    new_ports = list_com_ports_local()
                    if self.stop_scan.is_set() or self._closing:
                        break
                    self.ui_call(self._check_and_update_ports, new_ports)
            except Exception:
                pass
            if self.stop_scan.wait(2.0):
                break

    def filter_ignored_ports(self, raw_ports):
        import modules.app_core as app_core_mod
        ignored = {x.strip().upper() for x in (self.ignored_com_ports or []) if x and x.strip()}
        hide_bt = (self.var_hide_bt_ports.get() if hasattr(self, 'var_hide_bt_ports')
                   else getattr(self, 'saved_hide_bluetooth_ports', True))
        if hide_bt:
            try:
                fn = getattr(app_core_mod, 'get_bluetooth_com_ports', None)
                ports = fn() if fn else None
                if ports is None:
                    from modules.serial_util import get_bluetooth_com_ports
                    ports = get_bluetooth_com_ports()
                for bt_port in (ports or []):
                    if bt_port and bt_port.strip():
                        ignored.add(bt_port.strip().upper())
            except Exception:
                pass
        if not ignored:
            return list(raw_ports)
        return [p for p in raw_ports if p.strip().upper() not in ignored]

    def _check_and_update_ports(self, new_ports):
        if not self.winfo_exists():
            return
        if self.is_device_busy():
            return
        filtered_ports = self.filter_ignored_ports(new_ports)
        current_selection = self.port_cb.currentText().strip()

        newly_added = [p for p in filtered_ports if p not in self._previous_ports]
        self._previous_ports = set(filtered_ports)

        if self.saved_auto_select_new and newly_added and not (self.serial_connection and self.serial_connection.is_open):
            latest_new_port = newly_added[-1]
            self.port_cb.blockSignals(True)
            self.port_cb.clear()
            self.port_cb.addItems(filtered_ports)
            self.port_cb.setCurrentText(latest_new_port)
            self.port_cb.blockSignals(False)
            self.saved_com_port = latest_new_port
            self.save_config()
            self.set_status(f"Đã tự động chọn cổng mới cắm: {latest_new_port}", "info")
            if hasattr(self, '_refresh_backup_ports') and callable(self._refresh_backup_ports):
                try:
                    self._refresh_backup_ports()
                except Exception:
                    pass
        else:
            self.update_port_list(current_selection, filtered_ports)

    def refresh_ports_dropdown(self):
        from modules.serial_util import list_com_ports_local
        new_ports = list_com_ports_local()
        filtered_ports = self.filter_ignored_ports(new_ports)
        self._previous_ports = set(filtered_ports)
        current_selection = self.port_cb.currentText().strip()
        self.update_port_list(current_selection, filtered_ports)

    def on_port_selected(self, text: str = ""):
        port = self.port_cb.currentText().strip()
        if port:
            self.saved_com_port = port
            self.save_config()

    def on_baud_selected(self, text: str = ""):
        baud = self.baud_cb.currentText().strip()
        if baud:
            self.saved_baudrate = baud
            self.save_config()

    def on_serial_newline(self, event=None):
        pass

    def update_port_list(self, current_selection: str, new_ports: list):
        if self.winfo_exists():
            curr_items = [self.port_cb.itemText(i) for i in range(self.port_cb.count())]
            if curr_items != new_ports:
                self.port_cb.blockSignals(True)
                self.port_cb.clear()
                self.port_cb.addItems(new_ports)
                if self.saved_com_port and self.saved_com_port in new_ports:
                    self.port_cb.setCurrentText(self.saved_com_port)
                elif current_selection and current_selection in new_ports:
                    self.port_cb.setCurrentText(current_selection)
                elif new_ports:
                    self.port_cb.setCurrentText(new_ports[0])
                self.port_cb.blockSignals(False)

            if hasattr(self, '_refresh_backup_ports') and callable(self._refresh_backup_ports):
                try:
                    self._refresh_backup_ports()
                except Exception:
                    pass

    def is_device_busy(self) -> bool:
        flashing = hasattr(self, 'is_flashing') and (self.is_flashing.is_set() if hasattr(self.is_flashing, 'is_set') else bool(self.is_flashing))
        detecting = hasattr(self, 'is_detecting') and (self.is_detecting.is_set() if hasattr(self.is_detecting, 'is_set') else bool(self.is_detecting))
        connecting = bool(getattr(self, "is_connecting", False))
        partition_hw = bool(getattr(self, "_is_partition_hw_running", False))
        backup_hw = bool(getattr(self, "_is_backup_hw_running", False))
        return bool(flashing or detecting or connecting or partition_hw or backup_hw)

    def set_global_busy_state(self, is_busy: bool, operation_name: str = "") -> None:
        self.detect_btn.setEnabled(not is_busy)
        self.serial_toggle_btn.setEnabled(not is_busy)
        self.port_cb.setEnabled(not is_busy)
        self.baud_cb.setEnabled(not is_busy)

        if hasattr(self, '_set_flash_ui_state') and callable(self._set_flash_ui_state):
            try:
                self._set_flash_ui_state("disabled" if is_busy else "normal")
            except Exception:
                pass

        if hasattr(self, '_set_partition_ui_state') and callable(self._set_partition_ui_state):
            try:
                self._set_partition_ui_state("disabled" if is_busy else "normal")
            except Exception:
                pass

        if hasattr(self, '_set_backup_ui_state') and callable(self._set_backup_ui_state):
            try:
                self._set_backup_ui_state("disabled" if is_busy else "normal")
            except Exception:
                pass

        if is_busy:
            self._set_mcu_dependent_ui_state("disabled")
        else:
            if hasattr(self, 'serial_connection') and self.serial_connection and getattr(self.serial_connection, 'is_open', False):
                self._set_mcu_dependent_ui_state("normal")

        if is_busy and hasattr(self, "_stop_board_led_blink"):
            try:
                self._stop_board_led_blink()
            except Exception:
                pass

        if operation_name:
            op_clean = operation_name.strip()
            task_title = op_clean[0].upper() + op_clean[1:] if op_clean else ""
            if is_busy:
                self.update_global_status(
                    f"Đang {op_clean}...",
                    is_active=True,
                    progress=0.0,
                    task_label=f"Đang {op_clean}",
                )
            else:
                self.update_global_status(
                    f"Đã hoàn tất {op_clean}.",
                    is_active=False,
                    progress=None,
                    task_label=f"Hoàn tất: {task_title}",
                )
        elif not is_busy:
            self.status_prog.config(mode="determinate")

    def _set_mcu_dependent_ui_state(self, ui_state: str):
        enabled = (ui_state != "disabled")
        self.btn_scan_wifi.setEnabled(enabled)
        self.btn_connect_wifi.setEnabled(enabled)
        self.btn_connect_server.setEnabled(enabled)
        self.wifi_cb.setEnabled(enabled)
        self.wifi_pass_entry.setEnabled(enabled)
        self.ip_entry.setEnabled(enabled)
        self.port_entry.setEnabled(enabled)
        self.cb_auto_server.setEnabled(enabled)
        for btn in self.f_buttons:
            btn.setEnabled(enabled)
        self.serial_input.setEnabled(enabled)
        self.send_btn.setEnabled(enabled)
        if hasattr(self, 'reset_btn'):
            self.reset_btn.setEnabled(enabled)
        self.cb_crlf.setEnabled(enabled)
        self.cb_show_pwd.setEnabled(enabled)

    def _apply_theme_selection(self, preset: str, is_dark: bool):
        self.saved_theme_preset = "engineering"
        self.is_dark_mode = bool(is_dark)
        tokens = ThemeManager.instance().apply_theme("engineering", self.is_dark_mode)
        self._on_theme_changed(tokens)

    def toggle_theme(self):
        self.is_dark_mode = not self.is_dark_mode
        self.apply_theme()

    def apply_theme(self):
        self._apply_theme_selection(self.saved_theme_preset, self.is_dark_mode)

    def bring_to_front(self):
        """Đưa cửa sổ đang mở lên phía trước khi người dùng mở thêm phiên bản ứng dụng thứ hai."""
        if getattr(self, "_closing", False):
            return
        try:
            if self.isMinimized():
                self.showNormal()
            elif not self.isVisible():
                self.show()
            self.raise_()
            self.activateWindow()
            if os.name == "nt" and os.environ.get("QT_QPA_PLATFORM", "").lower() != "offscreen":
                import ctypes
                hwnd = int(self.winId())
                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def cleanup_resources(self, force: bool = False):
        """
        Giải phóng an toàn toàn bộ luồng nền, cổng Serial/COM, kết nối đang chạy,
        bộ đếm thời gian Qt, handle icon GDI và các tiến trình con của hệ điều hành.
        """
        if getattr(self, "_resources_cleaned", False) and not force:
            return
        self._resources_cleaned = True
        self._closing = True

        # 1. Dừng luồng quét cổng COM định kỳ
        stop_scan = getattr(self, "stop_scan", None)
        if stop_scan is not None and hasattr(stop_scan, "set"):
            stop_scan.set()
        scan_t = getattr(self, "_scan_thread", None)
        if scan_t is not None and scan_t.is_alive() and threading.current_thread() is not scan_t:
            try:
                scan_t.join(timeout=0.35)
            except Exception:
                pass

        # 2. Dừng nháy LED nhận diện Board Gốc (Tab 5) & trả cổng COM
        if hasattr(self, "_stop_board_led_blink"):
            try:
                self._stop_board_led_blink(join_timeout=0.35)
            except Exception:
                pass

        # 3. Đóng Serial Monitor & luồng đọc Serial
        stop_ser = getattr(self, "stop_serial_thread", None)
        if stop_ser is not None and hasattr(stop_ser, "set"):
            stop_ser.set()
        ser = getattr(self, "serial_connection", None)
        if ser is not None:
            for m_name in ("cancel_read", "cancel_write"):
                fn = getattr(ser, m_name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
            try:
                if getattr(ser, "is_open", True) and hasattr(ser, "close"):
                    ser.close()
            except Exception:
                pass
            self.serial_connection = None
        ser_t = getattr(self, "serial_thread", None)
        if ser_t is not None and ser_t.is_alive() and threading.current_thread() is not ser_t:
            try:
                ser_t.join(timeout=0.35)
            except Exception:
                pass

        # 4. Ngắt tác vụ esptool đang mở cổng (khi force hoặc khi thoát)
        try:
            from modules.esptool_util import abort_active_esptool
            abort_active_esptool()
        except Exception:
            pass

        if force:
            for ev_name in ("is_detecting", "is_flashing"):
                ev = getattr(self, ev_name, None)
                if ev is not None and hasattr(ev, "clear"):
                    try:
                        ev.clear()
                    except Exception:
                        pass
            for flag_name in ("is_connecting", "_is_partition_hw_running", "_is_backup_hw_running"):
                if hasattr(self, flag_name):
                    setattr(self, flag_name, False)
            for t_name in ("detect_thread", "flash_thread", "partition_hw_thread", "backup_hw_thread"):
                th = getattr(self, t_name, None)
                if th is not None and th.is_alive() and threading.current_thread() is not th:
                    try:
                        th.join(timeout=0.25)
                    except Exception:
                        pass

        # 5. Dừng toàn bộ QTimer (LogView flush & các QTimer con)
        for attr in ("inspector_txt", "raw_log_view", "monitor_txt", "flasher_txt", "part_log_txt", "backup_log_txt"):
            lv = getattr(self, attr, None)
            if lv is not None and hasattr(lv, "stop"):
                try:
                    lv.stop()
                except Exception:
                    pass
        try:
            for timer in self.findChildren(QTimer):
                try:
                    timer.stop()
                except Exception:
                    pass
        except Exception:
            pass

        # 6. Ngừng dispatcher để callback luồng nền không chạm widget đã hủy
        disp = getattr(self, "_dispatcher", None)
        if disp is not None and hasattr(disp, "shutdown"):
            try:
                disp.shutdown()
            except Exception:
                pass

        # 7. Thu hồi handle GDI icon & dọn mọi tiến trình con hệ điều hành
        try:
            from modules.app_core import destroy_window_icons_native
            destroy_window_icons_native(self)
        except Exception:
            pass
        try:
            from modules.single_instance import terminate_child_processes
            terminate_child_processes()
        except Exception:
            pass

    def on_closing(self) -> bool:
        is_flashing = getattr(self, "is_flashing", None)
        is_detecting = getattr(self, "is_detecting", None)
        is_busy = ((hasattr(self, "is_device_busy") and callable(self.is_device_busy) and self.is_device_busy())
                   or (is_flashing and is_flashing.is_set())
                   or (is_detecting and is_detecting.is_set()))
        if is_busy:
            shown = False
            try:
                import modules.app_core as app_core_mod
                if hasattr(app_core_mod, "messagebox") and hasattr(app_core_mod.messagebox, "showwarning"):
                    app_core_mod.messagebox.showwarning("Tác vụ chưa hoàn tất", "Thiết bị đang thực hiện tác vụ phần cứng. Vui lòng dừng tác vụ trước khi thoát.")
                    shown = True
            except Exception:
                pass
            if not shown:
                from modules.ui import dialogs_service as dlg_srv
                dlg_srv.show_warning("Tác vụ chưa hoàn tất", "Thiết bị đang thực hiện tác vụ phần cứng. Vui lòng dừng tác vụ trước khi thoát.", parent=getattr(self, "root", None))
            return False

        self._closing = True
        if hasattr(self, "stop_scan") and hasattr(self.stop_scan, "set"):
            self.stop_scan.set()
        if hasattr(self, "stop_serial_thread") and hasattr(self.stop_serial_thread, "set"):
            self.stop_serial_thread.set()
        if hasattr(self, "save_config") and callable(self.save_config):
            self.save_config()
        self.cleanup_resources(force=False)
        root_obj = getattr(self, "root", None)
        if root_obj and hasattr(root_obj, "destroy") and callable(root_obj.destroy):
            root_obj.destroy()
        if hasattr(self, "close") and callable(self.close):
            self.close()
        return True

    def closeEvent(self, event: QCloseEvent):
        if getattr(self, "_closing", False):
            self.cleanup_resources(force=False)
            event.accept()
            return

        if hasattr(self, "is_device_busy") and self.is_device_busy():
            from PyQt6.QtWidgets import QMessageBox
            ans = QMessageBox.question(
                self,
                "Xác nhận thoát khi đang bận",
                "Thiết bị đang thực hiện tác vụ phần cứng (Nạp Flash / Đọc chip / Nhân bản).\n"
                "Bạn có chắc chắn muốn dừng cưỡng bức tất cả tiến trình và thoát ngay không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._closing = True
            try:
                if hasattr(self, "save_config") and callable(self.save_config):
                    self.save_config()
            except Exception:
                pass
            self.cleanup_resources(force=True)
            event.accept()
            return

        self._closing = True
        if hasattr(self, "stop_scan") and hasattr(self.stop_scan, "set"):
            self.stop_scan.set()
        if hasattr(self, "stop_serial_thread") and hasattr(self.stop_serial_thread, "set"):
            self.stop_serial_thread.set()
        try:
            if hasattr(self, "save_config") and callable(self.save_config):
                self.save_config()
        except Exception:
            pass
        self.cleanup_resources(force=False)
        event.accept()
