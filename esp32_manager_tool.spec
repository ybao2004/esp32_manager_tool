# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('icons', 'icons')]
binaries = []
hiddenimports = [
    'PyQt6',
    'PyQt6.QtCore',
    'PyQt6.QtGui',
    'PyQt6.QtNetwork',
    'PyQt6.QtWidgets',
    'PyQt6.QtSvg',
    'modules.single_instance',
    'modules.ui',
    'modules.ui.text',
    'modules.ui.icons',
    'modules.ui.dispatch',
    'modules.ui.dialogs_service',
    'modules.ui.theme.tokens',
    'modules.ui.theme.qss',
    'modules.ui.theme.manager',
    'modules.ui.widgets.card',
    'modules.ui.widgets.collapsible',
    'modules.ui.widgets.disk_map',
    'modules.ui.widgets.info_bar',
    'modules.ui.widgets.key_value_table',
    'modules.ui.widgets.connection_bar',
    'modules.ui.widgets.log_view',
    'modules.ui.widgets.progress_row',
    'modules.ui.widgets.flow_layout',
    'modules.ui.widgets.sidebar',
    'modules.ui.widgets.update_badge',
    'modules.ui.pages.inspector_page',
    'modules.ui.pages.monitor_page',
    'modules.ui.pages.flasher_page',
    'modules.ui.pages.partition_page',
    'modules.ui.pages.backup_page',
    'modules.ui.pages.settings_page',
    'modules.ui.splash',
    'modules.ui.main_window',
    'modules.ui.models',
    'modules.ui.dialogs.about_update_dialogs',
    'modules.ui.dialogs.partition_edit_dialog',
    'modules.ui.dialogs.partition_data_dialog',
    'modules.ui.dialogs.preset_dialog',
    'modules.ui.dialogs.size_input_dialog',
    'modules.nvs_util',
    'modules.backup_utils',
    'modules.update_util',
    'modules.partition',
    'modules.partition.partition_model',
    'modules.partition.chip_database',
    'modules.partition.unit_formatter',
    'modules.partition.project_scanner',
    'modules.tabs.tab_partition',
    'modules.tabs.tab_backup_clone',
    'modules.tabs.tab_flasher',
    'modules.tabs.tab_inspector',
    'modules.tabs.tab_monitor',
]

for pkg in ('esptool', 'espefuse'):
    try:
        tmp_ret = collect_all(pkg)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception:
        pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', '_pytest', 'unittest', 'tkinter', '_tkinter'],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Esp32_manager_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icons/esp_icon_v3.ico'],
)
