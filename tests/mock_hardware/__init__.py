# -*- coding: utf-8 -*-
"""
Mock Hardware Package:
Provides offline simulation for PySerial, COM Port Registry,
esptool Bootloader Engine, and Headless Tkinter App Harness.
"""
from tests.mock_hardware.mock_serial import MockSerial
from tests.mock_hardware.mock_registry import MockPortInfo, MockPortRegistry
from tests.mock_hardware.mock_esptool import MockEsptoolEngine, MOCK_PROFILES
from tests.mock_hardware.app_harness import HeadlessAppHarness

__all__ = [
    "MockSerial",
    "MockPortInfo",
    "MockPortRegistry",
    "MockEsptoolEngine",
    "MOCK_PROFILES",
    "HeadlessAppHarness",
]
