"""Тесты mind-loop.json, memory.md и системного промпта."""

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tests.helpers import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))
import storage  # noqa: E402


class _FixedDatetime:
    """datetime с замороженным now() для предсказуемых имён бэкапов."""

    @staticmethod
    def now():
        return datetime(2026, 9, 9, 12, 0, 0)


class MindLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-store-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "bot" / "mind-loop.json"
        self.path.parent.mkdir()

    def _tmp_leftovers(self):
        return [p.name for p in self.tmp.rglob("*.tmp")]

    def test_load_missing_file_returns_empty_structure(self):
        data = storage.load_mind_loop(self.path)
        self.assertEqual(data["agent"], "bot")
        self.assertEqual(data["iterations"], [])
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)
        self.assertNotIn("seen_creator_messages", data)
        self.assertFalse(self.path.exists())

    def test_append_iteration_numbers_and_persists(self):
        data = storage.load_mind_loop(self.path)
        storage.append_iteration(self.path, data, {"user": "x"})
        storage.append_iteration(self.path, storage.load_mind_loop(self.path), {"user": "x"})
        data2 = storage.load_mind_loop(self.path)
        self.assertEqual([it["n"] for it in data2["iterations"]], [1, 2])
        self.assertTrue(all(it["timestamp"] for it in data2["iterations"]))
        self.assertEqual(self._tmp_leftovers(), [])

    def test_save_updates_updated_at(self):
        data = storage.load_mind_loop(self.path)
        data["updated_at"] = "old"
        storage.save_mind_loop(self.path, data)
        self.assertNotEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["updated_at"], "old"
        )

    def test_corrupt_json_backed_up_and_history_reset(self):
        self.path.write_text("{это не json", encoding="utf-8")
        data = storage.load_mind_loop(self.path)
        self.assertEqual(data["iterations"], [])
        backups = list(self.path.parent.glob("mind-loop.json.corrupt-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{это не json")
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), data)

    def test_wrong_structure_backed_up_too(self):
        self.path.write_text(json.dumps({"iterations": {}}), encoding="utf-8")
        data = storage.load_mind_loop(self.path)
        self.assertEqual(data["iterations"], [])
        self.assertEqual(len(list(self.path.parent.glob("*.corrupt-*"))), 1)

    def test_same_second_backups_not_overwritten(self):
        self.path.write_text("{битый", encoding="utf-8")
        with mock.patch.object(storage, "datetime", _FixedDatetime):
            storage.load_mind_loop(self.path)
            self.path.write_text("{снова битый", encoding="utf-8")
            storage.load_mind_loop(self.path)
        backups = sorted(p.name for p in self.path.parent.glob("*.corrupt-*"))
        self.assertEqual(
            backups,
            [
                "mind-loop.json.corrupt-20260909-120000",
                "mind-loop.json.corrupt-20260909-120000-1",
            ],
        )
        self.assertEqual(
            (self.path.parent / backups[0]).read_text(encoding="utf-8"), "{битый"
        )

    def test_atomic_write_leaves_no_tmp_files(self):
        data = storage.load_mind_loop(self.path)
        for i in range(3):
            storage.append_iteration(self.path, data, {"n": i + 1})
        self.assertEqual(self._tmp_leftovers(), [])


class ArchiveMindLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-arch-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "bot" / "mind-loop.json"
        self.path.parent.mkdir()

    def _tmp_leftovers(self):
        return [p.name for p in self.tmp.rglob("*.tmp")]

    def test_archive_creates_timestamped_copy_and_fresh_file(self):
        data = storage.load_mind_loop(self.path)
        storage.append_iteration(
            self.path, data, {"assistant_message": {"content": "дело"}}
        )
        with mock.patch.object(storage, "datetime", _FixedDatetime):
            archive = storage.archive_mind_loop(
                self.path, storage.load_mind_loop(self.path)
            )

        self.assertEqual(archive.name, "mind-loop-20260909-120000.json")
        archived = json.loads(archive.read_text(encoding="utf-8"))
        self.assertEqual(archived["agent"], "bot")
        self.assertEqual([it["n"] for it in archived["iterations"]], [1])
        fresh = storage.load_mind_loop(self.path)
        self.assertEqual(fresh["iterations"], [])
        self.assertEqual(fresh["session"], 2)
        self.assertEqual(fresh["agent"], "bot")
        self.assertTrue(fresh["woke_up_at"])
        self.assertEqual(self._tmp_leftovers(), [])

    def test_session_counter_increments_across_archives(self):
        data = storage.load_mind_loop(self.path)
        storage.append_iteration(self.path, data, {"n": 1})
        with mock.patch.object(storage, "datetime", _FixedDatetime):
            storage.archive_mind_loop(self.path, storage.load_mind_loop(self.path))
            self.assertEqual(storage.load_mind_loop(self.path)["session"], 2)
            storage.archive_mind_loop(self.path, storage.load_mind_loop(self.path))
            self.assertEqual(storage.load_mind_loop(self.path)["session"], 3)
        archives = sorted(p.name for p in self.path.parent.glob("mind-loop-*.json"))
        self.assertEqual(
            archives,
            [
                "mind-loop-20260909-120000-1.json",
                "mind-loop-20260909-120000.json",
            ],
        )

    def test_old_delivery_counter_is_removed_from_loaded_history(self):
        self.path.write_text(
            json.dumps({"iterations": [], "seen_creator_messages": 3}),
            encoding="utf-8",
        )
        data = storage.load_mind_loop(self.path)
        self.assertNotIn("seen_creator_messages", data)

    def test_archive_does_not_add_delivery_counter(self):
        data = storage.load_mind_loop(self.path)
        data["seen_creator_messages"] = 3
        with mock.patch.object(storage, "datetime", _FixedDatetime):
            storage.archive_mind_loop(self.path, data)
        self.assertNotIn("seen_creator_messages", storage.load_mind_loop(self.path))

    def test_archive_of_old_file_without_session_field(self):
        self.path.write_text(
            json.dumps({"agent": "bot", "created_at": "t", "updated_at": "t", "iterations": []}),
            encoding="utf-8",
        )
        with mock.patch.object(storage, "datetime", _FixedDatetime):
            storage.archive_mind_loop(self.path, storage.load_mind_loop(self.path))
        fresh = storage.load_mind_loop(self.path)
        self.assertEqual(fresh["session"], 2)
        self.assertTrue(fresh["woke_up_at"])


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-mem-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "memory.md"

    def test_read_missing_returns_empty_string(self):
        self.assertEqual(storage.read_memory(self.path), "")

    def test_write_read_roundtrip_utf8(self):
        text = "память: строка 1\nline 2 🤖"
        storage.write_memory(self.path, text)
        self.assertEqual(storage.read_memory(self.path), text)

    def test_write_overwrites_and_atomic(self):
        storage.write_memory(self.path, "старая")
        storage.write_memory(self.path, "новая")
        self.assertEqual(storage.read_memory(self.path), "новая")
        self.assertEqual([p.name for p in self.tmp.rglob("*.tmp")], [])


class SystemPromptTests(unittest.TestCase):
    def test_read(self):
        tmp = Path(tempfile.mkdtemp(prefix="ai-sp-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "system-prompt.md"
        path.write_text("Ты — агент.", encoding="utf-8")
        self.assertEqual(storage.read_system_prompt(path), "Ты — агент.")


if __name__ == "__main__":
    unittest.main()
