# -*- coding: utf-8 -*-
"""
ESP-IDF NVS (Non-Volatile Storage) Binary Parser & Encoder (v1.5).
Thuần Python (zlib.crc32 + struct), hỗ trợ đọc và đóng gói phân vùng NVS v1/v2 chuẩn ESP-IDF.
"""
from __future__ import annotations

import math
import struct
import zlib
from dataclasses import dataclass, field
from typing import Any

NVS_PAGE_SIZE = 4096
NVS_HEADER_SIZE = 32
NVS_BITMAP_SIZE = 32
NVS_ENTRY_SIZE = 32
NVS_ENTRIES_PER_PAGE = 126
NVS_MAX_KEY_LEN = 15

# Page states (uint32 little-endian)
PAGE_STATE_EMPTY = 0xFFFFFFFF
PAGE_STATE_ACTIVE = 0xFFFFFFFE
PAGE_STATE_FULL = 0xFFFFFFFC
PAGE_STATE_ERASING = 0xFFFFFFF8
PAGE_STATE_CORRUPT = 0x00000000

VALID_PAGE_STATES = {
    PAGE_STATE_EMPTY,
    PAGE_STATE_ACTIVE,
    PAGE_STATE_FULL,
    PAGE_STATE_ERASING,
}

# Page versions
NVS_VERSION_1 = 0xFF
NVS_VERSION_2 = 0xFE

# Entry bitmap states (2 bits per entry)
ENTRY_STATE_EMPTY = 0b11
ENTRY_STATE_WRITTEN = 0b10
ENTRY_STATE_ERASED = 0b00

# Data types
NVS_TYPE_U8 = 0x01
NVS_TYPE_I8 = 0x11
NVS_TYPE_U16 = 0x02
NVS_TYPE_I16 = 0x12
NVS_TYPE_U32 = 0x04
NVS_TYPE_I32 = 0x14
NVS_TYPE_U64 = 0x08
NVS_TYPE_I64 = 0x18
NVS_TYPE_SZ = 0x21
NVS_TYPE_BLOB = 0x41        # Legacy v1 blob
NVS_TYPE_BLOB_DATA = 0x42   # v2 chunked blob data
NVS_TYPE_BLOB_IDX = 0x48    # v2 blob index
NVS_TYPE_ANY = 0xFF

TYPE_CODE_TO_NAME: dict[int, str] = {
    NVS_TYPE_U8: "U8",
    NVS_TYPE_I8: "I8",
    NVS_TYPE_U16: "U16",
    NVS_TYPE_I16: "I16",
    NVS_TYPE_U32: "U32",
    NVS_TYPE_I32: "I32",
    NVS_TYPE_U64: "U64",
    NVS_TYPE_I64: "I64",
    NVS_TYPE_SZ: "SZ",
    NVS_TYPE_BLOB: "BLOB",
    NVS_TYPE_BLOB_DATA: "BLOB_DATA",
    NVS_TYPE_BLOB_IDX: "BLOB_IDX",
}

TYPE_NAME_TO_CODE: dict[str, int] = {
    "U8": NVS_TYPE_U8,
    "I8": NVS_TYPE_I8,
    "U16": NVS_TYPE_U16,
    "I16": NVS_TYPE_I16,
    "U32": NVS_TYPE_U32,
    "I32": NVS_TYPE_I32,
    "U64": NVS_TYPE_U64,
    "I64": NVS_TYPE_I64,
    "SZ": NVS_TYPE_SZ,
    "STRING": NVS_TYPE_SZ,
    "BLOB": NVS_TYPE_BLOB_DATA,
}

INT_TYPE_RANGES: dict[int, tuple[str, int, int]] = {
    NVS_TYPE_U8: ("<B", 0, 0xFF),
    NVS_TYPE_I8: ("<b", -0x80, 0x7F),
    NVS_TYPE_U16: ("<H", 0, 0xFFFF),
    NVS_TYPE_I16: ("<h", -0x8000, 0x7FFF),
    NVS_TYPE_U32: ("<I", 0, 0xFFFFFFFF),
    NVS_TYPE_I32: ("<i", -0x80000000, 0x7FFFFFFF),
    NVS_TYPE_U64: ("<Q", 0, 0xFFFFFFFFFFFFFFFF),
    NVS_TYPE_I64: ("<q", -0x8000000000000000, 0x7FFFFFFFFFFFFFFF),
}


def esp_nvs_crc32(data: bytes) -> int:
    """Tính CRC32-LE theo chuẩn esp_rom_crc32_le(UINT32_MAX, data, len) của ESP-IDF NVS."""
    return zlib.crc32(data, 0xFFFFFFFF) & 0xFFFFFFFF


@dataclass
class NvsEntry:
    namespace: str
    key: str
    type_name: str
    value: Any
    type_code: int = NVS_TYPE_SZ

    def __post_init__(self):
        norm_name = str(self.type_name or "SZ").upper()
        if norm_name in ("BLOB_DATA", "BLOB_IDX"):
            norm_name = "BLOB"
        elif norm_name == "STRING":
            norm_name = "SZ"
        self.type_name = norm_name
        self.type_code = TYPE_NAME_TO_CODE.get(norm_name, self.type_code)

    def format_value_display(self, max_len: int = 120) -> str:
        """Chuỗi hiển thị gọn trên bảng Key-Value."""
        if self.type_name in ("BLOB",):
            raw = bytes(self.value or b"")
            hex_preview = " ".join(f"{b:02X}" for b in raw[:24])
            suffix = " ..." if len(raw) > 24 else ""
            return f"[{len(raw)} B] {hex_preview}{suffix}".strip()
        txt = str(self.value)
        if len(txt) > max_len:
            return txt[: max_len - 3] + "..."
        return txt

    def to_serializable(self) -> dict[str, Any]:
        val = self.value
        if self.type_name == "BLOB":
            val = bytes(self.value or b"").hex().upper()
        return {
            "namespace": self.namespace,
            "key": self.key,
            "type": self.type_name,
            "value": val,
        }


@dataclass
class NvsParseResult:
    entries: list[NvsEntry] = field(default_factory=list)
    namespaces: list[str] = field(default_factory=list)
    version: int = 2
    page_count: int = 0
    active_pages: int = 0
    empty_pages: int = 0
    corrupt_pages: int = 0
    is_all_erased: bool = False
    is_encrypted_or_unknown: bool = False
    warnings: list[str] = field(default_factory=list)


def _decode_cstr(raw: bytes) -> str:
    nul = raw.find(b"\x00")
    slice_b = raw[:nul] if nul >= 0 else raw
    return slice_b.decode("utf-8", errors="replace")


def _encode_key_bytes(text: str, label: str = "Key") -> bytes:
    raw = str(text or "").encode("ascii", errors="strict")
    if not raw or len(raw) > NVS_MAX_KEY_LEN:
        raise ValueError(f"{label} '{text}' phải từ 1 đến {NVS_MAX_KEY_LEN} ký tự ASCII.")
    return raw + b"\x00" * (16 - len(raw))


def _get_entry_state(bitmap: bytes, idx: int) -> int:
    byte_idx = idx // 4
    bit_shift = (idx % 4) * 2
    return (bitmap[byte_idx] >> bit_shift) & 0x03


def _set_entry_state(bitmap: bytearray, idx: int, state: int) -> None:
    byte_idx = idx // 4
    bit_shift = (idx % 4) * 2
    mask = 0x03 << bit_shift
    bitmap[byte_idx] = (bitmap[byte_idx] & ~mask) | ((state & 0x03) << bit_shift)


def _decode_scalar(type_code: int, data8: bytes) -> int | None:
    spec = INT_TYPE_RANGES.get(type_code)
    if spec is None:
        return None
    fmt, _, _ = spec
    size = struct.calcsize(fmt)
    return struct.unpack(fmt, data8[:size])[0]


def _encode_scalar(type_code: int, value: Any) -> bytes:
    spec = INT_TYPE_RANGES.get(type_code)
    if spec is None:
        raise ValueError(f"Không hỗ trợ kiểu số NVS mã 0x{type_code:02X}.")
    fmt, lo, hi = spec
    iv = int(value, 0) if isinstance(value, str) else int(value)
    if iv < lo or iv > hi:
        raise ValueError(f"Giá trị {iv} vượt giới hạn [{lo}, {hi}] của {TYPE_CODE_TO_NAME.get(type_code)}.")
    packed = struct.pack(fmt, iv)
    return packed + b"\xFF" * (8 - len(packed))


def parse_nvs_binary(raw: bytes) -> NvsParseResult:
    """
    Giải mã dữ liệu nhị phân phân vùng NVS ESP-IDF (v1 & v2, 4KB/page).
    Phát hiện an toàn vùng trống hoàn toàn (0xFF) hoặc NVS mã hóa/không chuẩn.
    """
    res = NvsParseResult()
    if not raw:
        res.warnings.append("Dữ liệu phân vùng rỗng.")
        res.is_all_erased = True
        return res

    if len(raw) < NVS_PAGE_SIZE or (len(raw) % NVS_PAGE_SIZE) != 0:
        res.warnings.append(
            f"Kích thước dữ liệu ({len(raw)} B) không phải bội số của page 4096 B."
        )

    page_count = len(raw) // NVS_PAGE_SIZE
    res.page_count = page_count
    if page_count == 0:
        res.is_encrypted_or_unknown = True
        return res

    if all(b == 0xFF for b in raw):
        res.empty_pages = page_count
        res.is_all_erased = True
        return res

    parsed_pages: list[tuple[int, int, int, bytes]] = []
    seen_v1 = False
    seen_v2 = False

    for p_idx in range(page_count):
        page = raw[p_idx * NVS_PAGE_SIZE : (p_idx + 1) * NVS_PAGE_SIZE]
        if all(b == 0xFF for b in page):
            res.empty_pages += 1
            continue

        state, seq_no, version = struct.unpack("<IIB", page[:9])
        stored_crc = struct.unpack("<I", page[28:32])[0]
        calc_crc = esp_nvs_crc32(page[4:28])

        if state == PAGE_STATE_EMPTY:
            res.empty_pages += 1
            continue

        if state not in VALID_PAGE_STATES or stored_crc != calc_crc:
            res.corrupt_pages += 1
            continue

        if version == NVS_VERSION_1:
            seen_v1 = True
        elif version == NVS_VERSION_2:
            seen_v2 = True

        res.active_pages += 1
        parsed_pages.append((seq_no, p_idx, version, page))

    if not parsed_pages:
        res.is_encrypted_or_unknown = True
        res.warnings.append(
            "Không tìm thấy header NVS 4KB hợp lệ (có thể phân vùng đã bật NVS Encryption hoặc chứa dữ liệu nhị phân tùy biến)."
        )
        return res

    res.version = 1 if (seen_v1 and not seen_v2) else 2
    parsed_pages.sort(key=lambda it: (it[0], it[1]))

    ns_map: dict[int, str] = {}
    ordered_entries: dict[tuple[str, str], NvsEntry] = {}
    blob_chunks: dict[tuple[int, str, int], bytes] = {}
    blob_indices: dict[tuple[str, str], tuple[int, str, int, int, int]] = {}

    for _seq, _p_idx, _ver, page in parsed_pages:
        bitmap = page[NVS_HEADER_SIZE : NVS_HEADER_SIZE + NVS_BITMAP_SIZE]
        entries_area = page[NVS_HEADER_SIZE + NVS_BITMAP_SIZE :]

        idx = 0
        while idx < NVS_ENTRIES_PER_PAGE:
            st = _get_entry_state(bitmap, idx)
            if st != ENTRY_STATE_WRITTEN:
                idx += 1
                continue

            ebytes = entries_area[idx * NVS_ENTRY_SIZE : (idx + 1) * NVS_ENTRY_SIZE]
            ns_idx, dtype, span, chunk_idx, stored_ecrc = struct.unpack("<BBBBI", ebytes[:8])
            span = max(1, span)

            # Kiểm tra CRC entry header
            calc_ecrc = esp_nvs_crc32(ebytes[0:4] + ebytes[8:32])
            if stored_ecrc != calc_ecrc:
                idx += span
                continue

            key_str = _decode_cstr(ebytes[8:24])
            data8 = ebytes[24:32]

            if ns_idx == 0:
                if dtype == NVS_TYPE_U8:
                    ns_id_val = _decode_scalar(NVS_TYPE_U8, data8)
                    if ns_id_val is not None and ns_id_val > 0:
                        ns_map[ns_id_val] = key_str
                idx += span
                continue

            ns_name = ns_map.get(ns_idx, f"ns_{ns_idx}")

            if dtype in INT_TYPE_RANGES:
                val = _decode_scalar(dtype, data8)
                tname = TYPE_CODE_TO_NAME[dtype]
                ordered_entries[(ns_name, key_str)] = NvsEntry(
                    namespace=ns_name,
                    key=key_str,
                    type_name=tname,
                    value=val,
                    type_code=dtype,
                )
                # Nếu ghi đè lên key từng là blob index, dọn index cũ
                blob_indices.pop((ns_name, key_str), None)

            elif dtype in (NVS_TYPE_SZ, NVS_TYPE_BLOB, NVS_TYPE_BLOB_DATA):
                data_len, _reserved, data_crc = struct.unpack("<HHI", data8)
                extra_slots = span - 1
                avail_bytes = extra_slots * NVS_ENTRY_SIZE
                if idx + span <= NVS_ENTRIES_PER_PAGE and data_len <= avail_bytes:
                    payload_region = entries_area[(idx + 1) * NVS_ENTRY_SIZE : (idx + span) * NVS_ENTRY_SIZE]
                    payload = payload_region[:data_len]
                    if esp_nvs_crc32(payload) == data_crc:
                        if dtype == NVS_TYPE_SZ:
                            txt = payload[:-1] if payload.endswith(b"\x00") else payload
                            ordered_entries[(ns_name, key_str)] = NvsEntry(
                                namespace=ns_name,
                                key=key_str,
                                type_name="SZ",
                                value=txt.decode("utf-8", errors="replace"),
                                type_code=NVS_TYPE_SZ,
                            )
                            blob_indices.pop((ns_name, key_str), None)
                        elif dtype == NVS_TYPE_BLOB:
                            ordered_entries[(ns_name, key_str)] = NvsEntry(
                                namespace=ns_name,
                                key=key_str,
                                type_name="BLOB",
                                value=payload,
                                type_code=NVS_TYPE_BLOB,
                            )
                            blob_indices.pop((ns_name, key_str), None)
                        else:
                            blob_chunks[(ns_idx, key_str, chunk_idx)] = payload

            elif dtype == NVS_TYPE_BLOB_IDX:
                total_size, chunk_cnt, chunk_start = struct.unpack("<IBB", data8[:6])
                blob_indices[(ns_name, key_str)] = (ns_idx, key_str, total_size, chunk_cnt, chunk_start)

            idx += span

    # Lắp ghép các BLOB_IDX + BLOB_DATA v2
    for (ns_name, key_str), (ns_idx, _k, total_size, chunk_cnt, chunk_start) in blob_indices.items():
        assembled = bytearray()
        missing = False
        for c in range(chunk_cnt):
            chunk = blob_chunks.get((ns_idx, key_str, (chunk_start + c) & 0xFF))
            if chunk is None:
                missing = True
                break
            assembled.extend(chunk)
        if not missing:
            ordered_entries[(ns_name, key_str)] = NvsEntry(
                namespace=ns_name,
                key=key_str,
                type_name="BLOB",
                value=bytes(assembled[:total_size]),
                type_code=NVS_TYPE_BLOB,
            )
        else:
            res.warnings.append(f"Thiếu mảnh BLOB cho '{ns_name}:{key_str}'.")

    res.entries = list(ordered_entries.values())
    seen_ns: list[str] = []
    for n in list(ns_map.values()) + [e.namespace for e in res.entries]:
        if n and n not in seen_ns:
            seen_ns.append(n)
    res.namespaces = seen_ns
    return res


def _build_entry_bytes(
    ns_idx: int,
    type_code: int,
    span: int,
    chunk_idx: int,
    key_bytes: bytes,
    data8: bytes,
) -> bytes:
    head = struct.pack("<BBBB", ns_idx & 0xFF, type_code & 0xFF, span & 0xFF, chunk_idx & 0xFF)
    crc = esp_nvs_crc32(head + key_bytes + data8)
    return head + struct.pack("<I", crc) + key_bytes + data8


class _NvsPageBuilder:
    def __init__(self, seq_no: int, version_byte: int):
        self.seq_no = seq_no
        self.version_byte = version_byte
        self.bitmap = bytearray([0xFF] * NVS_BITMAP_SIZE)
        self.entries_buf = bytearray([0xFF] * (NVS_ENTRIES_PER_PAGE * NVS_ENTRY_SIZE))
        self.used_slots = 0

    @property
    def free_slots(self) -> int:
        return NVS_ENTRIES_PER_PAGE - self.used_slots

    def write_span(self, first_entry: bytes, extra_data: bytes = b"") -> None:
        extra_slots = math.ceil(len(extra_data) / NVS_ENTRY_SIZE) if extra_data else 0
        total_slots = 1 + extra_slots
        if total_slots > self.free_slots:
            raise ValueError("Không đủ slot trong page NVS.")

        start_idx = self.used_slots
        self.entries_buf[start_idx * NVS_ENTRY_SIZE : (start_idx + 1) * NVS_ENTRY_SIZE] = first_entry
        _set_entry_state(self.bitmap, start_idx, ENTRY_STATE_WRITTEN)

        if extra_data:
            padded = extra_data + b"\xFF" * (extra_slots * NVS_ENTRY_SIZE - len(extra_data))
            for k in range(extra_slots):
                slot_idx = start_idx + 1 + k
                chunk = padded[k * NVS_ENTRY_SIZE : (k + 1) * NVS_ENTRY_SIZE]
                self.entries_buf[slot_idx * NVS_ENTRY_SIZE : (slot_idx + 1) * NVS_ENTRY_SIZE] = chunk
                _set_entry_state(self.bitmap, slot_idx, ENTRY_STATE_WRITTEN)

        self.used_slots += total_slots

    def finalize(self, state: int) -> bytes:
        hdr_body = struct.pack("<IB", self.seq_no, self.version_byte) + b"\xFF" * 19
        crc = esp_nvs_crc32(hdr_body)
        header = struct.pack("<I", state) + hdr_body + struct.pack("<I", crc)
        return header + bytes(self.bitmap) + bytes(self.entries_buf)


def encode_nvs_binary(entries: list[NvsEntry], partition_size: int, version: int = 2) -> bytes:
    """
    Đóng gói danh sách NvsEntry thành ảnh nhị phân NVS chuẩn ESP-IDF khớp chính xác partition_size.
    Giữ ít nhất 1 page trống cuối cùng khi partition_size >= 2 page theo chuẩn wear-leveling.
    """
    if partition_size < NVS_PAGE_SIZE or (partition_size % NVS_PAGE_SIZE) != 0:
        raise ValueError(
            f"Kích thước phân vùng NVS ({partition_size} B) phải là bội số dương của {NVS_PAGE_SIZE} B."
        )

    total_pages = partition_size // NVS_PAGE_SIZE
    max_data_pages = (total_pages - 1) if total_pages >= 2 else 1
    version_byte = NVS_VERSION_1 if version == 1 else NVS_VERSION_2

    if not entries:
        return b"\xFF" * partition_size

    # Kiểm tra trùng (namespace, key) và thu thập namespace
    dedup: dict[tuple[str, str], NvsEntry] = {}
    ns_order: list[str] = []
    for e in entries:
        ns_clean = str(e.namespace or "").strip()
        key_clean = str(e.key or "").strip()
        _encode_key_bytes(ns_clean, "Namespace")
        _encode_key_bytes(key_clean, "Key")
        if ns_clean not in ns_order:
            ns_order.append(ns_clean)
        dedup[(ns_clean, key_clean)] = e

    if len(ns_order) > 254:
        raise ValueError("Số lượng Namespace vượt quá giới hạn tối đa (254) của NVS.")

    ns_to_id = {ns: idx + 1 for idx, ns in enumerate(ns_order)}
    pages: list[_NvsPageBuilder] = [_NvsPageBuilder(0, version_byte)]

    def get_page_with_slots(needed_slots: int) -> _NvsPageBuilder:
        if pages[-1].free_slots >= needed_slots:
            return pages[-1]
        if len(pages) >= max_data_pages:
            raise ValueError(
                f"Dữ liệu NVS vượt quá dung lượng khả dụng ({max_data_pages * NVS_PAGE_SIZE} B trên {total_pages} pages)."
            )
        new_p = _NvsPageBuilder(len(pages), version_byte)
        pages.append(new_p)
        return new_p

    # Ghi bảng ánh xạ Namespace
    for ns_name, ns_id in ns_to_id.items():
        pg = get_page_with_slots(1)
        eb = _build_entry_bytes(0, NVS_TYPE_U8, 1, 0xFF, _encode_key_bytes(ns_name, "Namespace"), _encode_scalar(NVS_TYPE_U8, ns_id))
        pg.write_span(eb)

    # Ghi từng entry
    for (ns_name, key_name), entry in dedup.items():
        ns_id = ns_to_id[ns_name]
        key_b = _encode_key_bytes(key_name, "Key")
        tcode = TYPE_NAME_TO_CODE.get(entry.type_name.upper(), entry.type_code)

        if tcode in INT_TYPE_RANGES:
            pg = get_page_with_slots(1)
            eb = _build_entry_bytes(ns_id, tcode, 1, 0xFF, key_b, _encode_scalar(tcode, entry.value))
            pg.write_span(eb)

        elif tcode == NVS_TYPE_SZ:
            raw_str = str(entry.value if entry.value is not None else "").encode("utf-8") + b"\x00"
            if len(raw_str) > 4000:
                raise ValueError(f"Chuỗi '{key_name}' vượt quá độ dài tối đa cho 1 chuỗi NVS ({len(raw_str)} > 4000 B).")
            span = 1 + math.ceil(len(raw_str) / NVS_ENTRY_SIZE)
            pg = get_page_with_slots(span)
            data8 = struct.pack("<HHI", len(raw_str), 0xFFFF, esp_nvs_crc32(raw_str))
            eb = _build_entry_bytes(ns_id, NVS_TYPE_SZ, span, 0xFF, key_b, data8)
            pg.write_span(eb, raw_str)

        else:
            raw_blob = bytes(entry.value if isinstance(entry.value, (bytes, bytearray)) else b"")
            if version == 1:
                span = 1 + (math.ceil(len(raw_blob) / NVS_ENTRY_SIZE) if raw_blob else 0)
                if span > NVS_ENTRIES_PER_PAGE:
                    raise ValueError(f"BLOB '{key_name}' quá lớn đối với NVS v1 ({len(raw_blob)} B).")
                pg = get_page_with_slots(span)
                data8 = struct.pack("<HHI", len(raw_blob), 0xFFFF, esp_nvs_crc32(raw_blob))
                eb = _build_entry_bytes(ns_id, NVS_TYPE_BLOB, span, 0xFF, key_b, data8)
                pg.write_span(eb, raw_blob)
            else:
                # NVS v2: BLOB_DATA từng mảnh + 1 BLOB_IDX
                if len(raw_blob) == 0:
                    pg = get_page_with_slots(2)
                    d8_chunk = struct.pack("<HHI", 0, 0xFFFF, esp_nvs_crc32(b""))
                    pg.write_span(_build_entry_bytes(ns_id, NVS_TYPE_BLOB_DATA, 1, 0, key_b, d8_chunk))
                    d8_idx = struct.pack("<IBBH", 0, 1, 0, 0xFFFF)
                    pg.write_span(_build_entry_bytes(ns_id, NVS_TYPE_BLOB_IDX, 1, 0xFF, key_b, d8_idx))
                else:
                    offset = 0
                    chunk_index = 0
                    while offset < len(raw_blob):
                        if pages[-1].free_slots < 2:
                            get_page_with_slots(2)
                        avail_bytes = (pages[-1].free_slots - 1) * NVS_ENTRY_SIZE
                        take = min(avail_bytes, len(raw_blob) - offset)
                        chunk = raw_blob[offset : offset + take]
                        span = 1 + math.ceil(len(chunk) / NVS_ENTRY_SIZE)
                        d8_chunk = struct.pack("<HHI", len(chunk), 0xFFFF, esp_nvs_crc32(chunk))
                        pages[-1].write_span(
                            _build_entry_bytes(ns_id, NVS_TYPE_BLOB_DATA, span, chunk_index, key_b, d8_chunk),
                            chunk,
                        )
                        offset += take
                        chunk_index += 1
                    pg_idx = get_page_with_slots(1)
                    d8_idx = struct.pack("<IBBH", len(raw_blob), chunk_index, 0, 0xFFFF)
                    pg_idx.write_span(_build_entry_bytes(ns_id, NVS_TYPE_BLOB_IDX, 1, 0xFF, key_b, d8_idx))

    out = bytearray()
    for i, pg in enumerate(pages):
        st = PAGE_STATE_FULL if i < len(pages) - 1 else PAGE_STATE_ACTIVE
        out.extend(pg.finalize(st))
    while len(out) < partition_size:
        out.extend(b"\xFF" * NVS_PAGE_SIZE)
    return bytes(out[:partition_size])
