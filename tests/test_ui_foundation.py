# -*- coding: utf-8 -*-
"""
Kiểm thử nền móng giao diện PyQt6 (Giai đoạn 1):
- Hàm thoát ký tự qt_text
- 6 bảng ThemeTokens
- Trình sinh build_qss
- Trình nạp biểu tượng get_icon từ file SVG Fluent UI
- Bộ điều phối luồng UiDispatcher
"""
import os
import sys
import threading
import time
import pytest
from PyQt6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from modules.ui.text import qt_text
from modules.ui.theme.tokens import get_tokens, ThemeTokens
from modules.ui.theme.qss import build_qss
from modules.ui.theme.manager import ThemeManager
from modules.ui.icons import get_icon
from modules.ui.dispatch import UiDispatcher


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv if sys.argv else ["test"])
    return app


def test_qt_text_escapes_ampersand():
    assert qt_text("Serial & Monitor") == "Serial && Monitor"
    assert qt_text("Flash && PSRAM") == "Flash && PSRAM"
    assert qt_text("No ampersand") == "No ampersand"
    assert qt_text("") == ""


def test_get_tokens_all_six_combinations():
    # v1.7: Chỉ giữ lại phong cách Kỹ thuật (engineering) Sáng/Tối; các giá trị cũ tự động chuẩn hóa về engineering
    for mode in ("light", "dark"):
        t = get_tokens("engineering", mode)
        assert isinstance(t, ThemeTokens)
        assert t.preset == "engineering"
        assert t.mode == mode
        assert t.window.startswith("#")
        assert t.accent.startswith("#")
        assert t.control_height > 0
        assert t.sidebar_width_expanded > t.sidebar_width_collapsed

    for legacy_preset in ("fluent", "vscode", "unknown"):
        t = get_tokens(legacy_preset, "dark")
        assert t.preset == "engineering"
        assert t.mode == "dark"


def test_build_qss_validity():
    for mode in ("light", "dark"):
        t = get_tokens("engineering", mode)
        qss = build_qss(t)
        assert isinstance(qss, str)
        assert len(qss) > 200
        assert "QMainWindow" in qss
        assert "#Sidebar" in qss
        assert t.accent in qss


def test_get_icon_renders_fluent_svgs(qapp):
    icons_to_test = [
        "inspector", "monitor", "flash", "partition", "backup",
        "settings", "menu", "refresh", "play", "stop", "plug_connected"
    ]
    for name in icons_to_test:
        ico = get_icon(name, color="#0067C0", size=20)
        assert not ico.isNull(), f"Icon {name} không được null!"
        pix = ico.pixmap(20, 20)
        assert not pix.isNull(), f"Pixmap của icon {name} không được null!"


def test_ui_dispatcher_cross_thread_dispatch(qapp):
    dispatcher = UiDispatcher()
    result = []
    done_event = threading.Event()

    def _worker():
        # Gọi từ luồng nền
        dispatcher.post(lambda val: result.append(val), "from_worker")
        done_event.set()

    th = threading.Thread(target=_worker)
    th.start()
    th.join(timeout=1.0)

    # Chạy vòng lặp sự kiện luồng chính để nhận tín hiệu
    deadline = time.time() + 1.0
    while not result and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.01)

    assert result == ["from_worker"]
