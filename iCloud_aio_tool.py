import os
import platform
import threading
import sqlite3
import pandas as pd
from tkinter import Tk, StringVar, BooleanVar, filedialog, messagebox, simpledialog
from tkinter.scrolledtext import ScrolledText
from pyicloud import PyiCloudService
import requests
import ttkbootstrap as ttk  # modern themes

class ModernDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("iCloud Data Manager")
        self.root.geometry("600x700")

        # Core variables
        self.apple_id = StringVar()
        self.password = StringVar()
        self.download_dir = StringVar()
        self.delete_after_download = BooleanVar()
        self.api = None
        self.os_name = platform.system()

        self.create_widgets()

    # ---------------------------
    # UI SETUP
    # ---------------------------
    def create_widgets(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # Tabs
        self.login_frame = ttk.Frame(notebook)
        self.photos_frame = ttk.Frame(notebook)
        self.drive_frame = ttk.Frame(notebook)
        self.messages_frame = ttk.Frame(notebook)

        notebook.add(self.login_frame, text="Login")
        notebook.add(self.photos_frame, text="Photos")
        notebook.add(self.drive_frame, text="Drive")
        if self.os_name == "Darwin":  # macOS only
            notebook.add(self.messages_frame, text="Messages")

        # Login Tab
        ttk.Label(self.login_frame, text="Apple ID", font=("Helvetica", 11)).pack(pady=5)
        ttk.Entry(self.login_frame, textvariable=self.apple_id, width=40).pack(pady=5)
        ttk.Label(self.login_frame, text="Password", font=("Helvetica", 11)).pack(pady=5)
        ttk.Entry(self.login_frame, textvariable=self.password, show="*", width=40).pack(pady=5)
        ttk.Button(self.login_frame, text="Select Download Folder", command=self.select_folder).pack(pady=5)
        ttk.Label(self.login_frame, textvariable=self.download_dir, wraplength=400).pack(pady=5)
        ttk.Checkbutton(self.login_frame, text="Delete after download", variable=self.delete_after_download).pack(pady=5)
        ttk.Button(self.login_frame, text="Login", bootstyle="success-outline", command=self.login).pack(pady=10)

        # Log box
        ttk.Label(self.root, text="Activity Log", font=("Helvetica", 11, "bold")).pack(pady=5)
        self.log_output = ScrolledText(self.root, height=12)
        self.log_output.pack(fill="both", expand=True, padx=10, pady=10)

        # Photos Tab
        ttk.Button(self.photos_frame, text="Download All Photos", bootstyle="info-outline",
                   command=lambda: threading.Thread(target=self.download_photos).start()).pack(pady=20)

        # Drive Tab
        ttk.Button(self.drive_frame, text="Download All Drive Files", bootstyle="info-outline",
                   command=lambda: threading.Thread(target=self.download_drive_files).start()).pack(pady=20)

        # Messages Tab (macOS only)
        if self.os_name == "Darwin":
            ttk.Label(self.messages_frame, text="Export iMessages to CSV", font=("Helvetica", 12, "bold")).pack(pady=10)
            ttk.Button(self.messages_frame, text="Export iMessages", bootstyle="secondary-outline",
                       command=lambda: threading.Thread(target=self.export_imessages).start()).pack(pady=20)

    # ---------------------------
    # CORE FUNCTIONS
    # ---------------------------
    def log(self, message):
        self.log_output.insert("end", message + "\n")
        self.log_output.see("end")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_dir.set(folder)

    # ---- LOGIN ----
    def login(self):
        apple_id = self.apple_id.get()
        password = self.password.get()

        if not apple_id or not password:
            messagebox.showerror("Error", "Please enter your Apple ID and password.")
            return

        try:
            self.api = PyiCloudService(apple_id, password)
            if self.api.requires_2fa:
                code = simpledialog.askstring("Two-Factor Authentication", "Enter the 2FA code sent to your devices:")
                if not code or not self.api.validate_2fa_code(code):
                    raise Exception("Invalid 2FA code.")
            messagebox.showinfo("Success", "Logged in successfully!")
            self.log("✅ Logged in to iCloud successfully.")
        except Exception as e:
            messagebox.showerror("Login Error", str(e))
            self.log(f"❌ Login failed: {e}")

    # ---- UNIVERSAL FILE DOWNLOADER ----
    def download_file(self, file_obj, folder_path, file_name):
        try:
            os.makedirs(folder_path, exist_ok=True)
            file_path = os.path.join(folder_path, file_name)

            if hasattr(file_obj, "download"):  # iCloud Photos
                self.log(f"Downloading photo/video: {file_name}")
                response = file_obj.download()
                with open(file_path, "wb") as f:
                    f.write(response.raw.read())
                self.log(f"✅ Downloaded {file_name}")

            else:  # iCloud Drive
                item_data = getattr(file_obj, "item", {})
                url = item_data.get("downloadURL")
                if not url:
                    self.log(f"Skipping {file_name}: No download URL.")
                    return
                response = self.api.session.get(url, stream=True)
                if response.status_code == 200:
                    with open(file_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    self.log(f"✅ Downloaded {file_name}")
                else:
                    self.log(f"Failed: {file_name} ({response.status_code})")

            if self.delete_after_download.get():
                try:
                    file_obj.delete()
                    self.log(f"🗑 Deleted {file_name} from iCloud.")
                except Exception as e:
                    self.log(f"Could not delete {file_name}: {e}")
        except Exception as e:
            self.log(f"Error downloading {file_name}: {e}")

    # ---- PHOTOS ----
    def download_photos(self):
        if not self.api or not self.download_dir.get():
            self.log("Please login and choose a download folder.")
            return

        self.log("Fetching photos...")
        try:
            for photo in self.api.photos.all:
                folder_name = photo.created.strftime("%Y-%m")
                save_folder = os.path.join(self.download_dir.get(), folder_name)
                self.download_file(photo, save_folder, photo.filename)
            self.log("✅ Photo download complete.")
        except Exception as e:
            self.log(f"Photo download error: {e}")

    # ---- DRIVE ----
    def download_drive_files(self):
        if not self.api or not self.download_dir.get():
            self.log("Please login and choose a download folder.")
            return

        self.log("Fetching iCloud Drive files...")
        try:
            def traverse_dir(items, path):
                for item in items:
                    name = getattr(item, 'name', 'UnnamedFile')
                    item_type = getattr(item, 'type', 'unknown')
                    self.log(f"Found: {name} ({item_type}) in {path}")

                    if item_type == 'folder':
                        sub_path = os.path.join(path, name)
                        os.makedirs(sub_path, exist_ok=True)
                        traverse_dir(item.dir(), sub_path)
                    elif hasattr(item, 'item') and 'downloadURL' in item.item:
                        self.download_file(item, path, name)

            base_path = os.path.join(self.download_dir.get(), "iCloud Drive Files")
            traverse_dir(self.api.drive.dir(), base_path)
            self.log("✅ Drive download complete.")
        except Exception as e:
            self.log(f"Drive download error: {e}")

    # ---- iMESSAGE EXPORT ----
    def export_imessages(self):
        self.log(f"Detected OS: {self.os_name}")
        if self.os_name != "Darwin":
            self.log("iMessage export is only available on macOS.")
            return

        try:
            db_path = os.path.expanduser("~/Library/Messages/chat.db")
            if not os.path.exists(db_path):
                self.log("No local Messages database found.")
                return

            conn = sqlite3.connect(db_path)
            df = pd.read_sql_query("""
                SELECT datetime(date/1000000000 + strftime('%s', '2001-01-01'), 'unixepoch') AS timestamp,
                       text,
                       handle.id AS sender
                FROM message
                LEFT JOIN handle ON message.handle_id = handle.rowid
                WHERE text IS NOT NULL
                ORDER BY date DESC
            """, conn)
            conn.close()

            export_path = os.path.join(self.download_dir.get() or os.getcwd(), "iMessages.csv")
            df.to_csv(export_path, index=False)
            self.log(f"✅ Exported {len(df)} messages to {export_path}")
        except Exception as e:
            self.log(f"iMessage export failed: {e}")

# ---------------------------
# RUN APP
# ---------------------------
if __name__ == "__main__":
    root = ttk.Window(themename="cosmo")  # modern theme
    app = ModernDownloaderApp(root)
    root.mainloop()
