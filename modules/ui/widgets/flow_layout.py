# -*- coding: utf-8 -*-
"""
FlowLayout: Bố cục tự xuống dòng (responsive) cho thanh công cụ / hàng nút.

- Các widget luôn giữ đúng kích thước sizeHint (không bị co cắt chữ như QHBoxLayout
  khi cửa sổ hẹp hơn tổng chiều rộng nội dung).
- Khi không đủ chỗ trên một dòng, phần tử tiếp theo được đưa xuống dòng mới.
- Hỗ trợ addStretch(): khoảng trống còn dư của dòng được dồn vào điểm stretch,
  nhờ đó nhóm nút phía sau stretch được căn phải giống QHBoxLayout.
- Hỗ trợ addSpacing(px) cho khoảng cách cố định.
"""
from PyQt6.QtCore import QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QHBoxLayout, QLayout, QSizePolicy, QSpacerItem, QWidget, QWidgetItem


class _StretchItem(QSpacerItem):
    """Điểm đánh dấu stretch (chiếm phần chiều rộng còn dư của dòng)."""

    def __init__(self):
        super().__init__(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)


class _FixedSpaceItem(QSpacerItem):
    """Khoảng cách cố định theo chiều ngang."""

    def __init__(self, px: int):
        super().__init__(int(px), 0, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)


class FlowLayout(QLayout):
    def __init__(self, parent: QWidget = None, h_spacing: int = 6, v_spacing: int = 6):
        super().__init__(parent)
        self._items: list = []
        self._h_spacing = int(h_spacing)
        self._v_spacing = int(v_spacing)
        self._last_height: int = 0
        self.setContentsMargins(0, 0, 0, 0)

    # ------------------------------------------------------------------ API
    def addItem(self, item):  # noqa: N802 (Qt API)
        self._items.append(item)
        self.invalidate()

    def addWidget(self, widget: QWidget):  # noqa: N802
        self.addChildWidget(widget)
        self.addItem(QWidgetItem(widget))

    def addStretch(self, _stretch: int = 1):  # noqa: N802
        self.addItem(_StretchItem())

    def addSpacing(self, px: int):  # noqa: N802
        self.addItem(_FixedSpaceItem(px))

    def setSpacing(self, spacing: int):  # noqa: N802
        self._h_spacing = self._v_spacing = int(spacing)
        self.invalidate()

    def spacing(self) -> int:
        return self._h_spacing

    def horizontalSpacing(self) -> int:  # noqa: N802
        return self._h_spacing

    def verticalSpacing(self) -> int:  # noqa: N802
        return self._v_spacing

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int):  # noqa: N802
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            self.invalidate()
            return item
        return None

    def expandingDirections(self):  # noqa: N802
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect):  # noqa: N802
        super().setGeometry(rect)
        needed_h = self._do_layout(rect, test_only=False)
        if needed_h != self._last_height:
            self._last_height = needed_h
            self.invalidate()
            parent = self.parent()
            if isinstance(parent, QLayout):
                parent.invalidate()
            pw = self.parentWidget()
            if pw is not None:
                pw.updateGeometry()

    def sizeHint(self) -> QSize:  # noqa: N802
        """Kích thước ưu tiên: cập nhật chiều cao theo số dòng thực tế gần nhất."""
        w = 0
        h = 0
        visible = 0
        for item in self._items:
            if self._is_hidden(item):
                continue
            hint = item.sizeHint()
            if visible and not isinstance(item, _StretchItem):
                w += self._h_spacing
            w += hint.width()
            h = max(h, hint.height())
            visible += 1
        m = self.contentsMargins()
        out_h = h + m.top() + m.bottom()
        if self._last_height > 0:
            out_h = max(out_h, self._last_height)
        return QSize(w + m.left() + m.right(), out_h)

    def minimumSize(self) -> QSize:  # noqa: N802
        """Kích thước tối thiểu: phần tử rộng nhất và đủ chiều cao cho các dòng đã ngắt."""
        size = QSize()
        for item in self._items:
            if self._is_hidden(item) or isinstance(item, QSpacerItem):
                continue
            size = size.expandedTo(item.minimumSize().expandedTo(item.sizeHint()))
        m = self.contentsMargins()
        out_h = size.height() + m.top() + m.bottom()
        if self._last_height > 0:
            out_h = max(out_h, self._last_height)
        return QSize(size.width() + m.left() + m.right(), out_h)

    # ------------------------------------------------------------ internals
    @staticmethod
    def _is_hidden(item) -> bool:
        w = item.widget()
        return w is not None and w.isHidden()

    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        avail_w = max(1, eff.width())

        # 1. Chia phần tử thành các dòng
        lines: list[list] = []
        cur: list = []
        cur_w = 0
        for item in self._items:
            if self._is_hidden(item):
                continue
            is_stretch = isinstance(item, _StretchItem)
            w = 0 if is_stretch else item.sizeHint().width()
            gap = self._h_spacing if (cur and not is_stretch) else 0
            if not is_stretch and cur and cur_w + gap + w > avail_w:
                lines.append(cur)
                cur, cur_w, gap = [], 0, 0
            if is_stretch and not cur:
                # Bỏ qua stretch ở đầu dòng mới: nhóm phía sau bắt đầu từ lề trái
                if lines:
                    continue
            cur.append(item)
            cur_w += gap + w
        if cur:
            lines.append(cur)

        # 2. Đặt vị trí
        y = eff.y()
        for line_idx, line in enumerate(lines):
            widgets = [it for it in line if not isinstance(it, _StretchItem)]
            line_h = max((it.sizeHint().height() for it in widgets), default=0)
            used = 0
            for i, it in enumerate(widgets):
                used += it.sizeHint().width() + (self._h_spacing if i else 0)
            stretches = [it for it in line if isinstance(it, _StretchItem)]
            extra = max(0, avail_w - used)
            per_stretch = (extra // len(stretches)) if stretches else 0

            x = eff.x()
            first = True
            for it in line:
                if isinstance(it, _StretchItem):
                    x += per_stretch
                    continue
                if not first:
                    x += self._h_spacing
                hint = it.sizeHint()
                if not test_only:
                    pol = it.widget().sizePolicy() if it.widget() else None
                    ih = hint.height()
                    if pol is not None and pol.verticalPolicy() in (
                        QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding
                    ):
                        ih = line_h
                    iy = y + (line_h - ih) // 2
                    it.setGeometry(QRect(QPoint(x, iy), QSize(hint.width(), ih)))
                x += hint.width()
                first = False
            y += line_h
            if line_idx < len(lines) - 1:
                y += self._v_spacing
        return y - rect.y() + m.bottom()


def make_group(parent: QWidget, *widgets, spacing: int = 4) -> QWidget:
    """Gom nhiều widget (vd: nhãn + combobox) thành một khối không bị tách khi xuống dòng."""
    box = QWidget(parent)
    box.setProperty("role", "transparent")
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    for w in widgets:
        if isinstance(w, int):
            lay.addSpacing(w)
        else:
            lay.addWidget(w)
    box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return box
