"""Тесты рамок вызова и результата tool."""

import json
import unittest

from tests.test_agent_iteration_logging import _IterationLoggingBase


class ToolBlockTests(_IterationLoggingBase):
    """Инструментальные блоки выводятся целиком и без ANSI-кодов."""

    def test_tool_blocks_not_truncated(self):
        long_arg = json.dumps({"command": "echo " + "B" * 300})
        long_result = "Результат:\n" + "C" * 300
        response = {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "run_bash", "arguments": long_arg},
            }],
        }
        logs = self._run(response, tool_result=long_result)
        self.assertEqual(len(logs), 6)
        call_block, result_block = logs[4], logs[5]
        self.assertIn("Tool: run_bash [вызов]", call_block)
        self.assertIn("┏━━", call_block)
        self.assertIn("┗", call_block)
        self.assertIn("B" * 300, call_block)
        self.assertNotIn("…", call_block)
        self.assertIn("Tool: run_bash [результат]", result_block)
        self.assertIn("╔══", result_block)
        self.assertIn("╚", result_block)
        self.assertIn(long_result.replace("\n", "\n║ "), result_block)
        self.assertNotIn("…", result_block)

    def test_no_ansi_codes_when_color_disabled(self):
        response = {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "get_memory", "arguments": "{}"},
            }],
        }
        for block in self._run(response, tool_result="ок"):
            self.assertNotIn("\x1b[", block)


if __name__ == "__main__":
    unittest.main()
