"""send_message / get_messages: базовое поведение переписки."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tool_registry as tools  # noqa: E402
from tests.tools_testkit import _paths  # noqa: E402

class MessageToolsTests(unittest.TestCase):
    """send_message / get_messages: переписка агента с создателем.

    get_messages: по умолчанию — постраничная выдача всей переписки;
    непрочитанные показанные сообщения получают отметку о переходе
    в прочитанные.
    """

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-msgtools-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = _paths(self.tmp / "memory.md", name="Марвин")

    def test_send_message_appends_agent_message(self):
        out = tools.execute_tool(
            "send_message", json.dumps({"text": "Привет, создатель!"}), self.paths
        )
        self.assertEqual(out, "Сообщение отправлено создателю")
        data = json.loads(self.paths.messages.read_text(encoding="utf-8"))
        self.assertEqual(len(data["messages"]), 1)
        message = data["messages"][0]
        self.assertEqual(message["from"], "agent")
        self.assertEqual(message["text"], "Привет, создатель!")
        self.assertTrue(message["timestamp"])

    def test_get_messages_empty_conversation(self):
        out = tools.execute_tool("get_messages", None, self.paths)
        self.assertEqual(out, "(переписки с создателем ещё нет)")

    def test_get_messages_does_not_use_removed_force_switch(self):
        from storage import SENDER_CREATOR, append_message

        append_message(self.paths.messages, SENDER_CREATOR, "привет")
        out = tools.execute_tool("get_messages", '{"force": true}', self.paths)
        self.assertIn("Переписка: показано 1 из 1", out)
        self.assertNotIn("параметр 'force' удалён", out)

    def _append_dialog(self, count: int = 12):
        """Чередование: нечётные — создатель, чётные — агент."""
        from storage import SENDER_AGENT, SENDER_CREATOR, append_message

        for i in range(1, count + 1):
            append_message(
                self.paths.messages,
                SENDER_CREATOR if i % 2 else SENDER_AGENT,
                f"сообщение {i}",
            )

    def test_get_messages_defaults_to_full_history_with_read_state(self):
        self._append_dialog(12)
        out = tools.execute_tool("get_messages", "{}", self.paths)
        lines = out.splitlines()
        self.assertEqual(
            lines[0], "Переписка: показано 10 из 12 сообщений (от старых к новым):"
        )
        self.assertEqual(len(lines), 12)  # шапка + 10 сообщений + подсказка
        self.assertNotIn("сообщение 1:", out)  # показана страница [2..11]
        self.assertIn("Марвин: сообщение 4", out)
        self.assertIn("Создатель: сообщение 3", out)
        self.assertIn(
            "сообщение 3 (не прочитано) (стало прочитанным)", out
        )
        self.assertIn(
            "сообщение 5 (не прочитано) (стало прочитанным)", out
        )
        self.assertIn("сообщение 4 (прочитано)", out)
        self.assertNotIn("сообщение 3 (прочитано)", out)
        # каждая строка помечена номером и состоянием прочитанности
        for line in lines[1:-1]:
            self.assertRegex(line, r"^\[\d+\] \[")
            self.assertRegex(
                line, r"\((?:не )?прочитано\)(?: \(стало прочитанным\))?$"
            )

    def test_get_messages_marks_shown_unread_read(self):
        from storage import SENDER_CREATOR, append_message

        append_message(self.paths.messages, SENDER_CREATOR, "привет")
        first = tools.execute_tool("get_messages", "{}", self.paths)
        self.assertIn("привет (не прочитано) (стало прочитанным)", first)
        saved = json.loads(self.paths.messages.read_text(encoding="utf-8"))
        self.assertTrue(saved["messages"][0]["read"])
        second = tools.execute_tool("get_messages", "{}", self.paths)
        self.assertIn("привет (прочитано)", second)
        self.assertNotIn("не прочитано", second)

    def test_get_messages_agent_messages_are_read(self):
        # агент сам писал — сообщение сразу прочитанное
        tools.execute_tool("send_message", '{"text": "сам писал"}', self.paths)
        out = tools.execute_tool("get_messages", "{}", self.paths)
        self.assertIn("сам писал (прочитано)", out)

    def test_full_history_preserved_in_file(self):
        # в messages.json хранится вся переписка, а не только последние 10
        from storage import SENDER_AGENT, append_message

        for i in range(15):
            tools.execute_tool(
                "send_message", json.dumps({"text": f"письмо {i}"}), self.paths
            )
        data = json.loads(self.paths.messages.read_text(encoding="utf-8"))
        self.assertEqual(len(data["messages"]), 15)
        self.assertEqual(data["messages"][0]["text"], "письмо 0")

    def test_send_message_requires_nonempty_string(self):
        for args in ("{}", '{"text": ""}', '{"text": "   "}', '{"text": 42}'):
            with self.subTest(args=args):
                out = tools.execute_tool("send_message", args, self.paths)
                self.assertTrue(out.startswith("Error: invalid arguments"), out)

    def test_send_message_creates_messages_file(self):
        # файла ещё нет — tool сам создаёт переписку с нуля
        self.assertFalse(self.paths.messages.exists())
        tools.execute_tool("send_message", '{"text": "первое"}', self.paths)


if __name__ == "__main__":
    unittest.main()
