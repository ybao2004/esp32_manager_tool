# -*- coding: utf-8 -*-
"""
Central pytest fixtures for esp32_manager_tool.
Provides standard mock hardware fixtures, monkeypatching hooks,
and headless Tkinter application harness lifecycles.
"""
import pytest
from unittest.mock import patch, MagicMock

from tests.mock_hardware.mock_serial import MockSerial
from tests.mock_hardware.mock_registry import MockPortRegistry
from tests.mock_hardware.mock_esptool import MockEsptoolEngine
from tests.mock_hardware.app_harness import HeadlessAppHarness


@pytest.fixture
def mock_serial_connection():
    """Provides a standalone MockSerial instance."""
    return MockSerial(port="COM3", baudrate=115200)


@pytest.fixture
def mock_serial(monkeypatch):
    """
    Patches serial.Serial to return a controlled MockSerial instance.
    Returns the created MockSerial instance.
    """
    active_connection = MockSerial(port="COM3", baudrate=115200)

    def _serial_factory(*args, **kwargs):
        port = args[0] if args else kwargs.get("port", "COM3")
        baud = args[1] if len(args) > 1 else kwargs.get("baudrate", 115200)
        active_connection.port = port
        active_connection.baudrate = baud
        active_connection.is_open = True
        active_connection.fault_disconnect = False
        return active_connection

    monkeypatch.setattr("serial.Serial", _serial_factory)
    monkeypatch.setattr("modules.tabs.tab_monitor.serial.Serial", _serial_factory, raising=False)

    return active_connection


@pytest.fixture
def mock_ports(monkeypatch):
    """
    Patches list_ports.comports across serial_util and serial.tools.list_ports.
    Returns the MockPortRegistry instance.
    """
    registry = MockPortRegistry(populate_defaults=True)
    monkeypatch.setattr("modules.serial_util.list_ports.comports", registry.comports)
    monkeypatch.setattr("serial.tools.list_ports.comports", registry.comports, raising=False)
    return registry


@pytest.fixture
def mock_esptool(monkeypatch):
    """
    Patches modules.esptool_util.esptool with MockEsptoolEngine.
    Returns the MockEsptoolEngine instance.
    """
    engine = MockEsptoolEngine(profile="ESP32-Default")
    monkeypatch.setattr("modules.esptool_util.esptool", engine)
    return engine


@pytest.fixture
def headless_app(mock_ports, mock_serial, mock_esptool, monkeypatch, tmp_path):
    """
    Initializes a full headless InspectorApp instance with all hardware mocks pre-applied.
    Yields (harness, app) and guarantees safe teardown on fixture completion.
    """
    test_config_path = str(tmp_path / "test_settings_esp32_manager_tool.json")
    monkeypatch.setattr("modules.config.CONFIG_FILE", test_config_path)
    monkeypatch.setattr("modules.app_core.CONFIG_FILE", test_config_path)

    harness = HeadlessAppHarness()
    app = harness.start(auto_scan=False)
    # Ensure fresh state
    app.ignored_com_ports = ["COM5"]
    yield harness, app
    harness.close()


@pytest.fixture
def dummy_firmware_file(tmp_path):
    """Factory fixture to create temporary dummy binary firmware files."""
    def _create(name="firmware.bin", size=1024, fill_byte=b"\xAA"):
        p = tmp_path / name
        p.write_bytes(fill_byte * size)
        return str(p)
    return _create


@pytest.fixture(autouse=True)
def mock_dialogs(monkeypatch):
    """
    Prevents modal dialogs from hanging tests, recording all dialog invocations.
    """
    calls = {
        "showinfo": [],
        "showwarning": [],
        "showerror": [],
        "askyesno": [],
        "askopenfilename": [],
        "asksaveasfilename": [],
        "return_askyesno": True,
        "return_open_filename": "",
        "return_save_filename": ""
    }

    def _info(title, message, **kwargs):
        calls["showinfo"].append((title, message))

    def _warn(title, message, **kwargs):
        calls["showwarning"].append((title, message))

    def _error(title, message, **kwargs):
        calls["showerror"].append((title, message))

    def _askyesno(title, message, **kwargs):
        calls["askyesno"].append((title, message))
        return calls.get("return_askyesno", True)

    def _askopenfilename(**kwargs):
        calls["askopenfilename"].append(kwargs)
        return calls.get("return_open_filename", "")

    def _asksaveasfilename(**kwargs):
        calls["asksaveasfilename"].append(kwargs)
        return calls.get("return_save_filename", "")

    monkeypatch.setattr("modules.qt_toolkit.messagebox.showinfo", _info)
    monkeypatch.setattr("modules.qt_toolkit.messagebox.showwarning", _warn)
    monkeypatch.setattr("modules.qt_toolkit.messagebox.showerror", _error)
    monkeypatch.setattr("modules.qt_toolkit.messagebox.askyesno", _askyesno)

    dlg_map = {
        "showinfo": _info,
        "showwarning": _warn,
        "showerror": _error,
        "askyesno": _askyesno,
    }
    for mod in (
        "modules.app_core",
        "modules.tabs.tab_partition",
        "modules.tabs.tab_backup_clone",
        "modules.tabs.tab_flasher",
        "modules.tabs.tab_inspector",
        "modules.tabs.tab_monitor",
        "modules.dialogs.partition_dialogs",
        "modules.dialogs.settings_dialog",
    ):
        for dlg_name, dlg_fn in dlg_map.items():
            monkeypatch.setattr(f"{mod}.messagebox.{dlg_name}", dlg_fn, raising=False)

    monkeypatch.setattr("modules.qt_toolkit.filedialog.askopenfilename", _askopenfilename)
    monkeypatch.setattr("modules.qt_toolkit.filedialog.asksaveasfilename", _asksaveasfilename)
    monkeypatch.setattr("modules.tabs.tab_partition.filedialog.askopenfilename", _askopenfilename, raising=False)
    monkeypatch.setattr("modules.tabs.tab_partition.filedialog.asksaveasfilename", _asksaveasfilename, raising=False)
    monkeypatch.setattr("modules.tabs.tab_flasher.filedialog.askopenfilename", _askopenfilename, raising=False)
    monkeypatch.setattr("modules.tabs.tab_flasher.filedialog.asksaveasfilename", _asksaveasfilename, raising=False)
    monkeypatch.setattr("modules.tabs.tab_backup_clone.filedialog.askopenfilename", _askopenfilename, raising=False)
    monkeypatch.setattr("modules.tabs.tab_backup_clone.filedialog.asksaveasfilename", _asksaveasfilename, raising=False)

    return calls


def pytest_sessionfinish(session, exitstatus):
    """Dừng bộ định thời QTimer của cửa sổ ẩn khi kết thúc phiên kiểm thử."""
    try:
        root = HeadlessAppHarness._shared_root
        if root is not None:
            if hasattr(root, "_pump_timer") and root._pump_timer is not None:
                root._pump_timer.stop()
            root.destroy()
    except Exception:
        pass
