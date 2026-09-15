"""Тесты статуса непрочитанных сообщений создателя в prompt."""


import shutil
import tempfile
import unittest

from tests.agent_common import (
    agent, append_message, load_messages, mark_messages_read,
    make_agent_dir, SENDER_AGENT, SENDER_CREATOR, _paths,
)
from tools_chat import handle_get_messages


class UnreadMessagesTests(unittest.TestCase):
    """В prompt попадает только сигнал, а не содержимое переписки."""

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-unread-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)
        append_message(self.paths.messages, SENDER_CREATOR, "первое сообщение")
        append_message(self.paths.messages, SENDER_AGENT, "ответ агента")
        append_message(self.paths.messages, SENDER_CREATOR, "второе сообщение")

    @staticmethod
    def _data(**extra) -> dict:
        return {"iterations": [], **extra}

    def test_unread_status_excludes_message_text(self):
        messages = agent.build_messages(self._data(), self.paths)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        content = messages[-1]["content"]
        self.assertIn("У тебя есть непрочитанные сообщения от создателя", content)
        self.assertIn("2 сообщения", content)
        self.assertIn("get_messages", content)
        self.assertNotIn("первое сообщение", content)
        self.assertNotIn("второе сообщение", content)

    def test_status_ignores_removed_delivery_counter(self):
        messages = agent.build_messages(
            self._data(seen_creator_messages=0), self.paths
        )
        content = messages[-1]["content"]
        self.assertIn("2 сообщения", content)
        self.assertNotIn("первое сообщение", content)
        self.assertNotIn("второе сообщение", content)

    def test_status_counts_only_unread_creator_messages(self):
        mark_messages_read(
            self.paths.messages,
            load_messages(self.paths.messages),
            [0],
        )
        content = agent.build_messages(self._data(), self.paths)[-1]["content"]
        self.assertIn("1 сообщение", content)
        self.assertNotIn("первое сообщение", content)
        self.assertNotIn("2 сообщения", content)

    def test_get_messages_clears_status_for_next_cycle(self):
        result = handle_get_messages({}, self.paths)
        self.assertIn("первое сообщение", result)
        content = agent.build_messages(self._data(), self.paths)[-1]["content"]
        self.assertNotIn("непрочитанные сообщения", content)
        self.assertNotIn("get_messages", content)

    def test_status_is_absent_when_all_messages_are_read(self):
        mark_messages_read(
            self.paths.messages,
            load_messages(self.paths.messages),
            [0, 2],
        )
        messages = agent.build_messages(self._data(), self.paths)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertNotIn("непрочитанные сообщения", messages[-1]["content"])
        self.assertNotIn("Сейчас нет новых сообщений", messages[-1]["content"])
        self.assertNotIn("get_messages", messages[-1]["content"])

    def test_custom_legacy_text_template_is_not_read(self):
        (self.folder / "unread-messages.md").write_text(
            "СЕКРЕТ: {messages}", encoding="utf-8"
        )
        content = agent.build_messages(self._data(), self.paths)[-1]["content"]
        self.assertIn("У тебя есть непрочитанные сообщения", content)
        self.assertNotIn("СЕКРЕТ", content)
        self.assertNotIn("первое сообщение", content)

    def test_status_remains_user_message_after_wake_up(self):
        data = self._data(session=2, woke_up_at="2026-09-10T00:00:00")
        messages = agent.build_messages(data, self.paths)
        self.assertEqual(
            [m["role"] for m in messages], ["system", "user", "user"]
        )
        self.assertIn("проснулся", messages[1]["content"])
        self.assertIn("У тебя есть непрочитанные сообщения", messages[2]["content"])
        self.assertNotIn("второе сообщение", messages[2]["content"])

    def test_broken_messages_file_means_no_status(self):
        self.paths.messages.write_text("{не json", encoding="utf-8")
        messages = agent.build_messages(self._data(), self.paths)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertNotIn("непрочитанные сообщения", messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
