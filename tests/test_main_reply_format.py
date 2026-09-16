"""Оформление переписки в режиме ``main.py <имя> reply``."""

import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent_console  # noqa: E402
import main_reply  # noqa: E402
from tests.helpers import env, make_agent_dir  # noqa: E402


class ReplyDisplayTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-reply-format-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.folder = make_agent_dir(self.root, "bot")

    def _write_messages(self, count: int):
        messages = [
            {
                "timestamp": f"2026-09-12T10:{index:02}:00",
                "from": "creator" if index % 2 else "agent",
                "text": f"сообщение {index}",
                "read": True,
            }
            for index in range(count)
        ]
        self.folder.joinpath("messages.json").write_text(
            json.dumps({"agent": "bot", "messages": messages}, ensure_ascii=False),
            encoding="utf-8",
        )

    def _run(self, text="") -> str:
        with mock.patch("builtins.input", return_value=text), \
             env(AGENTS_ROOT=str(self.root)), \
             redirect_stdout(StringIO()) as output:
            main_reply._reply_mode("bot")
        return output.getvalue()

    def test_history_is_framed_and_shows_all_absolute_message_numbers(self):
        self._write_messages(12)
        output = self._run()

        self.assertIn("═" * 24, output)
        self.assertIn("─" * 72, output)
        self.assertIn("вся переписка", output)
        self.assertIn("номера совпадают с get_messages", output)
        self.assertIn("[0] [2026-09-12T10:00:00]", output)
        self.assertIn("[2] [2026-09-12T10:02:00]", output)
        self.assertIn("[11] [2026-09-12T10:11:00]", output)
        self.assertIn("👤", output)
        self.assertIn("🤖", output)

    def test_reply_display_uses_readable_agent_color(self):
        self._write_messages(2)
        with mock.patch.object(agent_console, "USE_COLOR", True):
            output = self._run()

        self.assertIn(agent_console._Colors.CYAN, output)
        self.assertIn(agent_console._Colors.GREEN, output)
        self.assertIn(main_reply.AGENT_REPLY_COLOR, output)
        self.assertNotIn(agent_console._Colors.MAGENTA, output)
        self.assertIn(agent_console._Colors.RESET, output)

    def test_tty_uses_persistent_session_and_passes_history_cursor(self):
        self._write_messages(3)
        with mock.patch.object(main_reply, "_is_interactive_terminal", return_value=True), \
             mock.patch.object(main_reply, "run_reply_session") as run_session, \
             env(AGENTS_ROOT=str(self.root)), \
             redirect_stdout(StringIO()):
            main_reply._reply_mode("bot")

        run_session.assert_called_once()
        paths, count, callback = run_session.call_args.args
        self.assertEqual(paths.messages, self.folder / "messages.json")
        self.assertEqual(count, 3)
        self.assertTrue(callable(callback))


if __name__ == "__main__":
    unittest.main()
