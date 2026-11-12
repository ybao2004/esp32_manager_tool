import json
import os
import tempfile
import unittest

import modules.esptool_util as esptool_util
from modules.binary_scanner import (
    default_bootloader_offset, scan_project_bin_files, validate_binary_segments
)
from modules.esptool_util import (
    clean_esptool_ansi,
    decode_flash_device_id,
    derive_mac_addresses,
    esptool_command_succeeded,
    get_chip_data,
    parse_esp_app_desc,
    parse_esp_bootloader_desc,
    parse_esp_image_header,
    parse_esptool_output,
)
from modules.mac_database import ESPRESSIF_OUIS, get_mac_oui, is_espressif_oui
from modules.stream_util import StreamInterceptor


class MacDatabaseTests(unittest.TestCase):
    def test_full_espressif_snapshot_and_normalization(self):
        self.assertEqual(len(ESPRESSIF_OUIS), 335)
        self.assertTrue(is_espressif_oui("00-4b-12-aa-bb-cc"))
        self.assertTrue(is_espressif_oui("FCF5C4000001"))
        self.assertEqual(get_mac_oui("44:7b:30:01:02:03"), "44:7B:30")

    def test_oui_lookup_does_not_claim_unknown_or_invalid_mac(self):
        self.assertFalse(is_espressif_oui("8C:D0:B2:00:00:00"))
        self.assertFalse(is_espressif_oui("not-a-mac"))
        self.assertFalse(is_espressif_oui("00:4B:12:00:00:00garbage"))
        self.assertFalse(is_espressif_oui("00:4B-12:00:00:00"))


class BinaryUtilityTests(unittest.TestCase):
    def test_default_bootloader_offsets_cover_new_targets(self):
        self.assertEqual(default_bootloader_offset("esp32"), "0x1000")
        self.assertEqual(default_bootloader_offset("esp32s2"), "0x1000")
        self.assertEqual(default_bootloader_offset("esp32c5"), "0x2000")
        self.assertEqual(default_bootloader_offset("esp32p4"), "0x2000")
        self.assertEqual(default_bootloader_offset("esp32s31"), "0x2000")
        self.assertEqual(default_bootloader_offset("esp32c61"), "0x0")

    def test_segments_are_normalized_sorted_and_checked(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = os.path.join(temp_dir, "first.bin")
            second = os.path.join(temp_dir, "second.bin")
            with open(first, "wb") as stream:
                stream.write(b"a" * 16)
            with open(second, "wb") as stream:
                stream.write(b"b" * 16)

            valid, _message, pairs, max_end = validate_binary_segments([
                ("0x2000", second), ("0x1000", first),
            ])
            self.assertTrue(valid)
            self.assertEqual([offset for offset, _path in pairs], ["0x1000", "0x2000"])
            self.assertEqual(max_end, 0x2010)

    def test_segments_reject_overlap_duplicate_missing_and_low_offset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = os.path.join(temp_dir, "first.bin")
            second = os.path.join(temp_dir, "second.bin")
            with open(first, "wb") as stream:
                stream.write(b"a" * 32)
            with open(second, "wb") as stream:
                stream.write(b"b" * 32)

            self.assertFalse(validate_binary_segments([("0x1000", first), ("0x1010", second)])[0])
            self.assertFalse(validate_binary_segments([("0x1000", first), ("0x2000", first)])[0])
            self.assertFalse(validate_binary_segments([("0x1000", os.path.join(temp_dir, "missing.bin"))])[0])
            self.assertFalse(validate_binary_segments([("0x1000", first)], min_offset="0x2000")[0])

    def test_generic_scan_keeps_same_named_files_from_distinct_builds(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for folder in ("build_a", "build_b"):
                target_dir = os.path.join(temp_dir, folder)
                os.makedirs(target_dir)
                with open(os.path.join(target_dir, "firmware.bin"), "wb") as stream:
                    stream.write(folder.encode("ascii"))
            results = scan_project_bin_files(temp_dir, "esp32")
            self.assertEqual(len(results), 2)
            self.assertEqual(sum(bool(item["enabled"]) for item in results), 1)

    def test_esp_idf_scan_sorts_offsets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            for name in ("app.bin", "bootloader.bin"):
                with open(os.path.join(temp_dir, name), "wb") as stream:
                    stream.write(b"firmware")
            with open(os.path.join(temp_dir, "flasher_args.json"), "w", encoding="utf-8") as stream:
                json.dump({"flash_files": {"0x10000": "app.bin", "0x0": "bootloader.bin"}}, stream)

            results = scan_project_bin_files(temp_dir, "esp32s3")
            self.assertEqual([item["offset"] for item in results], ["0x0", "0x10000"])


class EsptoolUtilityTests(unittest.TestCase):
    def test_runner_passes_arguments_directly_and_records_exit_code(self):
        calls = []

        class FakeEsptool:
            __version__ = "5.0.0"

            @staticmethod
            def main(arguments):
                calls.append(arguments)
                print("fake output")

        original = esptool_util.esptool
        esptool_util.esptool = FakeEsptool
        self.addCleanup(setattr, esptool_util, "esptool", original)

        output = esptool_util.run_esptool_command(["--chip", "esp32", "flash-id"])
        self.assertEqual(calls, [["--chip", "esp32", "flash-id"]])
        self.assertTrue(esptool_command_succeeded(output))
        self.assertIn("fake output", output)

    def test_runner_translates_v5_names_for_esptool_v4(self):
        calls = []

        class FakeEsptoolV4:
            __version__ = "4.8.1"

            @staticmethod
            def main(arguments):
                calls.append(arguments)

        original = esptool_util.esptool
        esptool_util.esptool = FakeEsptoolV4
        self.addCleanup(setattr, esptool_util, "esptool", original)

        esptool_util.run_esptool_command(["flash-id", "read-mac"])
        self.assertEqual(calls, [["flash_id", "read_mac"]])

    def test_runner_records_system_exit_failure(self):
        class FailingEsptool:
            @staticmethod
            def main(_arguments):
                raise SystemExit(2)

        original = esptool_util.esptool
        esptool_util.esptool = FailingEsptool
        self.addCleanup(setattr, esptool_util, "esptool", original)

        output = esptool_util.run_esptool_command(["flash_id"])
        self.assertFalse(esptool_command_succeeded(output))
        self.assertIn("code: 2", output)

    def test_exit_status_requires_explicit_success(self):
        self.assertTrue(esptool_command_succeeded("done\n[Esptool exited with code: 0]"))
        self.assertFalse(esptool_command_succeeded("wrote output\n[Esptool exited with code: 2]"))
        self.assertFalse(esptool_command_succeeded("wrote output"))
        self.assertFalse(esptool_command_succeeded("A fatal error occurred\n[Esptool exited with code: 0]"))

    def test_output_parser_and_case_insensitive_chip_lookup(self):
        parsed = parse_esptool_output({"flash": (
            "Detecting chip type... ESP32-S3\n"
            "Chip is ESP32-S3 (revision v0.2)\n"
            "MAC: 01:23:45:67:89:AB\n"
            "Manufacturer: 0xef\nDetected flash size: 8MB"
        )})
        self.assertEqual(parsed["chip_name_key"], "ESP32-S3")
        self.assertEqual(parsed["revision"], "0.2")
        self.assertEqual(parsed["mac"], "0123456789AB")
        self.assertEqual(parsed["flash_mb"], 8.0)
        self.assertEqual(get_chip_data("esp32-s3")["name"], "ESP32-S3")

    def test_output_parser_supports_esptool_v5_chip_line(self):
        parsed = parse_esptool_output({"flash": (
            "Connected to ESP32-S3 on COM4:\n"
            "Chip type:          ESP32-S3 (QFN56) (revision v0.1)\n"
            "Features:           Wi-Fi, BT 5 (LE), Dual Core, 240MHz\n"
            "Crystal frequency:  40MHz\n"
            "MAC:                F4:12:FA:87:C6:DC\n"
            "Auto-detected flash size: 8MB"
        )})
        self.assertEqual(get_chip_data(parsed["chip_name_key"])["name"], "ESP32-S3")
        self.assertEqual(parsed["revision"], "0.1")
        self.assertEqual(parsed["crystal"], "40MHz")
        self.assertEqual(parsed["flash_mb"], 8.0)

    def test_chip_lookup_does_not_confuse_s31_with_s3(self):
        self.assertEqual(get_chip_data("ESP32-S31 (revision v0.0)")["name"], "ESP32-S31")
        self.assertEqual(get_chip_data("ESP32-D0WDQ6 (revision 1)")["name"], "ESP32")
        self.assertEqual(get_chip_data("ESP32-D0WDQ5 (revision 1)")["name"], "ESP32")

    def test_chip_lookup_supports_marketing_aliases_and_new_targets(self):
        self.assertEqual(get_chip_data("ESP8684")['name'], "ESP32-C2 (ESP8684)")
        self.assertEqual(get_chip_data("ESP8685")['name'], "ESP32-C3")
        self.assertEqual(get_chip_data("ESP32-H21")['name'], "ESP32-H21")
        self.assertEqual(get_chip_data("ESP32-H4")['name'], "ESP32-H4")

    def test_chip_lookup_supports_esp8266ex_name(self):
        self.assertEqual(get_chip_data("ESP8266EX")['name'], "ESP8266EX")

    def test_mac_derivation_wraps_at_48_bits(self):
        addresses = derive_mac_addresses("FFFFFFFFFFFF")
        self.assertEqual(addresses["MAC Wi-Fi Station"], "FF:FF:FF:FF:FF:FF")
        self.assertEqual(addresses["MAC Wi-Fi AP"], "00:00:00:00:00:00")
        self.assertEqual(addresses["MAC Bluetooth"], "00:00:00:00:00:01")
        self.assertEqual(addresses["MAC Ethernet / Nội bộ"], "00:00:00:00:00:02")

    def test_clean_ansi_and_decode_flash_device_id(self):
        raw = "Detecting chip type... ESP32-P4\n[1A[2K[1A[2K[1A[2KConnected to ESP32-P4 on COM7:"
        cleaned = clean_esptool_ansi(raw)
        self.assertNotIn("[1A[2K", cleaned)
        self.assertIn("Connected to ESP32-P4 on COM7:", cleaned)

        decoded = decode_flash_device_id("4018")
        self.assertIn("0x4018", decoded)
        self.assertIn("16 MB", decoded)
        self.assertIn("128 Mbit", decoded)

    def test_parse_esp32p4_full_inspection_and_boot_log(self):
        sample_output = (
            "esptool v5.3.0\n"
            "Serial port COM7:\n"
            "Connecting...\n"
            "Detecting chip type... ESP32-P4\n"
            "[1A[2K[1A[2K[1A[2KConnected to ESP32-P4 on COM7:\n"
            "Chip type:          ESP32-P4 (revision v3.2)\n"
            "Features:           Dual Core + LP Core, 400MHz\n"
            "Crystal frequency:  40MHz\n"
            "USB mode:           USB-Serial/JTAG\n"
            "MAC:                e8:f6:0a:eb:89:94\n"
            "Manufacturer: 46\n"
            "Device: 4018\n"
            "Detected flash size: 16MB\n"
            "Security Information:\n"
            "=====================\n"
            "Flags: 0x00000000 (0b0)\n"
            "Key Purposes: (0, 0, 0, 0, 0, 0)\n"
            "Chip ID: 18\n"
            "API Version: 0\n"
            "Secure Boot: Disabled\n"
            "Flash Encryption: Disabled\n"
            "SPI Boot Crypt Count (SPI_BOOT_CRYPT_CNT): 0x0\n"
            "PARTITION_ENTRY: nvs | data | nvs | 0x9000 | 0x6000 (24 KB)\n"
            "PARTITION_ENTRY: factory | app | factory | 0x10000 | 0x200000 (2.00 MB)\n"
            "I (263) hex_psram: vendor id    : 0x0d (AP)\n"
            "I (264) hex_psram: dev id       : 0x03 (generation 4)\n"
            "I (269) hex_psram: density      : 0x07 (256 Mbit)\n"
            "I (273) hex_psram: good-die     : 0x06 (Pass)\n"
            "I (291) hex_psram: BitMode      : 0x01 (X16 Mode)\n"
            "I (295) hex_psram: Readlatency  : 0x04 (14 cycles@Fixed)\n"
            "I (467) esp_psram: Found 32MB PSRAM device\n"
            "I (468) esp_psram: Speed: 200MHz\n"
            "I (470) hex_psram: psram CS IO is dedicated\n"
            "I (1387) esp_psram: SPI SRAM memory test OK\n"
            "I (1396) cpu_start: GPIO 38 and 37 are used as console UART I/O pins\n"
            "I (1397) cpu_start: cpu freq: 400000000 Hz\n"
            "I (1403) app_init: Project name:     wt_factory_esp32p4\n"
            "I (1408) app_init: App version:      9d1050d-dirty\n"
            "I (1412) app_init: Compile time:     Sep 15 2026 15:20:46\n"
            "I (1417) app_init: ELF file SHA256:  c01745214abcdef\n"
            "I (1422) app_init: ESP-IDF:          v6.0.1\n"
            "I (1425) efuse_init: Min chip rev:     v3.1\n"
            "I (1429) efuse_init: Max chip rev:     v3.99\n"
            "I (1444) heap_init: At 4FF7FB10 len 0003B4B0 (237 KiB): RETENT_RAM\n"
            "I (1466) esp_psram: Adding pool of 32768K of PSRAM memory to heap allocator\n"
            "I (1476) spi_flash: flash io: qio\n"
            "I (1749) factory_test_dut: HUSB CDC factory DUT ready: board=WT9932P4C61-TINY, gpio_count=27, mode=GPIO+CDC\n"
            "I (1879) board: I2C scan complete. Display: NO, Touch: NO, Camera: NO\n"
            "W (1929) factory_firmware: SDMMC mount failed: ESP_ERR_TIMEOUT\n"
            "I (1939) factory_firmware: Hardware status: DSI=0, CSI_init=0, SDMMC=0\n"
        )
        parsed = parse_esptool_output({"flash_id": sample_output})
        self.assertEqual(parsed["chip_name_key"], "ESP32-P4")
        self.assertEqual(parsed["revision"], "3.2")
        self.assertEqual(parsed["usb_mode"], "USB-Serial/JTAG")
        self.assertEqual(parsed["mac"], "E8F60AEB8994")
        self.assertEqual(parsed["flash_manufacturer"], "46")
        self.assertEqual(parsed["flash_device"], "4018")
        self.assertEqual(parsed["flash_mb"], 16.0)
        self.assertEqual(parsed["psram_mb"], 32)
        self.assertEqual(parsed["psram_speed"], "200MHz")
        self.assertEqual(parsed["psram_vendor"], "0x0d (AP)")
        self.assertEqual(parsed["psram_bit_mode"], "0x01 (X16 Mode)")
        self.assertEqual(parsed["psram_test_status"], "Đạt (SPI SRAM memory test OK)")
        self.assertEqual(parsed["psram_heap_pool_kb"], 32768)
        self.assertEqual(parsed["app_project_name"], "wt_factory_esp32p4")
        self.assertEqual(parsed["app_version"], "9d1050d-dirty")
        self.assertEqual(parsed["app_idf_ver"], "v6.0.1")
        self.assertEqual(parsed["app_min_chip_rev"], "v3.1")
        self.assertEqual(parsed["app_max_chip_rev"], "v3.99")
        self.assertEqual(parsed["runtime_flash_io"], "QIO")
        self.assertEqual(parsed["console_uart_pins"], "GPIO 38 and 37")
        self.assertIn("WT9932P4C61-TINY", parsed["board_info"])
        self.assertEqual(parsed["secure_boot"], "Disabled")
        self.assertEqual(parsed["flash_encryption"], "Disabled")
        self.assertEqual(len(parsed["partitions"]), 2)

    def test_parse_binary_image_and_app_descriptors(self):
        import struct
        # Construct 24-byte esp_image_header_t + 8-byte segment header + 256-byte esp_app_desc_t
        hdr = bytearray(32)
        hdr[0] = 0xE9
        hdr[1] = 3
        hdr[2] = 0  # QIO
        hdr[3] = (0x4 << 4) | 0xF  # 16MB, 80MHz
        struct.pack_into("<I", hdr, 4, 0x40000100)
        hdr[8] = 0xEE
        struct.pack_into("<H", hdr, 12, 0x0012)  # ESP32-P4
        struct.pack_into("<H", hdr, 15, 301)  # v3.1
        struct.pack_into("<H", hdr, 17, 399)  # v3.99
        hdr[23] = 1

        app_desc = bytearray(256)
        struct.pack_into("<I", app_desc, 0, 0xABCD5432)
        app_desc[16:16 + 13] = b"9d1050d-dirty"
        app_desc[48:48 + 18] = b"wt_factory_esp32p4"
        app_desc[80:80 + 8] = b"15:20:46"
        app_desc[96:96 + 11] = b"Sep 15 2026"
        app_desc[112:112 + 6] = b"v6.0.1"
        app_desc[144:176] = bytes.fromhex("c017452140000000000000000000000000000000000000000000000000000001")
        app_desc[180] = 16  # 64 KB MMU page size

        blob = bytes(hdr + app_desc)
        parsed_hdr = parse_esp_image_header(blob)
        self.assertEqual(parsed_hdr["spi_mode"], "QIO")
        self.assertEqual(parsed_hdr["spi_speed"], "80 MHz")
        self.assertEqual(parsed_hdr["spi_size_header"], "16 MB")
        self.assertEqual(parsed_hdr["min_chip_rev"], "v3.1")
        self.assertEqual(parsed_hdr["max_chip_rev"], "v3.99")

        parsed_app = parse_esp_app_desc(blob)
        self.assertEqual(parsed_app["app_project_name"], "wt_factory_esp32p4")
        self.assertEqual(parsed_app["app_version"], "9d1050d-dirty")
        self.assertEqual(parsed_app["app_compile_time"], "Sep 15 2026 15:20:46")
        self.assertEqual(parsed_app["app_idf_ver"], "v6.0.1")
        self.assertEqual(parsed_app["app_mmu_page_size"], "64 KB")
        self.assertTrue(parsed_app["app_elf_sha256"].startswith("c01745214"))

        boot_desc = bytearray(80)
        boot_desc[0] = 0x50
        boot_desc[3] = 1
        boot_desc[8:14] = b"v6.0.1"
        boot_desc[40:59] = b"Sep 15 2026 15:20:00"
        parsed_boot = parse_esp_bootloader_desc(bytes(hdr + boot_desc))
        self.assertEqual(parsed_boot["bootloader_idf_ver"], "v6.0.1")


class StreamUtilityTests(unittest.TestCase):
    def test_interceptor_splits_crlf_and_removes_ansi(self):
        received = []
        stream = StreamInterceptor(received.append)
        stream.write("\x1b[31mfirst\x1b[0m\rsecond\npartial")
        stream.flush()
        self.assertEqual(received, ["first", "second", "partial"])
        self.assertIn("first", stream.getvalue())


if __name__ == "__main__":
    unittest.main()
