"""Flat desktop styles and monochrome control icons."""
from PySide6.QtCore import QByteArray, Qt, QSize
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ACCENT = "#9ae2ff"
INK = "#252525"
MUTED = "#6b6b6b"

PATHS = {
    "cloud": '<path d="M6 18h12a4 4 0 0 0 .3-8A6.5 6.5 0 0 0 6 8.5 4.8 4.8 0 0 0 6 18Z"/>',
    "home": '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    "photos": '<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r="1.5"/><path d="m3 16 5-5 4 4 4-6 5 7"/>',
    "folder": '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',
    "messages": '<path d="M21 11a8 8 0 0 1-8 8H7l-4 3V11a9 9 0 0 1 18 0Z"/><path d="M7 10h10M7 14h6"/>',
    "activity": '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
    "settings": '<path d="M4 6h16M4 12h16M4 18h16"/><circle cx="9" cy="6" r="2" fill="white"/><circle cx="15" cy="12" r="2" fill="white"/><circle cx="9" cy="18" r="2" fill="white"/>',
    "arrow": '<path d="M5 12h14m-5-5 5 5-5 5"/>',
    "chevron": '<path d="m9 5 7 7-7 7"/>',
    "download": '<path d="M12 3v12m-5-5 5 5 5-5M4 16v4h16v-4"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "shield": '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6Z"/><path d="m8 12 3 3 5-6"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "refresh": '<path d="M20 10a8 8 0 1 0-1 7M20 4v6h-6"/>',
    "external": '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/>',
    "help": '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 4 3v2m-1 3h.01"/>',
    "file": '<path d="M14 3H5v18h14V8Zm0 0v6h5M8 13h8M8 17h5"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="3"/>',
    "lock": '<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>',
}


def icon(name, color=MUTED, size=24):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
           f'fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'
           + PATHS.get(name, PATHS["cloud"]) + '</svg>')
    pixmap = QPixmap(size * 2, size * 2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(QByteArray(svg.encode())).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


STYLE = """
QMainWindow, QDialog { background: #f5f5f7; }
QWidget { color: #252525; font-size: 13px; }
QLabel { background: transparent; border: none; }
QLabel[role="muted"], QLabel[role="small"] { color: #6b6b6b; }
QLabel[role="small"] { font-size: 12px; }
QLabel[role="title"] { font-size: 24px; font-weight: 600; }
QLabel[role="heading"] { font-size: 13px; font-weight: 600; }
QFrame#sidebar { background: #ececef; border-right: 1px solid #dcdce0; }
QFrame#card { background: #ffffff; border: 1px solid #dedee3; border-radius: 10px; }
QFrame#messagePanel { background: #ffffff; border: 1px solid #dedee3; border-radius: 10px; }
QFrame#line { background: #e6e6eb; max-height: 1px; border: 0; }
QPushButton { background: #ffffff; border: 1px solid #d2d2d7; border-radius: 6px; padding: 6px 12px; }
QPushButton:hover { background: #fafafa; border-color: #b8b8c0; }
QPushButton:pressed { background: #e8e8ed; }
QPushButton:disabled { color: #999999; border-color: #e5e5e5; background: #fafafa; }
QPushButton[variant="primary"] { background: #9ae2ff; color: #252525; border-color: #9ae2ff; }
QPushButton[variant="primary"]:hover { background: #b6eaff; border-color: #b6eaff; }
QPushButton[variant="primary"]:pressed { background: #83d9fb; border-color: #83d9fb; }
QPushButton[variant="primary"]:disabled { color: #888888; background: #edf7fa; border-color: #edf7fa; }
QPushButton[variant="quiet"] { background: transparent; border: none; color: #555555; padding: 8px; }
QPushButton[variant="quiet"]:hover { background: #e8f5fc; color: #252525; }
QPushButton[variant="nav"] { text-align: left; background: transparent; border: none; padding: 8px 10px; border-radius: 6px; color: #3a3a3c; }
QPushButton[variant="nav"]:checked { background: #9ae2ff; color: #252525; }
QPushButton[variant="nav"]:hover { background: #e0e0e5; }
QPushButton[variant="nav"]:checked:hover { background: #b6eaff; }
QPushButton[variant="danger"] { color: #923333; }
QPushButton#account { text-align: left; background: transparent; border: none; padding: 8px 10px; color: #3a3a3c; }
QPushButton#account:hover { background: #e0e0e5; }
QLineEdit, QComboBox { border: 1px solid #d2d2d7; background: #ffffff; border-radius: 6px; padding: 6px 9px; selection-background-color: #9ae2ff; selection-color: #252525; }
QLineEdit:focus { border: 2px solid #9ae2ff; padding: 5px 8px; }
QLineEdit:disabled { color: #999999; background: #f5f5f5; }
QCheckBox { spacing: 9px; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 2px; }
QScrollBar::handle:vertical { background: #cccccc; border-radius: 2px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QListWidget { background: #ffffff; border: none; outline: none; }
QListWidget::item { border-bottom: 1px solid #eeeeee; border-radius: 6px; padding: 12px 10px; }
QListWidget::item:selected { background: #9ae2ff; color: #252525; }
QListWidget::item:hover { background: #eef7fc; }
QListWidget::item:selected:hover { background: #b6eaff; }
QPlainTextEdit { background: #ffffff; border: 1px solid #dedee3; border-radius: 8px; padding: 10px; font-size: 12px; color: #555555; }
QListView#conversationView { background: #ffffff; border: none; outline: none; }
QSplitter::handle { background: #e8e8e8; width: 1px; }
QToolTip { background: #f7fbfd; color: #252525; border: 1px solid #d1dfe7; border-radius: 4px; padding: 5px; }
""".replace("#9ae2ff", ACCENT)
