"""diary_tags: частоты тегов дневника — оглавление тем (P6, часть 1)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import diary  # noqa: E402
import diary_tags  # noqa: E402
import tool_registry as tools  # noqa: E402
import tools_diary  # noqa: E402
import tools_diary_schema  # noqa: E402
from agent_paths import AgentPaths  # noqa: E402


def _diary(entries):
    return {"entries": entries}


def _entry(tags=(), kind="note"):
    return {"id": 1, "kind": kind, "tags": list(tags), "text": "текст"}


class TagsStatsTests(unittest.TestCase):
    """tags_stats/count_tags: подсчёт, фильтры, сортировка, limit."""

    def test_counts_all_entries(self):
        data = _diary([
            _entry(tags=["работа"]),
            _entry(tags=["работа"]),
            _entry(tags=["ещё"]),
        ])
        self.assertEqual(
            diary_tags.tags_stats(data), [("работа", 2), ("ещё", 1)]
        )

    def test_tags_lowercased(self):
        data = _diary([_entry(tags=["Создатель"]), _entry(tags=["создатель"])])
        self.assertEqual(diary_tags.tags_stats(data), [("создатель", 2)])

    def test_kinds_filter(self):
        data = _diary([
            _entry(tags=["ops"], kind="lesson"),
            _entry(tags=["диалог"], kind="event"),
        ])
        self.assertEqual(diary_tags.tags_stats(data, kinds=["lesson"]), [("ops", 1)])

    def test_sorting_count_desc_then_alpha(self):
        data = _diary([
            _entry(tags=["б"]),
            _entry(tags=["а"]), _entry(tags=["а"]),
            _entry(tags=["в"]), _entry(tags=["в"]),
        ])
        self.assertEqual(diary_tags.tags_stats(data), [("а", 2), ("в", 2), ("б", 1)])

    def test_limit_default_and_explicit(self):
        entries = [_entry(tags=[f"тег{i}"]) for i in range(12)]
        self.assertEqual(len(diary_tags.tags_stats(_diary(entries))),
                         diary_tags.DEFAULT_TAGS_LIMIT)
        self.assertEqual(len(diary_tags.tags_stats(_diary(entries), limit=3)), 3)

    def test_invalid_kinds_and_limit(self):
        data = _diary([])
        for kwargs in ({"kinds": ["мечта"]}, {"limit": 0},
                       {"limit": diary_tags.MAX_TAGS_LIMIT + 1}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(diary.ValidationError):
                    diary_tags.tags_stats(data, **kwargs)


class DiaryTagsToolTests(unittest.TestCase):
    """Обработчик diary_tags: формат ответа, фильтры, read-only."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-diarytags-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.paths = AgentPaths(
            folder=self.tmp,
            system_prompt=self.tmp / "system-prompt.md",
            mind_loop=self.tmp / "mind-loop.json",
            memory=self.tmp / "memory.md",
        )

    def _remember(self, text, tags=(), kind=None):
        args = {"text": text, "tags": list(tags)}
        if kind:
            args["kind"] = kind
        return tools.execute_tool("diary_remember", json.dumps(args), self.paths)

    def _tags(self, **kwargs):
        return tools.execute_tool("diary_tags", json.dumps(kwargs), self.paths)

    def test_empty_diary(self):
        self.assertEqual(self._tags(), "(дневник пуст)")

    def test_header_and_lines_format(self):
        self._remember("первая", tags=["работа"])
        self._remember("вторая", tags=["Работа", "сон"])
        out = self._tags()
        self.assertIn(
            "Дневник, темы: всего записей 2, всего тегов 2.",
            out,
        )
        self.assertIn("#работа — 2 записи", out)
        self.assertIn("#сон — 1 запись", out)

    def test_pluralization_5_entries(self):
        for i in range(5):
            self._remember(f"запись {i}", tags=["тема"])
        self.assertIn("#тема — 5 записей", self._tags())

    def test_min_count_hides_rare_with_tail(self):
        self._remember("частая", tags=["частая"])
        self._remember("частая 2", tags=["частая"])
        self._remember("редкая", tags=["редкая"])
        out = self._tags(min_count=2)
        self.assertIn("#частая — 2 записи", out)
        self.assertNotIn("#редкая", out)
        self.assertIn("(показаны топ-1 тегов с не менее чем 2 записями)", out)

    def test_no_tail_without_filters_or_truncation(self):
        self._remember("запись", tags=["тема"])
        self.assertNotIn("показаны топ-", self._tags())

    def test_tail_when_limit_truncates(self):
        for i in range(12):
            self._remember(f"запись {i}", tags=[f"тег{i}"])
        out = self._tags(limit=3)
        self.assertIn("(показаны топ-3 тегов с не менее чем 1 записью)", out)

    def test_empty_after_filters(self):
        self._remember("запись", tags=["тема"], kind="lesson")
        out = self._tags(kinds=["event"])
        self.assertEqual(out, "(нет тегов по этому фильтру; всего тегов: 1)")

    def test_kinds_filter(self):
        self._remember("урок", tags=["ops"], kind="lesson")
        self._remember("диалог", tags=["диалог"], kind="event")
        out = self._tags(kinds=["lesson"])
        self.assertIn("#ops", out)
        self.assertNotIn("#диалог", out)

    def test_invalid_arguments(self):
        for kwargs in (
            {"limit": 0},
            {"limit": diary_tags.MAX_TAGS_LIMIT + 1},
            {"limit": "десять"},
            {"min_count": 0},
            {"min_count": -1},
            {"min_count": 1.5},
            {"kinds": ["мечта"]},
            {"kinds": "note"},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertTrue(self._tags(**kwargs).startswith("Error: invalid arguments"))

    def test_read_only_file_unchanged(self):
        self._remember("запись", tags=["тема"])
        before = self.paths.diary.read_text(encoding="utf-8")
        self._tags(min_count=1, limit=5)
        self.assertEqual(self.paths.diary.read_text(encoding="utf-8"), before)

    def test_requires_paths(self):
        self.assertEqual(tools.execute_tool("diary_tags", "{}", None),
                         "Error: paths не заданы")


class DiaryTagsSchemaTests(unittest.TestCase):
    """Схема и регистрация diary_tags."""

    def test_registered_in_schema_and_handlers(self):
        names = [t["function"]["name"] for t in tools.TOOLS_SCHEMA]
        self.assertIn("diary_tags", names)
        self.assertIn("diary_tags", tools._HANDLERS)
        self.assertIs(tools._HANDLERS["diary_tags"], tools_diary.handle_diary_tags)

    def test_schema_boundaries_match_validation_constants(self):
        props = tools_diary_schema.TAGS_TOOL["function"]["parameters"]["properties"]
        self.assertIn(f"1-{diary_tags.MAX_TAGS_LIMIT}", props["limit"]["description"])
        self.assertIn(str(diary_tags.DEFAULT_TAGS_LIMIT), props["limit"]["description"])
        self.assertEqual(props["kinds"]["items"]["enum"], list(diary.DIARY_KINDS))


if __name__ == "__main__":
    unittest.main()
