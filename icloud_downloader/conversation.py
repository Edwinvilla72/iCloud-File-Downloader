"""A virtualized conversation view with rounded, content-sized message bubbles."""
import html
import math
from dataclasses import dataclass

from PySide6.QtCore import QAbstractListModel, QModelIndex, QPointF, QRectF, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QImage, QKeySequence, QPainter, QPen, QShortcut, QTextDocument, QTextOption
from PySide6.QtWidgets import QApplication, QAbstractItemView, QListView, QMenu, QStyledItemDelegate, QStyle

from .design import ACCENT, INK
from .messages import apple_ns_to_unix


class MessageModel(QAbstractListModel):
    def __init__(self, parent):
        super().__init__(parent)
        self.rows = []
        self.attachments = {}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if index.isValid() and role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            row = self.rows[index.row()]
            return f"{'You' if row[2] else row[3] or 'Other'}: {row[4]}" if role == Qt.ItemDataRole.AccessibleTextRole else row[4]
        return None

    def replace(self, rows, attachments):
        self.beginResetModel()
        self.rows, self.attachments = list(rows), dict(attachments)
        self.endResetModel()


@dataclass
class BubbleLayout:
    document: QTextDocument
    bubble: QRectF
    height: int
    caption: str


class MessageDelegate(QStyledItemDelegate):
    PADDING = 13
    MARGIN = 12

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.cache = {}

    def layout_for(self, index):
        width = max(80, self.view.viewport().width())
        key = (index.row(), width)
        if key in self.cache:
            return self.cache[key]
        mid, date, me, sender, text = self.view.messages.rows[index.row()]
        # Leave a clear opposite-side gutter, even when a message wraps.
        maximum = max(40, min(480, int(width * 0.78), width - 2 * self.MARGIN))
        font = QFont(self.view.font())
        font.setPixelSize(13)
        document = QTextDocument()
        document.setDefaultFont(font)
        document.setDocumentMargin(0)
        options = document.defaultTextOption()
        options.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(options)
        content = html.escape(text or "").replace('\n', '<br>')
        images = []
        for number, (src, name, thumbnail) in enumerate(self.view.messages.attachments.get(mid, [])):
            if content:
                content += '<br>'
            if src:
                url = html.escape(QUrl.fromLocalFile(src).toString(), quote=True)
                content += f'<a style="color:#286179;" href="{url}">{html.escape(name)}</a>'
                if thumbnail:
                    image = QImage.fromData(thumbnail)
                    if not image.isNull():
                        image = image.scaledToWidth(min(image.width(), maximum - 2 * self.PADDING), Qt.TransformationMode.SmoothTransformation)
                        resource = QUrl(f"message-image:{mid}:{number}")
                        images.append((resource, image))
                        content += f'<br><a href="{url}"><img src="{resource.toString()}" width="{image.width()}" height="{image.height()}"></a>'
            else:
                content += f'<span style="color:#777777;">Attachment unavailable: {html.escape(name)}</span>'
        document.setHtml(f'<span style="color:{INK};">{content or "<i>Attachment or system message</i>"}</span>')
        for resource, image in images:
            document.addResource(QTextDocument.ResourceType.ImageResource, resource, image)
        if images:
            document.markContentsDirty(0, document.characterCount())
        document.setTextWidth(maximum - 2 * self.PADDING)
        bubble_width = min(maximum, max(42, math.ceil(document.idealWidth()) + 2 * self.PADDING))
        document.setTextWidth(bubble_width - 2 * self.PADDING)
        bubble_height = math.ceil(document.size().height()) + 2 * self.PADDING - 4
        x = width - self.MARGIN - bubble_width if me else self.MARGIN
        bubble = QRectF(x, 8, bubble_width, bubble_height)
        dt = apple_ns_to_unix(date)
        stamp = dt.strftime("%b %d, %H:%M UTC") if dt else ""
        caption = stamp if me else f"{sender or 'Other'} · {stamp}".rstrip(' ·')
        result = BubbleLayout(document, bubble, math.ceil(bubble.bottom()) + 25, caption)
        self.cache[key] = result
        return result

    def sizeHint(self, option, index):
        return QSize(self.view.viewport().width(), self.layout_for(index).height)

    def paint(self, painter, option, index):
        layout = self.layout_for(index)
        me = self.view.messages.rows[index.row()][2]
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.translate(option.rect.topLeft())
        painter.setPen(QPen(QColor('#70b9d5'), 1) if option.state & QStyle.StateFlag.State_Selected else Qt.PenStyle.NoPen)
        painter.setBrush(QColor(ACCENT if me else '#eeeeF0'))
        painter.drawRoundedRect(layout.bubble, 16, 16)
        painter.save()
        painter.translate(layout.bubble.left() + self.PADDING, layout.bubble.top() + self.PADDING - 2)
        layout.document.drawContents(painter)
        painter.restore()
        caption_font = QFont(self.view.font())
        caption_font.setPixelSize(10)
        painter.setFont(caption_font)
        painter.setPen(QColor('#848489'))
        caption_rect = QRectF(self.MARGIN, layout.bubble.bottom() + 5,
                             self.view.viewport().width() - 2 * self.MARGIN, 15)
        alignment = Qt.AlignmentFlag.AlignRight if me else Qt.AlignmentFlag.AlignLeft
        caption = painter.fontMetrics().elidedText(layout.caption, Qt.TextElideMode.ElideRight, int(caption_rect.width()))
        painter.drawText(caption_rect, alignment | Qt.AlignmentFlag.AlignVCenter, caption)
        painter.restore()


class ConversationView(QListView):
    anchorClicked = Signal(QUrl)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('conversationView')
        self.messages = MessageModel(self)
        self.bubbles = MessageDelegate(self)
        self.placeholder = "Load conversations, then select one to read."
        self.setModel(self.messages)
        self.setItemDelegate(self.bubbles)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        copy = QShortcut(QKeySequence.StandardKey.Copy, self, activated=self.copy_message)
        copy.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def set_messages(self, rows, attachments):
        self.bubbles.cache.clear()
        self.messages.replace(rows, attachments)
        self.viewport().update()

    def show_placeholder(self, text):
        self.placeholder = text
        self.set_messages([], {})

    def document_for_row(self, row):
        return self.bubbles.layout_for(self.messages.index(row)).document

    def toPlainText(self):
        return '\n'.join(self.document_for_row(row).toPlainText() for row in range(self.messages.rowCount()))

    def resizeEvent(self, event):
        self.bubbles.cache.clear()
        super().resizeEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self.messages.rows:
            painter = QPainter(self.viewport())
            painter.setPen(QColor('#6b6b6b'))
            painter.drawText(self.viewport().rect().adjusted(12, 16, -12, -12),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                             self.placeholder)
            painter.end()

    def _anchor_at(self, point):
        index = self.indexAt(point)
        if not index.isValid():
            return ''
        layout = self.bubbles.layout_for(index)
        local = QPointF(point - self.visualRect(index).topLeft())
        local -= layout.bubble.topLeft() + QPointF(self.bubbles.PADDING, self.bubbles.PADDING - 2)
        return layout.document.documentLayout().anchorAt(local)

    def mouseMoveEvent(self, event):
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor if self._anchor_at(event.position().toPoint()) else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            anchor = self._anchor_at(event.position().toPoint())
            if anchor:
                self.anchorClicked.emit(QUrl(anchor))

    def copy_message(self):
        index = self.currentIndex()
        if index.isValid():
            QApplication.clipboard().setText(self.document_for_row(index.row()).toPlainText())

    def _context_menu(self, point):
        index = self.indexAt(point)
        if index.isValid():
            self.setCurrentIndex(index)
            menu = QMenu(self)
            menu.addAction("Copy Message", self.copy_message)
            menu.exec(self.viewport().mapToGlobal(point))
