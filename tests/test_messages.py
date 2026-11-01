import csv
import queue
import sqlite3
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from iCloud_aio_tool import iCloudDataManagerApp, message_text


def attributed_body(text):
    """Minimal typedstream archive, including multi-byte string lengths."""
    def shared(value):
        return b'\x84' + bytes([len(value)]) + value

    raw = text.encode('utf-8')
    length = bytes([len(raw)]) if len(raw) < 128 else b'\x81' + struct.pack('<H', len(raw))
    return (b'\x04\x0bstreamtyped\x81\xe8\x03' + shared(b'@') + b'\x84\x84'
            + shared(b'NSAttributedString') + b'\x00\x84' + shared(b'NSObject')
            + b'\x00\x85' + shared(b'@') + b'\x84\x84' + shared(b'NSString')
            + b'\x01\x84' + shared(b'NSObject') + b'\x00\x85' + shared(b'+')
            + length + raw + b'\x86\x86')


class MessagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.app = iCloudDataManagerApp.__new__(iCloudDataManagerApp)
        self.app.log = Mock()

    def database(self):
        path = self.home / 'Library' / 'Messages' / 'chat.db'
        path.parent.mkdir(parents=True)
        con = sqlite3.connect(path)
        self.addCleanup(con.close)
        con.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA wal_autocheckpoint=0;
            CREATE TABLE message (date INTEGER, is_from_me INTEGER, handle_id INTEGER,
                                  text TEXT, attributedBody BLOB);
            CREATE TABLE handle (id TEXT);
            CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
            CREATE TABLE attachment (filename TEXT, transfer_name TEXT);
            CREATE TABLE message_attachment_join (message_id INTEGER, attachment_id INTEGER);
        ''')
        return path, con

    def test_text_decoder_preserves_long_unicode_and_newlines(self):
        for text in ('Hello 👋\nNext line', 'Long message 🐈 ' * 100):
            with self.subTest(text_length=len(text)):
                self.assertEqual(message_text(None, attributed_body(text)), text)
        self.assertEqual(message_text('plain text', b'bad'), 'plain text')
        self.assertEqual(message_text(None, None), '')
        self.assertIn('unsupported', message_text(None, b'bad'))

    def test_snapshot_includes_committed_wal_data(self):
        path, con = self.database()
        con.execute("INSERT INTO message VALUES (1, 1, NULL, 'in WAL', NULL)")
        con.commit()
        self.assertTrue(Path(str(path) + '-wal').exists())
        self.app._messages_temp = tempfile.TemporaryDirectory(dir=self.temp.name)
        self.addCleanup(self.app._messages_temp.cleanup)
        with patch('iCloud_aio_tool.Path.home', return_value=self.home), patch(
                'iCloud_aio_tool.platform.system', return_value='Darwin'):
            snapshot = self.app.ensure_messages_db_copy()
        with sqlite3.connect(snapshot) as copied:
            self.assertEqual(copied.execute('SELECT text FROM message').fetchone()[0], 'in WAL')
        self.assertFalse((path.parent / 'DBCopies').exists())

    def test_pagination_and_export_with_low_sql_variable_limit(self):
        path, con = self.database()
        for index in range(250):
            con.execute('INSERT INTO message VALUES (?, 1, NULL, NULL, ?)',
                        (index, attributed_body(f'Message {index} 👋')))
            con.execute('INSERT INTO chat_message_join VALUES (1, ?)', (index + 1,))
        attachment = self.home / 'photo.txt'
        attachment.write_text('attachment')
        con.execute('INSERT INTO attachment VALUES (?, ?)', (str(attachment), attachment.name))
        con.execute('INSERT INTO message_attachment_join VALUES (1, 1)')
        con.commit()
        latest = self.app._fetch_messages_chunk(con, 1, 0, 100)
        older = self.app._fetch_messages_chunk(con, 1, 100, 100)
        self.assertEqual((latest[0][0], latest[-1][0]), (151, 250))
        self.assertEqual((older[0][0], older[-1][0]), (51, 150))
        self.assertEqual(latest[-1][-1], 'Message 249 👋')
        self.app.messages_db_copy = str(path)
        connect = sqlite3.connect

        def limited_connect(*args, **kwargs):
            connection = connect(*args, **kwargs)
            connection.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 10)
            return connection

        with patch('iCloud_aio_tool.sqlite3.connect', side_effect=limited_connect):
            exported = self.app._export_chat_by_rowid(1, 'Test chat', str(self.home / 'exports'))
        with exported.open(newline='') as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 250)
        self.assertEqual(rows[-1]['text'], 'Message 249 👋')
        self.assertEqual((exported.parent / 'attachments' / '1_photo.txt').read_text(), 'attachment')

    def test_worker_delivers_ui_callback_on_main_thread_and_prevents_overlap(self):
        self.app._ui_queue = queue.Queue()
        self.app._messages_busy = False
        self.app.messages_status = Mock()
        threads = []
        done = Mock(side_effect=lambda _: threads.append(threading.current_thread()))
        work = Mock(side_effect=lambda: threading.current_thread())
        self.app._messages_task('Loading', work, done)
        self.app._messages_task('Duplicate', work, done)
        deliver = self.app._ui_queue.get(timeout=5)
        done.assert_not_called()
        deliver()
        work.assert_called_once()
        self.assertIsNot(done.call_args.args[0], threading.main_thread())
        self.assertEqual(threads, [threading.main_thread()])

    def test_render_yields_between_batches(self):
        self.app.root = Mock()
        self.app.messages_status = Mock()
        self.app.conv_canvas = Mock()
        self.app.current_loaded = 0
        self.app._messages_busy = True
        self.app._add_message_bubble = Mock()
        rows = [(i, i, 1, '', 'hello') for i in range(25)]
        page = Mock()
        self.app._render_message_batch(page, rows, {}, 0, 25, True)
        self.assertEqual(self.app._add_message_bubble.call_count, 10)
        self.assertTrue(self.app._messages_busy)
        self.app.root.after.call_args.args[1]()
        self.assertEqual(self.app._add_message_bubble.call_count, 20)
        self.app.root.after.call_args.args[1]()
        self.assertEqual(self.app._add_message_bubble.call_count, 25)
        self.assertEqual(self.app.current_loaded, 25)
        self.assertFalse(self.app._messages_busy)


if __name__ == '__main__':
    unittest.main()
