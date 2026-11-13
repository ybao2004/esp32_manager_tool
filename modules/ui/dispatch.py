# -*- coding: utf-8 -*-
"""
Bộ điều phối giao diện an toàn đa luồng (Thread-safe UI Dispatcher) cho PyQt6.
Đảm bảo mọi tác vụ cập nhật widget từ luồng nền (background threads)
được chuyển an toàn về luồng sự kiện chính (Main GUI Thread).
"""
from PyQt6.QtCore import QObject, pyqtSignal, Qt, QTimer
import threading
import logging

logger = logging.getLogger(__name__)


class UiDispatcher(QObject):
    """
    Dispatcher sử dụng cơ chế tín hiệu Qt (QueuedConnection)
    để điều phối hàm callback về luồng chính an toàn.
    """
    _sig = pyqtSignal(object, tuple, int)
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = UiDispatcher()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sig.connect(self._run, Qt.ConnectionType.QueuedConnection)
        UiDispatcher._instance = self

    def _run(self, fn, args, delay_ms: int):
        if delay_ms > 0:
            QTimer.singleShot(delay_ms, lambda: _safe_call(fn, args))
        else:
            _safe_call(fn, args)

    def post(self, fn, *args, delay_ms: int = 0):
        """Đẩy hàm fn(*args) vào hàng đợi thực thi trên luồng chính."""
        self._sig.emit(fn, args, int(delay_ms))

    def drain(self):
        """Xử lý toàn bộ sự kiện GUI đang chờ trong hàng đợi."""
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app:
            app.processEvents()


def ui_call(fn, *args, delay_ms: int = 0):
    """Tiện ích toàn cục gửi hàm về luồng UI chính."""
    UiDispatcher.instance().post(fn, *args, delay_ms=delay_ms)


def _safe_call(fn, args):
    try:
        fn(*args)
    except RuntimeError:
        # Xảy ra nếu widget C++ bên dưới đã bị xóa
        pass
    except Exception as e:
        logger.exception(f"Lỗi khi thực thi ui_call callback: {e}")
