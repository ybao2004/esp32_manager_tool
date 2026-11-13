# -*- coding: utf-8 -*-
"""
Hộp thoại Giới thiệu (AboutDialog) và Kiểm tra Cập nhật (UpdateDialog) thuần PyQt6 (v1.8).
Thay thế hoàn toàn modules/dialogs/settings_dialog.py cũ.
"""
import os
import threading
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt

from modules.config import (
    APP_NAME, APP_VERSION, APP_AUTHOR, APP_LICENSE, GITHUB_REPO
)
from modules.help_content import about_features_text
from modules.update_util import check_for_updates, download_update_asset
from modules.ui import dialogs_service as dlg
from modules.ui.dispatch import UiDispatcher
from modules.ui.widgets.card import Card


class AboutDialog(QDialog):
    """Hộp thoại Giới thiệu phần mềm thuần PyQt6."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} - Giới thiệu")
        self.resize(600, 460)
        self.setMinimumSize(520, 380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        lbl_title = QLabel(APP_NAME, self)
        lbl_title.setProperty("role", "title")
        layout.addWidget(lbl_title)

        lbl_meta = QLabel(
            f"Phiên bản: v{APP_VERSION}   |   Tác giả: {APP_AUTHOR}   |   Giấy phép: {APP_LICENSE}",
            self
        )
        lbl_meta.setProperty("role", "section")
        layout.addWidget(lbl_meta)

        card = Card("Tính năng & Công nghệ", parent=self)
        self.txt_features = QPlainTextEdit(card)
        self.txt_features.setReadOnly(True)
        self.txt_features.setProperty("role", "log")
        self.txt_features.setPlainText(about_features_text())
        card.content_layout.addWidget(self.txt_features)
        layout.addWidget(card, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_close = QPushButton("Đóng", self)
        self.btn_close.setProperty("accent", "true")
        self.btn_close.setFixedWidth(110)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)


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
                        self.btn_download.setEnabled(True)
                    else:
                        self.lbl_check_status.setText(f"Bạn đang sử dụng phiên bản mới nhất (v{APP_VERSION}).")
                        self.btn_download.setEnabled(bool(res.get("download_url")))

                    size_str = f" ({asset_size / (1024*1024):.1f} MB)" if asset_size > 0 else ""
                    lines = [
                        f"[ BẢN PHÁT HÀNH: {rel_name} ({tag}) ]",
                        f"Ngày phát hành: {pub_date}",
                        f"File tải về: {asset_name if asset_name else 'Mã nguồn (.zip)'}{size_str}",
                        "-" * 72,
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
        dialog = UpdateDialog(parent=self if isinstance(self, QWidget) else None)
        dialog.exec()
