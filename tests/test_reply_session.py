"""Тесты постоянной отправки сообщений в reply-режиме."""

import json
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import reply_session
from storage import SENDER_CREATOR


@contextmanager
def _no_output(_enabled):
    yield


class _FakeWatcher:
    instances = []

    def __init__(self, path, seen_count, callback):
        self.started = False
        self.stopped = False
        self.seen_count = seen_count
        self.callback = callback
        self.__class__.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class ReplySessionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-reply-session-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.path = self.root / "messages.json"
        self.paths = SimpleNamespace(messages=self.path)
        _FakeWatcher.instances.clear()

    def test_sends_message_and_reads_next_one_without_restarting(self):
        with mock.patch.object(reply_session, "create_reply_session", return_value=object()), \
             mock.patch.object(reply_session, "ReplyWatcher", _FakeWatcher), \
             mock.patch.object(reply_session, "reply_output", _no_output), \
             mock.patch.object(reply_session, "read_reply", side_effect=["строка 1\nстрока 2", None]):
            reply_session.run_reply_session(self.paths, 4, lambda message, index: None)

        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["messages"][-1]["from"], SENDER_CREATOR)
        self.assertEqual(data["messages"][-1]["text"], "строка 1\nстрока 2")
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(len(_FakeWatcher.instances), 1)
        self.assertTrue(_FakeWatcher.instances[0].started)
        self.assertTrue(_FakeWatcher.instances[0].stopped)

    def test_empty_message_does_not_leave_session(self):
        with mock.patch.object(reply_session, "create_reply_session", return_value=None), \
             mock.patch.object(reply_session, "ReplyWatcher", _FakeWatcher), \
             mock.patch.object(reply_session, "reply_output", _no_output), \
             mock.patch.object(reply_session, "read_reply", side_effect=["   ", None]), \
             mock.patch.object(reply_session, "append_message") as append:
            reply_session.run_reply_session(self.paths, 0, lambda message, index: None)

        append.assert_not_called()
        self.assertTrue(_FakeWatcher.instances[0].stopped)


if __name__ == "__main__":
    unittest.main()
