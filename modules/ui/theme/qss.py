# -*- coding: utf-8 -*-
"""
Bộ sinh QSS Stylesheet cho PyQt6 từ ThemeTokens (v1.8).
Tối ưu hiển thị duy nhất cho phong cách Kỹ thuật (Engineering) với 2 chế độ Sáng (Light) & Tối (Dark).
Loại bỏ viền focus xanh gắt trên ô nhập liệu/dropdown và đồng bộ tương phản Sidebar & StatusBar.
"""
from modules.ui.icons import _get_icons_dir
from modules.ui.theme.tokens import ThemeTokens


def build_qss(t: ThemeTokens) -> str:
    """Sinh toàn bộ chuỗi QSS Stylesheet từ bảng Tokens hiện tại."""
    icons_dir = _get_icons_dir().replace("\\", "/")
    chevron_svg_path = (
        f"{icons_dir}/chevron_down_dark.svg"
        if t.mode == "dark"
        else f"{icons_dir}/chevron_down_light.svg"
    )
    neutral_focus_border = "#52637A" if t.is_dark else "#94A3B8"
    sidebar_hover_bg = "#1A222E" if t.is_dark else "#D6E1ED"
    sidebar_checked_bg = "#1D3557" if t.is_dark else t.accent
    sidebar_checked_border = t.accent

    return f"""
    /* =========================================================================
       1. CỬA SỔ GỐC & NỀN CHÍNH
       ========================================================================= */
    QMainWindow, QDialog, QScrollArea, QWidget#CentralWorkspace, QWidget#PageScrollCanvas {{
        background-color: {t.window};
        color: {t.text};
    }}

    QWidget {{
        color: {t.text};
        font-family: "{t.font_ui}", "Segoe UI", Arial, sans-serif;
        font-size: {t.font_size_pt}pt;
    }}

    QLabel, QCheckBox, QRadioButton, QWidget[role="transparent"], QFrame[role="transparent"] {{
        background-color: transparent;
    }}

    /* =========================================================================
       2. KHUNG THẺ (CARDS & KPI STAT CARDS)
       ========================================================================= */
    QFrame[role="card"] {{
        background-color: {t.surface};
        border: 1px solid {t.border};
        border-radius: {t.radius_card}px;
    }}
    QFrame[role="card_danger"] {{
        background-color: {t.surface};
        border: 1px solid {t.danger};
        border-radius: {t.radius_card}px;
    }}
    QFrame[role="kpi_card"] {{
        background-color: {t.surface};
        border: 1px solid {t.border};
        border-radius: {t.radius_card}px;
    }}

    /* =========================================================================
       3. NÚT BẤM (BUTTONS & SEGMENTED SWITCHER)
       ========================================================================= */
    QPushButton {{
        background-color: {t.surface};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: {t.radius_control}px;
        min-height: {t.control_height}px;
        padding: 0 12px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background-color: {t.surface_alt};
        border-color: {neutral_focus_border};
    }}
    QPushButton:pressed {{
        background-color: {t.selection};
    }}
    QPushButton:checked {{
        background-color: {t.selection};
        border-color: {t.accent};
        color: {t.text};
        font-weight: 600;
    }}
    QPushButton:disabled {{
        background-color: {t.surface_alt};
        color: {t.text_secondary};
        border-color: {t.border};
    }}

    /* Nút Accent (Màu chủ đạo) */
    QPushButton[accent="true"] {{
        background-color: {t.accent};
        color: {t.on_accent};
        border: 1px solid {t.accent};
        font-weight: 600;
    }}
    QPushButton[accent="true"]:hover {{
        background-color: {t.accent_hover};
        border-color: {t.accent_hover};
    }}
    QPushButton[accent="true"]:pressed {{
        background-color: {t.accent};
    }}
    QPushButton[accent="true"]:disabled {{
        background-color: {t.border};
        color: {t.text_secondary};
        border-color: {t.border};
    }}

    /* Nút Nguy hiểm (Xóa) */
    QPushButton[danger="true"] {{
        background-color: {t.danger};
        color: #FFFFFF;
        border: 1px solid {t.danger};
        font-weight: 600;
    }}
    QPushButton[danger="true"]:hover {{
        background-color: {t.danger};
        border-color: {t.danger};
    }}

    QPushButton[danger_outline="true"] {{
        background-color: {t.surface};
        color: {t.danger};
        border: 1px solid {t.danger};
        font-weight: 600;
    }}
    QPushButton[danger_outline="true"]:hover {{
        background-color: {t.danger};
        color: #FFFFFF;
    }}

    /* =========================================================================
       4. Ô NHẬP LIỆU & COMBOBOX (KHÔNG VIỀN FOCUS XANH)
       ========================================================================= */
    QLineEdit, QSpinBox {{
        background-color: {t.surface};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: {t.radius_control}px;
        min-height: {t.control_height}px;
        padding: 0 8px;
    }}
    QComboBox {{
        background-color: {t.surface};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: {t.radius_control}px;
        min-height: {t.control_height}px;
        padding: 0 4px 0 8px;
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QComboBox:on, QSpinBox:focus {{
        border: 1px solid {neutral_focus_border};
    }}
    QTableWidget QLineEdit, QTableView QLineEdit {{
        border: none;
        border-radius: 0px;
        background-color: transparent;
        min-height: 24px;
        padding: 0 6px;
    }}
    QTableWidget QLineEdit:focus, QTableView QLineEdit:focus {{
        border: none;
        background-color: {t.surface_alt};
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        background-color: {t.surface_alt};
        color: {t.text_secondary};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: center right;
        width: 18px;
        border-left: none;
    }}
    QComboBox::down-arrow {{
        image: url("{chevron_svg_path}");
        width: 12px;
        height: 12px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {t.surface};
        color: {t.text};
        selection-background-color: {t.selection};
        selection-color: {t.text};
        border: 1px solid {t.border};
        padding: 4px;
    }}

    /* =========================================================================
       5. HỘP KIỂM (CHECKBOX) & RADIOBUTTON (DO EngineeringProxyStyle VẼ VECTOR)
       ========================================================================= */
    QCheckBox, QRadioButton {{
        spacing: 8px;
        color: {t.text};
        background-color: transparent;
    }}

    /* =========================================================================
       6. NHẬT KÝ & VĂN BẢN (LOG VIEWS)
       ========================================================================= */
    QPlainTextEdit[role="log"] {{
        background-color: {t.log_bg};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: {t.radius_control}px;
        font-family: "{t.font_mono}", "Consolas", monospace;
        font-size: 9.5pt;
        padding: 6px;
    }}

    /* =========================================================================
       7. BẢNG DỮ LIỆU & CÂY PHÂN VÙNG (TABLE & TREE VIEW)
       ========================================================================= */
    QTableView, QTableWidget, QTreeView, QTreeWidget {{
        background-color: {t.surface};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: {t.radius_control}px;
        gridline-color: {t.border};
        selection-background-color: {t.selection};
        selection-color: {t.text};
        alternate-background-color: {t.surface_alt};
    }}
    QTreeView::item, QTreeWidget::item {{
        min-height: 26px;
        padding: 2px 4px;
    }}
    QTreeView::item:selected, QTreeWidget::item:selected {{
        background-color: {t.selection};
        color: {t.text};
    }}
    QHeaderView::section {{
        background-color: {t.surface_alt};
        color: {t.text};
        border: none;
        border-right: 1px solid {t.border};
        border-bottom: 1px solid {t.border};
        padding: 6px 8px;
        font-weight: 600;
    }}

    /* =========================================================================
       8. TAB WIDGET (DÙNG CHO CÀI ĐẶT & VIEW PHỤ)
       ========================================================================= */
    QTabWidget::pane {{
        border: 1px solid {t.border};
        border-radius: {t.radius_card}px;
        background-color: {t.surface};
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: {t.surface_alt};
        color: {t.text_secondary};
        border: 1px solid {t.border};
        border-bottom: none;
        border-top-left-radius: {t.radius_control}px;
        border-top-right-radius: {t.radius_control}px;
        padding: 7px 18px;
        margin-right: 4px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        background-color: {t.surface};
        color: {t.accent};
        border-bottom: 2px solid {t.accent};
    }}
    QTabBar::tab:hover:!selected {{
        background-color: {t.selection};
        color: {t.text};
    }}

    /* =========================================================================
       9. THANH TIẾN TRÌNH & THANH CUỘN
       ========================================================================= */
    QProgressBar {{
        background-color: {t.surface_alt};
        border: 1px solid {t.border};
        border-radius: 4px;
        text-align: center;
        min-height: 8px;
        max-height: 16px;
    }}
    QProgressBar::chunk {{
        background-color: {t.accent};
        border-radius: 3px;
    }}

    QScrollBar:vertical {{
        background-color: transparent;
        width: 8px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background-color: {t.border};
        min-height: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:vertical:hover {{
        background-color: {t.accent};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}

    QScrollBar:horizontal {{
        background-color: transparent;
        height: 8px;
        margin: 0;
    }}
    QScrollBar::handle:horizontal {{
        background-color: {t.border};
        min-width: 24px;
        border-radius: 4px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background-color: {t.accent};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}

    /* =========================================================================
       10. THANH ĐIỀU HƯỚNG BÊN TRÁI (#Sidebar)
       ========================================================================= */
    #Sidebar {{
        background-color: {t.sidebar_bg};
        border-right: 1px solid {t.border};
    }}
    #Sidebar QToolButton {{
        background-color: transparent;
        color: {t.sidebar_text};
        border: 1px solid transparent;
        border-radius: {t.radius_control}px;
        padding: 8px 10px;
        text-align: left;
        font-weight: 500;
        font-size: 9.5pt;
    }}
    #Sidebar QToolButton:hover {{
        background-color: {sidebar_hover_bg};
        color: {t.sidebar_text};
    }}
    #Sidebar QToolButton:checked {{
        background-color: {sidebar_checked_bg};
        color: #FFFFFF;
        font-weight: 600;
        border: 1px solid {sidebar_checked_border};
    }}

    /* =========================================================================
       11. THANH MENU, TOOLBAR, LABELS & STATUSBAR
       ========================================================================= */
    QMenuBar {{
        background-color: {t.window};
        border-bottom: 1px solid {t.border};
        padding: 2px 4px;
    }}
    QMenuBar::item:selected {{
        background-color: {t.surface_alt};
        border-radius: 3px;
    }}
    QMenu {{
        background-color: {t.surface};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: 4px;
        padding: 4px;
    }}
    QMenu::item:selected {{
        background-color: {t.selection};
        color: {t.text};
        border-radius: 2px;
    }}
    QStatusBar {{
        background-color: {t.surface};
        color: {t.text};
        border-top: 1px solid {t.border};
    }}
    QStatusBar QLabel {{
        background-color: transparent;
        color: {t.text};
    }}
    QToolTip {{
        background-color: {t.surface};
        color: {t.text};
        border: 1px solid {t.border};
        border-radius: 4px;
        padding: 5px 8px;
    }}
    QLabel[role="title"] {{
        font-size: {t.font_size_pt + 4}pt;
        font-weight: 700;
        color: {t.text};
        background-color: transparent;
    }}
    QLabel[role="subtitle"] {{
        font-size: {t.font_size_pt - 0.5}pt;
        color: {t.text_secondary};
        background-color: transparent;
    }}
    QLabel[role="section"] {{
        font-size: {t.font_size_pt}pt;
        font-weight: 600;
        color: {t.text};
        background-color: transparent;
    }}
    QLabel[role="kpi_title"] {{
        font-size: {t.font_size_pt - 1}pt;
        font-weight: 600;
        color: {t.text_secondary};
        background-color: transparent;
    }}
    QLabel[role="kpi_value"] {{
        font-size: {t.font_size_pt + 2}pt;
        font-weight: 700;
        color: {t.text};
        background-color: transparent;
    }}
    QLabel[role="kpi_sub"] {{
        font-size: {t.font_size_pt - 1}pt;
        color: {t.text_secondary};
        background-color: transparent;
    }}
    """
