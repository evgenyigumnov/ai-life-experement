"""Безопасный вывод аргументов inspect_image в консоль."""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import agent_console_blocks  # noqa: E402


class VisionConsoleTests(unittest.TestCase):
    def test_url_query_and_fragment_are_not_logged(self):
        args = json.dumps({
            "source": "https://example.org/photo.jpg?token=secret#private",
            "question": "что?",
        })
        output = agent_console_blocks._format_tool_call_block(1, "inspect_image", args)
        self.assertIn("https://example.org/photo.jpg", output)
        self.assertNotIn("secret", output)
        self.assertNotIn("private", output)

    def test_other_tools_keep_their_arguments(self):
        output = agent_console_blocks._format_tool_call_block(
            1, "run_bash", '{"command":"echo secret"}'
        )
        self.assertIn("secret", output)


if __name__ == "__main__":
    unittest.main()
