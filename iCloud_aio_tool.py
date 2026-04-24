"""
iCloud Data Manager
-------------------
Tabs:
- Login (Apple ID + iCloud login via pyicloud, download folder selection, delete-after-download toggle)
- Photos (Download all photos & videos, organized by YYYY-MM)
- Drive (Download all iCloud Drive files preserving folder structure)
- Emails (IMAP: save .eml + extract attachments)
- Backups (device list + OS-specific instructions)
- Messages (macOS only: export + in-app viewer with thumbnails, 500 recent + Load More)

Dependencies:
    pip install pyicloud requests pandas pillow
"""

import os
import re
import sys
import shutil
import sqlite3
import platform
import threading
import subprocess
from datetime import datetime
from pathlib import Path
from tkinter import Tk, StringVar, BooleanVar, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
from tkinter import Canvas, Frame, Label

import requests
from pyicloud import PyiCloudService

# Email handling
import imaplib
import email
from email.header import decode_header, make_header

# CSV + thumbnails
import pandas as pd
from PIL import Image, ImageTk

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
        self.messages_per_page = 500  # chunk size for "Load More"
        self._thumb_refs = []         # keep PhotoImage refs alive

        self.create_widgets()

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

        ttk.Button(top, text="Load Chats", command=lambda: threading.Thread(target=self.load_chats, daemon=True).start()).grid(row=0, column=0, **pad)
        ttk.Label(top, text="Select Chat:").grid(row=0, column=1, sticky="e", **pad)
        self.chat_combo = ttk.Combobox(top, textvariable=self.selected_chat_display, width=50, state="readonly", values=[])
        self.chat_combo.grid(row=0, column=2, sticky="ew", **pad)
        ttk.Button(top, text="Open", command=lambda: threading.Thread(target=self.open_selected_chat, daemon=True).start()).grid(row=0, column=3, sticky="w", **pad)

        mid = ttk.Frame(self.messages_frame)
        mid.grid(row=1, column=0, sticky="w", **pad)
        ttk.Button(mid, text="Load More (older 500)", command=lambda: threading.Thread(target=self.load_more_messages, daemon=True).start()).grid(row=0, column=0, **pad)
        ttk.Button(mid, text="Export Chat", command=lambda: threading.Thread(target=self.export_selected_chat, daemon=True).start()).grid(row=0, column=1, **pad)
        ttk.Button(mid, text="Open Attachments Folder", command=self.open_attachments_folder).grid(row=0, column=2, **pad)

        info = ("Viewer notes:\n"
                "• Loads the 500 most recent messages first; use 'Load More' for older messages.\n"
                "• Blue = Me, Gray = Other. Thumbnails shown for common image types.\n"
                "• If permissions error appears, grant Full Disk Access to Python (System Settings → Privacy & Security).")
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
            # Make width responsive
            self.conv_canvas.itemconfig(self.conv_inner_id, width=self.conv_canvas.winfo_width())

        def _on_canvas_config(event):
            self.conv_canvas.itemconfig(self.conv_inner_id, width=event.width)

        self.conv_inner.bind("<Configure>", _on_inner_config)
        self.conv_canvas.bind("<Configure>", _on_canvas_config)

    # ---------------------------
    # Helpers
    # ---------------------------
    def log(self, message: str):
        self.log_output.insert("end", message + "\n")
        self.log_output.see("end")
        self.root.update_idletasks()

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
                code = askstring("Two-Factor Authentication", "Enter the 2FA code sent to your devices:")
                if not code or not self.api.validate_2fa_code(code):
                    raise Exception("Invalid 2FA code.")
                if not self.api.is_trusted_session:
                    try:
                        self.api.trust_session()
                    except Exception:
                        pass
            messagebox.showinfo("Success", "Logged in to iCloud successfully.")
            self.log("Logged in to iCloud successfully.")
        except Exception as e:
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
                response = file_obj.download()
                with open(file_path, "wb") as f:
                    f.write(response.raw.read())
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
        if platform.system() != "Darwin":
            messagebox.showwarning("Messages", "Messages is macOS-only.")
            return None
        src_db = Path.home() / "Library" / "Messages" / "chat.db"
        if not src_db.exists():
            self.log("Messages DB not found at ~/Library/Messages/chat.db")
            messagebox.showerror("Messages", "Messages DB not found at ~/Library/Messages/chat.db")
            return None
        tmp_dir = Path.home() / "Library" / "Messages" / "DBCopies"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        dst_db = tmp_dir / f"chat_copy_{int(datetime.now().timestamp())}.db"
        try:
            shutil.copy2(src_db, dst_db)
            self.messages_db_copy = str(dst_db)
            return self.messages_db_copy
        except PermissionError:
            self.log("Permission denied. Grant Full Disk Access to Python and retry.")
            messagebox.showerror("Permissions", "Grant Full Disk Access to Python (System Settings → Privacy & Security).")
            return None
        except Exception as e:
            self.log(f"Copy chat.db failed: {e}")
            messagebox.showerror("Messages", f"Failed to copy chat.db: {e}")
            return None

    def load_chats(self):
        if not self.download_dir.get():
            self.log("Choose a download folder first (Login tab).")
            return
        db_path = self.ensure_messages_db_copy()
        if not db_path:
            return
        try:
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("""
                SELECT c.ROWID,
                       COALESCE(c.display_name, c.chat_identifier, 'Unknown') AS name,
                       c.chat_identifier
                FROM chat c
                ORDER BY name COLLATE NOCASE;
            """)
            rows = cur.fetchall()
            con.close()

            self.chat_rows, self.chat_map = [], {}
            values = []
            for rowid, name, identifier in rows:
                display = f"{name}  ({identifier})" if identifier and identifier != name else name
                display = display.strip() or f"Chat {rowid}"
                self.chat_rows.append({"rowid": rowid, "display": display, "identifier": identifier or ""})
                self.chat_map[display] = rowid
                values.append(display)

            self.chat_combo["values"] = values
            if values:
                self.chat_combo.current(0)
            self.log(f"Loaded {len(values)} chats.")
        except Exception as e:
            self.log(f"Load chats error: {e}")
            messagebox.showerror("Messages", f"Failed to load chats: {e}")

    def open_selected_chat(self):
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
        # Clear the conversation view
        for w in self.conv_inner.winfo_children():
            w.destroy()
        # Load first page
        self._load_chat_chunk(initial=True)

    def load_more_messages(self):
        if not self.current_chat_rowid:
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
                m.text
            FROM message m
            JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
            LEFT JOIN handle h ON h.ROWID = m.handle_id
            WHERE cmj.chat_id = ?
            ORDER BY m.date DESC, m.ROWID DESC
            LIMIT ? OFFSET ?;
        """, (chat_rowid, limit, offset))
        rows = cur.fetchall()
        rows.reverse()  # display ascending
        return rows

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

    def _load_chat_chunk(self, initial: bool):
        if not self.messages_db_copy:
            db_path = self.ensure_messages_db_copy()
            if not db_path:
                return
        try:
            con = sqlite3.connect(self.messages_db_copy)
            total = self._get_total_messages_for_chat(con, self.current_chat_rowid)
            offset = self.current_loaded
            limit = self.messages_per_page
            rows = self._fetch_messages_chunk(con, self.current_chat_rowid, offset, limit)
            msg_ids = [r[0] for r in rows]
            att_map = self._attachments_for_message_ids(con, msg_ids)
            con.close()

            if initial and total > self.messages_per_page:
                # Add a subtle notice at top
                Label(self.conv_inner, text=f"Showing latest {self.messages_per_page} of {total}. Click 'Load More' for older messages.",
                      fg="#555").pack(anchor="center", pady=(0,6))

            for (msg_id, date_val, is_from_me, handle_id, text) in rows:
                self._add_message_bubble(msg_id, date_val, is_from_me, handle_id, text, att_map.get(msg_id, []))

            self.current_loaded += len(rows)

            # Auto-scroll to bottom on initial open
            if initial:
                self.conv_canvas.after(50, lambda: self.conv_canvas.yview_moveto(1.0))

            if self.current_loaded >= total:
                # All loaded — maybe show a small note
                Label(self.conv_inner, text="No more messages.", fg="#888").pack(anchor="center", pady=(6,6))

        except Exception as e:
            self.log(f"Viewer load error: {e}")
            messagebox.showerror("Messages", f"Failed to load messages: {e}")

    def _add_message_bubble(self, msg_id, date_val, is_from_me, handle_id, text, attachments):
        # Simple bubble styling
        me = (is_from_me == 1)
        bg = "#cce4ff" if me else "#e8e8e8"
        fg = "#000000"
        align = "e" if me else "w"
        outer = Frame(self.conv_inner)
        outer.pack(fill="x", padx=6, pady=3)
        inner = Frame(outer, bg=bg, bd=0, highlightthickness=0)
        # width constraint for readability
        max_width = min(self.conv_inner.winfo_width() or 600, 600)

        # Text content
        dt = apple_ns_to_unix(date_val)
        ts = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""
        sender = "Me" if me else (handle_id or "Other")
        text = text or ""
        # Create a text label with wrapping
        lbl = Label(inner, text=text, wraplength=max_width-40, justify="left", bg=bg, fg=fg)
        lbl.pack(anchor="w", padx=10, pady=(8, 4))

        # Attachments (thumbnails or links)
        if attachments:
            home = Path.home()
            attach_root = home / "Library" / "Messages" / "Attachments"
            for (filename, transfer_name) in attachments:
                src = None
                if filename:
                    fpath = Path(filename).expanduser()
                    src = fpath if fpath.is_absolute() else attach_root / fpath
                if (not src or not src.exists()) and transfer_name:
                    alt = attach_root / transfer_name
                    if alt.exists():
                        src = alt
                if src and src.exists():
                    if is_image_file(src):
                        try:
                            im = Image.open(src)
                            im.thumbnail((280, 280))
                            tkim = ImageTk.PhotoImage(im)
                            img_label = Label(inner, image=tkim, bg=bg)
                            img_label.image = tkim
                            self._thumb_refs.append(tkim)
                            img_label.pack(anchor="w", padx=10, pady=(0,6))
                            img_label.bind("<Button-1>", lambda e, p=str(src): self._open_in_finder(p))
                        except Exception as e:
                            link = Label(inner, text=f"[Attachment: {src.name}]", fg="#0645AD", bg=bg, cursor="hand2")
                            link.pack(anchor="w", padx=10, pady=(0,6))
                            link.bind("<Button-1>", lambda e, p=str(src): self._open_in_finder(p))
                    else:
                        link = Label(inner, text=f"[Attachment: {src.name}]", fg="#0645AD", bg=bg, cursor="hand2")
                        link.pack(anchor="w", padx=10, pady=(0,6))
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
        display = self.selected_chat_display.get().strip()
        if not display:
            messagebox.showwarning("Messages", "Please select a chat first.")
            return
        rowid = self.chat_map.get(display)
        if not rowid:
            messagebox.showwarning("Messages", "Could not resolve selected chat.")
            return
        self._export_chat_by_rowid(rowid, display)

    def _export_chat_by_rowid(self, chat_rowid: int, chat_display: str):
        if not self.messages_db_copy:
            db_path = self.ensure_messages_db_copy()
            if not db_path:
                return
        chat_name = sanitize_filename(chat_display) or f"chat_{chat_rowid}"
        base_dir = Path(self.download_dir.get()) / "Messages" / chat_name
        attachments_dir = base_dir / "attachments"
        base_dir.mkdir(parents=True, exist_ok=True)
        attachments_dir.mkdir(parents=True, exist_ok=True)

        try:
            con = sqlite3.connect(self.messages_db_copy)
            cur = con.cursor()
            cur.execute("""
                SELECT m.ROWID, m.date, m.is_from_me, COALESCE(h.id, ''), m.text
                FROM message m
                JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
                LEFT JOIN handle h ON h.ROWID = m.handle_id
                WHERE cmj.chat_id = ?
                ORDER BY m.date ASC;
            """, (chat_rowid,))
            msgs = cur.fetchall()
            records = []
            for (msg_id, date_val, is_from_me, handle_id, text) in msgs:
                dt = apple_ns_to_unix(date_val)
                dt_str = dt.isoformat(sep=" ", timespec="seconds") if dt else ""
                direction = "Me" if is_from_me == 1 else (handle_id or "Other")
                records.append({"message_id": msg_id, "datetime_utc": dt_str, "from": direction, "text": text or ""})

            df = pd.DataFrame(records, columns=["message_id", "datetime_utc", "from", "text"])
            csv_path = base_dir / f"chat_with_{sanitize_filename(chat_name)}.csv"
            df.to_csv(csv_path, index=False, encoding="utf-8")
            self.log(f"Saved messages CSV: {csv_path}")

            msg_ids = [r["message_id"] for r in records]
            if msg_ids:
                q_marks = ",".join("?" for _ in msg_ids)
                cur.execute(f"""
                    SELECT maj.message_id, a.filename, a.transfer_name
                    FROM message_attachment_join maj
                    JOIN attachment a ON a.ROWID = maj.attachment_id
                    WHERE maj.message_id IN ({q_marks});
                """, msg_ids)
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

            con.close()
        except Exception as e:
            self.log(f"Export chat error: {e}")
            messagebox.showerror("Messages", f"Failed to export chat: {e}")

    def open_attachments_folder(self):
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
