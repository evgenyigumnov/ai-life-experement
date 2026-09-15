"""Юнит-тесты курсорной пагинации дневника."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))
import diary  # noqa: E402


class DiaryPaginationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-diary-page-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "diary.json"
        for i in range(1, 8):
            diary.remember(self.path, f"запись {i}")
        self.data = diary.load_diary(self.path)

    def test_before_id_in_new_order(self):
        self.assertEqual(
            [e["id"] for e in diary.recall(self.data, before_id=3)], [2, 1]
        )
        page, cursor = diary.recall_page(self.data, limit=3)
        self.assertEqual([e["id"] for e in page], [7, 6, 5])
        self.assertEqual(cursor, 5)

    def test_after_id_in_old_order(self):
        self.assertEqual(
            [e["id"] for e in diary.recall(self.data, after_id=3, order="old")],
            [4, 5, 6, 7],
        )
        page, cursor = diary.recall_page(self.data, limit=3, order="old")
        self.assertEqual([e["id"] for e in page], [1, 2, 3])
        self.assertEqual(cursor, 3)
        page, next_cursor = diary.recall_page(
            self.data, limit=3, order="old", after_id=cursor
        )
        self.assertEqual([e["id"] for e in page], [4, 5, 6])
        self.assertEqual(next_cursor, 6)

    def test_cursor_is_applied_after_filters(self):
        diary.remember(self.path, "важно: начало")
        diary.remember(self.path, "важно: конец")
        data = diary.load_diary(self.path)
        page, cursor = diary.recall_page(data, query="важно", limit=1)
        self.assertEqual([e["id"] for e in page], [9])
        page, next_cursor = diary.recall_page(
            data, query="важно", limit=1, before_id=cursor
        )
        self.assertEqual([e["id"] for e in page], [8])
        self.assertIsNone(next_cursor)

    def test_cursor_validation(self):
        for bad in (0, -1, 2.5, True, "abc", "1.5", [1]):
            with self.subTest(value=bad):
                with self.assertRaises(diary.ValidationError):
                    diary.recall(self.data, before_id=bad)
                with self.assertRaises(diary.ValidationError):
                    diary.recall(self.data, after_id=bad)

    def test_no_cursor_when_page_is_last(self):
        page, cursor = diary.recall_page(self.data, limit=10)
        self.assertEqual(len(page), 7)
        self.assertIsNone(cursor)


if __name__ == "__main__":
    unittest.main()
