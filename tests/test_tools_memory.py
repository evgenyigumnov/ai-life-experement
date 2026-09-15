"""get_memory / set_memory: рабочая память агента."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tool_registry as tools  # noqa: E402
from tests.tools_testkit import _paths  # noqa: E402

class MemoryToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-memtool-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.paths = _paths(self.tmp / "memory.md")
    def test_get_empty_memory(self):
        out = tools.execute_tool("get_memory", "{}", self.paths)
        self.assertEqual(out, "(память пуста)")

    def test_set_get_roundtrip(self):
        text = "память: шаг 1"
        out = tools.execute_tool("set_memory", json.dumps({"content": text}), self.paths)
        self.assertEqual(out, f"Memory updated ({len(text.encode('utf-8'))} bytes)")
        self.assertEqual(tools.execute_tool("get_memory", None, self.paths), text)

    def test_set_memory_requires_string(self):
        out = tools.execute_tool("set_memory", '{"content": 42}', self.paths)
        self.assertTrue(out.startswith("Error: invalid arguments"))




if __name__ == "__main__":
    unittest.main()
