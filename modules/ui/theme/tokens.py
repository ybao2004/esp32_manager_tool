# -*- coding: utf-8 -*-
"""
Hệ thống Design Tokens cho giao diện PyQt6 (v1.9)
Sử dụng duy nhất phong cách Kỹ thuật (Engineering) với 2 chế độ Sáng (Light) & Tối (Dark).
Đạt chuẩn tương phản khả năng truy cập WCAG 2.2 AA (tối thiểu 4.5:1) trên cả thanh Sidebar và StatusBar.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ThemeTokens:
    preset: str
    mode: str
    window: str
    surface: str
    surface_alt: str
    border: str
    text: str
    text_secondary: str
    accent: str
    accent_hover: str
    on_accent: str
    danger: str
    success: str
    warning: str
    sidebar_bg: str
    sidebar_text: str
    selection: str
    log_bg: str
    radius_card: int
    radius_control: int
    control_height: int
    font_ui: str
    font_size_pt: int
    font_mono: str
    spacing: int
    sidebar_width_expanded: int
    sidebar_width_collapsed: int
    sidebar_collapsed_default: bool

    @property
    def is_dark(self) -> bool:
        return self.mode == "dark"


AVAILABLE_PRESETS = ("engineering",)

_TOKENS_MAP = {
    ("engineering", "light"): ThemeTokens(
        preset="engineering", mode="light",
        window="#EEF2F6", surface="#FFFFFF", surface_alt="#E4EBF2", border="#CBD5E1",
        text="#0F172A", text_secondary="#475569",
        accent="#1565C0", accent_hover="#0D47A1", on_accent="#FFFFFF",
        danger="#C62828", success="#1B7F3A", warning="#D97706",
        sidebar_bg="#E6EDF5", sidebar_text="#0F172A",
        selection="#DBEAFE", log_bg="#F8FAFC",
        radius_card=5, radius_control=4, control_height=30,
        font_ui="Segoe UI", font_size_pt=9,
        font_mono="Consolas", spacing=8,
        sidebar_width_expanded=190, sidebar_width_collapsed=52,
        sidebar_collapsed_default=False
    ),
    ("engineering", "dark"): ThemeTokens(
        preset="engineering", mode="dark",
        window="#0E131A", surface="#18202B", surface_alt="#202A38", border="#2E3B4E",
        text="#E6EDF3", text_secondary="#94A3B8",
        accent="#3B82F6", accent_hover="#60A5FA", on_accent="#FFFFFF",
        danger="#F85149", success="#3FB950", warning="#F59E0B",
        sidebar_bg="#090D12", sidebar_text="#E2E8F0",
        selection="#1E3A5F", log_bg="#0B1016",
        radius_card=5, radius_control=4, control_height=30,
        font_ui="Segoe UI", font_size_pt=9,
        font_mono="Consolas", spacing=8,
        sidebar_width_expanded=190, sidebar_width_collapsed=52,
        sidebar_collapsed_default=False
    ),
}


def get_tokens(preset: str = "engineering", mode: str = "light") -> ThemeTokens:
    preset_key = "engineering"
    mode_key = str(mode).lower()
    if mode_key not in ("light", "dark"):
        mode_key = "light"
    return _TOKENS_MAP.get((preset_key, mode_key), _TOKENS_MAP[("engineering", "light")])
