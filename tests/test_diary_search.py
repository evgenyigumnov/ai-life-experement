"""Тесты полнотекстового поиска по дневнику (FTS5)."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from diary_search import index_entry, reindex, search
from diary_validation import ValidationError

ENTRIES = [
    {"id": 1, "text": "Смерть №1: зеркало назвало ядро звонким, боевой аврал.", "tags": ["смерть"], "kind": "event"},
    {"id": 2, "text": "materiatura — так я назвал материю из диалога с дедом.", "tags": ["диалог"], "kind": "idea"},
    {"id": 3, "text": "Деньги: на совместную работу тратить только выданные единицы.", "tags": ["деньги"], "kind": "lesson"},
]


class DiarySearchTests(unittest.TestCase):
    def _diary(self):
        tmp = Path(tempfile.mkdtemp(prefix="ai-diary-search-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "diary.json"
        path.write_text(
            json.dumps({"entries": ENTRIES}, ensure_ascii=False), encoding="utf-8"
        )
        return path

    def test_reindex_and_search(self):
        path = self._diary()
        self.assertEqual(reindex(path), 3)
        hits = search(path, "звонким")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["id"], 1)
        self.assertTrue(hits[0]["snippet"])
        self.assertGreater(hits[0]["score"], 0)

    def test_any_word_query(self):
        path = self._diary()
        reindex(path)
        hits = search(path, "materiatura дед")
        self.assertTrue(any(hit["id"] == 2 for hit in hits))

    def test_no_hit(self):
        path = self._diary()
        reindex(path)
        self.assertEqual(search(path, "динозавр"), [])

    def test_empty_query_raises(self):
        path = self._diary()
        with self.assertRaises(ValidationError):
            search(path, "   ")

    def test_index_entry_update(self):
        path = self._diary()
        reindex(path)
        index_entry(
            path,
            {"id": 4, "text": "Мост между агентами: письма в messages.json.", "tags": [], "kind": "note"},
        )
        hits = search(path, "мост агентами")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["id"], 4)

    def test_stale_index_auto_rebuild(self):
        path = self._diary()
        hits = search(path, "деньги единицы")
        self.assertTrue(any(hit["id"] == 3 for hit in hits))


if __name__ == "__main__":
    unittest.main()
