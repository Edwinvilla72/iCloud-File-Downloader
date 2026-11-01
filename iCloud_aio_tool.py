"""
iCloud Data Manager
-------------------
Tabs:
- Login (Apple ID + iCloud login via pyicloud, download folder selection, delete-after-download toggle)
- Photos (Download all photos & videos, organized by YYYY-MM)
- Drive (Download all iCloud Drive files preserving folder structure)
- Emails (IMAP: save .eml + extract attachments)
- Backups (device list + OS-specific instructions)
- Messages (macOS only: export + in-app viewer with thumbnails, 100 recent + Load More)

Dependencies:
    pip install pyicloud requests pandas pillow pytypedstream
"""

import os
import re
import sys
import shutil
import sqlite3
import platform
import threading
import subprocess
import queue
import tempfile
import time
from contextlib import closing
from datetime import datetime
from pathlib import Path
from tkinter import Tk, StringVar, BooleanVar, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
from tkinter import Canvas, Frame, Label


class _WindowedStream:
    def write(self, *_args, **_kwargs):
        return 0

    def flush(self):
        return None

    def isatty(self):
        return False


if sys.stdout is None:
    sys.stdout = _WindowedStream()

if sys.stderr is None:
    sys.stderr = _WindowedStream()

import requests
from pyicloud import PyiCloudService

# Email handling
import imaplib
import email
from email.header import decode_header, make_header

# CSV + thumbnails
import pandas as pd
from PIL import Image, ImageTk
try:
    import typedstream
    from typedstream.types.foundation import NSString
except ImportError:
    typedstream = None


def message_text(text, attributed_body):
    """Decode the body as a typedstream, never by slicing binary data as text."""
    if text:
        return text
    if not attributed_body:
        return ""
    if typedstream is None:
        return "[Message text unavailable: install pytypedstream]"
    try:
        body = typedstream.unarchive_from_data(bytes(attributed_body))
        # NSAttributedString's first field is its backing NSString. Ignore
        # attribute dictionaries so links and formatting never become body text.
        if body.clazz.name in (b"NSAttributedString", b"NSMutableAttributedString"):
            value = body.contents[0].values[0]
            if isinstance(value, NSString):
                return value.value
    except Exception:
        pass
    return "[Message text unavailable: unsupported attributedBody]"

# ---------------------------
# Utilities
# ---------------------------
def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "_", name)
    name = name.strip().strip(".")
    if not name:
        name = "untitled"
    if len(name) > max_len:
        name = name[:max_len].rstrip("_").rstrip(".")
    return name

def apple_ns_to_unix(ns_value: int):
    """Convert Apple's (ns or s since 2001-01-01) to datetime UTC."""
    try:
        if ns_value is None:
            return None
        if abs(ns_value) > 1e12:
            seconds = ns_value / 1_000_000_000
        else:
            seconds = ns_value
        unix_seconds = seconds + 978_307_200
        return datetime.utcfromtimestamp(unix_seconds)
    except Exception:
        return None

def is_image_file(path: Path) -> bool:
    ext = path.suffix.lower()
    return ext in {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"}  # HEIC not shown inline

# ---------------------------
# App
# ---------------------------
class iCloudDataManagerApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("iCloud Data Manager")
        self.root.geometry("980x980")

        # Core variables
        self.apple_id = StringVar()
        self.password = StringVar()
        self.download_dir = StringVar()
        self.delete_after_download = BooleanVar()
        self.api = None

        # Emails tab vars
        self.imap_app_password = StringVar()
        self.selected_mailbox = StringVar()
        self.imap = None
        self.mailboxes = []

        # Messages tab vars
        self.selected_chat_display = StringVar()
        self.chat_rows = []   # list of dicts {rowid, display, identifier}
        self.chat_map = {}    # display -> rowid
        self.messages_db_copy = None
        self.current_chat_rowid = None
        self.current_chat_display = ""
        self.current_loaded = 0       # number of messages currently displayed
        self.messages_per_page = 100
        self._thumb_refs = []         # keep PhotoImage refs alive
        self._ui_queue = queue.Queue()
        self._messages_busy = False
        self._messages_temp = tempfile.TemporaryDirectory(prefix="icloud-messages-")
        self._message_pages = []

        self.create_widgets()
        self.root.after(50, self._drain_ui_queue)

    # ---------------------------
    # UI SETUP
    # ---------------------------
    def create_widgets(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.login_frame    = ttk.Frame(notebook)
        self.photos_frame   = ttk.Frame(notebook)
        self.drive_frame    = ttk.Frame(notebook)
        self.emails_frame   = ttk.Frame(notebook)
        self.backup_frame   = ttk.Frame(notebook)
        self.messages_frame = ttk.Frame(notebook)

        notebook.add(self.login_frame,    text="Login")
        notebook.add(self.photos_frame,   text="Photos")
        notebook.add(self.drive_frame,    text="Drive")
        # notebook.add(self.emails_frame,   text="Emails")
        # notebook.add(self.backup_frame,   text="Backups")
        notebook.add(self.messages_frame, text="Messages")

        # Login Tab
        self._build_login_tab()

        # Global status log
        self.log_output = ScrolledText(self.root, height=10)
        self.log_output.pack(fill="both", expand=True, padx=10, pady=(0,10))

        # Other tabs
        self._build_photos_tab()
        self._build_drive_tab()
        # self._build_backups_tab()
        self._build_messages_tab()

    def _build_login_tab(self):
        pad = {"padx": 8, "pady": 6}
        ttk.Label(self.login_frame, text="Apple ID (email):").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(self.login_frame, textvariable=self.apple_id, width=45).grid(row=0, column=1, sticky="ew", **pad)

        ttk.Label(self.login_frame, text="iCloud Password:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(self.login_frame, textvariable=self.password, show="*", width=45).grid(row=1, column=1, sticky="ew", **pad)

        ttk.Button(self.login_frame, text="Select Download Folder", command=self.select_folder).grid(row=2, column=0, sticky="w", **pad)
        ttk.Label(self.login_frame, textvariable=self.download_dir, wraplength=420).grid(row=2, column=1, sticky="w", **pad)

        ttk.Checkbutton(self.login_frame, text="Delete after download (Photos/Drive only)",
                        variable=self.delete_after_download).grid(row=3, column=0, columnspan=2, sticky="w", **pad)

        ttk.Button(self.login_frame, text="Login to iCloud", command=self.login).grid(row=4, column=0, columnspan=2, **pad)
        self.login_frame.columnconfigure(1, weight=1)

        tip = ("2FA codes will be requested after iCloud login if required.")
        ttk.Label(self.login_frame, text=tip, foreground="#555").grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(0,10))

    def _build_photos_tab(self):
        ttk.Button(self.photos_frame, text="Download ALL Photos & Videos",
                   command=lambda: threading.Thread(target=self.download_photos, daemon=True).start()).pack(pady=14)
        ttk.Label(self.photos_frame, text="Photos/videos organized by YYYY-MM in your download folder.",
                  foreground="#555").pack()

    def _build_drive_tab(self):
        ttk.Button(self.drive_frame, text="Download ALL iCloud Drive Files",
                   command=lambda: threading.Thread(target=self.download_drive_files, daemon=True).start()).pack(pady=14)
        ttk.Label(self.drive_frame, text="Drive files mirror your iCloud Drive structure.",
                  foreground="#555").pack()


    # def _build_backups_tab(self):
    #     pad = {"padx": 8, "pady": 6}
    #     cols = ("name", "model", "backup_enabled", "last_backup")
    #     self.devices_tree = ttk.Treeview(self.backup_frame, columns=cols, show="headings", height=8)
    #     for c, w in zip(cols, (220, 140, 140, 180)):
    #         self.devices_tree.heading(c, text=c.replace("_", " ").title())
    #         self.devices_tree.column(c, width=w, anchor="w")
    #     self.devices_tree.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=8, pady=(8, 2))

    #     ttk.Button(self.backup_frame, text="Refresh Device List",
    #                command=lambda: threading.Thread(target=self.load_devices, daemon=True).start()
    #                ).grid(row=1, column=0, sticky="w", **pad)

    #     self.backup_instructions = ScrolledText(self.backup_frame, height=14)
    #     self.backup_instructions.grid(row=2, column=0, columnspan=3, sticky="nsew", padx=8, pady=(2, 8))

    #     self.backup_frame.rowconfigure(0, weight=1)
    #     self.backup_frame.rowconfigure(2, weight=1)
    #     self.backup_frame.columnconfigure(0, weight=1)

        # self.populate_backup_instructions()

    def _build_messages_tab(self):
        pad = {"padx": 8, "pady": 6}
        if platform.system() != "Darwin":
            ttk.Label(self.messages_frame, text="Messages viewer/export is available on macOS only.", foreground="#a00").grid(row=0, column=0, sticky="w", **pad)
            return

        # Top controls
        top = ttk.Frame(self.messages_frame)
        top.grid(row=0, column=0, sticky="ew", **pad)
        top.columnconfigure(3, weight=1)

        ttk.Button(top, text="Load Chats", command=self.load_chats).grid(row=0, column=0, **pad)
        ttk.Label(top, text="Select Chat:").grid(row=0, column=1, sticky="e", **pad)
        self.chat_combo = ttk.Combobox(top, textvariable=self.selected_chat_display, width=50, state="readonly", values=[])
        self.chat_combo.grid(row=0, column=2, sticky="ew", **pad)
        ttk.Button(top, text="Open", command=self.open_selected_chat).grid(row=0, column=3, sticky="w", **pad)

        mid = ttk.Frame(self.messages_frame)
        mid.grid(row=1, column=0, sticky="w", **pad)
        ttk.Button(mid, text="Load More (older 100)", command=self.load_more_messages).grid(row=0, column=0, **pad)
        ttk.Button(mid, text="Export Chat", command=self.export_selected_chat).grid(row=0, column=1, **pad)
        ttk.Button(mid, text="Open Attachments Folder", command=self.open_attachments_folder).grid(row=0, column=2, **pad)

        info = ("Viewer notes:\n"
                "• Loads the 100 most recent messages first; use 'Load More' for older messages.\n"
                "• Blue = Me, Gray = Other. Thumbnails shown for common image types.\n"
                "• Uses messages downloaded to this Mac. 'Load Chats' refreshes the snapshot.\n"
                "• Permission errors: grant Full Disk Access to the app launching this tool, then relaunch it.")
        ttk.Label(self.messages_frame, text=info, foreground="#555").grid(row=2, column=0, sticky="w", **pad)

        # Scrollable conversation area
        conv_container = Frame(self.messages_frame)
        conv_container.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)
        self.messages_frame.rowconfigure(3, weight=1)
        self.messages_frame.columnconfigure(0, weight=1)

        self.conv_canvas = Canvas(conv_container, highlightthickness=0)
        self.conv_scroll = ttk.Scrollbar(conv_container, orient="vertical", command=self.conv_canvas.yview)
        self.conv_canvas.configure(yscrollcommand=self.conv_scroll.set)
        self.conv_scroll.pack(side="right", fill="y")
        self.conv_canvas.pack(side="left", fill="both", expand=True)

        self.conv_inner = Frame(self.conv_canvas)
        self.conv_inner_id = self.conv_canvas.create_window((0, 0), window=self.conv_inner, anchor="nw")

        def _on_inner_config(event):
            self.conv_canvas.configure(scrollregion=self.conv_canvas.bbox("all"))

        def _on_canvas_config(event):
            self.conv_canvas.itemconfig(self.conv_inner_id, width=event.width)

        self.conv_inner.bind("<Configure>", _on_inner_config)
        self.conv_canvas.bind("<Configure>", _on_canvas_config)
        self.messages_status = StringVar(value="Ready")
        ttk.Label(self.messages_frame, textvariable=self.messages_status).grid(row=4, column=0, sticky="w", **pad)

    # ---------------------------
    # Helpers
    # ---------------------------
    def log(self, message: str):
        if threading.current_thread() is not threading.main_thread():
            self._ui_queue.put(lambda: self.log(message))
            return
        self.log_output.insert("end", message + "\n")
        self.log_output.see("end")

    def _drain_ui_queue(self):
        try:
            for _ in range(20):
                callback = self._ui_queue.get_nowait()
                try:
                    callback()
                except Exception:
                    self.root.report_callback_exception(*sys.exc_info())
        except queue.Empty:
            pass
        self.root.after(50, self._drain_ui_queue)

    def _messages_error(self, error):
        self._messages_busy = False
        detail = str(error)
        if isinstance(error, PermissionError) or "unable to open database" in detail.lower() or "authorization denied" in detail.lower():
            detail += ("\n\nIn System Settings → Privacy & Security → Full Disk Access, "
                       "enable the app launching this tool (Terminal, your IDE, or the packaged app), "
                       "then quit and relaunch it.")
        self.messages_status.set("Failed; see error details.")
        self.log(f"Messages: {detail}")
        messagebox.showerror("Messages", detail)

    def _messages_task(self, status, work, done):
        if self._messages_busy:
            return
        self._messages_busy = True
        self.messages_status.set(status)

        def worker():
            try:
                result = work()
            except Exception as error:
                self._ui_queue.put(lambda error=error: self._messages_error(error))
            else:
                def deliver():
                    try:
                        done(result)
                    except Exception as error:
                        self._messages_error(error)
                self._ui_queue.put(deliver)

        threading.Thread(target=worker, daemon=True).start()

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_dir.set(folder)
            self.populate_backup_instructions()

    def login(self):
        apple_id = self.apple_id.get().strip()
        password = self.password.get().strip()
        if not apple_id or not password:
            messagebox.showerror("Error", "Please enter your Apple ID and iCloud password.")
            return
        try:
            self.api = PyiCloudService(apple_id, password)
            if self.api.requires_2fa:
                from tkinter.simpledialog import askstring

                if not self.api.request_2fa_code():
                    raise Exception(
                        "Could not request a verification code. "
                        "Your account may require a security key."
                    )

                code = askstring(
                    "Two-Factor Authentication",
                    "Enter the code from your trusted device or SMS:",
                    parent=self.root,
                )
                if code is None:
                    self.api = None
                    self.log("iCloud login cancelled.")
                    return
                if not self.api.validate_2fa_code(code.strip()):
                    raise Exception("Apple rejected the verification code.")
                if not self.api.is_trusted_session:
                    try:
                        self.api.trust_session()
                    except Exception:
                        pass
            messagebox.showinfo("Success", "Logged in to iCloud successfully.")
            self.log("Logged in to iCloud successfully.")
        except Exception as e:
            self.api = None
            messagebox.showerror("Login Error", str(e))
            self.log(f"Login failed: {e}")

    # ---------------------------
    # Photos
    # ---------------------------
    def download_file(self, file_obj, folder_path, file_name):
        try:
            os.makedirs(folder_path, exist_ok=True)
            file_path = os.path.join(folder_path, file_name)
            if hasattr(file_obj, "download"):
                self.log(f"Downloading photo/video: {file_name}")
                content = file_obj.download()
                if not content:
                    self.log(f"Skipping {file_name}: No photo/video data returned.")
                    return
                with open(file_path, "wb") as f:
                    f.write(content)
            else:
                item_data = getattr(file_obj, "item", {})
                url = item_data.get("downloadURL", None)
                if not url:
                    self.log(f"Skipping {file_name}: No download URL.")
                    return
                self.log(f"Downloading drive file: {file_name}")
                response = self.api.session.get(url, stream=True)
                if response.status_code == 200:
                    with open(file_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                else:
                    self.log(f"Failed to download {file_name}: HTTP {response.status_code}")
                    return
            if self.delete_after_download.get():
                try:
                    file_obj.delete()
                except Exception as del_err:
                    self.log(f"Failed to delete {file_name}: {del_err}")
        except Exception as e:
            self.log(f"Error downloading {file_name}: {e}")

    def download_photos(self):
        if not self.api or not self.download_dir.get():
            self.log("Please login and choose a download folder.")
            return
        self.log("Fetching photos...")
        try:
            photos = self.api.photos.all
            for photo in photos:
                try:
                    created = getattr(photo, "created", None)
                    folder_name = created.strftime("%Y-%m") if created else "UnknownDate"
                    file_name = getattr(photo, "filename", f"photo_{datetime.now().timestamp()}")
                    save_folder = os.path.join(self.download_dir.get(), "Photos", folder_name)
                    self.download_file(photo, save_folder, file_name)
                except Exception as inner_e:
                    self.log(f"Skipping photo: {inner_e}")
            self.log("Photo download complete.")
        except Exception as e:
            self.log(f"Photo download error: {e}")

    # ---------------------------
    # Drive
    # ---------------------------
    def download_drive_files(self):
        if not self.api or not self.download_dir.get():
            self.log("Please login and choose a download folder.")
            return
        self.log("Fetching iCloud Drive files...")
        try:
            def traverse_dir(items, path):
                for item in items:
                    try:
                        name = getattr(item, 'name', 'UnnamedFile')
                        item_type = getattr(item, 'type', 'unknown')
                        if item_type == 'folder':
                            sub_path = os.path.join(path, name)
                            os.makedirs(sub_path, exist_ok=True)
                            traverse_dir(item.dir(), sub_path)
                        elif hasattr(item, 'item') and 'downloadURL' in item.item:
                            self.download_file(item, path, name)
                    except Exception as inner_e:
                        self.log(f"Skipping item: {inner_e}")

            base_path = os.path.join(self.download_dir.get(), "iCloud Drive Files")
            traverse_dir(self.api.drive.dir(), base_path)
            self.log("Drive files download complete.")
        except Exception as e:
            self.log(f"Drive download error: {e}")

    # ---------------------------
    # Backups
    # ---------------------------
    def load_devices(self):
        self.devices_tree.delete(*self.devices_tree.get_children())
        if not self.api:
            self.log("Login to iCloud to load devices.")
            return
        try:
            devices = getattr(self.api, "devices", None)
            if not devices:
                self.log("No devices found or endpoint unavailable.")
                return
            try:
                iterable = list(devices)
            except Exception:
                iterable = []
            if hasattr(devices, "devices"):
                iterable = devices.devices
            count = 0
            for dev in iterable:
                try:
                    name = getattr(dev, "name", None) or getattr(dev, "deviceDisplayName", "Unknown")
                    model = getattr(dev, "modelDisplayName", None) or "Unknown"
                    backup_enabled = getattr(dev, "isLocating", None)
                    last_backup = "Unknown"
                    self.devices_tree.insert("", "end", values=(name, model, "Unknown" if backup_enabled is None else str(backup_enabled), last_backup))
                    count += 1
                except Exception:
                    continue
            self.log(f"Devices listed: {count}")
        except Exception as e:
            self.log(f"Device listing error: {e}")

    def populate_backup_instructions(self):
        dl = self.download_dir.get().strip() or "<Your Download Folder>"
        os_name = platform.system()
        mac_text = f"""
macOS — Save an iPhone/iPad backup to your chosen folder
-------------------------------------------------------
1) Open Finder.
2) Connect iPhone/iPad via cable (or ensure Wi-Fi sync is enabled).
3) Select your device under “Locations”.
4) General tab → “Back Up Now” (choose “Back up all of the data on your Mac” for local).
5) Manage Backups… → right-click device → Show in Finder.
6) Copy the newest backup folder into:
   {dl}
"""
        win_text = f"""
Windows — Save an iPhone/iPad backup to your chosen folder
---------------------------------------------------------
1) Open iTunes (Microsoft Store).
2) Connect iPhone/iPad via USB.
3) Device icon → Summary → Backups → “This computer” → Back Up Now.
4) Win+R → %APPDATA%\\Apple Computer\\MobileSync\\Backup
5) Copy the newest backup folder into:
   {dl}
"""
        note = """
Notes
-----
• iCloud backups are encrypted; restore to a device or inspect with third-party tools at your discretion.
• Apple provides no public API to download/decrypt iCloud backups programmatically.
"""
        final = (mac_text if os_name == "Darwin" else win_text) + note
        self.backup_instructions.delete("1.0", "end")
        self.backup_instructions.insert("1.0", final)

    # ---------------------------
    # Messages: DB copy, chat list, export, viewer
    # ---------------------------
    def ensure_messages_db_copy(self):
        """Take a WAL-aware snapshot; called only by the Messages worker."""
        if platform.system() != "Darwin":
            raise RuntimeError("Messages is macOS-only.")
        src_db = Path.home() / "Library" / "Messages" / "chat.db"
        dst_db = Path(self._messages_temp.name) / "chat.db"
        deadline = time.monotonic() + 20

        def progress(_status, _remaining, _total):
            if time.monotonic() > deadline:
                raise TimeoutError("Messages database is busy. Wait a moment, then try Load Chats again.")

        # mode=ro prevents accidentally creating or modifying Apple's database.
        with closing(sqlite3.connect(src_db.as_uri() + "?mode=ro", uri=True, timeout=5)) as source:
            with closing(sqlite3.connect(dst_db)) as target:
                source.backup(target, pages=256, progress=progress, sleep=0.05)
        self.messages_db_copy = str(dst_db)
        return self.messages_db_copy

    def load_chats(self):
        def work():
            db_path = self.ensure_messages_db_copy()
            with closing(sqlite3.connect(db_path)) as con:
                return con.execute("""
                    SELECT c.ROWID,
                           COALESCE(NULLIF(c.display_name, ''), c.chat_identifier, 'Unknown'),
                           c.chat_identifier
                    FROM chat c ORDER BY 2 COLLATE NOCASE;
                """).fetchall()

        def done(rows):
            self.chat_rows, self.chat_map = [], {}
            values = []
            for rowid, name, identifier in rows:
                display = f"{name}  ({identifier})" if identifier and identifier != name else name
                # Different conversations can share a phone number or title.
                display = f"{display.strip() or 'Chat'} [#{rowid}]"
                self.chat_rows.append({"rowid": rowid, "display": display, "identifier": identifier or ""})
                self.chat_map[display] = rowid
                values.append(display)
            self.chat_combo["values"] = values
            self.selected_chat_display.set(values[0] if values else "")
            self.current_chat_rowid = None
            self.current_loaded = 0
            for widget in self.conv_inner.winfo_children():
                widget.destroy()
            self._thumb_refs.clear()
            self._message_pages.clear()
            self._messages_busy = False
            self.messages_status.set(f"Loaded {len(values)} chats.")
            self.log(f"Loaded {len(values)} chats.")

        self._messages_task("Reading Messages database…", work, done)

    def open_selected_chat(self):
        if self._messages_busy:
            return
        display = self.selected_chat_display.get().strip()
        if not display:
            messagebox.showwarning("Messages", "Select a chat first.")
            return
        rowid = self.chat_map.get(display)
        if not rowid:
            messagebox.showwarning("Messages", "Could not resolve selected chat.")
            return
        self.current_chat_rowid = rowid
        self.current_chat_display = display
        self.current_loaded = 0
        self._thumb_refs.clear()
        self._message_pages.clear()
        # Clear the conversation view
        for w in self.conv_inner.winfo_children():
            w.destroy()
        # Load first page
        self._load_chat_chunk(initial=True)

    def load_more_messages(self):
        if self._messages_busy or not self.current_chat_rowid:
            return
        self._load_chat_chunk(initial=False)

    def _get_total_messages_for_chat(self, con, chat_rowid: int) -> int:
        cur = con.cursor()
        cur.execute("""
            SELECT COUNT(*)
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            WHERE cmj.chat_id = ?;
        """, (chat_rowid,))
        return cur.fetchone()[0] or 0

    def _fetch_messages_chunk(self, con, chat_rowid: int, offset: int, limit: int):
        """Fetch messages newest-first with offset/limit, then reverse to display ascending."""
        cur = con.cursor()
        cur.execute("""
            SELECT
                m.ROWID,
                m.date,
                m.is_from_me,
                COALESCE(h.id, '') as handle_id,
                m.text, m.attributedBody
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            WHERE cmj.chat_id = ?
            ORDER BY m.date DESC, m.ROWID DESC
            LIMIT ? OFFSET ?;
        """, (chat_rowid, limit, offset))
        rows = cur.fetchall()
        rows.reverse()  # display ascending
        return [(*row[:4], message_text(row[4], row[5])) for row in rows]

    def _attachments_for_message_ids(self, con, msg_ids):
        if not msg_ids:
            return {}
        cur = con.cursor()
        q_marks = ",".join("?" for _ in msg_ids)
        cur.execute(f"""
            SELECT
                maj.message_id,
                a.filename,
                a.transfer_name
            FROM message_attachment_join maj
            JOIN attachment a ON a.ROWID = maj.attachment_id
            WHERE maj.message_id IN ({q_marks});
        """, msg_ids)
        result = {}
        for mid, filename, transfer_name in cur.fetchall():
            result.setdefault(mid, []).append((filename, transfer_name))
        return result

    def _prepare_attachments(self, att_map):
        """Resolve files and decode image pixels on the worker, away from Tk."""
        prepared = {}
        attach_root = Path.home() / "Library" / "Messages" / "Attachments"
        for mid, attachments in att_map.items():
            items = []
            for filename, transfer_name in attachments:
                src = Path(filename).expanduser() if filename else None
                if src and not src.is_absolute():
                    src = attach_root / src
                if (not src or not src.is_file()) and transfer_name:
                    src = attach_root / transfer_name
                thumbnail = None
                if src and src.is_file():
                    if is_image_file(src):
                        try:
                            with Image.open(src) as image:
                                image.thumbnail((280, 280))
                                thumbnail = image.convert("RGB").copy()
                        except Exception:
                            pass
                    items.append((src, thumbnail))
                else:
                    items.append((None, transfer_name or filename or "Attachment unavailable"))
            prepared[mid] = items
        return prepared

    def _load_chat_chunk(self, initial: bool):
        chat_id, offset = self.current_chat_rowid, self.current_loaded

        def work():
            with closing(sqlite3.connect(self.messages_db_copy)) as con:
                total = self._get_total_messages_for_chat(con, chat_id)
                rows = self._fetch_messages_chunk(con, chat_id, offset, self.messages_per_page)
                att_map = self._attachments_for_message_ids(con, [r[0] for r in rows])
            return total, rows, self._prepare_attachments(att_map)

        def done(result):
            total, rows, attachments = result
            if not rows:
                self._messages_busy = False
                self.messages_status.set(f"All {total} messages loaded.")
                return
            page = Frame(self.conv_inner)
            # Older pages belong above the messages already on screen.
            if self._message_pages:
                page.pack(fill="x", before=self._message_pages[0])
            else:
                page.pack(fill="x")
            self._message_pages.insert(0, page)
            self._render_message_batch(page, rows, attachments, 0, total, initial)

        self._messages_task("Loading messages…", work, done)

    def _render_message_batch(self, page, rows, attachments, index, total, initial):
        try:
            # Yield to macOS between small batches so input and repaint continue.
            end = min(index + 10, len(rows))
            for msg_id, date_val, is_from_me, handle_id, text in rows[index:end]:
                self._add_message_bubble(page, msg_id, date_val, is_from_me, handle_id, text,
                                         attachments.get(msg_id, []))
            self.messages_status.set(f"Displaying messages… {end}/{len(rows)}")
            if end < len(rows):
                self.root.after(10, lambda: self._render_message_batch(
                    page, rows, attachments, end, total, initial))
                return
            self.current_loaded += len(rows)
            self._messages_busy = False
            self.messages_status.set(f"Showing {self.current_loaded} of {total} messages.")
            self.conv_canvas.after_idle(lambda: self.conv_canvas.yview_moveto(1.0 if initial else 0.0))
        except Exception as error:
            self._messages_error(error)

    def _add_message_bubble(self, parent, msg_id, date_val, is_from_me, handle_id, text, attachments):
        # Simple bubble styling
        me = (is_from_me == 1)
        bg = "#cce4ff" if me else "#e8e8e8"
        fg = "#000000"
        align = "e" if me else "w"
        outer = Frame(parent)
        outer.pack(fill="x", padx=6, pady=3)
        inner = Frame(outer, bg=bg, bd=0, highlightthickness=0)
        # width constraint for readability
        max_width = max(240, min(self.conv_canvas.winfo_width(), 600))

        # Text content
        dt = apple_ns_to_unix(date_val)
        ts = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""
        sender = "Me" if me else (handle_id or "Other")
        text = text or ""
        # Create a text label with wrapping
        lbl = Label(inner, text=text, wraplength=max_width-40, justify="left", bg=bg, fg=fg)
        lbl.pack(anchor="w", padx=10, pady=(8, 4))

        # Only Tk image creation happens here; disk reads and resizing are done.
        for src, thumbnail in attachments:
            if src is None:
                Label(inner, text=f"[Unavailable: {thumbnail}]", bg=bg, fg="#555").pack(
                    anchor="w", padx=10, pady=(0, 6))
                continue
            if thumbnail is not None:
                tkim = ImageTk.PhotoImage(thumbnail, master=self.root)
                self._thumb_refs.append(tkim)
                link = Label(inner, image=tkim, bg=bg)
            else:
                link = Label(inner, text=f"[Attachment: {src.name}]", fg="#0645AD", bg=bg, cursor="hand2")
            link.pack(anchor="w", padx=10, pady=(0, 6))
            link.bind("<Button-1>", lambda e, p=str(src): self._open_in_finder(p))

        # Timestamp
        Label(inner, text=f"{sender} • {ts}", bg=bg, fg="#333").pack(anchor="w", padx=10, pady=(0,8))

        # Place bubble aligned left/right
        if align == "e":
            inner.pack(anchor="e", padx=10)
        else:
            inner.pack(anchor="w", padx=10)

    def _open_in_finder(self, path: str):
        try:
            subprocess.Popen(["open", path])
        except Exception as e:
            self.log(f"Open error: {e}")

    # Export features
    def export_selected_chat(self):
        if self._messages_busy:
            return
        display = self.selected_chat_display.get().strip()
        if not display:
            messagebox.showwarning("Messages", "Please select a chat first.")
            return
        rowid = self.chat_map.get(display)
        if not rowid:
            messagebox.showwarning("Messages", "Could not resolve selected chat.")
            return
        directory = self.download_dir.get()
        if not directory:
            messagebox.showwarning("Messages", "Choose a download folder in the Login tab first.")
            return

        def done(csv_path):
            self._messages_busy = False
            self.messages_status.set(f"Export complete: {csv_path}")

        self._messages_task("Exporting chat…",
                            lambda: self._export_chat_by_rowid(rowid, display, directory), done)

    def _export_chat_by_rowid(self, chat_rowid: int, chat_display: str, directory: str):
        if not self.messages_db_copy:
            db_path = self.ensure_messages_db_copy()
            if not db_path:
                return
        chat_name = sanitize_filename(chat_display) or f"chat_{chat_rowid}"
        base_dir = Path(directory) / "Messages" / chat_name
        attachments_dir = base_dir / "attachments"
        base_dir.mkdir(parents=True, exist_ok=True)
        attachments_dir.mkdir(parents=True, exist_ok=True)

        with closing(sqlite3.connect(self.messages_db_copy)) as con:
            cur = con.cursor()
            cur.execute("""
                SELECT m.ROWID, m.date, m.is_from_me, COALESCE(h.id, ''), m.text, m.attributedBody
                FROM message m
                JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                LEFT JOIN handle h ON h.ROWID = m.handle_id
                WHERE cmj.chat_id = ?
                ORDER BY m.date ASC;
            """, (chat_rowid,))
            msgs = cur.fetchall()
            records = []
            for (msg_id, date_val, is_from_me, handle_id, text, body) in msgs:
                dt = apple_ns_to_unix(date_val)
                dt_str = dt.isoformat(sep=" ", timespec="seconds") if dt else ""
                direction = "Me" if is_from_me == 1 else (handle_id or "Other")
                records.append({"message_id": msg_id, "datetime_utc": dt_str, "from": direction, "text": message_text(text, body)})

            df = pd.DataFrame(records, columns=["message_id", "datetime_utc", "from", "text"])
            csv_path = base_dir / f"chat_with_{sanitize_filename(chat_name)}.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8")
            self.log(f"Saved messages CSV: {csv_path}")

            if records:
                # Join by chat rather than binding every message ID: large chats
                # otherwise exceed SQLite's variable limit during export.
                cur.execute("""
                    SELECT maj.message_id, a.filename, a.transfer_name
                    FROM message_attachment_join maj
                    JOIN attachment a ON a.ROWID = maj.attachment_id
                    JOIN chat_message_join cmj ON cmj.message_id = maj.message_id
                    WHERE cmj.chat_id = ?;
                """, (chat_rowid,))
                atts = cur.fetchall()
                home = Path.home()
                attach_root = home / "Library" / "Messages" / "Attachments"
                copied = 0
                for (mid, filename, transfer_name) in atts:
                    src = None
                    if filename:
                        fpath = Path(filename).expanduser()
                        src = fpath if fpath.is_absolute() else attach_root / fpath
                    if (not src or not src.exists()) and transfer_name:
                        alt = attach_root / transfer_name
                        if alt.exists():
                            src = alt
                    if src and src.exists():
                        dest_name = sanitize_filename(f"{mid}_{src.name}", max_len=160)
                        dest_path = attachments_dir / dest_name
                        try:
                            shutil.copy2(src, dest_path)
                            copied += 1
                        except Exception as e:
                            self.log(f"Attachment copy error ({src}): {e}")
                self.log(f"Saved {copied} attachment(s) to: {attachments_dir}")

        return csv_path

    def open_attachments_folder(self):
        if not self.download_dir.get():
            messagebox.showwarning("Messages", "Choose a download folder in the Login tab first.")
            return
        if not self.current_chat_rowid:
            messagebox.showinfo("Messages", "Open a chat first.")
            return
        chat_name = sanitize_filename(self.current_chat_display) or f"chat_{self.current_chat_rowid}"
        base_dir = Path(self.download_dir.get()) / "Messages" / chat_name / "attachments"
        base_dir.mkdir(parents=True, exist_ok=True)
        self._open_in_finder(str(base_dir))

# ---------------------------
# App runner
# ---------------------------
def main():
    root = Tk()
    app = iCloudDataManagerApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
