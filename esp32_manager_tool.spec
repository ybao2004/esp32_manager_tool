# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('icons', 'icons')],
    hiddenimports=[
        'modules.update_util',
        'modules.partition',
        'modules.partition.partition_model',
        'modules.partition.chip_database',
        'modules.partition.unit_formatter',
        'modules.partition.project_scanner',
        'modules.dialogs.partition_dialogs',
        'modules.dialogs.settings_dialog',
        'modules.tabs.tab_partition',
        'modules.tabs.tab_flasher',
        'modules.tabs.tab_inspector',
        'modules.tabs.tab_monitor',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
