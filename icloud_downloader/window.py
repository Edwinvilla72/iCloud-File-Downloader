"""Qt desktop presentation. Workers return data; only the GUI thread touches widgets."""
import platform
import threading
import copy
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import (QObject, QRunnable, QSettings, QSize, Qt, QThreadPool,
                            QTimer, QUrl, Signal, Slot, QStandardPaths)
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QDialogButtonBox,
    QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QScrollArea, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget)

from . import APP_NAME
from .design import INK, MUTED, STYLE, icon
from .conversation import ConversationView
from .messages import MessagesStore
from .services import TransferResult, download_library


def label(text, role=None, wrap=False):
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    if role:
        result.setProperty("role", role)
    result.setWordWrap(wrap)
    return result


def button(text, callback=None, name=None, variant=None):
    result = QPushButton(text.replace("&", "&&"))
    result.setCursor(Qt.CursorShape.PointingHandCursor)
    if name:
        result.setIcon(icon(name, INK if variant == "primary" else MUTED, 18))
        result.setIconSize(QSize(18, 18))
    if variant:
        result.setProperty("variant", variant)
    if callback:
        result.clicked.connect(callback)
    return result


def card():
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(16)
    return frame, layout


def line():
    result = QFrame()
    result.setObjectName("line")
    result.setFixedHeight(1)
    return result


def readable_bytes(value):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{value} B"
        value /= 1024


class WorkerSignals(QObject):
    result = Signal(str, object)
    error = Signal(str, str)
    progress = Signal(str, str, object)


class Worker(QRunnable):
    def __init__(self, key, work):
        super().__init__()
        self.key, self.work = key, work
        self.signals = WorkerSignals()
        self.cancel = threading.Event()

    def run(self):
        try:
            result = self.work(lambda text, data=None: self.signals.progress.emit(self.key, text, copy.copy(data)), self.cancel)
            self.signals.result.emit(self.key, result)
        except Exception as error:
            self.signals.error.emit(self.key, str(error))


class AccountDialog(QDialog):
    def __init__(self, parent, email=""):
        super().__init__(parent)
        self.setWindowTitle("Connect your Apple Account")
        self.setMinimumWidth(430)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)
        layout.addWidget(label("Connect Apple Account", "heading"))
        layout.addWidget(label("Sign in to download Photos and Drive. Messages on this Mac work without an account.", "muted", True))
        layout.addWidget(label("Apple Account email", "small"))
        self.email = QLineEdit(email)
        self.email.setPlaceholderText("you@example.com")
        self.email.setAccessibleName("Apple Account email")
        layout.addWidget(self.email)
        layout.addWidget(label("Password", "small"))
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setAccessibleName("Apple Account password")
        layout.addWidget(self.password)
        layout.addWidget(label("Your password is used for this sign-in and is never saved by this application. Authentication cookies are kept locally by pyicloud.", "small", True))
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        connect = controls.addButton("Connect account", QDialogButtonBox.ButtonRole.AcceptRole)
        connect.setProperty("variant", "primary")
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        layout.addWidget(controls)
        self.password.returnPressed.connect(self.accept)


class MainWindow(QMainWindow):
    PAGES = ("Overview", "Photos & videos", "iCloud Drive", "Messages", "Transfers", "Preferences")

    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.api = None
        self.pending_api = None
        self.jobs = {}
        self.saved_count = 0
        self.saved_bytes = 0
        self.chat_id = None
        self.loaded_messages = 0
        self.total_messages = 0
        self.message_rows = []
        self.message_attachments = {}
        self.settings = QSettings("iCloud File Downloader", "iCloud_aio_tool")
        default = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)) / "iCloud Downloads"
        self.destination = str(default) if demo else self.settings.value("destination", str(default))
        self.store = MessagesStore()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.setWindowTitle(APP_NAME + (" — Preview" if demo else ""))
        self.setWindowIcon(icon("cloud", INK, 64))
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1280, available.width() - 40), min(900, available.height() - 60))
        self.setMinimumSize(900, 620)
        self.setStyleSheet(STYLE)
        self.location_labels = []
        self._build()
        if not demo:
            geometry = self.settings.value("geometry")
            if geometry:
                self.restoreGeometry(geometry)
        QShortcut(QKeySequence("Ctrl+1"), self, activated=lambda: self.navigate(0))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self.navigate(5))
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.choose_destination)
        self.navigate(0)

    def _build(self):
        host = QWidget()
        self.setCentralWidget(host)
        outer = QHBoxLayout(host)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)
        rail = QVBoxLayout(sidebar)
        rail.setContentsMargins(12, 22, 12, 16)
        rail.setSpacing(4)
        title = label("iCloud File\nDownloading Tool")
        title.setStyleSheet("font-size: 13px; font-weight: 600; padding: 0 10px 18px;")
        rail.addWidget(title)
        self.nav_buttons = []
        for index, name in enumerate(self.PAGES):
            if index == 4:
                rail.addSpacing(20)
            nav = button(name, lambda checked=False, i=index: self.navigate(i), variant="nav")
            nav.setCheckable(True)
            rail.addWidget(nav)
            self.nav_buttons.append(nav)
        rail.addStretch()
        self.account_button = button("Connect account", self.connect_account)
        self.account_button.setObjectName("account")
        rail.addWidget(self.account_button)
        outer.addWidget(sidebar)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self._overview()
        self._library_page("photos")
        self._library_page("drive")
        self._messages_page()
        self._transfers_page()
        self._preferences_page()

    def _page(self, title, subtitle, scrolling=True):
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(22)
        heading = QHBoxLayout()
        text = QVBoxLayout()
        text.setSpacing(6)
        text.addWidget(label(title, "title"))
        if subtitle:
            text.addWidget(label(subtitle, "muted", True))
        heading.addLayout(text, 1)
        layout.addLayout(heading)
        if scrolling:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(content)
            self.stack.addWidget(scroll)
        else:
            self.stack.addWidget(content)
        return layout, heading

    def _destination_row(self, layout):
        row = QHBoxLayout()
        copy = QVBoxLayout()
        copy.setSpacing(5)
        copy.addWidget(label("Download folder", "heading"))
        path = label(self._short_destination(), "muted", True)
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.location_labels.append(path)
        copy.addWidget(path)
        row.addLayout(copy, 1)
        row.addWidget(button("Choose Folder…", self.choose_destination))
        layout.addLayout(row)

    def _overview(self):
        layout, heading = self._page(APP_NAME, "")
        if self.demo:
            layout.addWidget(label("Preview — sample data", "small"))
        folder, folder_layout = card()
        self._destination_row(folder_layout)
        layout.addWidget(folder)
        group, group_layout = card()
        for title, description, index in (
            ("Photos & videos", "Download original files, organized by month.", 1),
            ("iCloud Drive", "Download files and keep the folder structure.", 2),
            ("Messages", "View and export conversations stored on a Mac.", 3),
        ):
            row = QHBoxLayout()
            copy = QVBoxLayout()
            copy.setSpacing(7)
            copy.addWidget(label(title, "heading"))
            copy.addWidget(label(description, "muted", True))
            row.addLayout(copy, 1)
            row.addWidget(button("Open", lambda checked=False, i=index: self.navigate(i)))
            group_layout.addLayout(row)
            if index < 3:
                group_layout.addWidget(line())
        layout.addWidget(group)
        layout.addStretch()

    def _library_page(self, kind):
        photo = kind == "photos"
        layout, heading = self._page("Photos & videos" if photo else "iCloud Drive",
            "Download the original photos and videos from your iCloud library." if photo
            else "Download your iCloud Drive files with their folder structure.")
        group, content = card()
        self._destination_row(content)
        content.addWidget(line())
        content.addWidget(label("Photos and videos are saved in Photos / YYYY-MM." if photo
                               else "Files are saved in iCloud Drive Files / your folders.", "muted", True))
        content.addWidget(button("Download all photos & videos" if photo else "Download all Drive files",
                               lambda: self.start_download(kind), variant="primary"),
                         alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(group)
        layout.addStretch()

    def _messages_page(self):
        layout, heading = self._page("Messages", "View and export conversations stored on this Mac.", scrolling=False)
        self.load_chats_button = button("Load conversations", self.load_chats, "refresh")
        heading.addWidget(self.load_chats_button)
        available = platform.system() == "Darwin" or self.demo
        self.load_chats_button.setEnabled(available)
        if not available:
            note = label("Messages uses the database maintained by the macOS Messages app. Photos and Drive work on Windows; local Messages access requires a Mac.", "muted", True)
            layout.addWidget(note)
        self.messages_note = label("Full Disk Access may be required. An iCloud sign-in is not needed.", "small", True)
        layout.addWidget(self.messages_note)
        panel = QFrame()
        panel.setObjectName("messagePanel")
        split_layout = QHBoxLayout(panel)
        split_layout.setContentsMargins(0, 0, 0, 0)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left.setMinimumWidth(230)
        conversations = QVBoxLayout(left)
        conversations.setContentsMargins(16, 17, 12, 12)
        conversations.setSpacing(13)
        self.chat_search = QLineEdit()
        self.chat_search.setPlaceholderText("Search conversations")
        self.chat_search.setAccessibleName("Search conversations")
        self.chat_search.addAction(icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.chat_search.textChanged.connect(self.filter_chats)
        conversations.addWidget(self.chat_search)
        self.chat_list = QListWidget()
        self.chat_list.setAccessibleName("Conversations")
        self.chat_list.currentItemChanged.connect(self.select_chat)
        conversations.addWidget(self.chat_list, 1)
        self.splitter.addWidget(left)
        right = QWidget()
        conversation = QVBoxLayout(right)
        conversation.setContentsMargins(20, 18, 20, 14)
        conversation.setSpacing(14)
        toolbar = QHBoxLayout()
        self.chat_title = label("Conversations", "heading")
        toolbar.addWidget(self.chat_title, 1)
        self.export_chat_button = button("Export chat", self.export_chat, "download")
        self.export_chat_button.setEnabled(False)
        toolbar.addWidget(self.export_chat_button)
        conversation.addLayout(toolbar)
        conversation.addWidget(line())
        self.message_view = ConversationView()
        self.message_view.anchorClicked.connect(self.open_attachment)
        self.message_view.setAccessibleName("Conversation messages")
        self.message_view.show_placeholder(self._empty_conversation())
        conversation.addWidget(self.message_view, 1)
        bottom = QHBoxLayout()
        self.messages_count = label("Select a conversation.", "small")
        bottom.addWidget(self.messages_count, 1)
        self.more_button = button("Load older", self.load_more, "refresh", "quiet")
        self.more_button.setEnabled(False)
        bottom.addWidget(self.more_button)
        conversation.addLayout(bottom)
        self.splitter.addWidget(right)
        self.splitter.setSizes([270, 650])
        split_layout.addWidget(self.splitter)
        layout.addWidget(panel, 1)
        if self.demo:
            self._demo_chats()

    def _transfers_page(self):
        layout, heading = self._page("Transfers", "")
        self.stop_button = button("Stop transfer", self.stop_transfer)
        self.stop_button.setVisible(False)
        heading.addWidget(self.stop_button)
        self.transfer_title = label("", "heading")
        self.transfer_detail = label("", "muted", True)
        self.transfer_summary = label("", "small")
        layout.addWidget(self.transfer_title)
        layout.addWidget(self.transfer_detail)
        layout.addWidget(self.transfer_summary)
        self.activity_log = QPlainTextEdit()
        self.activity_log.setReadOnly(True)
        self.activity_log.setMaximumBlockCount(2000)
        self.activity_log.setMinimumHeight(240)
        self.activity_log.setPlaceholderText("No transfers in this session.")
        layout.addWidget(self.activity_log, 1)
        if self.demo:
            self.activity_log.setPlainText("Preview — sample activity\n09:41  Saved 128 photos and videos\n09:42  Exported conversation")

    def _preferences_page(self):
        layout, heading = self._page("Preferences", "")
        frame, inside = card()
        inside.addWidget(label("Download location", "heading"))
        inside.addWidget(label("Photos, Drive files, and exported conversations each get their own folder.", "muted", True))
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit(self.destination)
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setAccessibleName("Download destination")
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(button("Choose folder", self.choose_destination, "folder"))
        inside.addLayout(folder_row)
        inside.addWidget(button("Open folder", self.open_destination, "external", "quiet"), alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(frame)
        frame, inside = card()
        inside.addWidget(label("Cloud originals", "heading"))
        inside.addWidget(label("By default, downloads leave everything in iCloud. Optional deletion applies only to new Photos and Drive transfers.", "muted", True))
        self.delete_option = QCheckBox("Delete cloud originals after downloading")
        self.delete_option.setChecked(False)
        inside.addWidget(self.delete_option)
        inside.addWidget(label("Confirmation is required for each transfer. This setting resets when the application closes.", "small", True))
        layout.addWidget(frame)
        frame, inside = card()
        row = QHBoxLayout()
        text = QVBoxLayout()
        text.addWidget(label("Your Apple Account", "heading"))
        self.account_detail = label("Not connected. Your local Messages library is still available on a Mac.", "muted", True)
        text.addWidget(self.account_detail)
        row.addLayout(text, 1)
        row.addWidget(button("Manage account", self.connect_account, "arrow"))
        inside.addLayout(row)
        layout.addWidget(frame)
        layout.addStretch()

    def navigate(self, index):
        self.stack.setCurrentIndex(index)
        for i, nav in enumerate(self.nav_buttons):
            nav.setChecked(i == index)

    def _short_destination(self):
        path = Path(self.destination)
        try:
            return "~/" + str(path.relative_to(Path.home()))
        except ValueError:
            return str(path)

    def choose_destination(self):
        if self.demo:
            self.preview_notice()
            return
        selected = QFileDialog.getExistingDirectory(self, "Choose download folder", self.destination)
        if selected:
            self.destination = selected
            self.settings.setValue("destination", selected)
            for location in self.location_labels:
                location.setText(self._short_destination())
            self.folder_edit.setText(selected)

    def open_destination(self):
        path = Path(self.destination)
        if self.demo:
            self.preview_notice()
        elif path.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.info("Your download location", "This folder will be created with your first download. You can choose an existing folder in Preferences.")

    def info(self, title, text):
        QMessageBox.information(self, title, text)

    def preview_notice(self):
        self.info("Preview", "This preview uses sample data. Run without --demo to use your account and files.")

    def _log(self, text):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.activity_log.appendPlainText(f"{stamp}   {text}")

    def _run(self, key, work, done):
        if key in self.jobs:
            return False
        worker = Worker(key, work)
        self.jobs[key] = (worker, done)
        worker.signals.result.connect(self._success, Qt.ConnectionType.QueuedConnection)
        worker.signals.error.connect(self._failure, Qt.ConnectionType.QueuedConnection)
        worker.signals.progress.connect(self._progress, Qt.ConnectionType.QueuedConnection)
        self.pool.start(worker)
        self._update_busy()
        return True

    @Slot(str, object)
    def _success(self, key, result):
        job = self.jobs.pop(key, None)
        self._update_busy()
        if job:
            try:
                job[1](result)
            except Exception as error:
                self._failure(key, str(error))

    @Slot(str, str)
    def _failure(self, key, text):
        self.jobs.pop(key, None)
        self._update_busy()
        if key == "cloud":
            self.transfer_title.setText("Transfer stopped" if text.startswith("Transfer stopped") else "Transfer failed")
            self.transfer_detail.setText(text)
            if not self.api:
                self.pending_api = None
                self.account_button.setText("Connect account")
        if key == "messages":
            self.messages_note.setText("Could not finish loading. You can try again.")
        if "unable to open database" in text.lower() or "authorization denied" in text.lower() or "permission" in text.lower():
            text += "\n\nOn macOS, grant Full Disk Access to Terminal, your IDE, or the packaged application, then quit and relaunch it."
        self._log(text)
        if not text.startswith("Transfer stopped"):
            QMessageBox.warning(self, "Error", text)

    @Slot(str, str, object)
    def _progress(self, key, text, data):
        self._log(text)
        if key == "cloud":
            self.transfer_detail.setText(text)
            if isinstance(data, TransferResult):
                self.transfer_summary.setText(f"{self.saved_count + data.saved} files saved, {readable_bytes(self.saved_bytes + data.bytes_saved)}")

    def _update_busy(self):
        messages_busy = "messages" in self.jobs
        self.load_chats_button.setEnabled(not messages_busy and (platform.system() == "Darwin" or self.demo))
        self.chat_list.setEnabled(not messages_busy)
        self.more_button.setEnabled(not messages_busy and self.chat_id is not None and self.loaded_messages < self.total_messages)
        self.export_chat_button.setEnabled(not messages_busy and self.chat_id is not None)
        self.account_button.setEnabled("cloud" not in self.jobs)
        self.stop_button.setVisible("cloud" in self.jobs and self.api is not None)
        self.stop_button.setEnabled("cloud" in self.jobs and self.api is not None)

    def connect_account(self):
        if self.demo:
            self.preview_notice()
            return
        if "cloud" in self.jobs:
            self.navigate(4)
            return
        if self.api:
            answer = QMessageBox.question(self, "Account connected", "Disconnect this session? Previously downloaded files and local authentication cookies will stay on this computer.")
            if answer == QMessageBox.StandardButton.Yes:
                self.api = None
                self.account_button.setText("Connect account")
                self.account_detail.setText("Not connected. Local Messages can still be used on a Mac.")
            return
        dialog = AccountDialog(self, self.settings.value("email", ""))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        email, password = dialog.email.text().strip(), dialog.password.text()
        dialog.password.clear()
        dialog.deleteLater()
        if not email or not password:
            self.info("Sign in", "Enter your Apple Account email and password.")
            return
        self.settings.setValue("email", email)
        self.account_button.setText("Connecting…")
        self._log("Connecting to Apple…")

        def work(report, cancel):
            from pyicloud import PyiCloudService
            return PyiCloudService(email, password)

        self._run("cloud", work, self._authenticated)

    def _authenticated(self, api):
        if api.requires_2fa:
            self.pending_api = api
            self.account_button.setText("Verification required")
            # Request and validate outside the GUI thread too.
            self._run("cloud", lambda report, cancel: api.request_2fa_code(), self._ask_code)
        elif getattr(api, "requires_2sa", False):
            self.pending_api = None
            self._failure("cloud", "This account requires legacy two-step authentication, which the application does not support yet.")
        else:
            self.api = api
            self.pending_api = None
            email = self.settings.value("email", "Connected")
            self.account_button.setText("Account connected")
            self.account_button.setToolTip(email)
            self.account_detail.setText(f"Connected as {email}")
            self._log("Your iCloud account is connected.")

    def _ask_code(self, requested):
        if not requested:
            self.pending_api = None
            self._failure("cloud", "Apple could not send a verification code. This account may require a security key or another verification method.")
            return
        code, accepted = QInputDialog.getText(self, "Verification code", "Enter the verification code from your trusted Apple device or SMS:")
        if not accepted or not code.strip():
            self.pending_api = None
            self.account_button.setText("Connect account")
            return
        api = self.pending_api

        def verify(report, cancel):
            if not api.validate_2fa_code(code.strip()):
                raise RuntimeError("Apple rejected that verification code. Please connect again.")
            if not api.is_trusted_session:
                api.trust_session()
            return api

        self._run("cloud", verify, self._authenticated)

    def start_download(self, kind):
        if self.demo:
            self.preview_notice()
            return
        if "cloud" in self.jobs:
            self.navigate(4)
            return
        if not self.api:
            self.connect_account()
            return
        delete = self.delete_option.isChecked()
        if delete:
            answer = QMessageBox.warning(self, "Download and delete cloud originals?",
                "Each original will be deleted from iCloud after its download is saved. Deletions can sync to other devices.\n\nDo you want to continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
            if answer != QMessageBox.StandardButton.Yes:
                return
        destination, api = self.destination, self.api
        self.navigate(4)
        self.transfer_title.setText("Downloading photos & videos" if kind == "photos" else "Downloading iCloud Drive files")
        self.transfer_detail.setText("Connecting to iCloud…")
        self._run("cloud", lambda report, cancel: download_library(api, kind, destination, cancel, report, delete), self._downloaded)

    def _downloaded(self, result):
        self.saved_count += result.saved
        self.saved_bytes += result.bytes_saved
        self.transfer_summary.setText(f"{self.saved_count} files saved, {readable_bytes(self.saved_bytes)} this session")
        self.transfer_title.setText("Transfer stopped. Completed files are kept." if result.cancelled else "Download complete" if not result.failed else "Download finished with errors")
        detail = f"{result.saved} files saved · {readable_bytes(result.bytes_saved)} · {result.failed} errors"
        self.transfer_detail.setText(detail)
        self._log(detail)

    def stop_transfer(self):
        if "cloud" in self.jobs:
            self.jobs["cloud"][0].cancel.set()
            self.stop_button.setEnabled(False)
            self.transfer_detail.setText("Stopping after the current network request… Completed files will be kept.")

    @staticmethod
    def _empty_conversation():
        return "Load conversations, then select one to read."

    def load_chats(self):
        if self.demo:
            self._demo_chats()
            return
        self.messages_note.setText("Reading a snapshot of your local Messages library…")
        self._run("messages", lambda report, cancel: self.store.chats(), self._chats_loaded)

    def _chats_loaded(self, chats):
        self.chat_list.blockSignals(True)
        self.chat_list.clear()
        self.chat_id = None
        self.message_rows = []
        self.loaded_messages = self.total_messages = 0
        self.message_view.show_placeholder(self._empty_conversation())
        for rowid, name, identifier in chats:
            item = QListWidgetItem(f"{name}\n{identifier or 'Conversation'}")
            item.setData(Qt.ItemDataRole.UserRole, rowid)
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            self.chat_list.addItem(item)
        self.chat_list.blockSignals(False)
        self.filter_chats(self.chat_search.text())
        self.messages_note.setText(f"{len(chats)} conversations · Local snapshot · Refresh to include new messages")
        self._update_busy()
        self._log(f"Loaded {len(chats)} conversations.")

    def filter_chats(self, query):
        for index in range(self.chat_list.count()):
            item = self.chat_list.item(index)
            item.setHidden(query.casefold() not in item.text().casefold())

    def select_chat(self, item, previous=None):
        if item is None or "messages" in self.jobs:
            return
        self.chat_id = item.data(Qt.ItemDataRole.UserRole)
        self.chat_title.setText(item.data(Qt.ItemDataRole.UserRole + 1))
        self.loaded_messages = 0
        self.message_rows = []
        self.message_attachments = {}
        if self.demo:
            self._demo_conversation()
        else:
            self.message_view.show_placeholder("Loading conversation…")
            self._fetch_page()

    def _fetch_page(self):
        chat_id, offset = self.chat_id, self.loaded_messages
        self._run("messages", lambda report, cancel: self.store.page(chat_id, offset, 100), self._page_loaded)

    def _page_loaded(self, result):
        total, rows, attachments = result
        self.total_messages = total
        self.loaded_messages += len(rows)
        self.message_rows = rows + self.message_rows
        self.message_attachments.update(attachments)
        self._render_conversation()
        self._update_busy()

    def _render_conversation(self):
        self.message_view.set_messages(self.message_rows, self.message_attachments)
        self.messages_count.setText(f"{self.loaded_messages:,} of {self.total_messages:,} messages · UTC")
        QTimer.singleShot(0, self.message_view.scrollToBottom if self.loaded_messages <= 100
                          else self.message_view.scrollToTop)

    def load_more(self):
        if self.demo:
            self.preview_notice()
        elif self.chat_id is not None and self.loaded_messages < self.total_messages:
            self._fetch_page()

    def export_chat(self):
        if self.demo:
            self.preview_notice()
            return
        if self.chat_id is None:
            return
        chat_id, name, destination = self.chat_id, self.chat_title.text(), self.destination
        self.messages_note.setText("Exporting this conversation and locally available attachments…")

        def done(path):
            self.messages_note.setText(f"Exported to {path.parent}")
            self._log(f"Conversation exported · {name}")

        self._run("messages", lambda report, cancel: self.store._export_chat_by_rowid(chat_id, name + f" [#{chat_id}]", destination, log=report), done)

    def open_attachment(self, url):
        # The document creates only local attachment links, never network links.
        if url.isLocalFile():
            QDesktopServices.openUrl(url)

    def _demo_chats(self):
        self.chat_list.blockSignals(True)
        self.chat_list.clear()
        for index, (name, preview) in enumerate((("Sample conversation", "Thank you."), ("Alex Morgan", "I sent the files."), ("Family", "Dinner at six?"), ("Jamie Chen", "See you tomorrow."))):
            item = QListWidgetItem(f"{name}\n{preview}")
            item.setData(Qt.ItemDataRole.UserRole, index + 1)
            item.setData(Qt.ItemDataRole.UserRole + 1, name)
            self.chat_list.addItem(item)
        self.chat_list.blockSignals(False)
        self.chat_list.setCurrentRow(0)
        self.messages_note.setText("Preview — sample conversations")

    def _demo_conversation(self):
        content = [(0, "Alex", "Can you send the files?"), (1, "You", "Yes, I will send them this afternoon."), (0, "Alex", "Thank you.")]
        self.message_rows = [(index, 800000000 + index * 120, me, sender, text) for index, (me, sender, text) in enumerate(content)]
        self.loaded_messages = self.total_messages = len(content)
        self._render_conversation()
        self.export_chat_button.setEnabled(True)

    def closeEvent(self, event):
        if self.jobs:
            self.info("Task running", "A task is still running. Stop the transfer and wait for it to finish before closing the application.")
            event.ignore()
            return
        if not self.demo:
            self.settings.setValue("geometry", self.saveGeometry())
        self.store.close()
        event.accept()
