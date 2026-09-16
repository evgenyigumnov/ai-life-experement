"""Регрессии интегрированного поиска и свежести индексов."""

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_paths import AgentPaths
from diary_storage import ensure_diary_file
import diary
from tools_diary import handle_diary_recall


class DiaryIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-diary-index-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "diary.json"
        ensure_diary_file(self.path, "bot")
        self.paths = AgentPaths(
            folder=self.tmp,
            system_prompt=self.tmp / "system-prompt.md",
            mind_loop=self.tmp / "mind-loop.json",
            memory=self.tmp / "memory.md",
            diary=self.path,
        )
        self.saved_env = {
            key: os.environ.get(key)
            for key in ("DIARY_EMBED_FAKE", "DIARY_EMBED_TOKEN", "DIARY_VEC_SO")
        }
        os.environ.pop("DIARY_EMBED_FAKE", None)
        os.environ.pop("DIARY_EMBED_TOKEN", None)
        os.environ["DIARY_VEC_SO"] = "/nonexistent/vec0.so"
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _entry(self, entry_id, text="common", tags=None):
        return {
            "id": entry_id,
            "timestamp": "2026-01-01T00:00:00",
            "kind": "note",
            "tags": tags or [],
            "text": text,
            "edited_at": None,
            "edit_count": 0,
        }

    def _write_entries(self, entries):
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["entries"] = entries
        data["next_id"] = max((entry["id"] for entry in entries), default=0) + 1
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _ids(output):
        return [int(value) for value in re.findall(r"\[id=(\d+)\]", output)]

    def test_ranked_order_and_cursor_are_preserved(self):
        self._write_entries([self._entry(i) for i in (1, 2, 3)])
        ranked = [{"id": 1}, {"id": 3}, {"id": 2}]
        with patch("tools_diary_recall.diary_index.search_ranked", return_value=ranked) as search:
            first = handle_diary_recall(
                {"query": "common", "mode": "hybrid", "limit": 2}, self.paths
            )
            second = handle_diary_recall(
                {"query": "common", "mode": "hybrid", "limit": 2, "before_id": 3},
                self.paths,
            )
        self.assertEqual(self._ids(first), [1, 3])
        self.assertEqual(self._ids(second), [2])
        self.assertEqual(search.call_args.kwargs["k"], 50)

    def test_filtered_candidates_are_not_capped_at_two_hundred(self):
        self._write_entries(
            [self._entry(i) for i in range(1, 251)]
            + [self._entry(251, tags=["rare"], text=" ".join(["noise"] * 300) + " common")]
        )
        output = handle_diary_recall(
            {"query": "common", "mode": "text", "tags": ["rare"], "limit": 1},
            self.paths,
        )
        self.assertEqual(self._ids(output), [251])

    def test_external_same_count_change_is_rebuilt_on_next_write(self):
        diary.remember(self.path, "oldunique")
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data["entries"][0]["text"] = "externalnew"
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        diary.remember(self.path, "anothernew")
        old = handle_diary_recall(
            {"query": "oldunique", "mode": "text"}, self.paths
        )
        new = handle_diary_recall(
            {"query": "externalnew", "mode": "text"}, self.paths
        )
        self.assertNotIn("[id=1]", old)
        self.assertIn("[id=1]", new)


if __name__ == "__main__":
    unittest.main()
