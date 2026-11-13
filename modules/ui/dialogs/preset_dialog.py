# -*- coding: utf-8 -*-
"""
Hộp thoại chọn mẫu bảng phân vùng chuẩn ESP-IDF (PresetSelectorDialog) cho PyQt6.
Cung cấp các mẫu phân vùng phổ biến: Default SPIFFS, Two OTA, Large App, LittleFS, 8MB/16MB.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QPlainTextEdit,
    QPushButton, QWidget, QSplitter
)
from PyQt6.QtCore import Qt
from typing import Optional

PRESET_CONFIGS = [
    {
        "name": "1. Chuẩn mặc định ESP-IDF (Factory 1MB + SPIFFS) - Flash 4MB",
        "flash_size": 4 * 1024 * 1024,
        "chip": "esp32",
        "csv": (
            "# ESP-IDF Partition Table - Default SPIFFS\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1M,\n"
            "storage,  data, spiffs,  ,        2800K,\n"
        )
    },
    {
        "name": "2. Cập nhật OTA kép (Factory + OTA_0 + OTA_1) - Flash 4MB",
        "flash_size": 4 * 1024 * 1024,
        "chip": "esp32",
        "csv": (
            "# ESP-IDF Partition Table - Two OTA\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x4000,\n"
            "otadata,  data, ota,     0xd000,  0x2000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1M,\n"
            "ota_0,    app,  ota_0,   ,        1M,\n"
            "ota_1,    app,  ota_1,   ,        1M,\n"
            "storage,  data, spiffs,  ,        800K,\n"
        )
    },
    {
        "name": "3. Ứng dụng lớn không OTA (Single Large App 3MB) - Flash 4MB",
        "flash_size": 4 * 1024 * 1024,
        "chip": "esp32",
        "csv": (
            "# ESP-IDF Partition Table - Large App 3MB (No OTA)\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 3M,\n"
            "storage,  data, spiffs,  ,        896K,\n"
        )
    },
    {
        "name": "4. Đa hệ thống tệp (LittleFS + FATFS) - Flash 4MB",
        "flash_size": 4 * 1024 * 1024,
        "chip": "esp32",
        "csv": (
            "# ESP-IDF Partition Table - Multi Storage\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1536K,\n"
            "web_fs,   data, littlefs, ,       1280K,\n"
            "data_log, data, fat,      ,       1M,\n"
        )
    },
    {
        "name": "5. Flash lớn 8MB có OTA kép (OTA_0 2.5MB + OTA_1 2.5MB) - Flash 8MB",
        "flash_size": 8 * 1024 * 1024,
        "chip": "esp32s3",
        "csv": (
            "# ESP-IDF Partition Table - 8MB Two OTA\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x4000,\n"
            "otadata,  data, ota,     0xd000,  0x2000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 2M,\n"
            "ota_0,    app,  ota_0,   ,        2560K,\n"
            "ota_1,    app,  ota_1,   ,        2560K,\n"
            "storage,  data, spiffs,  ,        600K,\n"
        )
    },
    {
        "name": "6. Flash cực lớn 16MB có OTA kép (OTA_0 4.5MB + OTA_1 4.5MB + FS 6MB) - Flash 16MB",
        "flash_size": 16 * 1024 * 1024,
        "chip": "esp32s3",
        "csv": (
            "# ESP-IDF Partition Table - 16MB Two OTA + FS\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x4000,\n"
            "otadata,  data, ota,     0xd000,  0x2000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 2M,\n"
            "ota_0,    app,  ota_0,   ,        4608K,\n"
            "ota_1,    app,  ota_1,   ,        4608K,\n"
            "storage,  data, spiffs,  ,        5000K,\n"
        )
    }
]


class PresetSelectorDialog(QDialog):
    def __init__(self, parent=None, is_dark_mode: bool = True):
        if parent is not None and not isinstance(parent, QWidget):
            parent = None
        super().__init__(parent)
        self.setWindowTitle("Chọn mẫu cấu hình bảng phân vùng ESP-IDF")
        self.resize(680, 420)
        self.selected_preset: Optional[dict] = None
        self.result: Optional[dict] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        lbl = QLabel("Danh sách mẫu cấu hình tiêu chuẩn ESP-IDF:", self)
        lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(lbl)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # Cột trái: List danh sách mẫu
        self.list_widget = QListWidget(splitter)
        for p in PRESET_CONFIGS:
            self.list_widget.addItem(p["name"])

        # Cột phải: Xem trước nội dung CSV
        self.preview_txt = QPlainTextEdit(splitter)
        self.preview_txt.setReadOnly(True)
        self.preview_txt.setStyleSheet("font-family: 'Consolas', monospace; font-size: 9pt;")

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        btn_cancel = QPushButton("Hủy bỏ", self)
        btn_cancel.clicked.connect(self.reject)
        btn_box.addWidget(btn_cancel)

        btn_apply = QPushButton("Áp dụng mẫu này", self)
        btn_apply.setProperty("accent", "true")
        btn_apply.clicked.connect(self._on_apply)
        btn_box.addWidget(btn_apply)
        layout.addLayout(btn_box)

        self.list_widget.currentRowChanged.connect(self._on_selection_changed)
        if PRESET_CONFIGS:
            self.list_widget.setCurrentRow(0)

    def _on_selection_changed(self, row: int):
        if 0 <= row < len(PRESET_CONFIGS):
            self.preview_txt.setPlainText(PRESET_CONFIGS[row]["csv"])

    def _on_apply(self):
        row = self.list_widget.currentRow()
        if 0 <= row < len(PRESET_CONFIGS):
            self.selected_preset = PRESET_CONFIGS[row]
            self.result = PRESET_CONFIGS[row]
            self.accept()
