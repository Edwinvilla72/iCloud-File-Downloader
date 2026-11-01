import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import io
import time
import threading
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace

from PIL import Image
from PySide6.QtCore import QThread, QUrl
from PySide6.QtGui import QTextDocument
from PySide6.QtWidgets import QApplication

from icloud_downloader.window import MainWindow


class DesktopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = MainWindow(demo=True)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.pool.waitForDone(5000)
        self.app.processEvents()
        self.window.close()
        self.app.processEvents()

    def pump_until(self, predicate):
        deadline = time.monotonic() + 5
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.assertTrue(predicate())

    def test_every_page_navigates_and_preview_search_filters(self):
        for index in range(6):
            self.window.nav_buttons[index].click()
            self.assertEqual(self.window.stack.currentIndex(), index)
            self.assertTrue(self.window.nav_buttons[index].isChecked())
        self.window.chat_search.setText('Family')
        visible = [self.window.chat_list.item(i).text() for i in range(self.window.chat_list.count()) if not self.window.chat_list.item(i).isHidden()]
        self.assertEqual(len(visible), 1)
        self.assertIn('Family', visible[0])

    def test_workers_keep_ui_live_and_deliver_on_gui_thread(self):
        started, release = threading.Event(), threading.Event()
        threads = []
        def work(report, cancel):
            threads.append(QThread.currentThread())
            started.set()
            release.wait(3)
            return 42
        def done(result):
            threads.append(QThread.currentThread())
            self.assertEqual(result, 42)
        self.window._run('messages', work, done)
        self.pump_until(started.is_set)
        self.window.navigate(5)
        self.assertEqual(self.window.stack.currentIndex(), 5)
        self.assertFalse(self.window._run('messages', work, done))
        release.set()
        self.pump_until(lambda: not self.window.jobs)
        self.assertIsNot(threads[0], self.app.thread())
        self.assertIs(threads[1], self.app.thread())

    def test_worker_error_recovers_controls(self):
        def work(report, cancel):
            raise PermissionError('Permission denied')
        with patch('icloud_downloader.window.QMessageBox.warning') as warning:
            self.window._run('messages', work, Mock())
            self.pump_until(lambda: not self.window.jobs)
            warning.assert_called_once()
            self.assertIn('Full Disk Access', warning.call_args.args[2])
        self.assertTrue(self.window.chat_list.isEnabled())

    def test_conversation_escapes_text_and_prepends_older_rows(self):
        self.window.loaded_messages = 0
        self.window.message_rows = []
        self.window.message_attachments = {}
        self.window._page_loaded((2, [(2, 800000000, 1, '', '<script>hi</script>')], {}))
        self.window._page_loaded((2, [(1, 700000000, 0, 'Alex', 'Older message')], {}))
        plain = self.window.message_view.toPlainText()
        self.assertIn('<script>hi</script>', plain)
        self.assertLess(plain.index('Older message'), plain.index('<script>'))
        self.assertFalse(self.window.more_button.isEnabled())

    def test_attachment_pixels_are_registered_without_gui_disk_reads(self):
        image = Image.new('RGB', (30, 20), '#9ae2ff')
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        self.window.loaded_messages = 0
        self.window.message_rows = []
        self.window.message_attachments = {}
        self.window._page_loaded((1, [(9, 800000000, 1, '', 'Photo')], {9: [('/fictional/photo.png', 'photo.png', stream.getvalue())]}))
        resource = self.window.message_view.document_for_row(0).resource(QTextDocument.ResourceType.ImageResource, QUrl('message-image:9:0'))
        self.assertEqual(resource.width(), 30)

    def test_bubbles_align_by_sender_and_fit_text(self):
        view = self.window.message_view
        view.set_messages([(1, 800000000, 0, 'Alex', 'Incoming'),
                           (2, 800000001, 1, '', 'Outgoing')], {})
        view.doItemsLayout()
        incoming = view.bubbles.layout_for(view.messages.index(0))
        outgoing = view.bubbles.layout_for(view.messages.index(1))
        width = view.viewport().width()
        self.assertEqual(incoming.bubble.left(), view.bubbles.MARGIN)
        self.assertEqual(outgoing.bubble.right(), width - view.bubbles.MARGIN)
        self.assertLess(incoming.bubble.width(), width * 0.6)
        self.assertGreater(outgoing.bubble.left(), incoming.bubble.right())

    def test_bubbles_wrap_after_resizing_and_copy_plain_text(self):
        view = self.window.message_view
        text = '<tag> Long message ' * 25
        view.set_messages([(1, 800000000, 1, '', text)], {})
        wide = view.bubbles.layout_for(view.messages.index(0))
        self.window.splitter.setSizes([450, 250])
        self.app.processEvents()
        narrow = view.bubbles.layout_for(view.messages.index(0))
        self.assertGreaterEqual(narrow.height, wide.height)
        self.assertLessEqual(narrow.bubble.right(), view.viewport().width())
        view.setCurrentIndex(view.messages.index(0))
        view.copy_message()
        self.assertEqual(QApplication.clipboard().text(), text)

    def test_message_copy_does_not_override_search_field_copy(self):
        from PySide6.QtGui import QKeySequence
        from PySide6.QtTest import QTest
        self.window.navigate(3)
        view = self.window.message_view
        view.set_messages([(1, 800000000, 1, '', 'Copied message')], {})
        view.setCurrentIndex(view.messages.index(0))
        view.setFocus()
        self.app.processEvents()
        QTest.keySequence(view, QKeySequence(QKeySequence.StandardKey.Copy))
        self.assertEqual(QApplication.clipboard().text(), 'Copied message')
        self.window.chat_search.setText('Family')
        self.window.chat_search.setFocus()
        self.window.chat_search.selectAll()
        self.app.processEvents()
        QTest.keySequence(self.window.chat_search, QKeySequence(QKeySequence.StandardKey.Copy))
        self.assertEqual(QApplication.clipboard().text(), 'Family')

    def test_preview_download_never_calls_backend(self):
        with patch('icloud_downloader.window.download_library') as download, patch.object(self.window, 'preview_notice') as notice:
            self.window.start_download('photos')
            notice.assert_called_once()
            download.assert_not_called()

    def test_two_factor_flow_requests_and_validates_in_worker(self):
        api = SimpleNamespace(requires_2fa=True, requires_2sa=False,
            request_2fa_code=Mock(return_value=True), is_trusted_session=True)
        worker_threads = []
        def validate(code):
            worker_threads.append(QThread.currentThread())
            self.assertEqual(code, '123456')
            api.requires_2fa = False
            return True
        api.validate_2fa_code = validate
        with patch('icloud_downloader.window.QInputDialog.getText', return_value=('123456', True)):
            self.window._authenticated(api)
            self.pump_until(lambda: self.window.api is api)
        api.request_2fa_code.assert_called_once()
        self.assertIsNot(worker_threads[0], self.app.thread())
        self.assertIsNone(self.window.pending_api)


if __name__ == '__main__':
    unittest.main()
