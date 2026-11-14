# -*- coding: utf-8 -*-
"""
Bảng hiển thị khóa - giá trị (KeyValueTable) cho thông số phần cứng ESP32 (v1.6).
Hỗ trợ tự động xuống dòng (Word Wrap), tự giãn chiều cao theo số dòng (không cuộn con)
và sao chép giá trị dễ dàng.
"""
from PyQt6.QtWidgets import (
    QTableWidget, QTableWidgetItem, QHeaderView, QMenu, QApplication
)
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QAction, QFont


class KeyValueTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Thông số", "Giá trị"])
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.setColumnWidth(0, 190)
        self.horizontalHeader().setStretchLastSection(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        self.horizontalHeader().setFixedHeight(26)
        self.setWordWrap(True)
        self.setAlternatingRowColors(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.horizontalHeader().sectionResized.connect(lambda *_: self.recompute_height())

    def recompute_height(self):
        """Tính lại chiều cao từng hàng theo độ rộng cột hiện tại và khóa chiều cao tổng của bảng."""
        if getattr(self, "_recomputing_height", False):
            return
        self._recomputing_height = True
        try:
            self.resizeRowsToContents()
            header_h = 26
            rows_h = sum(
                max(24, self.rowHeight(r))
                for r in range(self.rowCount())
                if not self.isRowHidden(r)
            )
            total_h = header_h + rows_h + 4
            self.setFixedHeight(max(68, total_h))
        finally:
            self._recomputing_height = False

    def showEvent(self, event):
        super().showEvent(event)
        self.recompute_height()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event is None or event.size().width() != event.oldSize().width():
            self.recompute_height()

    def set_rows(self, rows: list[tuple[str, str]]):
        self.setRowCount(len(rows))
        for row_idx, (k, v) in enumerate(rows):
            item_k = QTableWidgetItem(str(k))
            item_k.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_k.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            item_k.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))

            item_v = QTableWidgetItem(str(v))
            item_v.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item_v.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

            self.setItem(row_idx, 0, item_k)
            self.setItem(row_idx, 1, item_v)

        self.recompute_height()

    def populate(self, rows: list[tuple[str, str]]):
        self.set_rows(rows)

    def set_data(self, rows: list[tuple[str, str]]):
        self.set_rows(rows)

    def _show_context_menu(self, pos: QPoint):
        item = self.itemAt(pos)
        if not item:
            return
        row = item.row()
        val_item = self.item(row, 1)
        val_str = val_item.text() if val_item else ""

        menu = QMenu(self)
        act_copy = QAction("Sao chép giá trị", self)
        act_copy.triggered.connect(lambda: QApplication.clipboard().setText(val_str))
        menu.addAction(act_copy)

        act_copy_all = QAction("Sao chép dòng này (Thông số: Giá trị)", self)
        k_item = self.item(row, 0)
        k_str = k_item.text() if k_item else ""
        act_copy_all.triggered.connect(lambda: QApplication.clipboard().setText(f"{k_str}: {val_str}"))
        menu.addAction(act_copy_all)

        menu.exec(self.mapToGlobal(pos))
