"""Global stylesheet builder."""
from __future__ import annotations


def build_stylesheet(s: dict) -> str:
    accent = s.get("accent_color", "#d4a017")
    accent2 = s.get("accent_color2", "#8a5cf6")
    bg = s.get("bg_color", "#0b0e14")
    panel = s.get("panel_color", "#141a24")
    text = s.get("text_color", "#eef1f6")
    return f"""
    QMainWindow, QWidget {{
        background: {bg}; color: {text};
        font-family: "Segoe UI", "Vazirmatn", "Tahoma"; font-size: 13px;
    }}
    QLabel#PageTitle {{
        font-size: 21px; font-weight: 800; color: {accent};
        padding-bottom: 2px;
    }}
    QLabel {{ background: transparent; color: {text}; }}
    QPushButton {{
        background: rgba(255,255,255,0.05); color: {text};
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 11px; padding: 10px 18px; font-weight: 600;
    }}
    QPushButton:hover {{ background: rgba(255,255,255,0.11); border-color: rgba(255,255,255,0.2); }}
    QPushButton:pressed {{ background: rgba(255,255,255,0.16); }}
    QPushButton#PrimaryButton, QPushButton:checked {{
        background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {accent}, stop:1 {accent2});
        color: #0a0c10; border: none; font-weight: 800;
    }}
    QPushButton#DangerButton {{ background: #b6242f; color: #fff; border: none; }}
    QPushButton#DangerButton:hover {{ background: #d02b38; }}
    QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: rgba(255,255,255,0.045); border: 1px solid rgba(255,255,255,0.12);
        border-radius: 11px; padding: 10px 12px; color: {text}; min-height: 34px;
        selection-background-color: {accent};
    }}
    QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border: 1.5px solid {accent};
    }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QTableWidget {{
        background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.10);
        border-radius: 14px; gridline-color: rgba(255,255,255,0.06);
        alternate-background-color: rgba(255,255,255,0.02);
        selection-background-color: {accent}; selection-color: #000;
    }}
    QHeaderView::section {{
        background: rgba(255,255,255,0.05); padding: 10px; border: none;
        border-bottom: 2px solid {accent}; color: #9aa4b2; font-weight: 700;
    }}
    QGroupBox {{
        background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.10);
        border-radius: 16px; margin-top: 18px; padding: 16px; font-weight: 700; color: {accent};
    }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 16px; padding: 0 10px; color: {accent}; }}
    QFrame#KpiCard {{
        background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
            stop:0 rgba(255,255,255,0.06), stop:1 rgba(255,255,255,0.02));
        border: 1px solid rgba(255,255,255,0.12); border-radius: 16px;
    }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
    QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.15); min-height: 30px; border-radius: 5px; }}
    QScrollBar::handle:vertical:hover {{ background: {accent}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QDialog, QMessageBox {{ background: {panel}; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px; border-radius: 5px;
        border: 1.5px solid rgba(255,255,255,0.25); background: rgba(255,255,255,0.04);
    }}
    QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
    """


# ─────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────
