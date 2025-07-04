import os
from tkinter import Tk, Label, Button, Entry, filedialog, StringVar, messagebox
from tkinter import simpledialog
from pyicloud import PyiCloudService


class iCloudPhotoDownloader:
    def __init__(self, root):
        self.root = root
        self.root.title("iCloud Photo Downloader")
        self.root.geometry("400x370")
        
        # Variables
        self.apple_id = StringVar()
        self.password = StringVar()
        self.download_dir = StringVar()

        # Create the GUI
        Label(root, text="Apple ID:").pack(pady=5)
        Entry(root, textvariable=self.apple_id, width=40).pack(pady=5)

        Label(root, text="Password:").pack(pady=5)
        Entry(root, textvariable=self.password, show="*", width=40).pack(pady=5)

        Button(root, text="Select Download Folder", command=self.select_folder).pack(pady=5)
        Label(root, textvariable=self.download_dir, wraplength=350).pack(pady=5)

        Button(root, text="Start Download", command=self.start_download).pack(pady=10)
        Button(root, text="Test Mode (Download First Item)", command=self.test_mode).pack(pady=10)

        self.status_label = Label(root, text="", fg="green")
        self.status_label.pack(pady=10)

    def select_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.download_dir.set(folder)

    def to_camel_case(self, text):
        words = text.split()
        return words[0].lower() + ''.join(word.capitalize() for word in words[1:])

    def download_file(self, photo, folder_path, file_name):
        try:
            response = photo.download()
            if response is None:
                print(f"Failed to download {file_name}: No response from server.")
                return False
            file_path = os.path.join(folder_path, file_name)
            with open(file_path, "wb") as file:
                file.write(response.raw.read())
            print(f"Downloaded {file_name} to {folder_path}")
            return True
        except Exception as e:
            print(f"Failed to download {file_name}: {e}")
            return False

    def test_mode(self):
        apple_id = self.apple_id.get()
        password = self.password.get()
        download_dir = self.download_dir.get()

        if not apple_id or not password:
            messagebox.showerror("Error", "Please enter your Apple ID and password.")
            return

        if not download_dir:
            messagebox.showerror("Error", "Please select a download folder.")
            return

        self.status_label.config(text="Logging into iCloud...", fg="blue")
        self.root.update_idletasks()

        try:
            api = PyiCloudService(apple_id, password)
            if api.requires_2fa:
                code = simpledialog.askstring("Two-Factor Authentication", "Enter the 2FA code sent to your devices:")
                if not code or not api.validate_2fa_code(code):
                    raise Exception("Invalid 2FA code.")
            photos = api.photos.all

            if not photos:
                messagebox.showinfo("No Items", "No items found in your iCloud account.")
                return

            test_folder = os.path.join(download_dir, "Test")
            os.makedirs(test_folder, exist_ok=True)

            first_item = next(iter(photos), None)
            if first_item:
                file_name = self.to_camel_case(first_item.filename)
                self.download_file(first_item, test_folder, file_name)
            else:
                print("No items found in your iCloud library.")

            self.status_label.config(text="Test download complete!", fg="green")
            messagebox.showinfo("Test Mode Complete", f"Downloaded the first item to: {test_folder}")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_label.config(text="")

    def start_download(self):
        apple_id = self.apple_id.get()
        password = self.password.get()
        download_dir = self.download_dir.get()

        if not apple_id or not password:
            messagebox.showerror("Error", "Please enter your Apple ID and password.")
            return

        if not download_dir:
            messagebox.showerror("Error", "Please select a download folder.")
            return

        self.status_label.config(text="Logging into iCloud...", fg="blue")
        self.root.update_idletasks()

        try:
            api = PyiCloudService(apple_id, password)
            if api.requires_2fa:
                code = simpledialog.askstring("Two-Factor Authentication", "Enter the 2FA code sent to your devices:")
                if not code or not api.validate_2fa_code(code):
                    raise Exception("Invalid 2FA code.")
            photos = api.photos.all

            if not photos:
                messagebox.showinfo("No Items", "No items found in your iCloud account.")
                return

            total_items = len(photos)
            confirm = messagebox.askyesno("Confirm Download", f"Found {total_items} items. Start download?")
            if not confirm:
                return

            self.status_label.config(text=f"Downloading {total_items} items...", fg="blue")
            for photo in photos:
                try:
                    created_date = photo.created
                    folder_name = created_date.strftime("%Y-%m")
                    folder_name = self.to_camel_case(folder_name)

                    save_folder = os.path.join(download_dir, folder_name)
                    os.makedirs(save_folder, exist_ok=True)

                    file_name = self.to_camel_case(photo.filename)
                    self.download_file(photo, save_folder, file_name)
                except Exception as e:
                    print(f"Failed to download {photo.filename}: {e}")

            self.status_label.config(text="Download complete!", fg="green")
            messagebox.showinfo("Success", "All items downloaded successfully!")
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self.status_label.config(text="")


if __name__ == "__main__":
    root = Tk()
    app = iCloudPhotoDownloader(root)
    root.mainloop()
