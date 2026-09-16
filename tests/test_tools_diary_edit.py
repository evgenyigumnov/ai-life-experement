"""diary_edit и минимальный публичный API дневника."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tool_registry as tools  # noqa: E402
from tests.tools_testkit import _paths  # noqa: E402


class DiaryEditToolsTests(unittest.TestCase):
    """diary_edit и границы имён инструментов."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-diarytool-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.paths = _paths(self.tmp / "memory.md")

    def _call(self, name, **kwargs):
        return tools.execute_tool(name, json.dumps(kwargs), self.paths)

    def test_edit_flow(self):
        self._call("diary_remember", text="исходный текст")
        out = self._call("diary_edit", id=1, text="исправленный текст")
        self.assertEqual(out, "Запись id=1 обновлена (правок: 1)")
        self.assertIn("(изменена)", self._call("diary_recall"))

    def test_edit_errors(self):
        self._call("diary_remember", text="текст")
        for kwargs in ({}, {"id": 1, "text": ""}, {"id": "abc", "text": "текст"},
                       {"id": 99, "text": "текст"}):
            with self.subTest(kwargs=kwargs):
                self.assertTrue(self._call("diary_edit", **kwargs).startswith("Error:"))

    def test_removed_diary_mutations_are_unknown(self):
        for name in ("diary_forget", "diary_restore", "diary_history"):
            self.assertEqual(
                self._call(name), f"Error: unknown tool: {name}"
            )

    def test_diary_tools_require_paths(self):
        for name in ("diary_remember", "diary_recall", "diary_edit", "diary_tags"):
            with self.subTest(name=name):
                self.assertEqual(
                    tools.execute_tool(name, "{}", None),
                    "Error: paths не заданы",
                )

    def test_legacy_unprefixed_diary_names_unknown(self):
        for name in ("remember", "recall", "forget", "restore", "history"):
            self.assertEqual(
                tools.execute_tool(name, "{}", self.paths),
                f"Error: unknown tool: {name}",
            )


if __name__ == "__main__":
    unittest.main()
