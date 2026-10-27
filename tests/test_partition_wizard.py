import hashlib
import os
import struct
import tempfile
import unittest

from modules.partition.unit_formatter import (
    DisplayMode, parse_size_or_offset, format_bytes_human, format_hex,
    format_value, align_up, sector_count
)
from modules.partition.chip_database import (
    CHIP_FAMILY_DATABASE, get_chip_info
)
from modules.partition.partition_model import (
    PartitionTable, PartitionEntry, MAGIC_BYTES, MD5_PARTITION_BEGIN,
    TYPE_APP, TYPE_DATA, SUBTYPES_MAP
)
from modules.partition.project_scanner import scan_esp_project


class UnitFormatterTests(unittest.TestCase):
    def test_parse_size_or_offset_variants(self):
        self.assertEqual(parse_size_or_offset("0x10000"), 65536)
        self.assertEqual(parse_size_or_offset("0x1000"), 4096)
        self.assertEqual(parse_size_or_offset("64K"), 64 * 1024)
        self.assertEqual(parse_size_or_offset("64KB"), 64 * 1024)
        self.assertEqual(parse_size_or_offset("1M"), 1024 * 1024)
        self.assertEqual(parse_size_or_offset("1.5MB"), int(1.5 * 1024 * 1024))
        self.assertEqual(parse_size_or_offset("65536"), 65536)
        self.assertEqual(parse_size_or_offset("65,536"), 65536)

    def test_parse_size_or_offset_errors(self):
        with self.assertRaises(ValueError):
            parse_size_or_offset("")
        with self.assertRaises(ValueError):
            parse_size_or_offset(None)
        with self.assertRaises(ValueError):
            parse_size_or_offset("invalid_size")

    def test_format_helpers(self):
        self.assertEqual(format_hex(0x10000), "0x10000")
        self.assertEqual(format_hex(0x8000), "0x08000")
        self.assertEqual(format_bytes_human(1024 * 1024, compact=True), "1 MB")
        self.assertEqual(format_bytes_human(64 * 1024, compact=True), "64 KB")
        self.assertEqual(align_up(0x8000, 0x10000), 0x10000)
        self.assertEqual(align_up(0x10000, 0x10000), 0x10000)
        self.assertEqual(align_up(0x9001, 0x1000), 0xA000)
        self.assertEqual(sector_count(4096), 1)
        self.assertEqual(sector_count(4097), 2)


class ChipDatabaseTests(unittest.TestCase):
    def test_chip_lookup(self):
        esp32 = get_chip_info("esp32")
        self.assertEqual(esp32.bootloader_offset, 0x1000)
        self.assertEqual(esp32.cores, 2)

        s3 = get_chip_info("esp32-s3")
        self.assertEqual(s3.bootloader_offset, 0x0000)
        self.assertIn(8 * 1024 * 1024, s3.supported_flash_sizes)

        c3 = get_chip_info("esp32c3")
        self.assertEqual(c3.bootloader_offset, 0x0000)

        # Fallback to default
        unknown = get_chip_info("nonexistent_chip")
        self.assertEqual(unknown.id, "esp32")


class PartitionModelTests(unittest.TestCase):
    def setUp(self):
        self.sample_csv = (
            "# ESP-IDF Partition Table\n"
            "# Name,   Type, SubType, Offset,  Size, Flags\n"
            "nvs,      data, nvs,     0x9000,  0x6000,\n"
            "phy_init, data, phy,     0xf000,  0x1000,\n"
            "factory,  app,  factory, 0x10000, 1M,\n"
            "storage,  data, spiffs,  0x110000, 1800K,\n"
        )

    def test_csv_import_and_export_roundtrip(self):
        table = PartitionTable(flash_size=4 * 1024 * 1024)
        table.from_csv(self.sample_csv)
        self.assertEqual(len(table.entries), 4)

        nvs = table.entries[0]
        self.assertEqual(nvs.name, "nvs")
        self.assertEqual(nvs.type_str, "data")
        self.assertEqual(nvs.offset, 0x9000)
        self.assertEqual(nvs.size, 0x6000)

        factory = table.entries[2]
        self.assertEqual(factory.name, "factory")
        self.assertEqual(factory.type_str, "app")
        self.assertEqual(factory.offset, 0x10000)
        self.assertEqual(factory.size, 1024 * 1024)

        # Check export
        exported = table.to_csv()
        self.assertIn("factory, app, factory", exported)
        self.assertIn("0x10000", exported)

    def test_binary_compilation_and_decompilation(self):
        table = PartitionTable(flash_size=4 * 1024 * 1024)
        table.from_csv(self.sample_csv)

        bin_data = table.to_binary()
        self.assertEqual(len(bin_data), 4096)  # Padded to 0x1000 sector

        # Check magic bytes of first entry
        self.assertEqual(bin_data[:2], MAGIC_BYTES)

        # Decompile back
        table2 = PartitionTable(flash_size=4 * 1024 * 1024)
        table2.from_binary(bin_data)
        self.assertEqual(len(table2.entries), 4)
        self.assertEqual(table2.entries[0].name, "nvs")
        self.assertEqual(table2.entries[2].name, "factory")
        self.assertEqual(table2.entries[2].offset, 0x10000)
        self.assertEqual(table2.entries[2].size, 1024 * 1024)

    def test_validation_clean_table(self):
        table = PartitionTable(flash_size=4 * 1024 * 1024)
        table.from_csv(self.sample_csv)
        errors = table.validate()
        self.assertEqual(errors, [])

    def test_validation_detects_errors(self):
        table = PartitionTable(flash_size=4 * 1024 * 1024)
        # Duplicate name and misaligned app offset
        bad_csv = (
            "nvs,     data, nvs,     0x9000, 0x6000,\n"
            "nvs,     data, nvs,     0xf000, 0x1000,\n"  # Duplicate name
            "factory, app,  factory, 0x15000, 1M,\n"      # App not 64KB aligned
            "ota_0,   app,  ota_0,   0x120000, 1M,\n"     # Missing otadata
        )
        table.from_csv(bad_csv)
        errors = table.validate()
        self.assertTrue(any("trùng lặp" in e for e in errors))
        self.assertTrue(any("64 KB" in e for e in errors))
        self.assertTrue(any("otadata" in e for e in errors))

    def test_auto_pack_and_align(self):
        table = PartitionTable(flash_size=4 * 1024 * 1024)
        # Add unaligned entries
        table.add_entry(PartitionEntry("nvs", "data", "nvs", offset=0, size=0x6000))
        table.add_entry(PartitionEntry("factory", "app", "factory", offset=0, size=1024 * 1024))
        table.add_entry(PartitionEntry("storage", "data", "spiffs", offset=0, size=512 * 1024))

        table.auto_pack_and_align()

        # nvs should start at 0x9000 (after 0x8000 pt table)
        self.assertEqual(table.entries[0].offset, 0x9000)
        # factory app must align to 64KB -> 0x10000
        self.assertEqual(table.entries[1].offset, 0x10000)
        # storage starts right after factory -> 0x110000 (aligned to 4KB)
        self.assertEqual(table.entries[2].offset, 0x110000)

        # Validate should pass
        errors = table.validate()
        self.assertEqual(errors, [])

    def test_layout_with_unallocated(self):
        table = PartitionTable(flash_size=4 * 1024 * 1024, bootloader_offset=0x1000)
        table.from_csv(self.sample_csv)
        layout = table.get_layout_with_unallocated()

        # Should contain Bootloader, Partition Table, user entries, and ending Unallocated gap
        names = [e.name for e in layout]
        self.assertIn("Bootloader", names)
        self.assertIn("Partition Table", names)
        self.assertIn("Unallocated", names)


class ProjectScannerTests(unittest.TestCase):
    def test_scan_esp_project(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Create dummy partitions.csv
            csv_path = os.path.join(tmp_dir, "partitions.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write(
                    "nvs, data, nvs, 0x9000, 0x6000,\n"
                    "factory, app, factory, 0x10000, 1M,\n"
                )

            # Create dummy sdkconfig
            sdkconfig_path = os.path.join(tmp_dir, "sdkconfig")
            with open(sdkconfig_path, "w", encoding="utf-8") as f:
                f.write(
                    'CONFIG_IDF_TARGET="esp32s3"\n'
                    'CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y\n'
                    'CONFIG_ESPTOOLPY_FLASHSIZE="8MB"\n'
                )

            res = scan_esp_project(tmp_dir)
            self.assertIsNotNone(res)
            self.assertEqual(res.target_chip, "esp32s3")
            self.assertEqual(res.flash_size, 8 * 1024 * 1024)
            self.assertIsNotNone(res.partition_table)
            self.assertEqual(len(res.partition_table.entries), 2)


if __name__ == '__main__':
    unittest.main()
