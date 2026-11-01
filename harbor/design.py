"""Shared visual tokens, vector icons, and a resolution-independent illustration."""
from PySide6.QtCore import QByteArray, QRectF, Qt, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QLinearGradient
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

BLUE = "#4564ed"
INK = "#202b46"
MUTED = "#7a8499"

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
QMainWindow, QDialog { background: #f6f7fb; }
QWidget { color: #202b46; font-size: 13px; }
QLabel { background: transparent; border: none; }
QLabel[role="muted"] { color: #7a8499; }
QLabel[role="eyebrow"] { color: #8790a2; font-size: 10px; font-weight: 600; letter-spacing: 1.6px; }
QLabel[role="title"] { font-size: 30px; font-weight: 700; letter-spacing: -1px; }
QLabel[role="heading"] { font-size: 17px; font-weight: 600; }
QLabel[role="small"] { color: #7a8499; font-size: 11px; }
QLabel[role="metric"] { font-size: 30px; font-weight: 600; letter-spacing: -1px; }
QFrame#sidebar { background: #ffffff; border-right: 1px solid #e9ecf3; }
QFrame#card, QFrame#messagePanel { background: #ffffff; border: 1px solid #e7eaf2; border-radius: 14px; }
QFrame#hero { background: #eaf0ff; border: 1px solid #e1e8ff; border-radius: 18px; }
QFrame#line { background: #edf0f5; max-height: 1px; border: 0; }
QFrame#banner { background: #eef2ff; border: 1px solid #dfe6ff; border-radius: 10px; }
QPushButton { background: white; border: 1px solid #dfe4ed; border-radius: 8px; padding: 10px 15px; font-weight: 500; }
QPushButton:hover { background: #f3f5fb; border-color: #bdc9ed; }
QPushButton:pressed { background: #e6ebfb; }
QPushButton:disabled { color: #a1a9ba; background: #eef0f5; border-color: #e4e8f0; }
QPushButton[variant="primary"] { background: #4564ed; color: white; border: 1px solid #4564ed; }
QPushButton[variant="primary"]:hover { background: #3553db; border-color: #3553db; }
QPushButton[variant="primary"]:disabled { background: #aab8f5; border-color: #aab8f5; color: #f6f7ff; }
QPushButton[variant="quiet"] { background: transparent; border: none; color: #65718b; }
QPushButton[variant="quiet"]:hover { background: #eef2fa; color: #4564ed; }
QPushButton[variant="nav"] { text-align: left; background: transparent; border: none; padding: 12px 15px; color: #748098; border-radius: 9px; }
QPushButton[variant="nav"]:checked { background: #edf1ff; color: #4564ed; font-weight: 600; }
QPushButton[variant="nav"]:hover { background: #f3f5fb; }
QPushButton[variant="nav"]:checked:hover { background: #e7edff; }
QPushButton[variant="danger"] { color: #c24f61; background: #fff5f6; border-color: #f2dce0; }
QPushButton#account { text-align: left; border: none; background: #f6f7fb; padding: 13px; border-radius: 10px; }
QLineEdit, QComboBox { border: 1px solid #dfe4ed; background: #fff; border-radius: 8px; padding: 11px 12px; selection-background-color: #4564ed; }
QLineEdit:focus { border-color: #6c83ef; }
QLineEdit:disabled { color: #a1a9ba; background: #f1f3f8; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 17px; height: 17px; border-radius: 5px; border: 1px solid #cbd3e2; background: white; }
QCheckBox::indicator:checked { background: #4564ed; border: 4px solid #bfccff; }
QScrollArea { border: 0; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 1px; }
QScrollBar::handle:vertical { background: #d1d8e5; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { background: #e9edf7; border: 0; border-radius: 3px; height: 6px; text-align: center; }
QProgressBar::chunk { background: #5473f2; border-radius: 3px; }
QListWidget { background: white; border: none; outline: none; }
QListWidget::item { border-bottom: 1px solid #f0f2f7; padding: 16px 12px; border-radius: 6px; }
QListWidget::item:selected { background: #edf1ff; color: #4564ed; }
QListWidget::item:hover { background: #f5f7fc; }
QPlainTextEdit { background: #fff; border: 1px solid #e5e9f1; border-radius: 10px; padding: 12px; font-size: 12px; color: #65718b; }
QTextBrowser { background: white; border: none; padding: 16px; selection-background-color: #cad5ff; }
QSplitter::handle { background: #e9edf5; width: 1px; }
QToolTip { background: #202b46; color: white; border: none; padding: 7px; }
"""


class CloudIllustration(QWidget):
    """Decorative vector art painted by Qt; sharp at every display scale."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(310, 220)
        self.setMaximumWidth(440)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.translate(self.width() / 2 - 170, self.height() / 2 - 115)
        p.setPen(QPen(QColor("#d9e3ff"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        for size in (175, 240, 310):
            p.drawEllipse(QRectF(172-size/2, 112-size/2, size, size))
        # A small stack of prints, landscape and file, with soft shadows.
        p.save()
        p.translate(45, 75)
        p.rotate(-13)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#d0dbf7"))
        p.drawRoundedRect(QRectF(2, 6, 108, 124), 10, 10)
        p.setBrush(QColor("white"))
        p.drawRoundedRect(QRectF(0, 0, 108, 124), 10, 10)
        gradient = QLinearGradient(0, 8, 0, 105)
        gradient.setColorAt(0, QColor("#b8d7ef"))
        gradient.setColorAt(1, QColor("#e1eadc"))
        p.setBrush(gradient)
        p.drawRoundedRect(QRectF(8, 8, 92, 94), 5, 5)
        p.setBrush(QColor("#fff0c9"))
        p.drawEllipse(QRectF(62, 23, 18, 18))
        path = QPainterPath()
        path.moveTo(8, 85); path.lineTo(36, 48); path.lineTo(68, 84); path.lineTo(83, 65); path.lineTo(100, 85); path.lineTo(100, 102); path.lineTo(8, 102)
        p.setBrush(QColor("#89a99a")); p.drawPath(path)
        p.restore()
        p.save()
        p.translate(224, 54); p.rotate(12)
        p.setBrush(QColor("#d4dffa")); p.drawRoundedRect(QRectF(2, 6, 83, 107), 10, 10)
        p.setBrush(QColor("white")); p.drawRoundedRect(QRectF(0, 0, 83, 107), 10, 10)
        p.setBrush(QColor("#e9e4ff")); p.drawRoundedRect(QRectF(13, 14, 31, 34), 5, 5)
        p.setPen(QPen(QColor("#b6a1f1"), 2)); p.drawLine(21, 25, 36, 25); p.drawLine(21, 32, 32, 32)
        p.setPen(QPen(QColor("#dde3f0"), 4))
        for y, width in ((64, 53), (76, 40), (88, 46)):
            p.drawLine(14, y, 14+width, y)
        p.restore()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#c8d5fa")); p.drawRoundedRect(QRectF(111, 58, 127, 127), 34, 34)
        gradient = QLinearGradient(110, 45, 240, 178)
        gradient.setColorAt(0, QColor("#7d9bff")); gradient.setColorAt(1, QColor("#4564ed"))
        p.setBrush(gradient); p.drawRoundedRect(QRectF(111, 48, 127, 127), 34, 34)
        cloud = QPainterPath()
        cloud.moveTo(148, 133)
        cloud.cubicTo(128, 130, 132, 108, 148, 108)
        cloud.cubicTo(150, 81, 187, 80, 194, 106)
        cloud.cubicTo(217, 105, 219, 134, 197, 134)
        cloud.closeSubpath()
        p.setBrush(QColor("white")); p.drawPath(cloud)
        p.setBrush(QColor("white")); p.drawEllipse(QRectF(226, 158, 37, 37))
        p.setPen(QPen(QColor("#9ae2ff"), 2.5)); p.drawLine(237, 176, 243, 182); p.drawLine(243, 182, 253, 170)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor("#a4b8f7"))
        p.drawEllipse(QRectF(79, 39, 6, 6)); p.drawEllipse(QRectF(288, 183, 5, 5))
        p.end()
