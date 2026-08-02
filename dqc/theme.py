"""Visual language for the application.

One dark palette, applied through a single stylesheet so widget code stays
free of inline colours.
"""

BG = '#15171d'
SURFACE = '#1b1e26'
SURFACE_HI = '#232733'
BORDER = '#2c313d'
TEXT = '#e8eaf0'
MUTED = '#8b91a3'
ACCENT = '#5865f2'
ACCENT_HI = '#6b76f5'
GOOD = '#3ba55d'
WARN = '#e0a33e'
BAD = '#ed4245'

STYLESHEET = f"""
QWidget {{
    background: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 13px;
}}

QLabel[role="title"] {{
    font-size: 22px;
    font-weight: 600;
}}
QLabel[role="subtitle"] {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel[role="section"] {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QLabel[role="mono"] {{
    font-family: 'Cascadia Mono', Consolas, monospace;
    font-size: 12px;
    color: {MUTED};
}}

QLineEdit, QComboBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 9px 12px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT};
    outline: none;
}}

QPushButton {{
    background: {SURFACE_HI};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 9px 16px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {MUTED}; background: {SURFACE}; }}

QPushButton[role="primary"] {{
    background: {ACCENT};
    border: none;
    color: white;
    padding: 11px 20px;
}}
QPushButton[role="primary"]:hover {{ background: {ACCENT_HI}; }}
QPushButton[role="primary"]:disabled {{ background: {SURFACE_HI}; color: {MUTED}; }}

QPushButton[role="ghost"] {{
    background: transparent;
    border: 1px solid {BORDER};
    font-weight: 500;
}}
QPushButton[role="ghost"]:hover {{ background: {SURFACE_HI}; }}

QListWidget {{
    background: {BG};
    border: none;
    outline: none;
}}
QListWidget::item {{
    border-radius: 10px;
    margin: 2px 6px 2px 0px;
}}
QListWidget::item:selected {{ background: {SURFACE_HI}; }}
QListWidget::item:hover {{ background: {SURFACE}; }}

QFrame[role="card"] {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame[role="divider"] {{
    background: {BORDER};
    max-height: 1px;
    border: none;
}}

QProgressBar {{
    background: {SURFACE_HI};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
    border: none;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:vertical:hover,
QScrollBar::handle:horizontal:hover {{ background: {MUTED}; }}
QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
    border: none;
    background: none;
}}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QToolTip {{
    background: {SURFACE_HI};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 6px 8px;
    border-radius: 6px;
}}
"""
