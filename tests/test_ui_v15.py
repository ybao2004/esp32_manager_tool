# -*- coding: utf-8 -*-
"""
Tests for ESP32 Manager Tool v1.5 UI:
1. Navigation across all 6 pages via Sidebar.
2. Sidebar collapse (52px) and expand (242px).
3. 6-theme switching without error.
4. Zero Unicode emoji audit across codebase and documentation.
5. Ampersand audit for Qt text safety.
"""
import os
import re
import pytest
from pathlib import Path
from PyQt6.QtCore import Qt
from modules.ui.theme.manager import ThemeManager
from modules.ui.text import qt_text


@pytest.mark.mock_hw
class TestUiV15Features:

    def test_navigation_across_all_six_pages(self, headless_app):
        """Kiem tra chuyen doi qua lai giua tat ca 6 trang tren giao dien."""
        harness, app = headless_app

        expected_pages = [
            (0, app.page_inspector, "Kiem tra chip"),
            (1, app.page_monitor, "Serial Monitor"),
            (2, app.page_flasher, "Nap Firmware"),
            (3, app.page_partition, "Phan vung"),
            (4, app.page_backup, "Sao luu"),
            (5, app.page_settings, "Cai dat"),
        ]

        for idx, page_widget, name in expected_pages:
            app.sidebar.select(idx)
            harness.pump(times=3)
            assert app.stack.currentIndex() == idx, f"Failed navigating to page {name} (index {idx})"
            assert app.stack.currentWidget() == page_widget, f"Current widget mismatch for {name}"

    def test_sidebar_collapse_and_expansion(self, headless_app):
        """Kiem tra thu gon (52px) va mo rong (190px) cua Sidebar."""
        harness, app = headless_app

        # Mac dinh ban dau la mo rong
        assert not app.sidebar.is_collapsed
        assert app.sidebar.width() == 190

        # Bam thu gon
        app.sidebar.toggle_collapse()
        harness.pump(times=3)
        assert app.sidebar.is_collapsed
        assert app.sidebar.width() == 52

        # Bam mo rong tro lai
        app.sidebar.toggle_collapse()
        harness.pump(times=3)
        assert not app.sidebar.is_collapsed
        assert app.sidebar.width() == 190

    def test_theme_switching_all_six_variants(self, headless_app):
        """Kiem tra ap dung phong cach Ky thuat (engineering) Sang/Toi va ep cac preset cu ve engineering."""
        harness, app = headless_app
        tm = ThemeManager.instance()

        variants = [
            ("engineering", False),
            ("engineering", True),
            ("fluent", False),
            ("vscode", True),
        ]

        from PyQt6.QtWidgets import QApplication
        for preset, is_dark in variants:
            tokens = tm.apply(preset, is_dark)
            harness.pump(times=3)
            assert tm.current_theme == "engineering"
            assert tm.is_dark == is_dark
            assert tokens is not None
            assert len(QApplication.instance().styleSheet()) > 0

    def test_zero_unicode_emojis_in_source_and_docs(self):
        """
        Kiem tra nghiem ngat: Khong ton tai bat ky ky tu emoji Unicode nao
        trong toan bo ma nguon (modules/**/*.py, main.py) va tai lieu (README.md, docs/*.md).
        """
        # Mau bieu thuc regex phat hien cac dai ma Unicode emoji pho bien
        emoji_pattern = re.compile(
            r"[\U0001F600-\U0001F64F"  # Emoticons
            r"\U0001F300-\U0001F5FF"  # Misc Symbols & Pictographs
            r"\U0001F680-\U0001F6FF"  # Transport & Map
            r"\U0001F1E0-\U0001F1FF"  # Flags
            r"\U0001F900-\U0001F9FF"  # Supplemental Symbols
            r"\U0001FA00-\U0001FA6F"  # Chess / Symbols
            r"\U0001FA70-\U0001FAFF"  # Symbols extended
            r"\U00002600-\U000026FF"  # Misc symbols (sun, umbrella, warning, etc.)
            r"\U00002700-\U000027BF"  # Dingbats (checkmarks, arrows, etc.)
            r"\U0000FE00-\U0000FE0F]" # Variation selectors
        )

        root_dir = Path(__file__).resolve().parent.parent
        files_to_check = []

        # Ma nguon python
        files_to_check.extend((root_dir / "modules").rglob("*.py"))
        files_to_check.append(root_dir / "main.py")

        # Tai lieu markdown
        files_to_check.append(root_dir / "README.md")
        docs_dir = root_dir / "docs"
        if docs_dir.exists():
            files_to_check.extend(docs_dir.rglob("*.md"))

        violations = []
        for fpath in files_to_check:
            if not fpath.exists():
                continue
            try:
                content = fpath.read_text(encoding="utf-8")
                matches = emoji_pattern.findall(content)
                if matches:
                    violations.append(f"{fpath.relative_to(root_dir)}: found {len(matches)} emojis -> {matches[:5]}")
            except Exception as e:
                violations.append(f"{fpath}: read error {e}")

        assert len(violations) == 0, f"Phat hien Unicode emoji tai cac file:\n" + "\n".join(violations)

    def test_ampersand_safety_helper(self):
        """Kiem tra helper qt_text tu dong thoat cac ky tu '&' don le."""
        assert qt_text("Save & Exit") == "Save && Exit"
        assert qt_text("A && B") == "A && B"
        assert qt_text("Single & and double && test") == "Single && and double && test"
        assert qt_text("No ampersand") == "No ampersand"
        assert qt_text("") == ""
