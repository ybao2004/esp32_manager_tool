# -*- coding: utf-8 -*-
"""
Các trang giao diện người dùng PyQt6 cho ESP32 Manager Tool v1.5.
"""
from modules.ui.pages.inspector_page import InspectorPage
from modules.ui.pages.monitor_page import MonitorPage
from modules.ui.pages.flasher_page import FlasherPage
from modules.ui.pages.partition_page import PartitionPage
from modules.ui.pages.backup_page import BackupPage
from modules.ui.pages.settings_page import SettingsPage

__all__ = [
    "InspectorPage",
    "MonitorPage",
    "FlasherPage",
    "PartitionPage",
    "BackupPage",
    "SettingsPage",
]
