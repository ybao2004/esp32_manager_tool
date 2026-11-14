# -*- coding: utf-8 -*-
"""
Trình hiển thị nhật ký thời gian thực (High-Performance LogView) cho PyQt6.
Tối ưu hiệu năng cao với bộ gom lô (Batch Dispatcher), tô màu phân cấp lỗi ESP-IDF (I/W/E),
hỗ trợ dấu thời gian và tự động cuộn thông minh.
"""
import re
from PyQt6.QtWidgets import QTextEdit, QWidget
from PyQt6.QtGui import QTextCharFormat, QTextBlockFormat, QColor, QTextCursor, QFont, QFontMetricsF, QTextFormat
from PyQt6.QtCore import QTimer, Qt
from datetime import datetime
from collections import deque
from modules.config import So_dong_serial_toi_da
from modules.ui.theme.tokens import ThemeTokens
from modules.ui.theme.manager import ThemeManager


class LogView(QTextEdit):
    _ROLE_PROP = QTextFormat.Property.UserProperty + 1
    _CENTRAL_LOG_RE = re.compile(
        r"^\[[A-Za-zÀ-ỹ0-9 &_-]+\]\s+(?:\[\d{2}:\d{2}:\d{2}(?:\.\d{3})?\]\s+)?"
    )
    _BULLET_PREFIX_RE = re.compile(r"^(\s*(?:\[\d+/\d+\]\s+|->\s+|>>>\s+|[+\-*!]\s+))")
    _WS_PREFIX_RE = re.compile(r"^(\s+)")

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setProperty("role", "log")
        self.setReadOnly(True)
        self.setAcceptRichText(False)
        self.document().setMaximumBlockCount(So_dong_serial_toi_da)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._default_block_fmt = QTextBlockFormat()

        self.autoscroll = True
        self.timestamps = False

        self._current_tokens: ThemeTokens = ThemeManager.instance().tokens
        self._queue: deque[tuple[str, str | None]] = deque()

        # Timer gom lô (Batch Flush) 40ms để tránh nghẽn GUI khi log dồn dập
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(40)
        self._flush_timer.timeout.connect(self._flush_queue)
        self._flush_timer.start()

        self._formats: dict[str, QTextCharFormat] = {}
        self._update_formats(self._current_tokens)

        ThemeManager.instance().theme_changed.connect(self._on_theme_changed)

    def _update_formats(self, tokens: ThemeTokens):
        self._current_tokens = tokens
        font = QFont(tokens.font_mono, 9)

        # Định dạng text thông thường (Info - tự động nhận màu QSS theo Light/Dark)
        f_norm = QTextCharFormat()
        f_norm.setFont(font)
        f_norm.setProperty(self._ROLE_PROP, "info")
        self._formats["info"] = f_norm

        # Định dạng nhấn mạnh (Accent / Blue)
        f_accent = QTextCharFormat()
        f_accent.setFont(font)
        f_accent.setForeground(QColor(tokens.accent))
        f_accent.setProperty(self._ROLE_PROP, "accent")
        self._formats["accent"] = f_accent

        # Định dạng tiêu đề (Header - In đậm, tự nhận màu QSS theo Light/Dark)
        f_hdr = QTextCharFormat()
        font_bold = QFont(tokens.font_mono, 9)
        font_bold.setBold(True)
        f_hdr.setFont(font_bold)
        f_hdr.setProperty(self._ROLE_PROP, "header")
        self._formats["header"] = f_hdr

        # Định dạng Warning (Vàng / Cam)
        f_warn = QTextCharFormat()
        f_warn.setFont(font)
        f_warn.setForeground(QColor(tokens.warning))
        f_warn.setProperty(self._ROLE_PROP, "warning")
        self._formats["warning"] = f_warn

        # Định dạng Error (Đỏ)
        f_err = QTextCharFormat()
        f_err.setFont(font)
        f_err.setForeground(QColor(tokens.danger))
        f_err.setProperty(self._ROLE_PROP, "error")
        self._formats["error"] = f_err

        # Định dạng Success (Xanh lá)
        f_succ = QTextCharFormat()
        f_succ.setFont(font)
        f_succ.setForeground(QColor(tokens.success))
        f_succ.setProperty(self._ROLE_PROP, "success")
        self._formats["success"] = f_succ

        # Định dạng Mờ / Debug (Xám)
        f_muted = QTextCharFormat()
        f_muted.setFont(font)
        f_muted.setForeground(QColor(tokens.text_secondary))
        f_muted.setProperty(self._ROLE_PROP, "muted")
        self._formats["muted"] = f_muted

    def append_line(self, line: str, level: str | None = None):
        """Đưa dòng log vào hàng đợi để xả vào văn bản."""
        if line is None:
            return
        clean_text = str(line).rstrip("\r\n")

        # Thêm dấu thời gian nếu được bật
        if self.timestamps and clean_text:
            ts = datetime.now().strftime("[%H:%M:%S.%f]")[:-3] + "] "
            clean_text = ts + clean_text

        # Tự động nhận diện cấp độ nếu không truyền
        if not level:
            s_stripped = clean_text.strip()
            if s_stripped.startswith("E (") or "[LỖI]" in s_stripped or "error" in s_stripped.lower():
                level = "error"
            elif s_stripped.startswith("W (") or "[CẢNH BÁO]" in s_stripped or "warning" in s_stripped.lower():
                level = "warning"
            elif s_stripped.startswith("I (") or "[HỢP LỆ]" in s_stripped:
                level = "info"
            elif s_stripped.startswith("D (") or s_stripped.startswith("V ("):
                level = "muted"
            elif "thành công" in s_stripped.lower() or "ok" in s_stripped.lower():
                level = "success"
            else:
                level = "info"

        self._queue.append((clean_text, level))

    def append_text(self, text: str):
        """Ghi nhận chuỗi văn bản (có thể chứa nhiều dòng)."""
        if not text:
            return
        for line in str(text).splitlines():
            self.append_line(line)

    def _compute_hanging_indent_px(self, line: str) -> float:
        """Tính độ thụt lề treo (pixel) khi dòng nhật ký tự động xuống dòng."""
        if not line or not line.strip():
            return 0.0
        font = QFont(self._current_tokens.font_mono, 9)
        fm = QFontMetricsF(font)
        indent_px = 0.0
        if self._CENTRAL_LOG_RE.match(line):
            indent_px = fm.horizontalAdvance("    ")
        else:
            m_bullet = self._BULLET_PREFIX_RE.match(line)
            if m_bullet:
                indent_px = fm.horizontalAdvance(m_bullet.group(1))
            else:
                m_ws = self._WS_PREFIX_RE.match(line)
                if m_ws:
                    indent_px = fm.horizontalAdvance(m_ws.group(1))
        if indent_px <= 0.0:
            return 0.0
        vp = self.viewport()
        vp_w = float(vp.width()) if vp is not None else 0.0
        if vp_w > 120.0:
            indent_px = min(indent_px, vp_w * 0.35)
        return float(indent_px)

    def _make_block_format(self, indent_px: float) -> QTextBlockFormat:
        if indent_px <= 0.0:
            return self._default_block_fmt
        bf = QTextBlockFormat()
        bf.setLeftMargin(indent_px)
        bf.setTextIndent(-indent_px)
        return bf

    def _is_doc_empty(self) -> bool:
        doc = self.document()
        if doc is None:
            return True
        return doc.blockCount() <= 1 and doc.firstBlock().text() == ""

    def _flush_queue(self):
        if not self._queue:
            return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # Xả tối đa 500 dòng một nhịp timer để giữ FPS mượt mà
        count = 0
        while self._queue and count < 500:
            text_line, level = self._queue.popleft()
            if self._is_doc_empty() and not text_line.strip("\r\n"):
                count += 1
                continue
            fmt = self._formats.get(level or "info", self._formats["info"])
            if cursor.position() > 0:
                cursor.insertText("\n")
            indent_px = self._compute_hanging_indent_px(text_line)
            cursor.setBlockFormat(self._make_block_format(indent_px))
            cursor.insertText(text_line, fmt)
            count += 1

        if self.autoscroll:
            self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def clear_log(self):
        self._queue.clear()
        self.clear()

    # Compatibility methods with legacy tk.Text interface
    def insert(self, pos, text: str, tag=None):
        lvl = "info"
        if isinstance(tag, (list, tuple)):
            for t in tag:
                if t in ("red", "green", "blue", "warning", "header"):
                    lvl = t
                    break
        elif isinstance(tag, str):
            lvl = tag
        level_map = {
            "red": "error",
            "green": "success",
            "blue": "accent",
            "warning": "warning",
            "header": "header"
        }
        eff_lvl = level_map.get(lvl, "info")
        raw = str(text)
        if self._is_doc_empty():
            raw = raw.lstrip("\r\n")
            if not raw:
                return
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = self._formats.get(eff_lvl, self._formats.get("info", QTextCharFormat()))
        parts = raw.split("\n")
        for idx, part in enumerate(parts):
            if part:
                indent_px = self._compute_hanging_indent_px(part)
                cursor.setBlockFormat(self._make_block_format(indent_px))
                cursor.insertText(part, fmt)
            if idx < len(parts) - 1:
                cursor.insertText("\n", fmt)
                cursor.setBlockFormat(self._make_block_format(0.0))

    def index(self, pos="end-1c") -> str:
        self._flush_queue()
        lines = max(1, self.document().blockCount())
        return f"{lines}.0"

    def delete(self, start="1.0", end="end"):
        self._flush_queue()
        if start in ("1.0", 0) and end in ("end", "end-1c", None):
            self.clear_log()
        else:
            try:
                line_count = int(str(end).split(".")[0])
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                for _ in range(line_count):
                    cursor.movePosition(QTextCursor.MoveOperation.Down, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
            except Exception:
                self.clear_log()

    def winfo_exists(self) -> bool:
        return True

    def winfo_toplevel(self):
        return self.window()

    def config(self, **kwargs):
        if "state" in kwargs:
            self.setReadOnly(kwargs["state"] == "disabled")

    def configure(self, **kwargs):
        self.config(**kwargs)

    def see(self, pos):
        self._flush_queue()
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())

    def get(self, start="1.0", end="end") -> str:
        self._flush_queue()
        return self.toPlainText()

    def tag_configure(self, tag, **kwargs):
        if not hasattr(self, "_tags"):
            self._tags = {}
        if tag not in self._tags:
            self._tags[tag] = {}
        self._tags[tag].update(kwargs)

    def tag_cget(self, tag, opt):
        if not hasattr(self, "_tags"):
            self._tags = {}
        return self._tags.get(tag, {}).get(opt, 14 if opt == "lmargin2" else "")

    def cget(self, key):
        if key == "font":
            return "Consolas 10"
        return ""

    def text(self) -> str:
        """Trả về toàn bộ văn bản hiện tại (dùng cho các bài test)."""
        self._flush_queue()
        return self.toPlainText()

    def _recolor_existing_blocks(self):
        """Áp lại màu sắc mới cho toàn bộ các đoạn log đã hiển thị khi đổi theme."""
        doc = self.document()
        if doc is None or doc.isEmpty():
            return
        sb = self.verticalScrollBar()
        saved_scroll = sb.value() if sb is not None else 0
        was_at_max = sb is not None and sb.value() >= sb.maximum() - 2

        updates: list[tuple[int, int, str]] = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    role = frag.charFormat().property(self._ROLE_PROP)
                    if isinstance(role, str) and role in self._formats:
                        updates.append((frag.position(), frag.length(), role))
                it += 1
            block = block.next()

        if updates:
            cursor = QTextCursor(doc)
            cursor.beginEditBlock()
            for pos, length, role in updates:
                cursor.setPosition(pos)
                cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
                cursor.setCharFormat(self._formats[role])
            cursor.endEditBlock()

        if sb is not None:
            sb.setValue(sb.maximum() if (self.autoscroll and was_at_max) else saved_scroll)

    def _on_theme_changed(self, tokens: ThemeTokens):
        self._update_formats(tokens)
        self._recolor_existing_blocks()

    def stop(self):
        """Dừng bộ đếm thời gian flush và xóa hàng đợi log khi đóng ứng dụng."""
        if hasattr(self, "_flush_timer") and self._flush_timer is not None:
            try:
                self._flush_timer.stop()
            except Exception:
                pass
        if hasattr(self, "_queue"):
            self._queue.clear()

    def closeEvent(self, event):
        self.stop()
        super().closeEvent(event)
