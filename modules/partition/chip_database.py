# -*- coding: utf-8 -*-
"""
ESP32 Partition Engine - ESP32 Family Chip & Board Database
Hỗ trợ đầy đủ tất cả các dòng chip trong hệ sinh thái Espressif.
"""
from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class ChipInfo:
    id: str
    name: str
    arch: str
    cores: int
    wireless: str
    default_flash_size: int
    bootloader_offset: int
    supported_flash_sizes: List[int]
    description: str


CHIP_FAMILY_DATABASE: Dict[str, ChipInfo] = {
    "esp32": ChipInfo(
        id="esp32",
        name="ESP32 (Classic)",
        arch="Xtensa dual-core LX6 @ 240MHz",
        cores=2,
        wireless="Wi-Fi 4 (802.11b/g/n) + Bluetooth 4.2 / BLE",
        default_flash_size=4 * 1024 * 1024,
        bootloader_offset=0x1000,
        supported_flash_sizes=[2 * 1024 * 1024, 4 * 1024 * 1024, 8 * 1024 * 1024, 16 * 1024 * 1024],
        description="Dòng chip tiêu chuẩn phổ biến nhất, 2 nhân CPU mạnh mẽ."
    ),
    "esp32s2": ChipInfo(
        id="esp32s2",
        name="ESP32-S2",
        arch="Xtensa single-core LX7 @ 240MHz",
        cores=1,
        wireless="Wi-Fi 4 (802.11b/g/n) (Không có Bluetooth)",
        default_flash_size=4 * 1024 * 1024,
        bootloader_offset=0x1000,
        supported_flash_sizes=[2 * 1024 * 1024, 4 * 1024 * 1024, 8 * 1024 * 1024, 16 * 1024 * 1024],
        description="Có cổng USB-OTG phần cứng, bảo mật phần cứng nâng cao."
    ),
    "esp32s3": ChipInfo(
        id="esp32s3",
        name="ESP32-S3",
        arch="Xtensa dual-core LX7 @ 240MHz (AI Vector)",
        cores=2,
        wireless="Wi-Fi 4 (802.11b/g/n) + Bluetooth 5.0 / BLE",
        default_flash_size=8 * 1024 * 1024,
        bootloader_offset=0x0000,
        supported_flash_sizes=[4 * 1024 * 1024, 8 * 1024 * 1024, 16 * 1024 * 1024, 32 * 1024 * 1024],
        description="Chuyên AI, Camera, màn hình màu cảm ứng LCD, USB JTAG/OTG."
    ),
    "esp32c3": ChipInfo(
        id="esp32c3",
        name="ESP32-C3",
        arch="RISC-V single-core 32-bit @ 160MHz",
        cores=1,
        wireless="Wi-Fi 4 (802.11b/g/n) + Bluetooth 5.0 / BLE",
        default_flash_size=4 * 1024 * 1024,
        bootloader_offset=0x0000,
        supported_flash_sizes=[2 * 1024 * 1024, 4 * 1024 * 1024, 8 * 1024 * 1024],
        description="Kiến trúc RISC-V mã nguồn mở, thay thế hoàn hảo cho ESP8266."
    ),
    "esp32c2": ChipInfo(
        id="esp32c2",
        name="ESP32-C2 / ESP8684",
        arch="RISC-V single-core 32-bit @ 120MHz",
        cores=1,
        wireless="Wi-Fi 4 (802.11b/g/n) + Bluetooth 5.0 (LE)",
        default_flash_size=2 * 1024 * 1024,
        bootloader_offset=0x0000,
        supported_flash_sizes=[1 * 1024 * 1024, 2 * 1024 * 1024, 4 * 1024 * 1024],
        description="Dòng chip giá rẻ, tối ưu cho bóng đèn thông minh, ổ cắm IoT."
    ),
    "esp32c5": ChipInfo(
        id="esp32c5",
        name="ESP32-C5",
        arch="RISC-V single-core 32-bit @ 240MHz",
        cores=1,
        wireless="Dual-band 2.4/5GHz Wi-Fi 6 + Bluetooth 5.0 (LE)",
        default_flash_size=4 * 1024 * 1024,
        bootloader_offset=0x2000,
        supported_flash_sizes=[4 * 1024 * 1024, 8 * 1024 * 1024, 16 * 1024 * 1024],
        description="Hỗ trợ Wi-Fi băng tần kép 2.4GHz & 5GHz tốc độ cao."
    ),
    "esp32c6": ChipInfo(
        id="esp32c6",
        name="ESP32-C6",
        arch="RISC-V single-core 32-bit @ 160MHz",
        cores=1,
        wireless="Wi-Fi 6 (802.11ax) + Zigbee / Thread (802.15.4) + BLE 5.3",
        default_flash_size=4 * 1024 * 1024,
        bootloader_offset=0x0000,
        supported_flash_sizes=[4 * 1024 * 1024, 8 * 1024 * 1024, 16 * 1024 * 1024],
        description="Chuẩn Matter, Zigbee, Thread cho thiết bị Smart Home thế hệ mới."
    ),
    "esp32c61": ChipInfo(
        id="esp32c61",
        name="ESP32-C61",
        arch="RISC-V single-core 32-bit @ 160MHz",
        cores=1,
        wireless="Wi-Fi 6 + Bluetooth 5.0 (LE)",
        default_flash_size=4 * 1024 * 1024,
        bootloader_offset=0x0000,
        supported_flash_sizes=[2 * 1024 * 1024, 4 * 1024 * 1024, 8 * 1024 * 1024],
        description="Bản rút gọn chi phí của C6, tập trung Wi-Fi 6 và BLE."
    ),
    "esp32h2": ChipInfo(
        id="esp32h2",
        name="ESP32-H2",
        arch="RISC-V single-core 32-bit @ 96MHz",
        cores=1,
        wireless="IEEE 802.15.4 (Thread/Zigbee) + Bluetooth 5.2 (Không có Wi-Fi)",
        default_flash_size=4 * 1024 * 1024,
        bootloader_offset=0x0000,
        supported_flash_sizes=[2 * 1024 * 1024, 4 * 1024 * 1024, 8 * 1024 * 1024],
        description="Tiêu thụ điện cực thấp, chuyên cảm biến chạy pin dùng sóng Zigbee/Thread."
    ),
    "esp32p4": ChipInfo(
        id="esp32p4",
        name="ESP32-P4 (High-Performance)",
        arch="RISC-V dual-core @ 400MHz",
        cores=2,
        wireless="Không tích hợp RF (Dành cho xử lý tính toán cực mạnh)",
        default_flash_size=16 * 1024 * 1024,
        bootloader_offset=0x2000,
        supported_flash_sizes=[8 * 1024 * 1024, 16 * 1024 * 1024, 32 * 1024 * 1024],
        description="CPU 400MHz, bộ giải mã H.264, màn hình MIPI-DSI, camera MIPI-CSI."
    ),
    "esp8266": ChipInfo(
        id="esp8266",
        name="ESP8266 (Legacy)",
        arch="Xtensa single-core L106 @ 80/160MHz",
        cores=1,
        wireless="Wi-Fi 4 (802.11b/g/n)",
        default_flash_size=4 * 1024 * 1024,
        bootloader_offset=0x0000,
        supported_flash_sizes=[1 * 1024 * 1024, 2 * 1024 * 1024, 4 * 1024 * 1024],
        description="Bo mạch ESP đời đầu giá rẻ."
    )
}


def get_chip_info(chip_id: str) -> ChipInfo:
    """Lấy thông số chi tiết của chip theo ID"""
    clean_id = str(chip_id or "esp32").lower().replace("-", "")
    return CHIP_FAMILY_DATABASE.get(clean_id, CHIP_FAMILY_DATABASE["esp32"])
