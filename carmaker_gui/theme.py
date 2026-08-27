from __future__ import annotations

# Accessible industrial light palette for consistent contrast across displays.
COLORS = {
    "bg": "#F3F5F7",
    "sidebar": "#E9EDF2",
    "panel": "#FFFFFF",
    "panel_alt": "#F8FAFC",
    "border": "#B8C2CC",
    "border_soft": "#D7DEE6",
    "text": "#18212B",
    "muted": "#465566",
    "subtle": "#687789",
    "accent": "#0057B8",
    "accent_hover": "#004A9C",
    "accent_pressed": "#003F86",
    "accent_soft": "#E7F0FB",
    "success": "#166534",
    "warning": "#9A4D00",
    "danger": "#B42318",
    "disabled": "#8A96A3",
}


def stylesheet() -> str:
    c = COLORS
    return f"""
    * {{
        font-family: "Segoe UI", "Microsoft YaHei UI", "Noto Sans CJK SC", sans-serif;
        font-size: 14px;
    }}
    QMainWindow, QWidget#AppRoot {{
        background: {c['bg']};
        color: {c['text']};
    }}
    QWidget {{
        color: {c['text']};
    }}
    QScrollArea, QScrollArea > QWidget > QWidget {{
        background: {c['bg']};
        border: 0;
    }}
    QFrame#Sidebar {{
        background: {c['sidebar']};
        border-right: 1px solid {c['border_soft']};
    }}
    QLabel#BrandTitle {{
        font-size: 18px;
        font-weight: 700;
        color: {c['text']};
    }}
    QLabel#BrandSubtitle, QLabel#MutedLabel, QLabel#FieldHint {{
        color: {c['muted']};
    }}
    QLabel#PageTitle {{
        font-size: 24px;
        font-weight: 700;
        color: {c['text']};
    }}
    QLabel#PageSubtitle {{
        color: {c['muted']};
        font-size: 14px;
    }}
    QLabel#SectionTitle {{
        color: {c['text']};
        font-size: 15px;
        font-weight: 700;
    }}
    QPushButton#NavButton {{
        text-align: left;
        padding: 10px 13px;
        min-height: 28px;
        border: 1px solid transparent;
        border-left: 4px solid transparent;
        background: transparent;
        color: {c['muted']};
        border-radius: 4px;
    }}
    QPushButton#NavButton:hover {{
        background: #F4F7FA;
        color: {c['text']};
        border-color: {c['border_soft']};
        border-left-color: {c['border_soft']};
    }}
    QPushButton#NavButton:checked {{
        background: {c['panel']};
        border-color: {c['border_soft']};
        border-left: 4px solid {c['accent']};
        color: {c['text']};
        font-weight: 700;
    }}
    QFrame#Card, QGroupBox {{
        background: {c['panel']};
        border: 1px solid {c['border_soft']};
        border-radius: 7px;
    }}
    QGroupBox {{
        margin-top: 20px;
        padding: 20px 16px 16px 16px;
        font-weight: 700;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        top: 2px;
        padding: 2px 7px;
        color: {c['text']};
        background: {c['panel']};
    }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QListWidget, QTableWidget, QPlainTextEdit, QTextEdit {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 5px;
        padding: 7px 9px;
        color: {c['text']};
        selection-background-color: {c['accent']};
        selection-color: #FFFFFF;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
    QListWidget:focus, QTableWidget:focus, QPlainTextEdit:focus, QTextEdit:focus {{
        border: 2px solid {c['accent']};
        padding: 6px 8px;
    }}
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled,
    QListWidget:disabled, QTableWidget:disabled {{
        color: #637181;
        background: #EEF1F4;
        border-color: #D3D9E0;
    }}
    QComboBox::drop-down {{
        border: 0;
        width: 30px;
    }}
    QComboBox QAbstractItemView {{
        background: {c['panel']};
        color: {c['text']};
        selection-background-color: {c['accent_soft']};
        selection-color: {c['text']};
        border: 1px solid {c['border']};
    }}
    QPushButton {{
        background: {c['panel']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 5px;
        padding: 7px 13px;
        min-height: 28px;
    }}
    QPushButton:hover {{
        border-color: {c['accent']};
        background: {c['accent_soft']};
    }}
    QPushButton:pressed {{
        background: #D6E6F8;
    }}
    QPushButton:focus {{
        border: 2px solid {c['accent']};
        padding: 6px 12px;
    }}
    QPushButton:disabled {{
        background: #EEF1F4;
        color: #7A8794;
        border-color: #D3D9E0;
    }}
    QPushButton#PrimaryButton {{
        background: {c['accent']};
        border-color: {c['accent']};
        color: #FFFFFF;
        font-weight: 700;
    }}
    QPushButton#PrimaryButton:hover {{
        background: {c['accent_hover']};
        border-color: {c['accent_hover']};
        color: #FFFFFF;
    }}
    QPushButton#DangerButton {{
        background: #FFF1F0;
        border-color: #E7A6A1;
        color: #8F1D14;
        font-weight: 700;
    }}
    QPushButton#DangerButton:hover {{
        background: #FDE3E1;
        border-color: {c['danger']};
        color: #7A1710;
    }}
    QCheckBox {{
        spacing: 8px;
        color: {c['text']};
        min-height: 28px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border: 1px solid {c['border']};
        border-radius: 3px;
        background: {c['panel']};
    }}
    QCheckBox::indicator:checked {{
        background: {c['accent']};
        border-color: {c['accent']};
    }}
    QHeaderView::section {{
        background: #E8EDF3;
        color: #263646;
        border: 0;
        border-right: 1px solid {c['border_soft']};
        border-bottom: 1px solid {c['border']};
        padding: 9px;
        font-weight: 700;
    }}
    QTableWidget {{
        gridline-color: {c['border_soft']};
        alternate-background-color: #F8FAFC;
    }}
    QTableWidget::item {{
        padding: 7px;
    }}
    QTableWidget::item:selected, QListWidget::item:selected {{
        background: {c['accent_soft']};
        color: {c['text']};
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 12px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: #AAB5C1;
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #8795A4;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QToolTip {{
        background: #FFFFFF;
        color: {c['text']};
        border: 1px solid {c['border']};
        padding: 7px;
    }}
    """
