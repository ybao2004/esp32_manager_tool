# -*- coding: utf-8 -*-
"""
MockEsptoolEngine: Intercepts esptool CLI invocations and simulates
ROM Bootloader protocol, chip detection, flash reading/writing,
progress percentage streaming, and hardware fault injection.
"""
import os
import sys
from modules.partition.partition_model import PartitionTable

MOCK_PROFILES = {
    "ESP32-Default": {
        "chip": "ESP32",
        "chip_line": "ESP32-D0WD-V3 (revision v3.0)",
        "features": "Wi-Fi, BT, Dual Core, 240MHz, VRef calibration in efuse, Coding Scheme None",
        "crystal": "40MHz",
        "mac": "24:6F:28:AB:CD:EF",
        "manufacturer": "0xef",
        "manufacturer_name": "Winbond",
        "flash_device": "0x4016",
        "flash_size_mb": 4.0,
        "default_bootloader": 0x1000,
        "default_partition_table": 0x8000,
    },
    "ESP32-S3-16MB": {
        "chip": "ESP32-S3",
        "chip_line": "ESP32-S3 (QFN56) (revision v0.2)",
        "features": "Wi-Fi, BT 5 (LE), Dual Core, 240MHz, Embedded PSRAM 8MB",
        "crystal": "40MHz",
        "mac": "F4:12:FA:11:22:33",
        "manufacturer": "0xc8",
        "manufacturer_name": "GigaDevice",
        "flash_device": "0x4018",
        "flash_size_mb": 16.0,
        "default_bootloader": 0x0000,
        "default_partition_table": 0x8000,
    },
    "ESP32-C3-4MB": {
        "chip": "ESP32-C3",
        "chip_line": "ESP32-C3 (revision v0.3)",
        "features": "Wi-Fi, BLE, Single Core, 160MHz",
        "crystal": "40MHz",
        "mac": "60:55:F9:88:99:AA",
        "manufacturer": "0x20",
        "manufacturer_name": "XMC",
        "flash_device": "0x4016",
        "flash_size_mb": 4.0,
        "default_bootloader": 0x0000,
        "default_partition_table": 0x8000,
    },
    "ESP32-P5-Unknown": {
        "chip": "ESP32-P5",
        "chip_line": "ESP32-P5 (revision v0.1)",
        "features": "Wi-Fi 6, Dual Core",
        "crystal": "40MHz",
        "mac": "30:AE:A4:00:11:22",
        "manufacturer": "0xef",
        "manufacturer_name": "Winbond",
        "flash_device": "0x4017",
        "flash_size_mb": 8.0,
        "default_bootloader": 0x0000,
        "default_partition_table": 0x8000,
    }
}


class MockEsptoolEngine:
    """
    Virtual esptool module that replaces esptool in modules.esptool_util.
    Simulates CLI commands in-process with authentic stdout / stderr streams.
    """
    __version__ = "5.0.0"

    def __init__(self, profile="ESP32-Default"):
        self.set_profile(profile)
        self.fault_mode = None  # None, 'sync_error', 'exit_fail', 'bad_md5', 'baud_fail_all'
        self.last_executed_command = None
        self.command_history = []
        self.execution_count = 0
        self.flash_storage = {}  # In-memory offset -> byte storage

    def set_profile(self, profile_key):
        if profile_key not in MOCK_PROFILES:
            raise KeyError(f"Profile {profile_key} not found in MOCK_PROFILES")
        self.profile = MOCK_PROFILES[profile_key]
        self.profile_name = profile_key

    def main(self, arguments):
        """
        Emulate esptool.main(arguments).
        Redirects output to sys.stdout and sys.stderr.
        """
        args = [str(a) for a in arguments]
        self.last_executed_command = list(args)
        self.command_history.append(list(args))
        self.execution_count += 1

        # Check for global fault modes
        if self.fault_mode == 'sync_error':
            sys.stdout.write("Connecting........_____....._____....._____\n")
            sys.stdout.write("A fatal error occurred: Failed to connect to ESP32: Timed out waiting for packet header\n")
            sys.stdout.flush()
            raise SystemExit(2)

        if self.fault_mode == 'exit_fail':
            sys.stdout.write("A fatal error occurred: Invalid flash address specified.\n")
            sys.stdout.flush()
            raise SystemExit(1)

        if self.fault_mode == 'baud_fail_all':
            sys.stdout.write("Connecting...\nA fatal error occurred: Could not open port / Baudrate mismatch\n")
            sys.stdout.flush()
            raise SystemExit(2)

        # 1. flash-id / flash_id command
        if "flash-id" in args or "flash_id" in args:
            sys.stdout.write(f"Detecting chip type... {self.profile['chip']}\n")
            sys.stdout.write(f"Chip is {self.profile['chip_line']}\n")
            sys.stdout.write(f"Features: {self.profile['features']}\n")
            sys.stdout.write(f"Crystal is {self.profile['crystal']}\n")
            sys.stdout.write(f"MAC: {self.profile['mac']}\n")
            sys.stdout.write("Uploading stub...\nRunning stub...\nStub running...\n")
            sys.stdout.write(f"Manufacturer: {self.profile['manufacturer']}\n")
            sys.stdout.write(f"Device: {self.profile['flash_device']}\n")
            sys.stdout.write(f"Detected flash size: {int(self.profile['flash_size_mb'])}MB\n")
            sys.stdout.write("Hard resetting via RTS pin...\n")
            sys.stdout.flush()
            return

        # 2. read-mac / read_mac command
        if "read-mac" in args or "read_mac" in args:
            sys.stdout.write(f"MAC: {self.profile['mac']}\n")
            sys.stdout.flush()
            return

        # 3. erase-flash / erase_flash command
        if "erase-flash" in args or "erase_flash" in args:
            sys.stdout.write("Erasing flash (this may take a while)...\n")
            sys.stdout.write("Chip erase completed successfully in 2.5s\n")
            sys.stdout.write("Hard resetting via RTS pin...\n")
            sys.stdout.flush()
            return

        # 4. erase-region / erase_region command
        if "erase-region" in args or "erase_region" in args:
            idx = args.index("erase-region") if "erase-region" in args else args.index("erase_region")
            offset_str = args[idx + 1]
            size_str = args[idx + 2]
            sys.stdout.write(f"Erasing region at offset {offset_str}, size {size_str}...\n")
            sys.stdout.write("Region erase completed successfully.\n")
            sys.stdout.flush()
            return

        # 5. write-flash / write_flash command
        if "write-flash" in args or "write_flash" in args:
            sys.stdout.write("Writing to flash...\n")
            for pct in [15, 35, 60, 85, 100]:
                sys.stdout.write(f"Writing at 0x00010000... ({pct} %)\n")
                sys.stdout.flush()

            if self.fault_mode == 'bad_md5':
                sys.stdout.write("A fatal error occurred: MD5 of file does not match data in flash!\n")
                sys.stdout.flush()
                raise SystemExit(2)

            sys.stdout.write("Hash of data verified.\n")
            sys.stdout.write("Leaving... Hard resetting via RTS pin...\n")
            sys.stdout.flush()
            return

        # 6. read_flash / read-flash command
        if "read_flash" in args or "read-flash" in args:
            sys.stdout.write(f"Detecting chip type... {self.profile['chip']}\n")
            sys.stdout.write(f"Chip is {self.profile['chip_line']}\n")
            sys.stdout.flush()

            idx = args.index("read_flash") if "read_flash" in args else args.index("read-flash")
            offset_str = args[idx + 1]
            size_str = args[idx + 2]
            out_path = args[idx + 3]

            offset = int(offset_str, 16 if offset_str.lower().startswith("0x") else 10)
            size = int(size_str, 16 if size_str.lower().startswith("0x") else 10)

            # If reading partition table at 0x8000, synthesize valid partition binary
            if offset == 0x8000:
                table = PartitionTable(flash_size=int(self.profile['flash_size_mb'] * 1024 * 1024))
                csv_def = (
                    "# Name, Type, SubType, Offset, Size, Flags\n"
                    "nvs, data, nvs, 0x9000, 0x6000,\n"
                    "phy_init, data, phy, 0xf000, 0x1000,\n"
                    "factory, app, factory, 0x10000, 1M,\n"
                    "storage, data, spiffs, 0x110000, 1M,\n"
                )
                table.from_csv(csv_def)
                payload = table.to_binary()
            else:
                # Default binary payload for generic partition dumps
                payload = b"\xff" * min(size, 65536)

            # Ensure parent dir exists and write file
            os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(payload)

            sys.stdout.write(f"Read {size} bytes from 0x{offset:X} into {out_path}.\n")
            sys.stdout.flush()
            return

        # Fallback generic command
        sys.stdout.write(f"Executed mock esptool command: {' '.join(args)}\n")
        sys.stdout.flush()
