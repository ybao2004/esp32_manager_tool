import json
import os
import tempfile
import unittest

import modules.esptool_util as esptool_util
from modules.binary_scanner import (
    default_bootloader_offset, scan_project_bin_files, validate_binary_segments
)
from modules.esptool_util import (
    derive_mac_addresses,
    esptool_command_succeeded,
    get_chip_data,
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
