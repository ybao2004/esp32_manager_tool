# -*- coding: utf-8 -*-
"""
Mô hình biến trạng thái phản ứng (Reactive State Variables) nhẹ nhàng cho PyQt6 (v1.6).
Thay thế hoàn toàn lớp giả lập qt_toolkit cũ (2.978 dòng).
"""
from typing import Any, Callable, List

END = "end"
INSERT = "insert"


class StateVar:
    """Biến lưu trữ trạng thái nhẹ có hỗ trợ callback theo dõi thay đổi."""

    def __init__(self, value: Any = None, name: str = ""):
        self._value = value
        self._name = name
        self._callbacks: List[Callable] = []

    def get(self) -> Any:
        return self._value

    def set(self, value: Any) -> None:
        self._value = value
        for cb in list(self._callbacks):
            try:
                cb()
            except TypeError:
                try:
                    cb(self._name, "", "w")
                except Exception:
                    pass
            except Exception:
                pass

    def trace_add(self, mode: str, callback: Callable) -> str:
        if callable(callback) and callback not in self._callbacks:
            self._callbacks.append(callback)
        return f"trace_{len(self._callbacks)}"

    def trace(self, mode: str, callback: Callable) -> str:
        return self.trace_add(mode, callback)


class BooleanVar(StateVar):
    def __init__(self, master: Any = None, value: bool = False, name: str = ""):
        super().__init__(bool(value), name=name)

    def get(self) -> bool:
        return bool(self._value)

    def set(self, value: Any) -> None:
        super().set(bool(value))


class StringVar(StateVar):
    def __init__(self, master: Any = None, value: str = "", name: str = ""):
        super().__init__(str(value) if value is not None else "", name=name)

    def get(self) -> str:
        return str(self._value) if self._value is not None else ""

    def set(self, value: Any) -> None:
        super().set(str(value) if value is not None else "")


class IntVar(StateVar):
    def __init__(self, master: Any = None, value: int = 0, name: str = ""):
        try:
            v = int(value)
        except (ValueError, TypeError):
            v = 0
        super().__init__(v, name=name)

    def get(self) -> int:
        try:
            return int(self._value)
        except (ValueError, TypeError):
            return 0

    def set(self, value: Any) -> None:
        try:
            super().set(int(value))
        except (ValueError, TypeError):
            super().set(0)
