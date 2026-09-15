"""Валидация аргументов read_file (до обращения к песочнице)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sandbox_scripts  # noqa: E402
import tool_registry as tools  # noqa: E402
from tests.tools_testkit import _paths, bash_tool_on  # noqa: E402

class ReadFileValidationTests(unittest.TestCase):
    """Валидация аргументов read_file (до обращения к песочнице)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-readval-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = _paths(self.tmp / "memory.md")
        ctx = bash_tool_on()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)

    def _read(self, **kwargs):
        return tools.execute_tool("read_file", json.dumps(kwargs), self.paths)

    def test_missing_path(self):
        self.assertIn("Error: invalid arguments", self._read())

    def test_path_not_string(self):
        self.assertIn("Error: invalid arguments", self._read(path=42))

    def test_path_empty(self):
        self.assertIn("Error: invalid arguments", self._read(path="   "))

    def test_invalid_offset(self):
        for offset in (0, -1, "abc", 2.5, True):
            with self.subTest(offset=offset):
                out = self._read(path="/root/x", offset=offset)
                self.assertIn("Error: invalid arguments", out)
                self.assertIn("offset", out)

    def test_invalid_limit(self):
        for limit in ("abc", 2.5, True, [1]):
            with self.subTest(limit=limit):
                out = self._read(path="/root/x", limit=limit)
                self.assertIn("Error: invalid arguments", out)
                self.assertIn("limit", out)

    def test_out_of_range_limit_clamped_not_error(self):
        # Числовой limit вне [1, MAX] больше не ошибка валидации: он
        # приводится к границе (заметка в ответе — в ReadFileUnitTests).
        # Docker мокаем, чтобы класс остался «до песочницы».
        from unittest.mock import patch

        for limit in (0, -1, 1001, 99999):
            with self.subTest(limit=limit):
                with patch.object(
                    sandbox_scripts,
                    "check_docker_available",
                    return_value="Error: песочница docker недоступна (тест)",
                ):
                    out = self._read(path="/root/x", limit=limit)
                self.assertNotIn("invalid arguments", out)




if __name__ == "__main__":
    unittest.main()
