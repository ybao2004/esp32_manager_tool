# -*- coding: utf-8 -*-
"""
Bộ quản lý Theme tập trung (ThemeManager) cho PyQt6 (v1.8).
Sử dụng duy nhất phong cách Kỹ thuật (Engineering) với chế độ Sáng / Tối mượt mà.
Bao gồm EngineeringProxyStyle kết xuất Checkbox & RadioButton vector chống cắt mép trên mọi DPI.
"""
import os
import weakref
from PyQt6 import sip
from PyQt6.QtCore import QObject, QRectF, Qt
from PyQt6.QtWidgets import QApplication, QProxyStyle, QStyle, QStyleFactory
from PyQt6.QtGui import (
    QFont, QFontDatabase, QPalette, QColor, QPainter, QPainterPath, QPen, QBrush
)
from modules.ui.theme.tokens import ThemeTokens, get_tokens
from modules.ui.theme.qss import build_qss


class EngineeringProxyStyle(QProxyStyle):
    """Vẽ chỉ báo CheckBox và RadioButton bằng vector QPainter tròn/vuông đầy đặn ở mọi mức DPI."""

    def __init__(self, tokens: ThemeTokens):
        base = QStyleFactory.create("Fusion")
        super().__init__(base)
        self._tokens = tokens

    def set_tokens(self, tokens: ThemeTokens):
        self._tokens = tokens

    def pixelMetric(self, metric, option=None, widget=None):
        if metric in (
            QStyle.PixelMetric.PM_IndicatorWidth,
            QStyle.PixelMetric.PM_IndicatorHeight,
            QStyle.PixelMetric.PM_ExclusiveIndicatorWidth,
            QStyle.PixelMetric.PM_ExclusiveIndicatorHeight,
        ):
            return 18
        return super().pixelMetric(metric, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element == QStyle.PrimitiveElement.PE_IndicatorCheckBox and option is not None:
            self._draw_checkbox_indicator(option, painter)
            return
        if element == QStyle.PrimitiveElement.PE_IndicatorRadioButton and option is not None:
            self._draw_radio_indicator(option, painter)
            return
        super().drawPrimitive(element, option, painter, widget)

    def _draw_checkbox_indicator(self, option, painter: QPainter):
        t = self._tokens
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = QRectF(option.rect)
        sz = max(12.0, min(r.width(), r.height()) - 3.0)
        cx = r.center().x()
        cy = r.center().y()
        box = QRectF(cx - sz / 2.0, cy - sz / 2.0, sz, sz)

        checked = bool(option.state & QStyle.StateFlag.State_On)
        partial = bool(option.state & QStyle.StateFlag.State_NoChange)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        unchecked_border = "#64748B" if not t.is_dark else "#52637A"
        if checked or partial:
            fill_col = QColor(t.accent_hover if hover and enabled else t.accent)
            border_col = QColor(fill_col)
            if not enabled:
                fill_col.setAlpha(120)
                border_col.setAlpha(120)
        else:
            fill_col = QColor(t.surface_alt if not enabled else t.surface)
            border_col = QColor(t.accent if (hover and enabled) else unchecked_border)
            if not enabled:
                border_col.setAlpha(120)

        painter.setPen(QPen(border_col, 1.3))
        painter.setBrush(QBrush(fill_col))
        painter.drawRoundedRect(box, 3.0, 3.0)

        if checked:
            path = QPainterPath()
            path.moveTo(box.left() + box.width() * 0.23, box.top() + box.height() * 0.52)
            path.lineTo(box.left() + box.width() * 0.43, box.top() + box.height() * 0.72)
            path.lineTo(box.left() + box.width() * 0.78, box.top() + box.height() * 0.29)
            pen = QPen(QColor("#FFFFFF"), max(1.8, sz * 0.13), Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        elif partial:
            pen = QPen(QColor("#FFFFFF"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            painter.drawLine(
                int(round(box.left() + box.width() * 0.25)),
                int(round(box.center().y())),
                int(round(box.right() - box.width() * 0.25)),
                int(round(box.center().y())),
            )

        painter.restore()

    def _draw_radio_indicator(self, option, painter: QPainter):
        t = self._tokens
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        r = QRectF(option.rect)
        sz = max(12.0, min(r.width(), r.height()) - 3.0)
        cx = r.center().x()
        cy = r.center().y()
        circle = QRectF(cx - sz / 2.0, cy - sz / 2.0, sz, sz)

        checked = bool(option.state & QStyle.StateFlag.State_On)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)

        unchecked_border = "#64748B" if not t.is_dark else "#52637A"
        if checked:
            fill_col = QColor(t.accent_hover if hover and enabled else t.accent)
            border_col = QColor(fill_col)
            if not enabled:
                fill_col.setAlpha(120)
                border_col.setAlpha(120)
            painter.setPen(QPen(border_col, 1.3))
            painter.setBrush(QBrush(fill_col))
            painter.drawEllipse(circle)

            dot_r = sz * 0.23
            dot_rect = QRectF(cx - dot_r, cy - dot_r, dot_r * 2.0, dot_r * 2.0)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor("#FFFFFF")))
            painter.drawEllipse(dot_rect)
        else:
            fill_col = QColor(t.surface_alt if not enabled else t.surface)
            border_col = QColor(t.accent if (hover and enabled) else unchecked_border)
            if not enabled:
                border_col.setAlpha(120)
            painter.setPen(QPen(border_col, 1.3))
            painter.setBrush(QBrush(fill_col))
            painter.drawEllipse(circle)

        painter.restore()


class _WeakSignal:
    """Bộ phát tín hiệu dùng tham chiếu yếu (WeakMethod) tránh giữ sống QWidget đã hủy."""

    def __init__(self):
        self._slots: list = []

    def connect(self, slot):
        try:
            ref = weakref.WeakMethod(slot) if hasattr(slot, "__self__") and slot.__self__ is not None else weakref.ref(slot)
            self._slots.append(ref)
        except TypeError:
            pass

    def emit(self, *args, **kwargs):
        alive = []
        for ref in list(self._slots):
            fn = ref()
            if fn is None:
                continue
            owner = getattr(fn, "__self__", None)
            if owner is not None and isinstance(owner, QObject) and sip.isdeleted(owner):
                continue
            alive.append(ref)
            try:
                fn(*args, **kwargs)
            except RuntimeError:
                pass
        self._slots = alive


class ThemeManager(QObject):
    _instance = None
    _fonts_registered = False
    _style_initialized = False

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @classmethod
    def ensure_system_fonts(cls):
        """Đăng ký trực tiếp các file font chuẩn của Windows để tránh lỗi ô vuông (tofu) ở chế độ offscreen."""
        if cls._fonts_registered:
            return
        cls._fonts_registered = True
        win_fonts = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
        for font_file in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf", "segoeuil.ttf", "consola.ttf", "consolab.ttf", "arial.ttf"):
            fpath = os.path.join(win_fonts, font_file)
            if os.path.isfile(fpath):
                try:
                    QFontDatabase.addApplicationFont(fpath)
                except Exception:
                    pass

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme_changed = _WeakSignal()
        self.current_preset = "engineering"
        self.current_mode = "light"
        self.tokens: ThemeTokens = get_tokens(self.current_preset, self.current_mode)
        self._proxy_style: EngineeringProxyStyle | None = None

    @property
    def preset(self) -> str:
        return self.current_preset

    @property
    def current_theme(self) -> str:
        return self.current_preset

    @property
    def mode(self) -> str:
        return self.current_mode

    @property
    def is_dark(self) -> bool:
        return self.current_mode == "dark"

    def apply(self, preset: str, mode: str | bool):
        """Áp dụng theme mới (phong cách Kỹ thuật Sáng/Tối) cho toàn bộ ứng dụng."""
        self.ensure_system_fonts()
        new_preset = "engineering"
        if isinstance(mode, bool):
            new_mode = "dark" if mode else "light"
        else:
            new_mode = str(mode).lower()
            if new_mode not in ("light", "dark"):
                new_mode = "light"

        app = QApplication.instance()
        already_applied = (
            ThemeManager._style_initialized
            and new_preset == self.current_preset
            and new_mode == self.current_mode
            and app is not None
            and bool(app.styleSheet())
        )

        self.current_preset = new_preset
        self.current_mode = new_mode
        self.tokens = get_tokens(self.current_preset, self.current_mode)

        if app is not None and not already_applied:
            if not ThemeManager._style_initialized or self._proxy_style is None:
                self._proxy_style = EngineeringProxyStyle(self.tokens)
                app.setStyle(self._proxy_style)
                ThemeManager._style_initialized = True
            else:
                self._proxy_style.set_tokens(self.tokens)

            # Thiết lập bảng màu Palette cơ bản
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor(self.tokens.window))
            pal.setColor(QPalette.ColorRole.WindowText, QColor(self.tokens.text))
            pal.setColor(QPalette.ColorRole.Base, QColor(self.tokens.surface))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor(self.tokens.surface_alt))
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(self.tokens.surface))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor(self.tokens.text))
            pal.setColor(QPalette.ColorRole.Text, QColor(self.tokens.text))
            pal.setColor(QPalette.ColorRole.Button, QColor(self.tokens.surface))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor(self.tokens.text))
            pal.setColor(QPalette.ColorRole.Highlight, QColor(self.tokens.selection))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor(self.tokens.text))
            app.setPalette(pal)

            # Thiết lập Font chữ
            font = QFont(self.tokens.font_ui, int(self.tokens.font_size_pt))
            app.setFont(font)

            # Áp dụng chuỗi QSS
            qss_content = build_qss(self.tokens)
            app.setStyleSheet(qss_content)

        # Phát tín hiệu để các widget tự vẽ (DiskMap, Sidebar, v.v.) vẽ lại
        self.theme_changed.emit(self.tokens)
        return self.tokens

    def apply_theme(self, preset: str, mode: str | bool):
        """Hàm tương thích cho MainWindow."""
        return self.apply(preset, mode)
