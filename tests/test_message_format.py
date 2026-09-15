"""Общий формат строк переписки для CLI и get_messages."""

import unittest

from message_format import format_message_line


class MessageFormatTests(unittest.TestCase):
    def test_cli_line_has_status_without_cursor(self):
        message = {"from": "creator", "timestamp": "t", "text": "привет", "read": False}
        self.assertEqual(
            format_message_line(message, "bot"),
            "[t] Создатель: привет (не прочитано)",
        )

    def test_tool_line_adds_cursor_and_agent_label(self):
        message = {"from": "agent", "timestamp": "t", "text": "ответ", "read": True}
        self.assertEqual(
            format_message_line(message, "bot", index=3),
            "[3] [t] bot: ответ (прочитано)",
        )


if __name__ == "__main__":
    unittest.main()
