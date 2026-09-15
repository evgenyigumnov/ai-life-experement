"""get_messages: пагинация, курсор, лимиты, валидация аргументов."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tool_registry as tools  # noqa: E402
from tests.tools_testkit import _paths  # noqa: E402


class MessagePagingTests(unittest.TestCase):
    """Постраничная выдача переписки: limit, cursor, read-статусы страниц."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-msgtools-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = _paths(self.tmp / "memory.md", name="Марвин")

    def _append_dialog(self, count: int = 12):
        """Чередование: нечётные — создатель, чётные — агент."""
        from storage import SENDER_AGENT, SENDER_CREATOR, append_message

        for i in range(1, count + 1):
            append_message(
                self.paths.messages,
                SENDER_CREATOR if i % 2 else SENDER_AGENT,
                f"сообщение {i}",
            )

    def test_get_messages_limit_and_cursor_page_full_history(self):
        from storage import SENDER_CREATOR, append_message

        for i in range(1, 4):
            append_message(self.paths.messages, SENDER_CREATOR, f"письмо {i}")
        first = tools.execute_tool(
            "get_messages", '{"limit": 2}', self.paths
        )
        self.assertIn("Переписка: показано 2 из 3", first)
        self.assertIn("письмо 2", first)
        self.assertIn("письмо 3", first)
        self.assertNotIn("письмо 1", first)
        self.assertIn(
            "(есть более старые сообщения: следующая страница — "
            "get_messages(cursor=1))",
            first,
        )
        second = tools.execute_tool("get_messages", '{"cursor": 1}', self.paths)
        self.assertIn("Переписка: показано 1 из 3", second)
        self.assertIn("письмо 1", second)
        self.assertNotIn("есть более старые", second)

    def test_get_messages_default_shows_last_page_with_indices(self):
        self._append_dialog(12)
        out = tools.execute_tool("get_messages", "{}", self.paths)
        lines = out.splitlines()
        self.assertEqual(
            lines[0], "Переписка: показано 10 из 12 сообщений (от старых к новым):"
        )
        self.assertEqual(len(lines), 12)  # шапка + 10 сообщений + подсказка
        self.assertTrue(lines[1].startswith("[2] ["))
        self.assertIn("Марвин: сообщение 4", out)
        self.assertIn("Создатель: сообщение 3", out)
        self.assertNotIn("сообщение 1:", out)  # страница — последние 10
        self.assertIn(
            "(есть более старые сообщения: следующая страница — "
            "get_messages(cursor=2))",
            out,
        )

    def test_get_messages_cursor_pagination_walks_to_beginning(self):
        self._append_dialog(12)
        page = tools.execute_tool("get_messages", '{"cursor": 2}', self.paths)
        self.assertIn("показано 2 из 12", page)
        self.assertTrue("сообщение 1" in page and "сообщение 2" in page)
        self.assertNotIn("есть более старые", page)  # дошли до начала

    def test_get_messages_cursor_browses_history(self):
        self._append_dialog(4)
        out = tools.execute_tool("get_messages", '{"cursor": 3}', self.paths)
        self.assertIn("Переписка: показано 3 из 4", out)

    def test_get_messages_marks_only_shown_page(self):
        # просмотр последней страницы не помечает прочитанными невыданные
        from storage import SENDER_CREATOR, append_message

        for i in range(1, 7):
            append_message(self.paths.messages, SENDER_CREATOR, f"письмо {i}")
        out = tools.execute_tool(
            "get_messages", '{"limit": 3}', self.paths
        )
        self.assertIn("письмо 6", out)
        self.assertIn(
            "письмо 6 (не прочитано) (стало прочитанным)", out
        )
        saved = json.loads(self.paths.messages.read_text(encoding="utf-8"))
        self.assertEqual(
            [m["read"] for m in saved["messages"]],
            [False, False, False, True, True, True],
        )

    def test_get_messages_old_file_without_read_flags_migrates(self):
        # старый messages.json без флага read: вся переписка уже прочитана
        raw = {
            "agent": "Марвин",
            "messages": [
                {"timestamp": "2026-09-11T00:00:00", "from": "creator", "text": "старое"},
            ],
        }
        self.paths.messages.write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8"
        )
        out = tools.execute_tool("get_messages", "{}", self.paths)
        self.assertIn("старое (прочитано)", out)

    def test_get_messages_empty_page_before_start(self):
        self._append_dialog(3)
        out = tools.execute_tool("get_messages", '{"cursor": 0}', self.paths)
        self.assertEqual(
            out, "(более старых сообщений нет; всего сообщений в переписке: 3)"
        )

    def test_get_messages_validates_arguments(self):
        self._append_dialog(2)
        bad_args = [
            '{"limit": 0}',
            '{"limit": 51}',
            '{"limit": 2.5}',
            '{"limit": "десять"}',
            '{"cursor": -1}',
            '{"cursor": 1.5}',
            '{"cursor": "два"}',
        ]
        for args in bad_args:
            with self.subTest(args=args):
                out = tools.execute_tool("get_messages", args, self.paths)
                self.assertTrue(out.startswith("Error: invalid arguments"), out)



if __name__ == "__main__":
    unittest.main()
