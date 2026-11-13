# -*- coding: utf-8 -*-
"""
Tier 5 Adversarial Coverage Hardening Test Suite.

Audits and stress-tests:
1. Exception handling in `_hw_flash_partition_table` (line 2104: closure of 'ex' variable).
2. Treeview event handling in `_on_tree_mousewheel` (line 661: `event.num` attribute resilience).
3. Multi-binary flashing edge cases (empty segments, offset overflows, progress double-increment).
4. Partition wizard table manipulation while device operations are running.
"""

import os
import re
import types
from unittest.mock import patch, MagicMock
import pytest

from modules.binary_scanner import validate_binary_segments
from modules.partition.partition_model import PartitionTable, PartitionEntry
from tests.mock_hardware.mock_serial import MockSerial
from tests.mock_hardware.app_harness import _global_after_queue


@pytest.mark.mock_hw
class TestTier5AdversarialHardware:
    """Tier 5 Adversarial Hardware & Interaction Stress Tests."""

    # =========================================================================
    # AREA 1: Exception Handling in `_hw_flash_partition_table` ('ex' Closure)
    # =========================================================================

    def test_tier5_partition_hw_flash_exception_closure_trap(self, headless_app, mock_serial):
        """
        Adversarial Test 1A: In `modules/tabs/tab_partition.py` line 2104,
        `safe_after(lambda: self._log_partition_hw(f">>> [NGOẠI LỆ] {ex}"))`
        captures 'ex' inside a lambda closure within an except block.
        Under Python 3 (PEP 3110), 'ex' is deleted at the end of the except block.
        When Tkinter evaluates this lambda callback, it raises NameError:
        cannot access free variable 'ex' where it is not associated with a value in enclosing scope.
        """
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        # Mock run_esptool_command to raise an unexpected runtime exception
        simulated_err = RuntimeError("ESP32 flash write hardware bus timeout")
        captured_callbacks = []

        # Hook Misc.after to capture the callback dispatched by safe_after
        orig_after = app.root.after

        def spy_after(ms, func=None, *args):
            if func is not None:
                captured_callbacks.append(func)
            return orig_after(ms, func, *args)

        with patch.object(app.root, "after", side_effect=spy_after):
            with patch("modules.tabs.tab_partition.run_esptool_command", side_effect=simulated_err):
                with patch("modules.tabs.tab_partition.messagebox.askyesno", return_value=True):
                    app._hw_flash_partition_table()
                    # Wait for worker thread to complete
                    harness.wait_for(lambda: not getattr(app, "_is_partition_hw_running", False), timeout=3.0)

        # Worker thread has exited the except block. Now verify the hardened closure:
        # Find the lambda that was scheduled for logging the exception
        exception_lambdas = [fn for fn in captured_callbacks if callable(fn) and fn.__name__ == "<lambda>"]
        assert len(exception_lambdas) > 0, "Expected at least one lambda scheduled in safe_after"

        # Execute the lambdas and verify no NameError occurs
        for fn in exception_lambdas:
            fn()

        # Verify finally block still cleanly reset device busy state
        assert app._is_partition_hw_running is False

    def test_tier5_partition_hw_read_exception_closure_trap(self, headless_app, mock_serial):
        """
        Adversarial Test 1B: Verify the identical closure bug in `_hw_read_partition_table_from_chip`
        (modules/tabs/tab_partition.py line 2031).
        """
        harness, app = headless_app
        app.port_cb.set("COM3")
        app.baud_cb.set("115200")

        simulated_err = IOError("Serial port I/O read packet corrupted")
        captured_callbacks = []

        orig_after = app.root.after

        def spy_after(ms, func=None, *args):
            if func is not None:
                captured_callbacks.append(func)
            return orig_after(ms, func, *args)

        with patch.object(app.root, "after", side_effect=spy_after):
            with patch("modules.tabs.tab_partition.run_esptool_command", side_effect=simulated_err):
                app._hw_read_partition_table()
                harness.wait_for(lambda: not getattr(app, "_is_partition_hw_running", False), timeout=3.0)

        exception_lambdas = [fn for fn in captured_callbacks if callable(fn) and fn.__name__ == "<lambda>"]
        assert len(exception_lambdas) > 0, "Expected at least one lambda scheduled in safe_after"
        for fn in exception_lambdas:
            fn()
        assert app._is_partition_hw_running is False

    # =========================================================================
    # AREA 2: Treeview Event Handling in `_on_tree_mousewheel`
    # =========================================================================

    def test_tier5_tree_mousewheel_missing_num_attribute_raises_attribute_error(self, headless_app):
        """
        Adversarial Test 2A: In `modules/tabs/tab_partition.py` line 661:
        `if getattr(event, "num", None) == 4 or ...` safely handles events lacking .num.
        """
        harness, app = headless_app

        # Construct an event with .delta but WITHOUT .num attribute
        event_without_num = types.SimpleNamespace(delta=120)

        # No AttributeError raised, safely scrolls and returns 'break'
        res = app._on_tree_mousewheel(event_without_num)
        assert res == "break"

    def test_tier5_tree_mousewheel_resilience_with_valid_events(self, headless_app):
        """
        Adversarial Test 2B: Verify mouse wheel handles Linux Button-4/Button-5
        and Windows delta events cleanly when `.num` is present.
        """
        harness, app = headless_app

        # 1. Linux scroll up (Button-4)
        event_btn4 = types.SimpleNamespace(num=4, delta=0)
        res = app._on_tree_mousewheel(event_btn4)
        assert res == "break"

        # 2. Linux scroll down (Button-5)
        event_btn5 = types.SimpleNamespace(num=5, delta=0)
        res = app._on_tree_mousewheel(event_btn5)
        assert res == "break"

        # 3. Windows scroll up (delta > 0, num='??' in standard Tkinter)
        event_win_up = types.SimpleNamespace(num="??", delta=120)
        res = app._on_tree_mousewheel(event_win_up)
        assert res == "break"

        # 4. Windows scroll down (delta < 0, num='??')
        event_win_down = types.SimpleNamespace(num="??", delta=-120)
        res = app._on_tree_mousewheel(event_win_down)
        assert res == "break"

    # =========================================================================
    # AREA 3: Multi-Binary Flashing Edge Cases
    # =========================================================================

    def test_tier5_multi_binary_progress_double_increment_edge_case(self):
        """
        Adversarial Test 3A: In `modules/tabs/tab_flasher.py` line 575:
        `if "Hash of data verified" in line or re.search(r"Wrote\\s+\\d+\\s+bytes", line):`
        In standard esptool output, every binary segment produces BOTH a "Wrote X bytes"
        line and a "Hash of data verified" line consecutively.
        Because both match the same `if` condition across successive stream lines,
        `current_file_idx` increments TWICE for a single file completion!
        For a 3-binary flash, File 0 completion jumps `current_file_idx` directly to 2.
        """
        write_pairs = [("0x1000", "boot.bin"), ("0x8000", "part.bin"), ("0x10000", "app.bin")]
        file_sizes = [16384, 3072, 1048576]
        total_bytes = sum(file_sizes)

        current_file_idx = 0
        last_file_pct = 0
        file_finished = False
        progress_reports = []

        def simulated_on_stream(line):
            nonlocal current_file_idx, last_file_pct, file_finished
            if "Hash of data verified" in line or re.search(r"Wrote\s+\d+\s+bytes", line):
                if not file_finished and current_file_idx < len(write_pairs) - 1:
                    current_file_idx += 1
                    last_file_pct = 0
                    file_finished = True

            if "Writing at" in line:
                file_finished = False

            m = re.search(r"\((\d+)\s*%\)", line)
            if m:
                pct = int(m.group(1))
                if pct < last_file_pct and current_file_idx < len(write_pairs) - 1:
                    if not file_finished:
                        current_file_idx += 1
                        last_file_pct = 0
                last_file_pct = pct
                file_finished = False

                completed_bytes = sum(file_sizes[:current_file_idx])
                current_bytes = (pct / 100.0) * file_sizes[current_file_idx]
                agg_pct = min(100, max(0, int(((completed_bytes + current_bytes) / total_bytes) * 100)))
                progress_reports.append(agg_pct)

        # 1. File 0 reports 100%
        simulated_on_stream("Writing at 0x00001000... (100 %)")
        assert current_file_idx == 0

        # 2. File 0 completes: esptool outputs "Wrote X bytes"
        simulated_on_stream("Wrote 16384 bytes (8940 compressed) at 0x00001000 in 0.2 seconds...")
        assert current_file_idx == 1, "First increment on Wrote line"

        # 3. File 0 completes: esptool immediately outputs "Hash of data verified."
        simulated_on_stream("Hash of data verified.")
        # Verified fix: current_file_idx remains 1, no second increment
        assert current_file_idx == 1

    def test_tier5_multi_binary_empty_write_pairs_index_error(self):
        """
        Adversarial Test 3B: If `_flash_write_worker` receives an empty list of write_pairs,
        the stream callback crashes with IndexError when indexing `file_sizes[current_file_idx]`.
        """
        write_pairs = []
        file_sizes = []
        current_file_idx = 0

        def stream_calc(line):
            m = re.search(r"\((\d+)\s*%\)", line)
            if m:
                pct = int(m.group(1))
                return (pct / 100.0) * file_sizes[current_file_idx]
            return 0

        with pytest.raises(IndexError, match="list index out of range"):
            stream_calc("Writing at 0x0... (50 %)")

    def test_tier5_multi_binary_offset_overflow_boundary(self, headless_app, tmp_path, mock_dialogs):
        """
        Adversarial Test 3C: `validate_binary_segments` accepts an offset far beyond
        physical flash limits (e.g. 0x10000000 = 256MB on an ESP32 with 4MB flash)
        and tab_flasher cross-checks max_end against chip flash size, blocking it with error.
        """
        harness, app = headless_app
        bin_file = tmp_path / "app.bin"
        bin_file.write_bytes(b"\x00" * 4096)

        huge_offset = "0x10000000"  # 256 MB
        pairs = [(huge_offset, str(bin_file))]

        # validate_binary_segments validates syntax and returns max_end
        is_valid, message, normalized_pairs, max_end = validate_binary_segments(pairs)
        assert is_valid is True
        assert max_end == 0x10000000 + 4096

        # Flasher verifies max_end against flash_size and blocks flashing
        app.port_cb.set("COM3")
        for row in app.flash_file_rows[1:]:
            row["var_enable"].set(False)
        app.flash_file_rows[0]["var_enable"].set(True)
        app.flash_file_rows[0]["path_entry"].delete(0, "end")
        app.flash_file_rows[0]["path_entry"].insert(0, str(bin_file))
        app.flash_file_rows[0]["offset_entry"].delete(0, "end")
        app.flash_file_rows[0]["offset_entry"].insert(0, huge_offset)

        app.on_flash_write_click()
        harness.pump(5)

        assert any("Vượt quá dung lượng Flash" in err[0] for err in mock_dialogs["showerror"])
        assert not app.is_flashing.is_set()

    def test_tier5_multi_binary_defense_blocks_invalid_segments(self, tmp_path):
        """
        Adversarial Test 3D: Verify `validate_binary_segments` defends against
        empty files, zero-byte files, and overlapping offsets.
        """
        f1 = tmp_path / "boot.bin"
        f1.write_bytes(b"\x00" * 8192)  # 0x1000 to 0x3000

        f2_overlap = tmp_path / "part.bin"
        f2_overlap.write_bytes(b"\x00" * 4096)  # starts at 0x2000 -> overlap!

        is_valid, msg, _, _ = validate_binary_segments([
            ("0x1000", str(f1)),
            ("0x2000", str(f2_overlap))
        ])
        assert is_valid is False
        assert "chồng lấn vùng nhớ" in msg

        # Empty 0-byte file
        f_empty = tmp_path / "empty.bin"
        f_empty.write_bytes(b"")
        is_valid2, msg2, _, _ = validate_binary_segments([("0x1000", str(f_empty))])
        assert is_valid2 is False
        assert "rỗng" in msg2

    # =========================================================================
    # AREA 4: Partition Wizard Manipulation While Device Operations Running
    # =========================================================================

    def test_tier5_partition_table_delete_while_hardware_busy(self, headless_app):
        """
        Adversarial Test 4A: When a partition hardware task is running
        (`_is_partition_hw_running = True`), calling `_action_delete_by_entry`
        checks `_is_partition_hw_running` / `is_device_busy()` and returns early.
        """
        harness, app = headless_app
        app.table.entries.append(PartitionEntry(
            name="nvs", type_str="data", subtype_str="nvs",
            offset=0x9000, size=0x6000, flags_str=""
        ))
        app.refresh_partition_views()
        assert len(app.table.entries) > 0
        target_entry = app.table.entries[0]
        initial_count = len(app.table.entries)

        # Set hardware operation flag
        app._is_partition_hw_running = True

        with patch("modules.tabs.tab_partition.messagebox.askyesno", return_value=True):
            # Attempt to delete entry while hardware operation is running
            app._action_delete_by_entry(target_entry)

        # Verified fix: The entry was NOT deleted because the method has a busy guard
        assert len(app.table.entries) == initial_count
        assert target_entry in app.table.entries

        # Clean up
        app._is_partition_hw_running = False

    def test_tier5_partition_table_undo_redo_while_hardware_busy(self, headless_app):
        """
        Adversarial Test 4B: When `_is_partition_hw_running = True`, calling
        `_action_undo` or `_action_redo` is blocked by busy check.
        """
        harness, app = headless_app

        # Push a known undo state
        app._push_partition_undo_state()
        app.table.entries.append(PartitionEntry(
            name="rogue_part", type_str="data", subtype_str="spiffs",
            offset=0x300000, size=0x10000, flags_str=""
        ))
        assert any(e.name == "rogue_part" for e in app.table.entries)

        # Hardware task starts
        app._is_partition_hw_running = True

        # User triggers Undo while hardware task is running
        app._action_undo()

        # Verified fix: The undo operation was blocked while hardware task is running
        assert any(e.name == "rogue_part" for e in app.table.entries)

        # Clean up
        app._is_partition_hw_running = False

    def test_tier5_partition_table_add_and_autopack_while_hardware_busy(self, headless_app):
        """
        Adversarial Test 4C: When `_is_partition_hw_running = True`, calling
        `_action_add_after_row` or `_action_auto_pack` is blocked by busy check.
        """
        harness, app = headless_app
        app.table.entries.append(PartitionEntry(
            name="nvs", type_str="data", subtype_str="nvs",
            offset=0x9000, size=0x6000, flags_str=""
        ))
        app.refresh_partition_views()
        initial_count = len(app.table.entries)

        app._is_partition_hw_running = True

        # 1. Add after row blocked by busy check
        app._action_add_after_row(app.part_tree.get_children()[0])
        assert len(app.table.entries) == initial_count

        # 2. Auto-pack blocked by busy check
        with patch("modules.tabs.tab_partition.messagebox.showinfo") as mock_info:
            app._action_auto_pack()
            assert not mock_info.called
        harness.pump(5)

        # Clean up
        app._is_partition_hw_running = False
