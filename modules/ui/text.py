# -*- coding: utf-8 -*-
"""
Tiện ích xử lý chuỗi văn bản cho giao diện PyQt6.
"""

def qt_text(s: str) -> str:
    """
    Escape ký tự '&' thành '&&' cho QPushButton, QCheckBox, QRadioButton,
    QGroupBox, QAction, QMenu, QTabWidget nhằm tránh Qt tự động nhận diện
    ký tự '&' là phím tắt (mnemonic underline).
    """
    if not s:
        return ""
    # Nếu chuỗi đã được escape (có '&&') thì không nhân đôi lần nữa
    # Chuẩn hóa: thay '&' đơn lẻ thành '&&'
    import re
    # Thay thế các '&' không đi liền với '&' khác
    return re.sub(r'(?<!&)&(?!&)', '&&', str(s))
