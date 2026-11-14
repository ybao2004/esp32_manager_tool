# -*- coding: utf-8 -*-
"""
Hộp thoại Giới thiệu (AboutDialog) và Kiểm tra Cập nhật (UpdateDialog) thuần PyQt6 (v1.5.1).
Thay thế hoàn toàn modules/dialogs/settings_dialog.py cũ.
"""
import os
import threading
import weakref
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QPlainTextEdit, QProgressBar, QWidget, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap

from modules.config import (
    APP_NAME, APP_VERSION, APP_AUTHOR, APP_LICENSE, GITHUB_REPO
)
from modules.update_util import check_for_updates, download_update_asset, is_newer_version
from modules.ui import dialogs_service as dlg
from modules.ui.dispatch import UiDispatcher
from modules.ui.widgets.card import Card
from modules.ui.icons import bind_themed_icon
from modules.ui.splash import resolve_splash_logo_path
from modules.ui.theme.manager import ThemeManager


_ABOUT_FEATURE_ITEMS = [
    (
        "chip",
        "Kiểm tra Chip",
        "Dò Silicon Revision, Crystal, Flash/PSRAM, vùng nhớ Heap, MAC & đối soát OUI Espressif.",
    ),
    (
        "window_console",
        "Serial Monitor & Log",
        "Theo dõi UART thời gian thực, 15 phím IoT (Wi-Fi/TCP) và nhật ký tập trung từ mọi tab.",
    ),
    (
        "flash",
        "Nạp Firmware Flash",
        "Nạp đồng thời tối đa 4 tệp .bin theo offset, kiểm tra chồng lấn và xóa sạch toàn bộ Flash.",
    ),
    (
        "partition",
        "Phân vùng (Wizard)",
        "Sơ đồ DiskMap trực quan, tự dò chip, tự căn biên 4K/64K và kiểm soát giới hạn dung lượng.",
    ),
    (
        "copy",
        "Sao lưu & Chép đa mạch",
        "Đọc/ghi/xóa NVS & Hex phân trang, xuất hồ sơ SHA-256 và nhân bản đồng loạt nhiều board.",
    ),
    (
        "settings",
        "Cài đặt & Cập nhật",
        "Giao diện Kỹ thuật Sáng/Tối, phím chức năng F1–F15, lọc cổng COM và cập nhật từ GitHub.",
    ),
]


class AboutDialog(QDialog):
    """Hộp thoại Giới thiệu phần mềm & Bản quyền thuần PyQt6."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Giới thiệu & Bản quyền")
        self.resize(740, 560)
        self.setMinimumSize(680, 500)

        self._repo_url = f"https://github.com/{GITHUB_REPO}.git"
        self._web_url = f"https://github.com/{GITHUB_REPO}"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # 1. Hero Banner Card
        self.hero_frame = QFrame(self)
        hero_layout = QHBoxLayout(self.hero_frame)
        hero_layout.setContentsMargins(16, 14, 16, 14)
        hero_layout.setSpacing(14)

        self.lbl_app_logo = QLabel(self.hero_frame)
        self.lbl_app_logo.setFixedSize(68, 68)
        self.lbl_app_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_app_logo()
        hero_layout.addWidget(self.lbl_app_logo, 0, Qt.AlignmentFlag.AlignTop)

        hero_info = QVBoxLayout()
        hero_info.setContentsMargins(0, 0, 0, 0)
        hero_info.setSpacing(6)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)

        self.lbl_title = QLabel(APP_NAME, self.hero_frame)
        self.lbl_title.setProperty("role", "title")
        title_row.addWidget(self.lbl_title)

        self.lbl_badge_ver = QLabel(f"v{APP_VERSION}", self.hero_frame)
        self.lbl_badge_lic = QLabel(APP_LICENSE, self.hero_frame)
        self.lbl_badge_auth = QLabel(f"Tác giả: {APP_AUTHOR}", self.hero_frame)
        for badge in (self.lbl_badge_ver, self.lbl_badge_lic, self.lbl_badge_auth):
            title_row.addWidget(badge)
        title_row.addStretch(1)
        hero_info.addLayout(title_row)

        self.lbl_tagline = QLabel(
            "Bộ công cụ kỹ thuật chẩn đoán phần cứng, nạp Flash, thiết kế phân vùng & nhân bản đa mạch Espressif.",
            self.hero_frame,
        )
        self.lbl_tagline.setWordWrap(True)
        hero_info.addWidget(self.lbl_tagline)

        repo_row = QHBoxLayout()
        repo_row.setContentsMargins(0, 2, 0, 0)
        repo_row.setSpacing(8)

        self.lbl_repo_icon = QLabel(self.hero_frame)
        bind_themed_icon(self.lbl_repo_icon, "open", size=14, role="accent")
        repo_row.addWidget(self.lbl_repo_icon)

        self.lbl_repo_link = QLabel(self.hero_frame)
        self.lbl_repo_link.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_repo_link.setOpenExternalLinks(True)
        self.lbl_repo_link.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.lbl_repo_link.setCursor(Qt.CursorShape.PointingHandCursor)
        repo_row.addWidget(self.lbl_repo_link)

        self.btn_copy_repo = QPushButton("Sao chép link", self.hero_frame)
        bind_themed_icon(self.btn_copy_repo, "copy", size=13, role="muted")
        self.btn_copy_repo.setFixedHeight(24)
        self.btn_copy_repo.clicked.connect(self._on_copy_repo)
        repo_row.addWidget(self.btn_copy_repo)
        repo_row.addStretch(1)
        hero_info.addLayout(repo_row)

        hero_layout.addLayout(hero_info, 1)
        layout.addWidget(self.hero_frame)

        # 2. Lưới 6 thẻ tính năng cốt lõi theo từng Tab
        self.lbl_features_heading = QLabel("Tính năng & Công nghệ cốt lõi", self)
        self.lbl_features_heading.setProperty("role", "section")
        layout.addWidget(self.lbl_features_heading)

        features_grid = QGridLayout()
        features_grid.setContentsMargins(0, 0, 0, 0)
        features_grid.setHorizontalSpacing(10)
        features_grid.setVerticalSpacing(8)

        self._feature_cards: list[tuple[QFrame, QLabel, QLabel, QLabel]] = []
        for idx, (icon_name, f_title, f_desc) in enumerate(_ABOUT_FEATURE_ITEMS):
            f_card = QFrame(self)
            card_row = QHBoxLayout(f_card)
            card_row.setContentsMargins(11, 9, 11, 9)
            card_row.setSpacing(10)

            ic_badge = QLabel(f_card)
            ic_badge.setFixedSize(30, 30)
            ic_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bind_themed_icon(ic_badge, icon_name, size=17, role="accent")
            card_row.addWidget(ic_badge, 0, Qt.AlignmentFlag.AlignTop)

            txt_col = QVBoxLayout()
            txt_col.setContentsMargins(0, 0, 0, 0)
            txt_col.setSpacing(2)

            lbl_ft = QLabel(f_title, f_card)
            lbl_fd = QLabel(f_desc, f_card)
            lbl_fd.setWordWrap(True)
            txt_col.addWidget(lbl_ft)
            txt_col.addWidget(lbl_fd, 1)

            card_row.addLayout(txt_col, 1)
            features_grid.addWidget(f_card, idx // 2, idx % 2)
            self._feature_cards.append((f_card, ic_badge, lbl_ft, lbl_fd))

        features_grid.setColumnStretch(0, 1)
        features_grid.setColumnStretch(1, 1)
        layout.addLayout(features_grid, 1)

        # 3. Dải nền tảng công nghệ gọn gàng
        self.tech_bar = QFrame(self)
        tech_layout = QHBoxLayout(self.tech_bar)
        tech_layout.setContentsMargins(12, 7, 12, 7)
        tech_layout.setSpacing(8)

        self.lbl_tech_title = QLabel("Nền tảng công nghệ:", self.tech_bar)
        tech_layout.addWidget(self.lbl_tech_title)

        self._tech_pills: list[QLabel] = []
        for tech_name in ("Python", "PyQt6", "esptool", "PySerial", "NVS / Partition Parser"):
            pill = QLabel(tech_name, self.tech_bar)
            tech_layout.addWidget(pill)
            self._tech_pills.append(pill)
        tech_layout.addStretch(1)
        layout.addWidget(self.tech_bar)

        # 4. Hàng nút chân trang
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 2, 0, 0)
        self.btn_open_update = QPushButton("Kiểm tra cập nhật", self)
        bind_themed_icon(self.btn_open_update, "arrow_download")
        self.btn_open_update.clicked.connect(self._on_open_update)
        btn_row.addWidget(self.btn_open_update)

        btn_row.addStretch(1)

        self.btn_close = QPushButton("Đóng", self)
        self.btn_close.setProperty("accent", "true")
        self.btn_close.setFixedWidth(110)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        tm = ThemeManager.instance()
        self._apply_theme(tm.tokens)
        tm.theme_changed.connect(self._apply_theme)

    def _load_app_logo(self):
        icon_path = resolve_splash_logo_path()
        if icon_path and os.path.isfile(icon_path):
            pix = QPixmap(icon_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    50,
                    50,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.lbl_app_logo.setPixmap(scaled)
                return
        bind_themed_icon(self.lbl_app_logo, "chip", size=40, role="accent")

    def _apply_theme(self, tokens):
        try:
            _ = self.hero_frame.isVisible()
        except RuntimeError:
            return
        if tokens is None:
            return

        self.hero_frame.setStyleSheet(
            f"QFrame {{ background-color: {tokens.surface}; border: 1px solid {tokens.border}; border-radius: 8px; }}"
            f"QLabel {{ border: none; background: transparent; }}"
        )
        self.lbl_app_logo.setStyleSheet(
            f"background-color: {tokens.surface_alt}; border: 1px solid {tokens.border}; border-radius: 10px;"
        )
        self.lbl_title.setStyleSheet(
            f"font-size: 15pt; font-weight: 700; color: {tokens.text}; background: transparent; border: none;"
        )
        self.lbl_badge_ver.setStyleSheet(
            f"background-color: {tokens.selection}; color: {tokens.accent}; border: 1px solid {tokens.accent};"
            "border-radius: 4px; padding: 2px 8px; font-size: 8.5pt; font-weight: 700;"
        )
        neutral_pill_css = (
            f"background-color: {tokens.surface_alt}; color: {tokens.text}; border: 1px solid {tokens.border};"
            "border-radius: 4px; padding: 2px 8px; font-size: 8.5pt; font-weight: 600;"
        )
        self.lbl_badge_lic.setStyleSheet(neutral_pill_css)
        self.lbl_badge_auth.setStyleSheet(neutral_pill_css)
        self.lbl_tagline.setStyleSheet(
            f"font-size: 9pt; color: {tokens.text_secondary}; background: transparent; border: none;"
        )
        self.lbl_repo_link.setText(
            f'<a href="{self._web_url}" style="color: {tokens.accent}; text-decoration: none; font-weight: 600;">{self._repo_url}</a>'
        )
        self.btn_copy_repo.setStyleSheet("padding: 0 9px; font-size: 8.5pt;")

        self.lbl_features_heading.setStyleSheet(
            f"font-size: 9.5pt; font-weight: 700; color: {tokens.text}; background: transparent;"
        )

        for f_card, ic_badge, lbl_ft, lbl_fd in self._feature_cards:
            f_card.setStyleSheet(
                f"QFrame {{ background-color: {tokens.surface}; border: 1px solid {tokens.border}; border-radius: 6px; }}"
                f"QLabel {{ border: none; background: transparent; }}"
            )
            ic_badge.setStyleSheet(
                f"background-color: {tokens.selection}; border: none; border-radius: 6px;"
            )
            lbl_ft.setStyleSheet(
                f"font-size: 9pt; font-weight: 700; color: {tokens.text}; background: transparent; border: none;"
            )
            lbl_fd.setStyleSheet(
                f"font-size: 8.5pt; color: {tokens.text_secondary}; background: transparent; border: none;"
            )

        self.tech_bar.setStyleSheet(
            f"QFrame {{ background-color: {tokens.surface_alt}; border: 1px solid {tokens.border}; border-radius: 6px; }}"
            f"QLabel {{ border: none; background: transparent; }}"
        )
        self.lbl_tech_title.setStyleSheet(
            f"font-size: 8.5pt; font-weight: 700; color: {tokens.text_secondary}; background: transparent; border: none;"
        )
        tech_pill_css = (
            f"background-color: {tokens.surface}; color: {tokens.text}; border: 1px solid {tokens.border};"
            "border-radius: 4px; padding: 2px 7px; font-size: 8pt; font-weight: 600;"
        )
        for pill in self._tech_pills:
            pill.setStyleSheet(tech_pill_css)

    def _on_copy_repo(self):
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(self._repo_url)
        self.btn_copy_repo.setText("Đã chép")
        self_ref = weakref.ref(self)

        def _restore():
            obj = self_ref()
            if obj is not None:
                try:
                    obj.btn_copy_repo.setText("Sao chép link")
                except RuntimeError:
                    pass

        QTimer.singleShot(1400, _restore)

    def _on_open_update(self):
        self.accept()
        parent = self.parent()
        if parent is not None and hasattr(parent, "open_update_dialog"):
            parent.open_update_dialog()


class UpdateDialog(QDialog):
    """Hộp thoại Kiểm tra và Tải bản cập nhật phần mềm từ GitHub Releases."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Kiểm tra cập nhật phần mềm")
        self.resize(680, 500)
        self.setMinimumSize(600, 420)

        self.latest_update_info = {}
        self.download_in_progress = threading.Event()
        self._cancel_event = threading.Event()
        self._dispatcher = UiDispatcher.instance()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 1. Thẻ thông tin phiên bản
        top_card = Card("Kiểm Tra Phiên Bản Mới", parent=self)
        lbl_ver = QLabel(
            f"Phiên bản hiện tại: v{APP_VERSION}   |   Kho lưu trữ: https://github.com/{GITHUB_REPO}",
            top_card
        )
        lbl_ver.setProperty("role", "section")
        top_card.content_layout.addWidget(lbl_ver)

        check_row = QHBoxLayout()
        self.lbl_check_status = QLabel("Nhấn nút bên phải để kiểm tra bản phát hành mới nhất từ GitHub.", top_card)
        check_row.addWidget(self.lbl_check_status, 1)
        self.btn_check = QPushButton("Kiểm Tra Bản Cập Nhật", top_card)
        self.btn_check.setProperty("accent", "true")
        self.btn_check.clicked.connect(self.on_check_update_click)
        check_row.addWidget(self.btn_check)
        top_card.content_layout.addLayout(check_row)
        layout.addWidget(top_card)

        # 2. Chi tiết bản phát hành
        rel_card = Card("Chi Tiết Bản Phát Hành (Release Notes)", parent=self)
        self.txt_release_notes = QPlainTextEdit(rel_card)
        self.txt_release_notes.setReadOnly(True)
        self.txt_release_notes.setProperty("role", "log")
        self.txt_release_notes.setPlainText(
            "Chưa kiểm tra cập nhật.\nBấm 'Kiểm Tra Bản Cập Nhật' để lấy thông tin phát hành mới nhất."
        )
        rel_card.content_layout.addWidget(self.txt_release_notes)
        layout.addWidget(rel_card, 1)

        # 3. Khung tải về
        dl_card = Card("Tải Bản Cập Nhật", parent=self)
        self.pb_download = QProgressBar(dl_card)
        self.pb_download.setRange(0, 100)
        self.pb_download.setValue(0)
        dl_card.content_layout.addWidget(self.pb_download)

        dl_row = QHBoxLayout()
        self.lbl_download_status = QLabel("Sẵn sàng.", dl_card)
        dl_row.addWidget(self.lbl_download_status, 1)
        self.btn_download = QPushButton("Tải Bản Cập Nhật Về Máy", dl_card)
        self.btn_download.setEnabled(False)
        self.btn_download.clicked.connect(self.on_download_click)
        dl_row.addWidget(self.btn_download)
        dl_card.content_layout.addLayout(dl_row)
        layout.addWidget(dl_card)

        # 4. Nút đóng
        bottom_row = QHBoxLayout()
        bottom_row.addStretch(1)
        self.btn_close = QPushButton("Đóng", self)
        self.btn_close.setFixedWidth(110)
        self.btn_close.clicked.connect(self.accept)
        bottom_row.addWidget(self.btn_close)
        layout.addLayout(bottom_row)

    def on_check_update_click(self):
        self.btn_check.setEnabled(False)
        self.lbl_check_status.setText("Đang kết nối GitHub Releases API...")

        def worker():
            res = check_for_updates(current_version=APP_VERSION, repo=GITHUB_REPO)

            def update_ui():
                self.btn_check.setEnabled(True)
                self.latest_update_info.clear()
                self.latest_update_info.update(res)

                if res.get("status") == "success":
                    tag = res.get("latest_version", "")
                    has_up = res.get("has_update", False)
                    rel_name = res.get("release_name", tag)
                    pub_date = res.get("published_at", "")
                    notes = res.get("release_notes", "")
                    asset_name = res.get("asset_name", "")
                    asset_size = res.get("asset_size", 0)

                    if has_up:
                        self.lbl_check_status.setText(f"Có bản cập nhật mới: {tag} (Hiện tại: v{APP_VERSION})")
                        self.btn_download.setEnabled(bool(res.get("download_url")))
                    else:
                        if tag and is_newer_version(APP_VERSION, tag):
                            self.lbl_check_status.setText(f"Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION}). Bản phát hành trên GitHub: {tag}.")
                        else:
                            self.lbl_check_status.setText(f"Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION}).")
                        self.btn_download.setEnabled(False)

                    size_str = f" ({asset_size / (1024*1024):.1f} MB)" if asset_size > 0 else ""
                    lines = [
                        f"[ BẢN PHÁT HÀNH: {rel_name} ({tag}) ]",
                        f"Ngày phát hành: {pub_date}",
                        f"File tải về: {asset_name if asset_name else 'Mã nguồn (.zip)'}{size_str}",
                        "",
                        "Nội dung cập nhật & cải tiến:",
                        notes if notes else "(Không có ghi chú phát hành)."
                    ]
                    self.txt_release_notes.setPlainText("\n".join(lines))
                elif res.get("status") == "no_releases":
                    self.lbl_check_status.setText("Kho GitHub chưa tạo Release chính thức.")
                    self.txt_release_notes.setPlainText(res.get("message", ""))
                    self.btn_download.setEnabled(False)
                else:
                    self.lbl_check_status.setText("Lỗi khi kiểm tra cập nhật.")
                    self.txt_release_notes.setPlainText(f"Lỗi: {res.get('message', 'Không xác định')}")
                    self.btn_download.setEnabled(False)

            self._dispatcher.post(update_ui)

        threading.Thread(target=worker, daemon=True).start()

    def on_download_click(self):
        if self.download_in_progress.is_set():
            return

        download_url = self.latest_update_info.get("download_url")
        if not download_url:
            dlg.showinfo("Thông báo", "Không tìm thấy đường dẫn tải file cập nhật trực tiếp.", parent=self)
            return

        default_name = self.latest_update_info.get("asset_name", "Esp32_manager_tool_update.exe")
        ext = os.path.splitext(default_name)[1] or ".exe"
        dest_path = dlg.asksaveasfilename(
            title="Chọn vị trí lưu file cập nhật",
            defaultextension=ext,
            initialfile=default_name,
            filetypes=[("Update Files (*.exe;*.zip)", "*.exe *.zip"), ("All Files (*.*)", "*.*")],
            parent=self
        )
        if not dest_path:
            return

        self._cancel_event.clear()
        self.download_in_progress.set()
        self.btn_download.setEnabled(False)
        self.btn_check.setEnabled(False)
        self.lbl_download_status.setText("Đang kết nối tải file...")
        self.pb_download.setValue(0)

        def worker():
            def progress_cb(percent, downloaded, total):
                if self._cancel_event.is_set():
                    return
                def update_progress():
                    self.pb_download.setValue(int(round(percent)))
                    if total > 0:
                        self.lbl_download_status.setText(
                            f"Đang tải: {downloaded / (1024*1024):.2f} MB / {total / (1024*1024):.2f} MB ({percent:.1f}%)"
                        )
                    else:
                        self.lbl_download_status.setText(f"Đang tải: {downloaded / (1024*1024):.2f} MB...")
                self._dispatcher.post(update_progress)

            success, msg = download_update_asset(
                download_url,
                dest_path,
                progress_callback=progress_cb,
                cancel_event=self._cancel_event,
            )

            def download_finished():
                self.download_in_progress.clear()
                if self._cancel_event.is_set() or not self.isVisible():
                    return
                self.btn_download.setEnabled(True)
                self.btn_check.setEnabled(True)
                if success:
                    self.pb_download.setValue(100)
                    self.lbl_download_status.setText(f"Tải thành công: {os.path.basename(dest_path)}")
                    dlg.showinfo(
                        "Tải hoàn tất",
                        f"Đã tải thành công bản cập nhật về máy:\n{dest_path}\n\n"
                        "Bạn có thể đóng ứng dụng và chạy file này để sử dụng bản mới.",
                        parent=self
                    )
                else:
                    self.lbl_download_status.setText("Lỗi khi tải bản cập nhật.")
                    dlg.showerror("Lỗi tải file", f"Không thể tải bản cập nhật:\n{msg}", parent=self)

            self._dispatcher.post(download_finished)

        threading.Thread(target=worker, daemon=True).start()

    def reject(self):
        self._cancel_event.set()
        super().reject()

    def closeEvent(self, event):
        self._cancel_event.set()
        super().closeEvent(event)


class AboutUpdateMixin:
    """Mixin cung cấp các phương thức mở Cài đặt, Giới thiệu và Kiểm tra cập nhật cho MainWindow."""

    def open_settings_dialog(self, initial_tab_index: int = 0):
        """Chuyển thẳng đến trang Cài đặt trên Sidebar và mở đúng Tab con."""
        if hasattr(self, "notebook") and hasattr(self, "settings_tab"):
            self.notebook.select(self.settings_tab)
        if hasattr(self, "page_settings") and hasattr(self.page_settings, "select_sub_tab"):
            self.page_settings.select_sub_tab(initial_tab_index)

    def open_about_dialog(self):
        dialog = AboutDialog(parent=self if isinstance(self, QWidget) else None)
        dialog.exec()

    def open_update_dialog(self):
        """Chuyển sang trang Cài đặt và mở đúng Sub-tab 3 (Cập nhật Phần mềm) để kiểm tra cập nhật."""
        self.open_settings_dialog(2)
        if hasattr(self, "trigger_update_check"):
            self.trigger_update_check(silent=False)
        elif hasattr(self, "page_settings") and hasattr(self.page_settings, "start_update_check"):
            self.page_settings.start_update_check(silent=False)
