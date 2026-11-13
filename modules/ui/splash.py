# -*- coding: utf-8 -*-
"""
Màn hình khởi động (Startup Splash Screen) thuần QWidget cho ESP32 Manager Tool.
- Hiển thị logo ứng dụng, tên phần mềm, phiên bản, thanh tiến độ và bước đang nạp bằng giao diện QSS thuần (không dùng ảnh tĩnh làm nền splash).
- Khóa chặt kích thước, vị trí và stylesheet cục bộ để không dịch chuyển hoặc đổi cỡ khi ThemeManager áp dụng theme toàn cục.
- Hiển thị ngay trên Windows Taskbar khi mở ứng dụng, nằm ở lớp cửa sổ bình thường (không ghim luôn-trên-cùng và không tự đẩy xuống cuối cùng).
"""
import os
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)
from modules.config import APP_NAME, APP_VERSION


def resolve_splash_logo_path(base_dir: str | None = None) -> str:
    """Tìm ảnh logo ứng dụng PNG/ICO để gắn lên màn hình khởi động và biểu tượng cửa sổ."""
    candidates = []
    search_roots = []
    if base_dir:
        search_roots.append(str(base_dir))
    if hasattr(sys, "_MEIPASS"):
        search_roots.append(str(getattr(sys, "_MEIPASS")))
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    search_roots.append(repo_root)

    for root in search_roots:
        for fname in ("esp_icon_v3_128.png", "esp_icon_v3_256.png", "esp_icon_v3.png", "esp_icon_v3.ico"):
            candidates.append(os.path.join(root, "icons", fname))

    for path in candidates:
        if os.path.isfile(path):
            return path
    return ""


class StartupSplash(QWidget):
    """Màn hình khởi động QWidget thuần có kích thước/bố cục bất biến qua mọi mốc tiến độ."""

    def __init__(self, width: int = 520, height: int = 290):
        super().__init__()
        self.setObjectName("startupSplash")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowSystemMenuHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(width, height)
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self._drag_pos = None

        app = QApplication.instance()
        if app is not None and not app.windowIcon().isNull():
            self.setWindowIcon(app.windowIcon())
        else:
            fallback_icon = resolve_splash_logo_path()
            if fallback_icon:
                self.setWindowIcon(QIcon(fallback_icon))

        self._current_progress = 0
        self._current_stage = "Đang khởi tạo..."

        # Khóa toàn bộ stylesheet cục bộ theo ID để ThemeManager.apply_theme() không làm xê dịch font/padding giữa chừng.
        self.setStyleSheet("""
            QWidget#startupSplash {
                background: transparent;
                font-family: "Segoe UI", Arial, sans-serif;
            }
            QFrame#splashCard {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #0F172A, stop:1 #162238
                );
                border: 1px solid #2A3B58;
                border-radius: 14px;
            }
            QFrame#splashAccentBar {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284C7, stop:0.65 #0EA5E9, stop:1 #38BDF8
                );
                border: none;
                border-radius: 2px;
            }
            QLabel#splashLogo {
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QLabel#splashTitle {
                color: #F8FAFC;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 19pt;
                font-weight: 700;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QLabel#splashVersion {
                color: #38BDF8;
                background-color: #16304B;
                border: 1px solid #0284C7;
                border-radius: 9px;
                padding: 0px;
                margin: 0px;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9pt;
                font-weight: 700;
            }
            QLabel#splashSubtitle {
                color: #CBD5E1;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9.5pt;
                font-weight: 500;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QLabel#splashModules {
                color: #94A3B8;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 8.5pt;
                font-weight: 400;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QLabel#splashStage {
                color: #E2E8F0;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9pt;
                font-weight: 500;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QLabel#splashPct {
                color: #38BDF8;
                font-family: "Segoe UI", Arial, sans-serif;
                font-size: 9pt;
                font-weight: 700;
                background: transparent;
                border: none;
                padding: 0px;
                margin: 0px;
            }
            QProgressBar#splashProgressBar {
                background-color: #22324D;
                border: none;
                border-radius: 4px;
                min-height: 8px;
                max-height: 8px;
                padding: 0px;
                margin: 0px;
            }
            QProgressBar#splashProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284C7, stop:1 #38BDF8
                );
                border: none;
                border-radius: 4px;
            }
        """)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.card = QFrame(self)
        self.card.setObjectName("splashCard")
        self.card.setFixedSize(width, height)
        outer.addWidget(self.card)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(22, 16, 22, 24)
        card_layout.setSpacing(12)

        self.accent_bar = QFrame(self.card)
        self.accent_bar.setObjectName("splashAccentBar")
        self.accent_bar.setFixedHeight(4)
        card_layout.addWidget(self.accent_bar)

        body = QVBoxLayout()
        body.setContentsMargins(8, 8, 8, 0)
        body.setSpacing(10)

        # Hàng đầu: Logo + Tên app + Phiên bản + Mô tả (tất cả khóa cố định chiều cao)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(18)

        self.lbl_logo = QLabel(self.card)
        self.lbl_logo.setObjectName("splashLogo")
        self.lbl_logo.setFixedSize(84, 84)
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_path = resolve_splash_logo_path()
        if logo_path:
            logo_pix = QPixmap(logo_path)
            if not logo_pix.isNull():
                self.lbl_logo.setPixmap(
                    logo_pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        top_row.addWidget(self.lbl_logo, 0, Qt.AlignmentFlag.AlignTop)

        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(5)

        title_line = QHBoxLayout()
        title_line.setContentsMargins(0, 0, 0, 0)
        title_line.setSpacing(10)
        self.lbl_title = QLabel("ESP32 Manager Tool", self.card)
        self.lbl_title.setObjectName("splashTitle")
        self.lbl_title.setFixedHeight(34)
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_line.addWidget(self.lbl_title)

        self.lbl_version = QLabel(f"v{APP_VERSION}", self.card)
        self.lbl_version.setObjectName("splashVersion")
        self.lbl_version.setFixedSize(58, 22)
        self.lbl_version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_line.addWidget(self.lbl_version, 0, Qt.AlignmentFlag.AlignVCenter)
        title_line.addStretch(1)
        title_col.addLayout(title_line)

        self.lbl_subtitle = QLabel("Bộ công cụ Kỹ thuật & Quản lý Phần cứng Espressif", self.card)
        self.lbl_subtitle.setObjectName("splashSubtitle")
        self.lbl_subtitle.setFixedHeight(22)
        self.lbl_subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_col.addWidget(self.lbl_subtitle)

        self.lbl_modules = QLabel("Chip Inspector · Serial Monitor & Log · Flasher · Partition · Direct Clone", self.card)
        self.lbl_modules.setObjectName("splashModules")
        self.lbl_modules.setFixedHeight(20)
        self.lbl_modules.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        title_col.addWidget(self.lbl_modules)

        title_col.addStretch(1)
        top_row.addLayout(title_col, 1)
        body.addLayout(top_row)

        body.addStretch(1)

        # Khối tiến trình hiện tại + % (khóa cố định chiều cao & độ rộng cột %)
        stage_row = QHBoxLayout()
        stage_row.setContentsMargins(0, 0, 0, 0)
        stage_row.setSpacing(8)
        self.lbl_stage = QLabel(self._current_stage, self.card)
        self.lbl_stage.setObjectName("splashStage")
        self.lbl_stage.setFixedHeight(22)
        self.lbl_stage.setWordWrap(False)
        self.lbl_stage.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        stage_row.addWidget(self.lbl_stage, 1)

        self.lbl_pct = QLabel("0%", self.card)
        self.lbl_pct.setObjectName("splashPct")
        self.lbl_pct.setFixedSize(48, 22)
        self.lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        stage_row.addWidget(self.lbl_pct, 0)
        body.addLayout(stage_row)

        self.progress_bar = QProgressBar(self.card)
        self.progress_bar.setObjectName("splashProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        body.addWidget(self.progress_bar)
        card_layout.addLayout(body, 1)

        self._center_on_screen()
        self._apply_taskbar_window_style()

    def _center_on_screen(self) -> None:
        """Căn giữa màn hình khởi động đúng một lần trên vùng làm việc của màn hình chính."""
        app = QApplication.instance()
        screen = self.screen() or (app.primaryScreen() if app is not None else None)
        if screen is not None:
            avail = screen.availableGeometry()
            x = avail.x() + max(0, (avail.width() - self.width()) // 2)
            y = avail.y() + max(0, (avail.height() - self.height()) // 2)
            self.setGeometry(x, y, self.width(), self.height())

    def _apply_taskbar_window_style(self) -> None:
        """Đưa cửa sổ splash lên Windows Taskbar (WS_EX_APPWINDOW) mà không đổi Z-order hiện tại."""
        if os.name != "nt" or os.environ.get("QT_QPA_PLATFORM", "").lower() == "offscreen":
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            if not hwnd:
                return

            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOPMOST = 0x00000008
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020

            user32 = ctypes.windll.user32
            user32.SetWindowPos.argtypes = [
                wintypes.HWND,
                wintypes.HWND,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                wintypes.UINT,
            ]
            user32.SetWindowPos.restype = wintypes.BOOL

            ex_style = int(user32.GetWindowLongW(hwnd, GWL_EXSTYLE))
            new_ex_style = (ex_style & ~WS_EX_TOOLWINDOW & ~WS_EX_TOPMOST) | WS_EX_APPWINDOW
            if new_ex_style != ex_style:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                # Giữ SWP_NOZORDER để tuyệt đối không tự đẩy màn hình khởi động xuống đáy Z-order.
                user32.SetWindowPos(
                    hwnd,
                    0,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
                )
        except Exception:
            pass

    def showEvent(self, event) -> None:
        self._apply_taskbar_window_style()
        super().showEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None
        event.accept()

    def set_stage(self, progress: int | float, stage_text: str = "", process_events: bool = True) -> None:
        """Cập nhật tiến độ (0-100) và mô tả bước khởi động mà không làm thay đổi kích thước/vị trí."""
        clamped = max(0, min(100, int(round(float(progress)))))
        self._current_progress = clamped
        self.progress_bar.setValue(clamped)
        self.lbl_pct.setText(f"{clamped}%")
        if stage_text:
            self._current_stage = str(stage_text)
            fallback_w = max(200, self.width() - 120)
            avail_w = self.lbl_stage.width() if self.isVisible() and self.lbl_stage.width() >= fallback_w else fallback_w
            elided = self.lbl_stage.fontMetrics().elidedText(
                self._current_stage, Qt.TextElideMode.ElideRight, avail_w
            )
            self.lbl_stage.setText(elided)
        if process_events:
            app = QApplication.instance()
            if app is not None:
                self.repaint()
                app.processEvents()

    def finish(self, main_window=None) -> None:
        """Đóng màn hình khởi động sau khi cửa sổ chính đã hiển thị xong."""
        if main_window is not None:
            app = QApplication.instance()
            if app is not None:
                app.processEvents()
        self.close()
