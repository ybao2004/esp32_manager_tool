# -*- coding: utf-8 -*-
"""
Hộp thoại giao diện thuần PyQt6 cho ESP32 Manager Tool (v1.5).
"""
from modules.ui.dialogs.size_input_dialog import SizeInputDialog
from modules.ui.dialogs.preset_dialog import PresetSelectorDialog
from modules.ui.dialogs.partition_edit_dialog import PartitionEditDialog, parse_with_unit
from modules.ui.dialogs.partition_data_dialog import PartitionDataDialog, NvsEntryEditorDialog
from modules.ui.dialogs.about_update_dialogs import AboutDialog, UpdateDialog, AboutUpdateMixin

__all__ = [
    "SizeInputDialog",
    "PresetSelectorDialog",
    "PartitionEditDialog",
    "PartitionDataDialog",
    "NvsEntryEditorDialog",
    "parse_with_unit",
    "AboutDialog",
    "UpdateDialog",
    "AboutUpdateMixin",
]
