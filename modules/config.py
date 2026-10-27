# -*- coding: utf-8 -*-
"""
Esp32 manager tool v1.0 - Configuration & Constants
"""
import os
import sys

# Backward-compatible re-export; the registry itself lives in mac_database.py.
from modules.mac_database import ESPRESSIF_OUIS

# ==========================================
# --- KHU VỰC DỄ DÀNG TÙY CHỈNH (CONFIG) ---
# ==========================================
# 1. Đường dẫn thư mục lưu file cấu hình. 
# Mặc định: os.path.expanduser("~") -> (Thường là C:\Users\<Tên_User_Của_Bạn>)
CONFIG_DIR = os.path.expanduser("~") 

# 2. Tên file cấu hình
# ── Settings file: <CONFIG_DIR>/setting_<scriptname>.json ──────────
CONFIG_FILENAME = "settings_esp32_manager_tool.json"

# Đường dẫn đầy đủ của file cấu hình (Tự động nối thư mục và tên file)
CONFIG_FILE = os.path.join(CONFIG_DIR, CONFIG_FILENAME)

APP_NAME = "Esp32 manager tool"
APP_VERSION = "1.0"
GITHUB_REPO = "ybao2004/esp32_manager_tool"

REPORT_FONT_SIZE = 10
DEFAULT_WINDOW_WIDTH = 1280 
DEFAULT_WINDOW_HEIGHT = 720
DEFAULT_GEOMETRY = f"{DEFAULT_WINDOW_WIDTH}x{DEFAULT_WINDOW_HEIGHT}+20+20"

Tu_dong_cuon = True
Them_dau_thoi_gian = False
So_dong_serial_toi_da = 20000

# Cấu hình tên hiển thị và lệnh gửi đi cho các nút F1 -> F15
CONTROL_CONFIG = {
    1: ("F1", "CMD_ON"),
    2: ("F2", "CMD_OFF"),
    3: ("F3", "CMD_RESET"),
    4: ("F4", "CMD_INFO"),
    5: ("F5", "CMD_START"),
    6: ("F6", "CMD_PAUSE"),
    7: ("F7", "CMD_STOP"),
    8: ("F8", "CMD_MODE_1"),
    9: ("F9", "CMD_MODE_2"),
    10: ("F10", "CMD_CUSTOM_1"),
    11: ("F11", "CMD_CUSTOM_2"),
    12: ("F12", "CMD_CUSTOM_3"),
    13: ("F13", "CMD_CUSTOM_4"),
    14: ("F14", "CMD_CUSTOM_5"),
    15: ("F15", "CMD_CUSTOM_6"),
}

# Cấu hình lệnh gửi đi cho các tác vụ Mạng (WiFi / Server)
NETWORK_COMMANDS = {
    "SCAN_WIFI": "SCAN_WIFI",                 
    "CONNECT_WIFI": "CONNECT_WIFI",           
    "DISCONNECT_WIFI": "DISCONNECT_WIFI",     
    "CONNECT_SERVER": "CONNECT_SERVER",       
    "DISCONNECT_SERVER": "DISCONNECT_SERVER"  
}

# --- BẢNG MÀU CHO GIAO DIỆN (PALETTES) ---
LIGHT_PALETTE = {
    "bg": "#f0f0f0", "fg": "#000000", "text_bg": "#ffffff", "text_fg": "#000000",
    "btn_bg": "#e1e1e1", "btn_hover": "#d4d4d4", "btn_pressed": "#c8c8c8",
    "disabled_bg": "#e9e9e9", "disabled_fg": "#8a8a8a", "border": "#cccccc",
    "accent": "#005fb8", "success": "#008000", "error": "#d50000", "warning": "#d55e00",
    "select_bg": "#005fb8", "select_fg": "#ffffff"
}

DARK_PALETTE = {
    "bg": "#2b2b2b", "fg": "#f0f0f0", "text_bg": "#1e1e1e", "text_fg": "#ffffff",
    "btn_bg": "#444444", "btn_hover": "#5a5a5a", "btn_pressed": "#333333",
    "disabled_bg": "#3a3a3a", "disabled_fg": "#a0a0a0", "border": "#4d4d4d",
    "accent": "#4dabf7", "success": "#00e676", "error": "#ff6b6b", "warning": "#ffaa00",
    "select_bg": "#264f78", "select_fg": "#ffffff"
}

COMMON_BAUDS = ["Tự động", "9600", "57600", "74880", "115200", "230400", "460800", "921600"]
FLASH_BAUDS = ["921600", "460800", "230400", "115200"]
FLASH_CHIP_TARGETS = [
    "auto", "esp32", "esp32s2", "esp32s3", "esp32c2", "esp32c3",
    "esp32c5", "esp32c6", "esp32c61", "esp32h2", "esp32h21",
    "esp32h4", "esp32p4", "esp32s31", "esp8266",
]

# --- CSDL Chip và Flash ---
FLASH_MANUFACTURERS = {
    "20": "XMC", "68": "XMC", "c8": "GigaDevice", "ef": "Winbond", "1c": "EON",
    "0b": "Puya", "85": "Puya", "d8": "Puya", "a1": "Fudan", "c2": "Macronix (MX)",
    "e0": "Fremont", "5e": "Zbit", "eb": "TH (Tongxin)", "31": "Wwcache"
}

CHIP_DATABASE = { 
    "ESP32": { "name": "ESP32", "architecture": "Xtensa dual-core 32-bit LX6", "cores": 2, "cpu_freq_mhz": [160, 240], "mips_max": "600 MIPS (DMIPS)", "sram_kb": 520, "rom_kb": 448, "wifi": "Wi-Fi 4 (802.11 b/g/n)", "bluetooth": "Bluetooth v4.2 BR/EDR + BLE", "features": ["ADC", "DAC", "TWAI (CAN)", "Cảm biến Hall"] }, 
    "ESP32-D2WD": { "name": "ESP32-D2WD", "architecture": "Xtensa dual-core 32-bit LX6", "cores": 2, "cpu_freq_mhz": [160, 240], "mips_max": "600 MIPS (DMIPS)", "sram_kb": 520, "rom_kb": 448, "wifi": "Wi-Fi 4 (802.11 b/g/n)", "bluetooth": "Bluetooth v4.2 BR/EDR + BLE", "features": ["Flash 2MB tích hợp", "ADC", "DAC"] }, 
    "ESP32-S2": { "name": "ESP32-S2", "architecture": "Xtensa single-core 32-bit LX7", "cores": 1, "cpu_freq_mhz": [160, 240], "mips_max": "300 MIPS (DMIPS)", "sram_kb": 320, "rom_kb": 128, "wifi": "Wi-Fi 4 (802.11 b/g/n)", "bluetooth": None, "features": ["USB OTG", "LCD/Camera Interface", "Cảm biến nhiệt độ"] }, 
    "ESP32-S3": { "name": "ESP32-S3", "architecture": "Xtensa dual-core 32-bit LX7", "cores": 2, "cpu_freq_mhz": [160, 240], "mips_max": "600 MIPS (DMIPS)", "sram_kb": 512, "rom_kb": 384, "wifi": "Wi-Fi 4 (802.11 b/g/n)", "bluetooth": "Bluetooth 5 (LE)", "features": ["AI Acceleration", "USB OTG", "LCD/Camera Interface"] }, 
    "ESP32-C2": { "name": "ESP32-C2 (ESP8684)", "architecture": "RISC-V 32-bit single-core", "cores": 1, "cpu_freq_mhz": [120], "mips_max": "135 MIPS (DMIPS)", "sram_kb": 272, "rom_kb": 576, "wifi": "Wi-Fi 4 (802.11 b/g/n)", "bluetooth": "Bluetooth 5 (LE)", "features": ["Low Power Consumption"] }, 
    "ESP32-C3": { "name": "ESP32-C3", "architecture": "RISC-V 32-bit single-core", "cores": 1, "cpu_freq_mhz": [160], "mips_max": "408 CoreMark (~400 MIPS)", "sram_kb": 400, "rom_kb": 384, "wifi": "Wi-Fi 4 (802.11 b/g/n)", "bluetooth": "Bluetooth 5 (LE)", "features": ["ADC", "TWAI (CAN)", "Cảm biến nhiệt độ"] }, 
    "ESP32-C5": { "name": "ESP32-C5", "architecture": "RISC-V 32-bit single-core + LP core", "cores": 1, "cpu_freq_mhz": [240], "mips_max": "Tối đa 240 MHz", "sram_kb": 400, "rom_kb": 320, "wifi": "Wi-Fi 6 dual-band (2.4/5 GHz)", "bluetooth": "Bluetooth Core 6.0 (LE)", "features": ["802.15.4 (Thread/Zigbee)", "HP SRAM 384 KB + LP SRAM 16 KB"] }, 
    "ESP32-C6": { "name": "ESP32-C6", "architecture": "RISC-V 32-bit single-core", "cores": 1, "cpu_freq_mhz": [160], "mips_max": "400 MIPS (DMIPS)", "sram_kb": 512, "rom_kb": 320, "wifi": "Wi-Fi 6 (802.11ax)", "bluetooth": "Bluetooth 5.3 (LE)", "features": ["802.15.4 (Thread/Zigbee)", "Low-power LP Core"] }, 
    "ESP32-C61": { "name": "ESP32-C61", "architecture": "RISC-V 32-bit single-core", "cores": 1, "cpu_freq_mhz": [160], "mips_max": "Tối đa 160 MHz", "sram_kb": 320, "rom_kb": 256, "wifi": "Wi-Fi 6 (802.11ax)", "bluetooth": "Bluetooth Core 6.0 (LE)", "features": ["Wi-Fi 6 tiết kiệm chi phí", "USB Serial/JTAG"] }, 
    "ESP32-H2": { "name": "ESP32-H2", "architecture": "RISC-V 32-bit single-core", "cores": 1, "cpu_freq_mhz": [96], "mips_max": "240 MIPS (DMIPS)", "sram_kb": 320, "rom_kb": 128, "wifi": None, "bluetooth": "Bluetooth 5.3 (LE)", "features": ["802.15.4 (Thread/Zigbee)", "Low Power Consumption"] }, 
    "ESP32-H21": { "name": "ESP32-H21", "architecture": "RISC-V 32-bit single-core", "cores": 1, "cpu_freq_mhz": [96], "mips_max": "Tối đa 96 MHz", "sram_kb": 320, "rom_kb": 128, "wifi": None, "bluetooth": "Bluetooth 5.4 (LE)", "features": ["802.15.4 (Thread/Zigbee)", "Thiết kế công suất thấp"] },
    "ESP32-H4": { "name": "ESP32-H4", "architecture": "RISC-V 32-bit dual-core", "cores": 2, "cpu_freq_mhz": [96], "mips_max": "Tối đa 96 MHz", "sram_kb": 384, "rom_kb": 128, "wifi": None, "bluetooth": "Bluetooth 5.4 (LE)", "features": ["802.15.4 (Thread/Zigbee)", "Bluetooth Channel Sounding"] },
    "ESP32-P4": { "name": "ESP32-P4", "architecture": "RISC-V dual-core 32-bit + LP core", "cores": 2, "cpu_freq_mhz": [360, 400], "mips_max": "Tối đa 400 MHz", "sram_kb": 800, "rom_kb": 144, "wifi": None, "bluetooth": None, "features": ["HP L2MEM 768 KB + LP SRAM 32 KB", "MIPI-DSI/CSI", "H.264 Encoder", "2D Graphics Acceleration"] }, 
    "ESP32-S31": { "name": "ESP32-S31", "architecture": "RISC-V 32-bit dual-core + LP core", "cores": 2, "cpu_freq_mhz": [320], "mips_max": "Tối đa 320 MHz", "sram_kb": 544, "rom_kb": 320, "wifi": "Wi-Fi 6 (2.4 GHz)", "bluetooth": "Bluetooth 5.4 LE + Classic", "features": ["802.15.4", "USB 2.0 High-Speed OTG", "JPEG/PPA", "CAN FD"] },
    "ESP8266": { "name": "ESP8266EX", "architecture": "Xtensa single-core 32-bit L106", "cores": 1, "cpu_freq_mhz": [80, 160], "mips_max": "160 MIPS", "sram_kb": 96, "rom_kb": 64, "wifi": "Wi-Fi 4 (802.11 b/g/n)", "bluetooth": None, "features": ["ADC"] }, 
    "ESP8285": { "name": "ESP8285", "architecture": "Xtensa single-core 32-bit L106", "cores": 1, "cpu_freq_mhz": [80, 160], "mips_max": "160 MIPS", "sram_kb": 96, "rom_kb": 64, "wifi": "Wi-Fi 4 (802.11 b/g/n)", "bluetooth": None, "features": ["Flash 1MB tích hợp", "ADC"] }
}
