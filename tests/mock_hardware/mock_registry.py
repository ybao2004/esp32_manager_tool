# -*- coding: utf-8 -*-
"""
MockPortRegistry: Port enumeration and USB hotplug emulator.
Provides simulated list_ports.comports() results, Bluetooth device detection,
and dynamic hotplug / unplug events for testing.
"""


class MockPortInfo:
    """Simulates pyserial ListPortInfo object."""

    def __init__(self, device: str, description: str = "", hwid: str = ""):
        self.device = device
        self.description = description
        self.hwid = hwid
        self.name = device
        self.manufacturer = ""
        self.product = description
        self.interface = None

    def __repr__(self):
        return f"<MockPortInfo device={self.device!r} description={self.description!r}>"


class MockPortRegistry:
    """
    Simulates serial.tools.list_ports registry.
    Permits dynamic addition, removal, and querying of serial ports.
    """

    def __init__(self, populate_defaults=True):
        self._ports = {}
        if populate_defaults:
            self._ports["COM3"] = MockPortInfo(
                "COM3",
                "Silicon Labs CP210x USB to UART Bridge",
                "USB\\VID_10C4&PID_EA60\\0001"
            )
            self._ports["COM4"] = MockPortInfo(
                "COM4",
                "USB-Enhanced-SERIAL CH340",
                "USB\\VID_1A86&PID_7523\\0002"
            )
            self._ports["COM5"] = MockPortInfo(
                "COM5",
                "Standard Serial over Bluetooth link",
                "BTHENUM\\{00001101-0000-1000-8000-00805F9B34FB}_LOCALMFG&0000"
            )

    def comports(self):
        """Return a snapshot list of current MockPortInfo devices."""
        return list(self._ports.values())

    def add_port(self, device: str, description: str = "USB Serial Port", hwid: str = "USB\\VID_303A&PID_1001"):
        """Simulate plugging in a new device."""
        info = MockPortInfo(device, description, hwid)
        self._ports[device] = info
        return info

    def remove_port(self, device: str):
        """Simulate unplugging a device."""
        return self._ports.pop(device, None)

    def clear(self):
        """Remove all ports."""
        self._ports.clear()

    def set_ports(self, port_data):
        """Explicitly override all ports (accepts dict or list of port strings)."""
        self._ports.clear()
        if isinstance(port_data, dict):
            for dev, (desc, hwid) in port_data.items():
                self._ports[dev] = MockPortInfo(dev, desc, hwid)
        elif isinstance(port_data, list):
            for dev in port_data:
                self._ports[dev] = MockPortInfo(dev, f"USB Serial Device ({dev})", "USB VID:PID=10C4:EA60")
