"""Тесты автоматической загрузки новых ответов агента."""

import shutil
import tempfile
import threading
import unittest
from pathlib import Path

from reply_watcher import ReplyWatcher
from storage import SENDER_AGENT, SENDER_CREATOR, append_message


class ReplyWatcherTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-reply-watch-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.path = self.root / "messages.json"

    def test_reports_only_agent_messages_appended_after_start(self):
        received = []
        ready = threading.Event()

        def on_message(message, index):
            received.append((index, message["text"]))
            ready.set()

        watcher = ReplyWatcher(self.path, 0, on_message, interval=0.01)
        watcher.start()
        try:
            append_message(self.path, SENDER_CREATOR, "мой вопрос")
            append_message(self.path, SENDER_AGENT, "ответ агента")
            self.assertTrue(ready.wait(1.0))
        finally:
            watcher.stop()

        self.assertEqual(received, [(1, "ответ агента")])

    def test_existing_messages_are_not_reprinted(self):
        append_message(self.path, SENDER_AGENT, "старый ответ")
        received = []
        watcher = ReplyWatcher(
            self.path,
            1,
            lambda message, index: received.append((index, message["text"])),
            interval=0.01,
        )
        watcher.start()
        try:
            self.assertFalse(threading.Event().wait(0.05))
        finally:
            watcher.stop()
        self.assertEqual(received, [])


if __name__ == "__main__":
    unittest.main()
