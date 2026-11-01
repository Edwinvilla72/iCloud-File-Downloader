# Desktop development

The desktop interface uses PySide6 (Qt Widgets). The README contains the original project text and is kept separate from this technical guide.

## Run

```sh
python -m pip install -r requirements.txt
python iCloud_aio_tool.py
```

Use `--demo` to view sample data without signing in. Use `--screenshot previews/overview.png` to render an offscreen preview and exit.

## Files

- `iCloud_aio_tool.py`: application entry point and palette.
- `icloud_downloader/design.py`: flat styles, the `#9ae2ff` accent, and control icons.
- `icloud_downloader/window.py`: layouts, navigation, dialogs, and worker signals.
- `icloud_downloader/services.py`: streamed downloads, cancellation, and complete-file writes.
- `icloud_downloader/messages.py`: local SQLite snapshots, text decoding, and export.

Qt layouts resize controls with the window. Workers handle network access, database queries, and image decoding; their signals update widgets on the GUI thread.

## Checks and packaging

```sh
python -m unittest discover -s tests -v
python -m PyInstaller --noconfirm iCloud_aio_tool.spec
```

Build on the target platform. Windows produces `dist/iCloud_aio_tool.exe`; macOS produces `dist/iCloud File Downloading Tool.app`. The release workflow builds both. Live Apple authentication and downloads require separate account testing.
