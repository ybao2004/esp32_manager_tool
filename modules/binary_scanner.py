# -*- coding: utf-8 -*-
"""
ESP Tool & Hardware Inspector v2.0 - Smart Project Binary Scanner
"""
import os
import json


def _safe_mtime(path):
    """Return a stable sort value even if a build artifact disappears mid-scan."""
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0.0


def parse_address(value):
    """Parse a decimal/hex address and reject negative values."""
    text = str(value).strip()
    if not text:
        raise ValueError("địa chỉ đang để trống")
    address = int(text, 16 if text.lower().startswith("0x") else 10)
    if address < 0:
        raise ValueError("địa chỉ không được là số âm")
    return address


def validate_binary_segments(pairs, min_offset=0):
    """
    Validate firmware segments before passing them to esptool.

    Returns ``(is_valid, message, normalized_pairs, max_end)``.  Pairs are
    sorted by address so command construction and overlap checks are stable.
    """
    if not pairs:
        return False, "Chưa chọn file firmware nào.", [], 0

    try:
        minimum = parse_address(min_offset)
    except (TypeError, ValueError) as exc:
        return False, f"Offset đích không hợp lệ: {exc}", [], 0

    segments = []
    seen_paths = set()
    for index, pair in enumerate(pairs, start=1):
        try:
            raw_offset, raw_path = pair
        except (TypeError, ValueError):
            return False, f"Dữ liệu firmware ở hàng {index} không hợp lệ.", [], 0

        try:
            offset = parse_address(raw_offset)
        except (TypeError, ValueError) as exc:
            return False, f"Offset ở hàng {index} không hợp lệ: {exc}", [], 0

        if offset < minimum:
            return False, (
                f"Offset 0x{offset:X} ở hàng {index} nhỏ hơn offset đích "
                f"0x{minimum:X}."
            ), [], 0

        path = os.path.abspath(os.path.normpath(os.path.expanduser(str(raw_path).strip())))
        if not os.path.isfile(path):
            return False, f"File firmware ở hàng {index} không tồn tại:\n{path}", [], 0
        path_key = os.path.normcase(path)
        if path_key in seen_paths:
            return False, f"File firmware bị chọn lặp lại:\n{path}", [], 0
        seen_paths.add(path_key)

        try:
            size = os.path.getsize(path)
        except OSError as exc:
            return False, f"Không thể đọc kích thước file:\n{path}\n{exc}", [], 0
        if size <= 0:
            return False, f"File firmware đang rỗng:\n{path}", [], 0

        segments.append((offset, offset + size, path))

    segments.sort(key=lambda segment: segment[0])
    for previous, current in zip(segments, segments[1:]):
        prev_start, prev_end, prev_path = previous
        curr_start, _curr_end, curr_path = current
        if prev_end > curr_start:
            return False, (
                "Các file firmware bị chồng lấn vùng nhớ:\n"
                f"- {os.path.basename(prev_path)}: 0x{prev_start:X} - 0x{prev_end - 1:X}\n"
                f"- {os.path.basename(curr_path)}: bắt đầu tại 0x{curr_start:X}"
            ), [], 0

    normalized_pairs = [(f"0x{start:X}", path) for start, _end, path in segments]
    max_end = max(end for _start, end, _path in segments)
    return True, "Các vùng firmware hợp lệ.", normalized_pairs, max_end

def default_bootloader_offset(target_chip):
    """Return the conventional bootloader offset for an Espressif target."""
    chip_name = str(target_chip or "esp32").lower().replace("-", "")
    if chip_name in {"esp32c5", "esp32p4", "esp32s31"}:
        return "0x2000"
    if chip_name in {"esp32", "esp32s2"}:
        return "0x1000"
    return "0x0"


def scan_project_bin_files(project_dir, target_chip="esp32"):
    """
    Quét và nhận diện thông minh các file .bin trong thư mục dự án.
    Hỗ trợ: ESP-IDF (flasher_args.json), PlatformIO (.pio/build), Arduino IDE và thư mục bất kỳ.
    """
    results = []
    if not project_dir or not os.path.isdir(project_dir):
        return results

    chip_name = str(target_chip or "esp32").lower()
    boot_off = default_bootloader_offset(chip_name)

    # A manifest is an indivisible build: never silently drop missing segments.
    manifests = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in [".git", "node_modules"]]
        if "flasher_args.json" in files:
            manifests.append(os.path.join(root, "flasher_args.json"))
    if manifests:
        fpath = max(manifests, key=lambda path: (_safe_mtime(path), path))
        try:
            with open(fpath, encoding="utf-8") as stream:
                data = json.load(stream)
            flash_files = data.get("flash_files")
            if not isinstance(flash_files, dict) or not flash_files:
                raise ValueError("flash_files phải là bảng không rỗng")
            pairs = [(off, os.path.join(os.path.dirname(fpath), path))
                     for off, path in flash_files.items()]
            valid, message, pairs, _end = validate_binary_segments(pairs)
            if not valid:
                raise ValueError(message)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise ValueError(f"Bộ firmware không hợp lệ ({fpath}):\n{exc}") from exc
        return [{
            "enabled": True,
            "role": "Bootloader" if "bootloader" in path.lower() else
                    "Partition Table" if "partition" in path.lower() else "Firmware Ứng dụng",
            "offset": off, "path": path,
            "size_kb": os.path.getsize(path) / 1024.0,
            "source": "ESP-IDF (flasher_args.json)"
        } for off, path in pairs]

    # 2. Kiểm tra dự án PlatformIO: .pio/build/<env>/
    pio_build = os.path.join(project_dir, ".pio", "build")
    if os.path.isdir(pio_build):
        try:
            envs = [os.path.join(pio_build, d) for d in os.listdir(pio_build) if os.path.isdir(os.path.join(pio_build, d))]
            if envs:
                envs.sort(key=_safe_mtime, reverse=True)
                chosen_env = envs[0]
                env_name = os.path.basename(chosen_env)
                candidates = [
                    ("bootloader.bin", boot_off, "Bootloader"),
                    ("partitions.bin", "0x8000", "Partition Table"),
                    ("boot_app0.bin", "0xe000", "Boot App0"),
                    ("firmware.bin", "0x10000", "Firmware Ứng dụng")
                ]
                for fname, off, role in candidates:
                    p = os.path.join(chosen_env, fname)
                    if os.path.isfile(p):
                        sz_kb = os.path.getsize(p) / 1024.0
                        results.append({
                            "enabled": True,
                            "role": role,
                            "offset": off,
                            "path": os.path.normpath(p),
                            "size_kb": sz_kb,
                            "source": f"PlatformIO ({env_name})"
                        })
                if results:
                    return results
        except Exception:
            pass

    # 3. Quét thông minh đệ quy (Arduino IDE / Thư mục build thông thường)
    base_depth = project_dir.rstrip(os.sep).count(os.sep)
    found_map = {}
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in [".git", ".vscode", ".idea", "node_modules"]]
        if root.count(os.sep) - base_depth >= 4:
            dirs[:] = []
        for f in files:
            if f.lower().endswith(".bin"):
                full_p = os.path.normpath(os.path.join(root, f))
                fl = f.lower()
                try:
                    sz_kb = os.path.getsize(full_p) / 1024.0
                except Exception:
                    sz_kb = 0.0

                uncertain = False
                if "merged" in fl or "all-in-one" in fl or "all_in_one" in fl:
                    role = "File gộp — cần xác nhận offset"
                    off = "0x0"
                    uncertain = True
                elif "bootloader" in fl:
                    role = "Bootloader"
                    off = boot_off
                elif "partition" in fl:
                    role = "Partition Table"
                    off = "0x8000"
                elif "boot_app0" in fl or "ota_data" in fl:
                    role = "Boot App0"
                    off = "0xe000"
                elif "firmware" in fl or ".ino.bin" in fl:
                    role = "Firmware Ứng dụng"
                    off = "0x10000"
                elif "spiffs" in fl or "littlefs" in fl:
                    role = "Filesystem (SPIFFS/LittleFS)"
                    off = ""
                    uncertain = True
                else:
                    role = "File .bin khác — cần xác nhận offset"
                    off = ""
                    uncertain = True

                # Keep distinct files even when separate build folders contain
                # the same basename; silently overwriting one can select stale
                # firmware from an unrelated environment.
                found_map[os.path.normcase(full_p)] = {
                    "enabled": True,
                    "role": role,
                    "offset": off,
                    "path": full_p,
                    "size_kb": sz_kb,
                    "source": "Cần xác nhận offset" if uncertain else "Quét thư mục (offset gợi ý)",
                    "offset_uncertain": uncertain,
                }

    def offset_key(item):
        try:
            return int(item["offset"], 16 if item["offset"].lower().startswith("0x") else 10)
        except Exception:
            return 99999999

    res_list = list(found_map.values())
    # Select one directory as a build unit; never mix independently newest files.
    groups = {}
    for item in res_list:
        groups.setdefault(os.path.dirname(item["path"]), []).append(item)
    chosen = max(groups, key=lambda folder: (
        max(_safe_mtime(item["path"]) for item in groups[folder]), folder
    )) if groups else None
    selected_offsets = set()
    for item in sorted(res_list, key=lambda item: (-_safe_mtime(item["path"]), item["path"])):
        address = offset_key(item)
        item["enabled"] = (not item.get("offset_uncertain", False)
                           and os.path.dirname(item["path"]) == chosen
                           and address not in selected_offsets)
        if item["enabled"]:
            selected_offsets.add(address)

    res_list.sort(key=lambda item: (offset_key(item), not item["enabled"], os.path.normcase(item["path"])))
    return res_list
