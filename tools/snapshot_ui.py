# -*- coding: utf-8 -*-
"""
Tự động tạo bộ ảnh chụp màn hình UI v1.6 (36 screenshots).
6 trang x 6 theme variants:
- fluent_light, fluent_dark
- engineering_light, engineering_dark
- vscode_light, vscode_dark
Độ phân giải chuẩn: 1366 x 820 px (Offscreen Headless, Font Windows Segoe UI & Consolas).
"""
import os
import sys
import shutil
from pathlib import Path

# Đảm bảo chạy không cần màn hình vật lý (Headless offscreen)
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication

# Đảm bảo thư mục gốc nằm trong sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from modules.app_core import InspectorApp
from modules.ui.theme.manager import ThemeManager
from modules.partition.partition_model import PartitionEntry


def populate_sample_data(window: InspectorApp):
    """Nạp dữ liệu mẫu chân thực vào giao diện để ảnh chụp có đầy đủ thông tin."""
    # 1. Thanh kết nối toàn cục
    if hasattr(window, "port_cb"):
        if window.port_cb.findText("COM7") < 0:
            window.port_cb.addItem("COM7")
        window.port_cb.setCurrentText("COM7")
    if hasattr(window, "baud_cb"):
        window.baud_cb.setCurrentText("115200")
    if hasattr(window, "lbl_conn"):
        window.lbl_conn.setText("ĐÃ KẾT NỐI: COM7 @ 115200 bps")
        if hasattr(window, "_refresh_status_bar_theme"):
            window._refresh_status_bar_theme()
    if hasattr(window, "conn_bar"):
        window.conn_bar.set_chip_badge_info("ESP32-P4 · 16MB Flash · 32MB PSRAM", is_active=True)

    # 2. Trang 1: Kiểm tra chip (Inspector - nạp báo cáo thật + 4 thẻ KPI)
    if hasattr(window, "_display_formatted_report"):
        window._display_formatted_report({
            "chip_name_key": "ESP32-P4",
            "chip_line": "ESP32-P4 (revision v3.2)",
            "features_line": "High-Performance MCU, Dual-Core RISC-V 400MHz, LP-Core, 2D-DMA, MIPI-DSI/CSI",
            "crystal_line": "40MHz",
            "mac": "e8:f6:0a:eb:89:94",
            "flash_manufacturer": "0xef",
            "flash_device": "0x4018",
            "flash_mb": 16.0,
            "psram_mb": 32,
            "psram_vendor": "APMemory (0x0D - Gen 4)",
            "psram_speed": "200MHz",
            "psram_mode": "HEX / 16-bit DDR",
            "fw_project_name": "wt_factory_esp32p4_hmi",
            "fw_version": "v2.4.0-prod",
            "fw_idf_ver": "v5.4.1-dirty",
            "fw_compile_time": "Nov 12 2026 / 14:20:05",
            "fw_cpu_freq": "400 MHz",
            "partitions": [
                "nvs | data | nvs | 0x9000 | 0x6000 (24 KB)",
                "otadata | data | ota | 0xF000 | 0x2000 (8 KB)",
                "app0 | app | ota_0 | 0x20000 | 0x200000 (2.00 MB)",
                "storage | data | littlefs | 0x420000 | 0xBE0000 (11.88 MB)",
            ],
            "heap_regions": [
                "L2MEM: 768 KiB (@ 0x4FF00000)",
                "PSRAM Pool: 32768 KiB (@ 0x48000000)",
            ],
        })

    # 3. Trang 2: Serial Monitor
    monitor_sample = (
        "I (263) hex_psram: vendor id    : 0x0d (AP)\n"
        "I (264) hex_psram: dev id       : 0x03 (generation 4)\n"
        "I (269) hex_psram: density      : 0x07 (256 Mbit)\n"
        "I (467) esp_psram: Found 32MB PSRAM device @ 200MHz\n"
        "I (471) cpu_start: Multicore app (HP RISC-V Dual Core @ 400MHz)\n"
        "I (1387) esp_psram: SPI SRAM memory test OK\n"
        "I (1403) app_init: Project name:     wt_factory_esp32p4_hmi\n"
        "I (1422) app_init: ESP-IDF:          v5.4.1\n"
        "I (1433) efuse_init: Chip rev:       v3.2\n"
        "I (1466) esp_psram: Adding pool of 32768K of PSRAM memory to heap allocator\n"
        "I (1519) main_task: Started on CPU0\n"
        "I (1539) factory_firmware: Starting HUSB CDC and pin-to-pin factory service\n"
        "I (1749) factory_test_dut: HUSB CDC factory DUT ready: board=WT9932P4C61-TINY, gpio_count=27\n"
    )
    if hasattr(window, "monitor_txt"):
        try:
            window.monitor_txt.delete("1.0", "end")
            window.monitor_txt.insert("1.0", monitor_sample)
        except Exception:
            pass

    # 4. Trang 3: Nạp Firmware
    if hasattr(window, "flash_file_rows") and len(window.flash_file_rows) >= 3:
        samples = [
            (True, "D:/Firmware/esp32p4_hmi/build/bootloader/bootloader.bin", "0x2000", "29.4 KB"),
            (True, "D:/Firmware/esp32p4_hmi/build/partition_table/partition-table.bin", "0x8000", "4.0 KB"),
            (True, "D:/Firmware/esp32p4_hmi/build/wt_factory_esp32p4_hmi.bin", "0x20000", "1.48 MB"),
        ]
        for idx, (en, pth, off, sz_txt) in enumerate(samples):
            row = window.flash_file_rows[idx]
            row["var_enable"].set(en)
            row["path_entry"].delete(0, "end")
            row["path_entry"].insert(0, pth)
            row["offset_entry"].delete(0, "end")
            row["offset_entry"].insert(0, off)
            if "size_label" in row:
                row["size_label"].setText(sz_txt)

    if hasattr(window, "flasher_txt"):
        flasher_sample = (
            "esptool.py v4.8.1\n"
            "Serial port COM7\n"
            "Chip is ESP32-P4 (revision v3.2)\n"
            "Configuring flash size: 16MB...\n"
            "Writing at 0x00020000... (74 %)\n"
            "Wrote 1552384 bytes (912408 compressed) at 0x00020000 in 10.2 seconds (effective 1217.5 kbit/s)...\n"
            "Hash of data verified.\n"
        )
        window.flasher_txt.delete("1.0", "end")
        window.flasher_txt.insert("1.0", flasher_sample)

    # 5. Trang 4: Bảng phân vùng (Partition Wizard)
    if hasattr(window, "table") and window.table is not None:
        if hasattr(window, "part_chip_var") and hasattr(window, "_on_chip_changed"):
            window.part_chip_var.set("ESP32-P4")
            window._on_chip_changed()
        window.table.flash_size = 16 * 1024 * 1024
        window.table.entries.clear()
        e_nvs = PartitionEntry("nvs", "data", "nvs", 0x9000, 0x6000)
        e_ota = PartitionEntry("otadata", "data", "ota", 0xF000, 0x2000)
        e_app0 = PartitionEntry("app0", "app", "ota_0", 0x20000, 0x200000)
        e_app0.used_size = int(1.48 * 1024 * 1024)
        e_app1 = PartitionEntry("app1", "app", "ota_1", 0x220000, 0x200000)
        e_fs = PartitionEntry("storage", "data", "littlefs", 0x420000, 0xBE0000)
        for e in (e_nvs, e_ota, e_app0, e_app1, e_fs):
            window.table.add_entry(e)
        if hasattr(window, "refresh_partition_views"):
            window.refresh_partition_views()


def generate_all_snapshots():
    out_dir = root_dir / "screenshots_v16"
    out_dir.mkdir(parents=True, exist_ok=True)

    artifact_dir = Path(r"C:\Users\Y Bao\.gemini\antigravity\brain\a4edb686-92dc-4d00-be34-b385cf48e702\screenshots_v16")
    artifact_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    ThemeManager.ensure_system_fonts()

    window = InspectorApp(auto_start=False)
    window.resize(1366, 820)
    window.show()

    # Nạp dữ liệu mẫu
    populate_sample_data(window)

    theme_configs = [
        ("fluent", False, "fluent_light"),
        ("fluent", True, "fluent_dark"),
        ("engineering", False, "engineering_light"),
        ("engineering", True, "engineering_dark"),
        ("vscode", False, "vscode_light"),
        ("vscode", True, "vscode_dark"),
    ]

    pages = [
        (0, "01_inspector"),
        (1, "02_monitor"),
        (2, "03_flasher"),
        (3, "04_partition"),
        (4, "05_backup"),
        (5, "06_settings"),
    ]

    tm = ThemeManager.instance()
    generated_files = []

    print(f"Bắt đầu xuất 36 ảnh chụp màn hình UI v1.6 vào thư mục: {out_dir}")

    for preset, is_dark, theme_label in theme_configs:
        tm.apply(preset, is_dark)
        app.processEvents()

        for page_idx, page_name in pages:
            window.sidebar.select(page_idx)
            for _ in range(6):
                app.processEvents()

            pixmap = window.grab()
            file_name = f"{page_name}_{theme_label}.png"
            target_path = out_dir / file_name
            pixmap.save(str(target_path), "PNG")
            shutil.copy2(target_path, artifact_dir / file_name)
            generated_files.append(target_path)
            print(f"  [OK] Đã xuất: {file_name} ({pixmap.width()}x{pixmap.height()})")

    # Chụp thêm 1 ảnh Chế độ Bảng thông số 2 cột (Trang 1 - Grid Mode) để đối chiếu Hybrid View
    tm.apply("fluent", False)
    window.sidebar.select(0)
    window.page_inspector.btn_view_grid.click()
    for _ in range(6):
        app.processEvents()
    grid_pix = window.grab()
    grid_name = "01b_inspector_grid_fluent_light.png"
    grid_pix.save(str(out_dir / grid_name), "PNG")
    shutil.copy2(out_dir / grid_name, artifact_dir / grid_name)
    print(f"  [OK] Đã xuất: {grid_name}")

    window.close()
    print(f"\nHoàn tất xuất {len(generated_files)} + 1 ảnh chụp màn hình UI v1.6!")
    return generated_files


if __name__ == "__main__":
    generate_all_snapshots()
