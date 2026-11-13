# -*- coding: utf-8 -*-
"""
Dịch vụ hộp thoại tập trung (Centralized Dialogs Service) cho PyQt6.
Thay thế hoàn toàn tkinter.messagebox và tkinter.filedialog.
Đơn giản hóa việc mock/kiểm thử tự động ở một điểm duy nhất.
"""
import os
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QInputDialog, QWidget
from typing import Optional, List


def _valid_parent(parent: Optional[QWidget]) -> Optional[QWidget]:
    """Đảm bảo parent là QWidget hợp lệ (trả về None nếu là đối tượng giả lập headless)."""
    return parent if isinstance(parent, QWidget) else None


def show_info(title: str, message: str, parent: Optional[QWidget] = None) -> None:
    box = QMessageBox(QMessageBox.Icon.Information, title, message, QMessageBox.StandardButton.Ok, _valid_parent(parent))
    box.exec()


def show_warning(title: str, message: str, parent: Optional[QWidget] = None) -> None:
    box = QMessageBox(QMessageBox.Icon.Warning, title, message, QMessageBox.StandardButton.Ok, _valid_parent(parent))
    box.exec()


def show_error(title: str, message: str, parent: Optional[QWidget] = None) -> None:
    box = QMessageBox(QMessageBox.Icon.Critical, title, message, QMessageBox.StandardButton.Ok, _valid_parent(parent))
    box.exec()


def ask_yes_no(title: str, message: str, danger: bool = False, parent: Optional[QWidget] = None) -> bool:
    """
    Hộp thoại xác nhận Có / Không.
    Nếu danger=True, nút xác nhận 'Có' được gắn thuộc tính danger='true' (màu đỏ).
    """
    box = QMessageBox(QMessageBox.Icon.Question, title, message, QMessageBox.StandardButton.NoButton, _valid_parent(parent))
    yes_btn = box.addButton("Có", QMessageBox.ButtonRole.YesRole)
    no_btn = box.addButton("Không", QMessageBox.ButtonRole.NoRole)
    box.setDefaultButton(no_btn)

    if danger:
        yes_btn.setProperty("danger", "true")

    box.exec()
    return box.clickedButton() == yes_btn


def ask_ok_cancel(title: str, message: str, parent: Optional[QWidget] = None) -> bool:
    box = QMessageBox(QMessageBox.Icon.Question, title, message, QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel, _valid_parent(parent))
    return box.exec() == QMessageBox.StandardButton.Ok


def ask_string(title: str, prompt: str, initialvalue: str = "", parent: Optional[QWidget] = None, **kwargs) -> Optional[str]:
    """Hiển thị hộp thoại nhập chuỗi một dòng, trả về None nếu người dùng hủy."""
    text, ok = QInputDialog.getText(_valid_parent(parent), str(title), str(prompt), text=str(initialvalue or ""))
    return text if ok else None


def ask_open_file(title: str = "Mở file", filters: str = "Tất cả file (*.*)", parent: Optional[QWidget] = None) -> str:
    path, _ = QFileDialog.getOpenFileName(_valid_parent(parent), title, "", filters)
    return path or ""


def ask_open_files(title: str = "Mở nhiều file", filters: str = "Tất cả file (*.*)", parent: Optional[QWidget] = None) -> List[str]:
    paths, _ = QFileDialog.getOpenFileNames(_valid_parent(parent), title, "", filters)
    return paths or []


def ask_save_file(title: str = "Lưu file", default_name: str = "", filters: str = "Tất cả file (*.*)", parent: Optional[QWidget] = None) -> str:
    path, _ = QFileDialog.getSaveFileName(_valid_parent(parent), title, default_name, filters)
    return path or ""


def ask_directory(title: str = "Chọn thư mục", parent: Optional[QWidget] = None) -> str:
    path = QFileDialog.getExistingDirectory(_valid_parent(parent), title)
    return path or ""


# Backward-compatible aliases for messagebox and filedialog APIs
showinfo = show_info
showwarning = show_warning
showerror = show_error
askyesno = ask_yes_no
askokcancel = ask_ok_cancel
askstring = ask_string


def askopenfilename(title: str = "Mở file", filetypes: tuple | list | str = "Tất cả file (*.*)", initialdir: str = "", **kwargs) -> str:
    flt_str = "Tất cả file (*.*)"
    if isinstance(filetypes, (list, tuple)):
        parts = []
        for item in filetypes:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                parts.append(f"{item[0]} ({item[1]})")
        if parts:
            flt_str = ";;".join(parts)
    elif isinstance(filetypes, str):
        flt_str = filetypes
    path, _ = QFileDialog.getOpenFileName(_valid_parent(kwargs.get("parent")), title, initialdir, flt_str)
    return path or ""


def asksaveasfilename(title: str = "Lưu file", initialfile: str = "", defaultextension: str = "", filetypes: tuple | list | str = "Tất cả file (*.*)", initialdir: str = "", **kwargs) -> str:
    flt_str = "Tất cả file (*.*)"
    if isinstance(filetypes, (list, tuple)):
        parts = []
        for item in filetypes:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                parts.append(f"{item[0]} ({item[1]})")
        if parts:
            flt_str = ";;".join(parts)
    default_name = os.path.join(initialdir, initialfile) if (initialdir and initialfile) else initialfile
    path, _ = QFileDialog.getSaveFileName(_valid_parent(kwargs.get("parent")), title, default_name, flt_str)
    return path or ""


def askdirectory(title: str = "Chọn thư mục", initialdir: str = "", **kwargs) -> str:
    path = QFileDialog.getExistingDirectory(_valid_parent(kwargs.get("parent")), title, initialdir)
    return path or ""

