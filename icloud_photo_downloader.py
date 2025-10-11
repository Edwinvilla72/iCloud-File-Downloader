import os
import threading
from tkinter import Tk, Label, Entry, Button, StringVar, filedialog, messagebox, BooleanVar
from tkinter import simpledialog
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from pyicloud import PyiCloudService
import requests

class iCloudDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("iCloud Downloader")
        self.root.geometry("500x600")

        self.apple_id = StringVar()
        self.password = StringVar()
        self.download_dir = StringVar()
        self.delete_after_download = BooleanVar()
        self.api = None

        self.create_widgets()

    def create_widgets(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True)

        self.login_frame = ttk.Frame(notebook)
        self.photos_frame = ttk.Frame(notebook)
        self.drive_frame = ttk.Frame(notebook)

        notebook.add(self.login_frame, text='Login')
        notebook.add(self.photos_frame, text='Photos')
        notebook.add(self.drive_frame, text='Drive')

        # Login Tab
        ttk.Label(self.login_frame, text="Apple ID:").pack(pady=5)
        ttk.Entry(self.login_frame, textvariable=self.apple_id, width=40).pack(pady=5)
        ttk.Label(self.login_frame, text="Password:").pack(pady=5)
        ttk.Entry(self.login_frame, textvariable=self.password, show="*", width=40).pack(pady=5)
        ttk.Button(self.login_frame, text="Select Download Folder", command=self.select_folder).pack(pady=5)
        ttk.Label(self.login_frame, textvariable=self.download_dir, wraplength=400).pack(pady=5)
        ttk.Checkbutton(self.login_frame, text="Delete after download", variable=self.delete_after_download).pack(pady=5)
        ttk.Button(self.login_frame, text="Login", command=self.login).pack(pady=10)

        # Status log
        self.log_output = ScrolledText(self.root, height=10)
        self.log_output.pack(fill="both", expand=True)

        # Photos Tab
        ttk.Button(self.photos_frame, text="Download All Photos", command=lambda: threading.Thread(target=self.download_photos).start()).pack(pady=20)

        # Drive Tab
        ttk.Button(self.drive_frame, text="Download All Drive Files", command=lambda: threading.Thread(target=self.download_drive_files).start()).pack(pady=20)

    def log(self, message):
        self.log_output.insert("end", message + "\n")
        self.log_output.see("end")

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_dir.set(folder)

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
            self.log("Logged in to iCloud successfully.")
        except Exception as e:
            messagebox.showerror("Login Error", str(e))
            self.log(f"Login failed: {e}")


    # downloads each individual file
    # if photo, follow photo rules, else, its a drive file
    def download_file(self, file_obj, folder_path, file_name):
        try:
            os.makedirs(folder_path, exist_ok=True)
            file_path = os.path.join(folder_path, file_name)

            # ---- Case 1: iCloud Photos ----
            if hasattr(file_obj, "download"):
                self.log(f"Downloading photo/video: {file_name}")
                response = file_obj.download()
                with open(file_path, "wb") as f:
                    f.write(response.raw.read())
                self.log(f"Downloaded {file_name} to {folder_path}")

            # ---- Case 2: iCloud Drive Files ----
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
                        total = int(response.headers.get("content-length", 0))
                        downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                percent = int((downloaded / total) * 100) if total else 0
                                self.log(f"Downloading {file_name}: {percent}%")
                    self.log(f"Downloaded {file_name} to {folder_path}")
                else:
                    self.log(f"Failed to download {file_name}: HTTP {response.status_code}")

            # ---- Optional deletion after download ----
            if self.delete_after_download.get():
                try:
                    file_obj.delete()
                    self.log(f"Deleted {file_name} from iCloud.")
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
                folder_name = photo.created.strftime("%Y-%m")
                file_name = photo.filename
                save_folder = os.path.join(self.download_dir.get(), folder_name)
                self.download_file(photo, save_folder, file_name)
            self.log("Photo download complete.")
        except Exception as e:
            self.log(f"Photo download error: {e}")

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
                        self.log(f"Found: {name} ({item_type}) in {path}")

                        if item_type == 'folder':
                            sub_path = os.path.join(path, name)
                            os.makedirs(sub_path, exist_ok=True)
                            sub_items = item.dir()
                            traverse_dir(sub_items, sub_path)
                        elif hasattr(item, 'item') and 'downloadURL' in item.item:
                            self.download_file(item, path, name)
                    except Exception as inner_e:
                        self.log(f"Skipping item due to error: {inner_e}")

            root_items = self.api.drive.dir()
            base_path = os.path.join(self.download_dir.get(), "iCloud Drive Files")
            traverse_dir(root_items, base_path)

            self.log("Drive files download complete.")
        except Exception as e:
            self.log(f"Drive download error: {e}")

if __name__ == "__main__":
    root = Tk()
    app = iCloudDownloaderApp(root)
    root.mainloop()
