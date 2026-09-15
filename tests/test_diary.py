"""Юнит-тесты базовых операций дневника."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))
import diary  # noqa: E402


class DiaryBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-diary-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "bot" / "diary.json"
        diary.ensure_diary_file(self.path, "bot")


class LoadSaveTests(DiaryBase):
    def test_ensure_creates_file_once(self):
        diary.remember(self.path, "первая запись")
        self.assertFalse(diary.ensure_diary_file(self.path, "bot"))
        self.assertEqual(len(diary.load_diary(self.path)["entries"]), 1)

    def test_load_missing_file_returns_empty_without_writing(self):
        missing = self.tmp / "ghost" / "diary.json"
        data = diary.load_diary(missing)
        self.assertEqual(data["entries"], [])
        self.assertEqual(data["next_id"], 1)
        self.assertFalse(missing.exists())

    def test_corrupt_file_is_backed_up_and_reset(self):
        self.path.write_text("{это не json", encoding="utf-8")
        self.assertEqual(diary.load_diary(self.path)["entries"], [])
        backups = list(self.path.parent.glob("diary.json.corrupt-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{это не json")

    def test_wrong_structure_is_backed_up_too(self):
        self.path.write_text(json.dumps({"entries": {}}), encoding="utf-8")
        self.assertEqual(diary.load_diary(self.path)["entries"], [])
        self.assertEqual(len(list(self.path.parent.glob("*.corrupt-*"))), 1)

    def test_save_updates_timestamp(self):
        data = diary.load_diary(self.path)
        data["updated_at"] = "old"
        diary.save_diary(self.path, data)
        self.assertNotEqual(
            json.loads(self.path.read_text(encoding="utf-8"))["updated_at"], "old"
        )


class RememberTests(DiaryBase):
    def test_returns_entry_and_persists(self):
        entry = diary.remember(
            self.path,
            "Создатель впервые спросил о моих мечтах",
            tags=["создатель", "диалог"],
            kind="event",
        )
        self.assertEqual(
            (entry["id"], entry["kind"], entry["tags"]),
            (1, "event", ["создатель", "диалог"]),
        )
        self.assertTrue(entry["timestamp"])
        self.assertEqual(diary.load_diary(self.path)["entries"], [entry])
        self.assertEqual(diary.load_diary(self.path)["next_id"], 2)

    def test_defaults_and_id_monotonicity(self):
        first = diary.remember(self.path, "один")
        second = diary.remember(self.path, "два")
        third = diary.remember(self.path, "три")
        self.assertEqual([e["id"] for e in (first, second, third)], [1, 2, 3])
        self.assertEqual(first["kind"], "note")
        self.assertEqual(first["tags"], [])
        self.assertIsNone(first["edited_at"])

    def test_next_id_recovers_from_inconsistent_file(self):
        diary.remember(self.path, "один")
        diary.remember(self.path, "два")
        data = diary.load_diary(self.path)
        data["next_id"] = 1
        diary.save_diary(self.path, data)
        self.assertEqual(diary.remember(self.path, "три")["id"], 3)

    def test_tags_and_kind_are_normalized(self):
        entry = diary.remember(
            self.path, "текст", tags=["Docker", " docker ", "", "Deploy"], kind=" Event "
        )
        self.assertEqual(entry["tags"], ["docker", "deploy"])
        self.assertEqual(entry["kind"], "event")

    def test_validation(self):
        for bad in (None, 42, "", "   "):
            with self.subTest(field="text", value=bad):
                with self.assertRaises(diary.ValidationError):
                    diary.remember(self.path, bad)
        for bad in ("dream", "", 42, True):
            with self.subTest(field="kind", value=bad):
                with self.assertRaises(diary.ValidationError):
                    diary.remember(self.path, "текст", kind=bad)
        for bad in ("тег", 42, [42], ["x" * 65], [f"t{i}" for i in range(11)]):
            with self.subTest(field="tags", value=bad):
                with self.assertRaises(diary.ValidationError):
                    diary.remember(self.path, "текст", tags=bad)

    def test_text_limit_and_missing_file(self):
        with self.assertRaises(diary.ValidationError):
            diary.remember(self.path, "а" * (diary.MAX_ENTRY_CHARS + 1))
        entry = diary.remember(self.tmp / "fresh" / "diary.json", "текст")
        self.assertEqual(entry["id"], 1)


class RecallTests(DiaryBase):
    def setUp(self):
        super().setUp()
        diary.remember(self.path, "Развернул docker", tags=["docker", "работа"], kind="lesson")
        diary.remember(self.path, "Создатель спросил о мечтах", tags=["диалог"], kind="event")
        diary.remember(self.path, "Идея: вести дневник", tags=["диалог"], kind="idea")

    def test_filters_and_order(self):
        data = diary.load_diary(self.path)
        self.assertEqual([e["id"] for e in diary.recall(data)], [3, 2, 1])
        self.assertEqual([e["id"] for e in diary.recall(data, order="old")], [1, 2, 3])
        self.assertEqual([e["id"] for e in diary.recall(data, query="DOCKER")], [1])
        self.assertEqual([e["id"] for e in diary.recall(data, tags=["диалог", "создатель"])], [])
        self.assertEqual([e["id"] for e in diary.recall(data, kinds=["idea", "lesson"])], [3, 1])

    def test_limit_and_bad_arguments(self):
        data = diary.load_diary(self.path)
        self.assertEqual([e["id"] for e in diary.recall(data, limit=2)], [3, 2])
        for kwargs in (
            {"query": ""}, {"query": 42}, {"limit": 0},
            {"limit": diary.MAX_RECALL_LIMIT + 1}, {"order": "сначала"},
            {"kinds": ["мечта"]}, {"tags": "тег"},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(diary.ValidationError):
                    diary.recall(data, **kwargs)


class IdTests(DiaryBase):
    def test_string_id_and_missing_entry(self):
        diary.remember(self.path, "текст")
        self.assertEqual(diary.validate_entry_id("1"), 1)
        self.assertIsNone(diary.get_entry(diary.load_diary(self.path), 7))

    def test_bad_ids_rejected(self):
        for bad in (0, -3, 2.5, True, "abc", "1.5", None, [1]):
            with self.subTest(value=bad):
                with self.assertRaises(diary.ValidationError):
                    diary.validate_entry_id(bad)


if __name__ == "__main__":
    unittest.main()
