"""Флаг ENABLE_BASH_TOOL: гейтинг песочницы в схеме и исполнении."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tool_registry as tools  # noqa: E402
from tests.helpers import env  # noqa: E402
from tests.tools_testkit import _paths  # noqa: E402

class BashToolDisabledTests(unittest.TestCase):
    """run_bash по умолчанию выключен (ENABLE_BASH_TOOL)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-bashoff-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = _paths(self.tmp / "memory.md")

    def test_disabled_by_default(self):
        with env(ENABLE_BASH_TOOL=None):
            self.assertFalse(tools.bash_tool_enabled())

    def test_disabled_by_explicit_false(self):
        for raw in ("0", "false", "off", "no", ""):
            with self.subTest(raw=raw):
                with env(ENABLE_BASH_TOOL=raw):
                    self.assertFalse(tools.bash_tool_enabled())

    def test_enabled_by_flag(self):
        for raw in ("1", "true", "ON", "Yes"):
            with self.subTest(raw=raw):
                with env(ENABLE_BASH_TOOL=raw):
                    self.assertTrue(tools.bash_tool_enabled())

    def test_unrecognized_value_is_disabled(self):
        # строгая валидация — в config_env.load_config; здесь безопасный дефолт
        with env(ENABLE_BASH_TOOL="maybe"):
            self.assertFalse(tools.bash_tool_enabled())

    def test_schema_excludes_run_bash_when_disabled(self):
        with env(ENABLE_BASH_TOOL=None, BRAVE_KEY=None):
            names = [t["function"]["name"] for t in tools.build_tools_schema()]
            self.assertNotIn("run_bash", names)
            self.assertNotIn("read_file", names)  # песочница выключена целиком
            self.assertEqual(
                names,
                [
                    "send_message",
                    "get_messages",
                    "get_memory",
                    "set_memory",
                    "sleep",
                    "diary_remember",
                    "diary_recall",
                    "diary_edit",
                    "diary_tags",
                    "web_fetch",
                    "inspect_image",
                    "money_balance",
                    "money_spend",
                ],
            )

    def test_schema_includes_run_bash_when_enabled(self):
        with env(BRAVE_KEY="test-brave-key"):
            names = [t["function"]["name"] for t in tools.build_tools_schema(True)]
        self.assertEqual(
            names,
            [
                "run_bash",
                "read_file",
                "write",
                "edit",
                "grep",
                "find",
                "ls",
                "send_message",
                "get_messages",
                "get_memory",
                "set_memory",
                "sleep",
                "diary_remember",
                "diary_recall",
                "diary_edit",
                "diary_tags",
                "internet_search",
                "web_fetch",
                "inspect_image",
                "money_balance",
                "money_spend",
            ],
        )

    def test_schema_env_flag_overrides_default(self):
        with env(ENABLE_BASH_TOOL="1"):
            names = [t["function"]["name"] for t in tools.build_tools_schema()]
            self.assertIn("run_bash", names)

    def test_execute_run_bash_returns_error_when_disabled(self):
        with env(ENABLE_BASH_TOOL=None):
            out = tools.execute_tool("run_bash", '{"command": "ls"}', self.paths)
            self.assertTrue(out.startswith("Error:"), out)
            self.assertIn("выключен", out)
            self.assertIn("ENABLE_BASH_TOOL", out)

    def test_execute_read_file_returns_error_when_disabled(self):
        with env(ENABLE_BASH_TOOL=None):
            out = tools.execute_tool(
                "read_file", '{"path": "/root/x"}', self.paths
            )
            self.assertTrue(out.startswith("Error:"), out)
            self.assertIn("выключен", out)
            self.assertIn("ENABLE_BASH_TOOL", out)

    def test_new_file_tools_are_disabled_with_the_sandbox(self):
        calls = {
            "write": {"path": "/root/x", "content": "x"},
            "edit": {"path": "/root/x", "old": "x", "new": "y"},
            "grep": {"pattern": "x"},
            "find": {"pattern": "*"},
            "ls": {},
        }
        with env(ENABLE_BASH_TOOL=None):
            for name, args in calls.items():
                with self.subTest(name=name):
                    out = tools.execute_tool(name, json.dumps(args), self.paths)
                    self.assertIn("выключен", out)
                    self.assertIn("ENABLE_BASH_TOOL", out)

    def test_other_tools_work_when_bash_disabled(self):
        with env(ENABLE_BASH_TOOL=None):
            out = tools.execute_tool("set_memory", '{"content": "текст"}', self.paths)
            self.assertTrue(out.startswith("Memory updated"))




if __name__ == "__main__":
    unittest.main()
