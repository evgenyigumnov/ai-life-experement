"""Юнит-тесты точечной правки записи дневника."""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))
import diary  # noqa: E402


class DiaryEditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-diary-edit-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "diary.json"
        self.entry = diary.remember(self.path, "первоначальный текст")

    def test_edit_changes_only_target(self):
        other = diary.remember(self.path, "другая запись")
        updated = diary.edit_entry(self.path, self.entry["id"], "исправленный текст")
        self.assertEqual(updated["text"], "исправленный текст")
        self.assertEqual(updated["edit_count"], 1)
        self.assertTrue(updated["edited_at"])
        data = diary.load_diary(self.path)
        self.assertEqual([e["text"] for e in data["entries"]], ["исправленный текст", other["text"]])
        self.assertEqual(data["entries"][1]["edit_count"], 0)

    def test_edit_increments_count(self):
        diary.edit_entry(self.path, 1, "текст 2")
        updated = diary.edit_entry(self.path, "1", "текст 3")
        self.assertEqual(updated["edit_count"], 2)

    def test_edit_validates_id_and_text(self):
        with self.assertRaises(diary.EntryNotFound):
            diary.edit_entry(self.path, 99, "текст")
        for text in ("", "x" * (diary.MAX_ENTRY_CHARS + 1)):
            with self.subTest(text=text[:10]):
                with self.assertRaises(diary.ValidationError):
                    diary.edit_entry(self.path, 1, text)


if __name__ == "__main__":
    unittest.main()
