# -*- coding: utf-8 -*-
"""
Màn hình khởi động (Startup Splash Screen) cho ESP32 Manager Tool.
- Hiển thị ngay logo ứng dụng, tên phần mềm, phiên bản, thanh tiến độ và bước đang nạp.
- Hỗ trợ chuyển tiếp mượt mà từ PyInstaller native splash (`pyi_splash`) sang Qt `StartupSplash`.
- Cung cấp hàm tạo ảnh banner PNG đồng bộ cho `pyi_splash` trong bản đóng gói `--onefile`.
"""
import os
import sys
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSplashScreen,
    QVBoxLayout,
)
from modules.config import APP_NAME, APP_VERSION


def resolve_splash_logo_path(base_dir: str | None = None) -> str:
    """Tìm ảnh logo PNG độ phân giải cao dùng cho màn hình khởi động."""
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


def close_pyi_splash() -> bool:
    """Đóng màn hình chờ giải nén PyInstaller (pyi_splash) nếu đang chạy ở chế độ frozen."""
    try:
        import pyi_splash  # type: ignore[import-not-found]
        if getattr(pyi_splash, "is_alive", lambda: True)():
            pyi_splash.close()
        return True
    except Exception:
        return False


def _render_card_pixmap(width: int = 520, height: int = 300, include_unpack_footer: bool = False) -> QPixmap:
    """Vẽ nền thẻ splash sắc nét phong cách Engineering cho cả QSplashScreen và banner PNG pyi_splash."""
    pixmap = QPixmap(width, height)
    if include_unpack_footer:
        pixmap.fill(QColor("#0F172A"))
    else:
        pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    radius = 0.0 if include_unpack_footer else 14.0
    rect = QRectF(1.0, 1.0, width - 2.0, height - 2.0)
    path = QPainterPath()
    if radius > 0:
        path.addRoundedRect(rect, radius, radius)
    else:
        path.addRect(rect)

    bg_grad = QLinearGradient(0, 0, width, height)
    bg_grad.setColorAt(0.0, QColor("#0F172A"))
    bg_grad.setColorAt(1.0, QColor("#162238"))
    painter.fillPath(path, bg_grad)

    # Viền mảnh và dải nhấn trên cùng
    painter.setPen(QPen(QColor("#2A3B58"), 1.5))
    painter.drawPath(path)

    painter.save()
    painter.setClipPath(path)
    accent_grad = QLinearGradient(0, 0, width, 0)
    accent_grad.setColorAt(0.0, QColor("#0284C7"))
    accent_grad.setColorAt(0.65, QColor("#0EA5E9"))
    accent_grad.setColorAt(1.0, QColor("#38BDF8"))
    painter.fillRect(QRectF(0, 0, width, 4.0), accent_grad)

    if include_unpack_footer:
        logo_path = resolve_splash_logo_path()
        if logo_path:
            logo_pix = QPixmap(logo_path)
            if not logo_pix.isNull():
                scaled = logo_pix.scaled(
                    84, 84, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                painter.drawPixmap(34, 42, scaled)

        painter.setPen(QColor("#F8FAFC"))
        painter.setFont(QFont("Segoe UI", 19, QFont.Weight.Bold))
        painter.drawText(QRectF(138, 42, width - 168, 36), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "ESP32 Manager Tool")

        painter.setPen(QColor("#38BDF8"))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        painter.drawText(
            QRectF(138, 80, width - 168, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"Phiên bản v{APP_VERSION}  |  Bộ công cụ phần cứng Espressif",
        )

        painter.setPen(QColor("#94A3B8"))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(
            QRectF(138, 108, width - 168, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Inspector · Serial · Flasher · Partition · Direct Clone",
        )

        # Dải thông báo giải nén trước khi Qt khởi chạy
        painter.setPen(QColor("#CBD5E1"))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        painter.drawText(
            QRectF(34, height - 66, width - 68, 22),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "Đang giải nén tài nguyên thực thi...",
        )

        bar_bg = QPainterPath()
        bar_bg.addRoundedRect(QRectF(34, height - 38, width - 68, 8), 4.0, 4.0)
        painter.fillPath(bar_bg, QColor("#22324D"))

        bar_fg = QPainterPath()
        bar_fg.addRoundedRect(QRectF(34, height - 38, (width - 68) * 0.28, 8), 4.0, 4.0)
        painter.fillPath(bar_fg, QColor("#0EA5E9"))

    painter.restore()
    painter.end()
    return pixmap


def generate_pyi_splash_image(output_path: str) -> str:
    """Sinh file ảnh PNG banner cho PyInstaller native splash (`pyi_splash`)."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    pix = _render_card_pixmap(520, 300, include_unpack_footer=True)
    pix.save(output_path, "PNG")
    return output_path


class StartupSplash(QSplashScreen):
    """Màn hình khởi động có logo, tên ứng dụng, phiên bản, thanh tiến độ và bước khởi tạo."""

    def __init__(self, width: int = 520, height: int = 300):
        base_pix = _render_card_pixmap(width, height, include_unpack_footer=False)
        super().__init__(base_pix)
        # Dùng cờ Window (không dùng SplashScreen / WindowStaysOnTopHint) để hiện ngay trên Taskbar
        # và cho phép các cửa sổ khác che lên bình thường trong lúc khởi động.
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

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 28, 30, 30)
        root.setSpacing(12)

        # Hàng đầu: Logo + Tên app + Phiên bản + Mô tả
        top_row = QHBoxLayout()
        top_row.setSpacing(18)

        self.lbl_logo = QLabel(self)
        self.lbl_logo.setFixedSize(84, 84)
        self.lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_logo.setStyleSheet("background: transparent;")
        logo_path = resolve_splash_logo_path()
        if logo_path:
            logo_pix = QPixmap(logo_path)
            if not logo_pix.isNull():
                self.lbl_logo.setPixmap(
                    logo_pix.scaled(80, 80, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                )
        top_row.addWidget(self.lbl_logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        title_line = QHBoxLayout()
        title_line.setSpacing(10)
        self.lbl_title = QLabel("ESP32 Manager Tool", self)
        self.lbl_title.setStyleSheet(
            "color: #F8FAFC; font-size: 19pt; font-weight: 700; background: transparent;"
        )
        title_line.addWidget(self.lbl_title)

        self.lbl_version = QLabel(f"v{APP_VERSION}", self)
        self.lbl_version.setStyleSheet(
            "color: #38BDF8; background-color: #16304B; border: 1px solid #0284C7;"
            "border-radius: 9px; padding: 2px 9px; font-size: 9pt; font-weight: 700;"
        )
        title_line.addWidget(self.lbl_version)
        title_line.addStretch(1)
        title_col.addLayout(title_line)

        self.lbl_subtitle = QLabel("Bộ công cụ Kỹ thuật & Quản lý Phần cứng Espressif", self)
        self.lbl_subtitle.setStyleSheet("color: #CBD5E1; font-size: 9.5pt; font-weight: 500; background: transparent;")
        title_col.addWidget(self.lbl_subtitle)

        self.lbl_modules = QLabel("Chip Inspector · Serial Monitor · Flasher · Partition · Direct Clone", self)
        self.lbl_modules.setStyleSheet("color: #94A3B8; font-size: 8.5pt; background: transparent;")
        title_col.addWidget(self.lbl_modules)

        title_col.addStretch(1)
        top_row.addLayout(title_col, 1)
        root.addLayout(top_row)

        root.addStretch(1)

        # Khối tiến trình hiện tại + %
        stage_row = QHBoxLayout()
        stage_row.setSpacing(8)
        self.lbl_stage = QLabel(self._current_stage, self)
        self.lbl_stage.setStyleSheet("color: #E2E8F0; font-size: 9pt; font-weight: 500; background: transparent;")
        stage_row.addWidget(self.lbl_stage, 1)

        self.lbl_pct = QLabel("0%", self)
        self.lbl_pct.setStyleSheet("color: #38BDF8; font-size: 9pt; font-weight: 700; background: transparent;")
        self.lbl_pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        stage_row.addWidget(self.lbl_pct)
        root.addLayout(stage_row)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background-color: #22324D;
                border: none;
                border-radius: 4px;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0284C7, stop:1 #38BDF8
                );
                border-radius: 4px;
            }
        """)
        root.addWidget(self.progress_bar)
        self._apply_taskbar_window_style()

    def _apply_taskbar_window_style(self) -> None:
        """Bảo đảm cửa sổ splash hiện ngay trên Windows Taskbar và không bị khóa luôn-trên-cùng."""
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
            HWND_NOTOPMOST = -2
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
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
            user32.SetWindowPos(
                hwnd,
                HWND_NOTOPMOST,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_FRAMECHANGED,
            )
        except Exception:
            pass

    def showEvent(self, event) -> None:
        self._apply_taskbar_window_style()
        super().showEvent(event)

    def mousePressEvent(self, event) -> None:
        # Không gọi super().mousePressEvent (mặc định của QSplashScreen sẽ ẩn splash khi click);
        # thay vào đó cho phép kéo di chuyển nhẹ màn hình khởi động.
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

    def set_stage(self, progress: int | float, stage_text: str = "", process_events: bool = True):
        """Cập nhật tiến độ (0-100) và mô tả bước khởi động đang thực thi."""
        clamped = max(0, min(100, int(round(float(progress)))))
        self._current_progress = clamped
        self.progress_bar.setValue(clamped)
        self.lbl_pct.setText(f"{clamped}%")
        if stage_text:
            self._current_stage = str(stage_text)
            self.lbl_stage.setText(self._current_stage)
        if process_events:
            app = QApplication.instance()
            if app is not None:
                self.repaint()
                app.processEvents()
