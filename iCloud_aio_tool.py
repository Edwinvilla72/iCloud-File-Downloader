"""iCloud File Downloading Tool desktop entry point. Run with --demo to explore without an account."""
import argparse
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="iCloud File Downloading Tool")
    parser.add_argument("--demo", action="store_true", help="Explore a read-only interface with fictional sample data")
    parser.add_argument("--screenshot", type=Path, help="Render an offscreen preview to a PNG file")
    parser.add_argument("--page", choices=("overview", "photos", "drive", "messages", "transfers", "preferences"), default="overview")
    args = parser.parse_args()
    if args.screenshot:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFont, QFontDatabase, QPalette, QColor
    from PySide6.QtWidgets import QApplication
    from icloud_downloader import APP_NAME
    from icloud_downloader.design import ACCENT, INK
    from icloud_downloader.window import MainWindow

    app = QApplication(sys.argv[:1])
    app.setApplicationName("iCloud_aio_tool")
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("iCloud File Downloader")
    # AppKit controls need a native window context; use Fusion for offscreen
    # preview exports while keeping the macOS style in the actual Mac app.
    native_mac = sys.platform == "darwin" and app.platformName() == "cocoa"
    app.setStyle("macOS" if native_mac else "Fusion")
    # Use the installed Apple system font on macOS; other platforms keep their
    # own system UI font. No Apple font files are bundled with the application.
    font = QFont(".AppleSystemUIFont") if sys.platform == "darwin" else QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPointSizeF(13 if sys.platform == "darwin" else 10)
    app.setFont(font)
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f5f5f7"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Text, QColor(INK))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(INK))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(INK))
    app.setPalette(palette)
    window = MainWindow(demo=args.demo or bool(args.screenshot))
    window.navigate(("overview", "photos", "drive", "messages", "transfers", "preferences").index(args.page))
    window.show()
    if args.screenshot:
        window.resize(1120, 760)
        def capture():
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            if not window.grab().save(str(args.screenshot)):
                raise RuntimeError("Could not save preview image")
            window.close()
            app.quit()
        QTimer.singleShot(400, capture)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
