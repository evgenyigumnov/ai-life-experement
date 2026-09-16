"""Защита и форматирование вывода read_file."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools_readfile import format_read_file_result  # noqa: E402


class ReadFileOutputTests(unittest.TestCase):
    def test_page_output_uses_common_byte_limit(self):
        data = {
            "path": "x",
            "size": 250000,
            "total_lines": 100,
            "start": 1,
            "end": 100,
            "lines": [f"line-{index}-" + "A" * 2400 for index in range(100)],
        }
        result = format_read_file_result(data)
        self.assertLessEqual(len(result.encode("utf-8")), 52 * 1024)
        self.assertIn("truncatedBy=bytes", result)
        self.assertIn("продолжение — read_file offset=", result)
        self.assertNotIn("line-99-", result)

    def test_empty_file_page_is_end_of_file(self):
        data = {
            "path": "empty",
            "size": 0,
            "total_lines": 0,
            "start": 1,
            "end": 0,
            "lines": [],
        }
        result = format_read_file_result(data)
        self.assertIn("0 строк", result)
        self.assertIn("(конец файла)", result)
        self.assertNotIn("offset=", result)


if __name__ == "__main__":
    unittest.main()
