from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from icloud_downloader.messages import sanitize_filename
from icloud_downloader.services import Cancelled, download_library, save_chunks


class Response:
    def __init__(self, chunks=(b'hello', b' world'), fail=False):
        self.chunks, self.fail = chunks, fail

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def raise_for_status(self):
        if self.fail:
            raise RuntimeError('HTTP 403')

    def iter_content(self, size):
        yield from self.chunks


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cancel = threading.Event()

    def test_atomic_write_preserves_existing_files(self):
        target = self.root / 'memory.jpg'
        target.write_bytes(b'original')
        self.assertEqual(save_chunks((b'new',), target, self.cancel), 3)
        self.assertEqual(target.read_bytes(), b'original')
        self.assertEqual((self.root / 'memory (2).jpg').read_bytes(), b'new')

    def test_cancellation_and_failure_remove_partials(self):
        def interrupted():
            yield b'partial'
            self.cancel.set()
            yield b'unfinished'
        with self.assertRaises(Cancelled):
            save_chunks(interrupted(), self.root / 'video.mov', self.cancel)
        self.assertEqual(list(self.root.iterdir()), [])
        self.cancel.clear()
        def failed():
            yield b'partial'
            raise OSError('Lost connection')
        with self.assertRaises(OSError):
            save_chunks(failed(), self.root / 'video.mov', self.cancel)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_drive_uses_nodes_and_keeps_hierarchy(self):
        file = SimpleNamespace(name='Notes.txt', type='file', size=11, open=Mock(return_value=Response()), delete=Mock())
        folder = SimpleNamespace(name='Projects', type='folder', get_children=lambda: [file])
        api = SimpleNamespace(drive=SimpleNamespace(root=SimpleNamespace(get_children=lambda: [folder])))
        result = download_library(api, 'drive', self.root, self.cancel, Mock())
        self.assertEqual((result.saved, result.failed), (1, 0))
        self.assertEqual((self.root / 'iCloud Drive Files/Projects/Notes.txt').read_bytes(), b'hello world')
        file.delete.assert_not_called()

    def test_streamed_photos_delete_only_after_success(self):
        photo = SimpleNamespace(filename='Moment.jpg', created=datetime(2026, 10, 1),
            download_url=lambda: 'https://example.invalid/original', delete=Mock())
        api = SimpleNamespace(photos=SimpleNamespace(all=[photo]), session=SimpleNamespace(get=Mock(return_value=Response(fail=True))))
        result = download_library(api, 'photos', self.root, self.cancel, Mock(), delete=True)
        self.assertEqual((result.saved, result.failed), (0, 1))
        photo.delete.assert_not_called()
        api.session.get.return_value = Response()
        photo.delete.side_effect = lambda: self.assertTrue((self.root / 'Photos/2026-10/Moment.jpg').is_file())
        result = download_library(api, 'photos', self.root, self.cancel, Mock(), delete=True)
        self.assertEqual((result.saved, result.failed, result.bytes_saved), (1, 0, 11))
        photo.delete.assert_called_once()

    def test_cancel_returns_completed_counts(self):
        photo = SimpleNamespace(filename='a.jpg', created=None, download_url=lambda: 'url', delete=Mock())
        api = SimpleNamespace(photos=SimpleNamespace(all=[photo, photo]), session=SimpleNamespace(get=lambda *a, **k: Response()))
        def report(text, data=None):
            if text.startswith('Saved'):
                self.cancel.set()
        result = download_library(api, 'photos', self.root, self.cancel, report)
        self.assertEqual(result.saved, 1)
        self.assertTrue(result.cancelled)

    def test_windows_names_and_traversal_are_sanitized(self):
        for value in ('CON', 'nul.txt', 'COM1.jpg', 'LPT9'):
            self.assertTrue(sanitize_filename(value).startswith('_'))
        for value in ('..', '../../escape', 'a\\b', 'bad\x00name'):
            cleaned = sanitize_filename(value)
            self.assertNotIn('/', cleaned)
            self.assertNotIn('\\', cleaned)
            self.assertNotIn('\x00', cleaned)
            self.assertNotEqual(cleaned, '..')


if __name__ == '__main__':
    unittest.main()
