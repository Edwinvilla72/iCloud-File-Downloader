"""Cancellable downloads, independent of the desktop interface."""
from dataclasses import dataclass
from pathlib import Path
import os
import tempfile

from .messages import sanitize_filename


class Cancelled(Exception):
    pass


@dataclass
class TransferResult:
    saved: int = 0
    failed: int = 0
    bytes_saved: int = 0
    cancelled: bool = False


def check_cancelled(cancel):
    if cancel.is_set():
        raise Cancelled("Transfer stopped. Completed files are kept.")


def unique_path(path):
    """Never overwrite an earlier download, including same-name cloud assets."""
    candidate = path
    index = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        index += 1
    return candidate


def save_chunks(chunks, target, cancel):
    """Publish only a complete file; clean up partials on error or cancellation."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target = unique_path(target)
    fd, partial = tempfile.mkstemp(prefix=".icloud-", suffix=".part", dir=target.parent)
    size = 0
    try:
        with os.fdopen(fd, "wb") as stream:
            for chunk in chunks:
                check_cancelled(cancel)
                if chunk:
                    stream.write(chunk)
                    size += len(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        check_cancelled(cancel)
        os.replace(partial, target)
        return size
    finally:
        if os.path.exists(partial):
            os.unlink(partial)


def download_library(api, kind, directory, cancel, report, delete=False):
    result = TransferResult()
    destination = Path(directory)

    def save(item, path, photo=False):
        check_cancelled(cancel)
        report(f"Downloading {path.name}")
        try:
            if photo:
                url = item.download_url()
                if not url:
                    raise RuntimeError("Apple returned no photo data")
                with api.session.get(url, stream=True, timeout=60) as response:
                    response.raise_for_status()
                    size = save_chunks(response.iter_content(256 * 1024), path, cancel)
            else:
                with item.open(stream=True, timeout=60) as response:
                    # pyicloud returns a synthetic response for zero-byte files.
                    if getattr(item, "size", None) != 0:
                        response.raise_for_status()
                    size = save_chunks(response.iter_content(256 * 1024), path, cancel)
            result.saved += 1
            result.bytes_saved += size
            report(f"Saved · {path.name}", result)
            if delete:
                check_cancelled(cancel)
                outcome = item.delete()
                if outcome is False:
                    raise RuntimeError("Apple did not confirm deletion")
                report(f"Removed from iCloud · {path.name}")
        except Cancelled:
            raise
        except Exception as error:
            result.failed += 1
            report(f"Needs attention · {path.name}: {error}", result)

    try:
        if kind == "photos":
            report("Connecting to your photo library…")
            for photo in api.photos.all:
                check_cancelled(cancel)
                created = getattr(photo, "created", None)
                month = created.strftime("%Y-%m") if created else "Unknown date"
                name = sanitize_filename(getattr(photo, "filename", "Untitled photo"), 180)
                save(photo, destination / "Photos" / month / name, photo=True)
        else:
            report("Reading your iCloud Drive folders…")

            def walk(folder, path):
                check_cancelled(cancel)
                path.mkdir(parents=True, exist_ok=True)
                for node in folder.get_children():
                    check_cancelled(cancel)
                    target = path / sanitize_filename(node.name, 180)
                    if node.type == "folder":
                        walk(node, target)
                    elif node.type == "file":
                        save(node, target)

            walk(api.drive.root, destination / "iCloud Drive Files")
    except Cancelled:
        result.cancelled = True
    return result
