"""sleep: досрочное завершение сессии по решению агента."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tool_registry as tools  # noqa: E402
import tools_sleep  # noqa: E402
from tool_context import ToolContext  # noqa: E402
from tests.tools_testkit import _paths  # noqa: E402


class SleepToolTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-sleeptool-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.paths = _paths(self.tmp / "memory.md")

    def test_schema_requires_reason(self):
        function = tools_sleep.SLEEP_TOOL["function"]
        self.assertEqual(function["name"], "sleep")
        self.assertEqual(function["parameters"]["required"], ["reason"])
        self.assertIn("reason", function["parameters"]["properties"])
        self.assertIs(tools._HANDLERS["sleep"], tools_sleep.handle_sleep)

    def test_sleep_requests_archive_in_active_iteration(self):
        context = ToolContext("client", "model", 0.7)
        reason = "устал: контекст стал слишком большим"

        result = tools.execute_tool(
            "sleep", json.dumps({"reason": reason}), self.paths, context
        )

        self.assertEqual(result, f"Сон запрошен: {reason}")
        self.assertTrue(context.sleep_requested)
        self.assertEqual(context.sleep_reason, reason)

    def test_sleep_requires_active_context(self):
        result = tools.execute_tool(
            "sleep", {"reason": "контекст велик"}, self.paths, None
        )
        self.assertEqual(
            result, "Error: sleep: отсутствует контекст текущего цикла"
        )

    def test_sleep_rejects_missing_or_invalid_reason(self):
        for arguments in ({}, {"reason": ""}, {"reason": 42}):
            with self.subTest(arguments=arguments):
                context = ToolContext("client", "model", 0.7)
                result = tools.execute_tool("sleep", arguments, self.paths, context)
                self.assertTrue(result.startswith("Error: invalid arguments"))
                self.assertFalse(context.sleep_requested)


if __name__ == "__main__":
    unittest.main()
