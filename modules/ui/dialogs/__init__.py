# -*- coding: utf-8 -*-
"""
Hộp thoại giao diện thuần PyQt6 cho ESP32 Manager Tool (v1.6).
"""
from modules.ui.dialogs.size_input_dialog import SizeInputDialog
from modules.ui.dialogs.preset_dialog import PresetSelectorDialog
from modules.ui.dialogs.erase_region_dialog import EraseRegionDialog
from modules.ui.dialogs.partition_edit_dialog import PartitionEditDialog, parse_with_unit
from modules.ui.dialogs.about_update_dialogs import AboutDialog, UpdateDialog, AboutUpdateMixin

__all__ = [
    "SizeInputDialog",
    "PresetSelectorDialog",
    "EraseRegionDialog",
    "PartitionEditDialog",
    "parse_with_unit",
    "AboutDialog",
    "UpdateDialog",
    "AboutUpdateMixin",
]
