"""Интеграционные тесты: новый поиск внутри жизненного цикла дневника.

Пользовательский сценарий diary_recall/remember/edit без ручного
reindex_*: автоиндексация старых записей, обновление индексов при записи
и правке, пересборка отсутствующего/устаревшего индекса, работа без
токена DeepInfra и без vec0.so, сохранение фильтров и пагинации.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))

import diary  # noqa: E402
import diary_vec  # noqa: E402
from agent_paths import AgentPaths  # noqa: E402
from tools_diary import (  # noqa: E402
    handle_diary_edit,
    handle_diary_recall,
    handle_diary_remember,
)


def _vec_so_path() -> str | None:
    """Путь к vec0.so, если он есть: DIARY_VEC_SO, рядом с модулем или в /tmp."""
    candidates = [os.environ.get("DIARY_VEC_SO"), str(Path(diary_vec.__file__).with_name("vec0.so")), "/tmp/vec0.so"]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


class IntegrationBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-diary-int-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.diary_path = self.tmp / "bot" / "diary.json"
        diary.ensure_diary_file(self.diary_path, "bot")
        self.paths = AgentPaths(
            folder=self.diary_path.parent,
            system_prompt=self.tmp / "system-prompt.md",
            mind_loop=self.tmp / "mind-loop.json",
            memory=self.tmp / "memory.md",
            diary=self.diary_path,
        )
        self._saved_env = {
            key: os.environ.get(key)
            for key in ("DIARY_EMBED_FAKE", "DIARY_EMBED_TOKEN", "DIARY_VEC_SO")
        }
        self.addCleanup(self._restore_env)
        os.environ["DIARY_EMBED_FAKE"] = "1"
        os.environ.pop("DIARY_EMBED_TOKEN", None)
        so = _vec_so_path()
        if so:
            os.environ["DIARY_VEC_SO"] = so

    def _restore_env(self):
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def recall(self, **args) -> str:
        return handle_diary_recall(args, self.paths)

    def remember(self, text, **args) -> str:
        return handle_diary_remember(dict(text=text, **args), self.paths)

    def edit(self, entry_id, text) -> str:
        return handle_diary_edit({"id": entry_id, "text": text}, self.paths)

    def write_entry_directly(self, entry: dict) -> None:
        """Запись в обход операций дневника — имитация внешнего изменения."""
        data = json.loads(self.diary_path.read_text(encoding="utf-8"))
        data["entries"].append(entry)
        data["next_id"] = max(entry["id"] + 1, data.get("next_id") or 1)
        self.diary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class AutoIndexTests(IntegrationBase):
    def _seed_existing(self) -> None:
        """Старые записи до появления механизма индексов — вручную в файл."""
        data = json.loads(self.diary_path.read_text(encoding="utf-8"))
        data["entries"] = [
            {
                "id": 1,
                "timestamp": "2026-01-01T00:00:00",
                "kind": "note",
                "tags": ["работа"],
                "text": "старая запись про нейросети и обучение",
                "edited_at": None,
                "edit_count": 0,
            },
            {
                "id": 2,
                "timestamp": "2026-01-02T00:00:00",
                "kind": "event",
                "tags": ["дом"],
                "text": "старая запись про ремонт кухни",
                "edited_at": None,
                "edit_count": 0,
            },
        ]
        data["next_id"] = 3
        self.diary_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def test_existing_entries_found_without_manual_reindex(self):
        self._seed_existing()
        self.assertFalse(self.diary_path.with_suffix(".search.db").exists())
        out = self.recall(query="нейросети", mode="text")
        self.assertIn("[id=1]", out)
        self.assertIn("нейросети", out)
        self.assertTrue(self.diary_path.with_suffix(".search.db").exists())

    def test_missing_index_is_rebuilt(self):
        self.remember("запись про телескопы и звёзды")
        search_db = self.diary_path.with_suffix(".search.db")
        self.recall(query="телескопы", mode="text")
        self.assertTrue(search_db.exists())
        search_db.unlink()
        out = self.recall(query="телескопы", mode="text")
        self.assertIn("телескопы", out)

    def test_stale_index_rebuilt_after_external_change(self):
        self.remember("запись про телескопы и звёзды")
        self.recall(query="телескопы", mode="text")
        self.write_entry_directly(
            {
                "id": 50,
                "timestamp": "2026-02-01T00:00:00",
                "kind": "note",
                "tags": [],
                "text": "внешняя запись про квазары",
                "edited_at": None,
                "edit_count": 0,
            }
        )
        out = self.recall(query="квазары", mode="text")
        self.assertIn("[id=50]", out)


class WriteHooksTests(IntegrationBase):
    def test_remember_is_searchable_immediately(self):
        self.remember("запись про марсианские хроники")
        out = self.recall(query="марсианские", mode="text")
        self.assertIn("[id=1]", out)

    def test_edit_replaces_old_text_in_index(self):
        self.remember("запись про старыйуникальныйтермин")
        self.assertIn("[id=1]", self.recall(query="старыйуникальныйтермин", mode="text"))
        self.edit(1, "запись про новыйуникальныйтермин")
        old = self.recall(query="старыйуникальныйтермин", mode="text")
        self.assertNotIn("[id=1]", old)
        new = self.recall(query="новыйуникальныйтермин", mode="text")
        self.assertIn("[id=1]", new)


class FallbackTests(IntegrationBase):
    def test_works_without_token_and_vec0(self):
        os.environ.pop("DIARY_EMBED_FAKE", None)
        os.environ.pop("DIARY_EMBED_TOKEN", None)
        os.environ["DIARY_VEC_SO"] = "/nonexistent/vec0.so"
        self.remember("запись про тихий океан")
        out = self.recall(query="океан")
        self.assertIn("океан", out)
        self.assertTrue(self.diary_path.with_suffix(".search.db").exists())
        self.assertFalse(self.diary_path.with_suffix(".vec.db").exists())

    def test_vec_index_built_when_available(self):
        if not _vec_so_path():
            self.skipTest("нет vec0.so: векторная часть недоступна")
        self.remember("строка про единорогов на луне")
        out = self.recall(query="строка про единорогов на луне", mode="hybrid")
        self.assertIn("[id=1]", out)
        self.assertTrue(self.diary_path.with_suffix(".vec.db").exists())


class FiltersPaginationTests(IntegrationBase):
    def _seed_three(self) -> None:
        self.remember("кухня: первый вариант", tags=["дом"], kind="note")
        self.remember("кухня: второй вариант", tags=["дом"], kind="note")
        self.remember("кухня: третий вариант", tags=["работа"], kind="event")

    def test_filters_and_pagination_with_search(self):
        self._seed_three()
        page_one = self.recall(query="кухня", mode="text", limit=1)
        self.assertIn("показано 1 записей", page_one)
        self.assertIn("[id=3]", page_one)
        cursor = re.search(r"before_id=(\d+)", page_one)
        self.assertIsNotNone(cursor)
        page_two = self.recall(
            query="кухня", mode="text", limit=1, before_id=int(cursor.group(1))
        )
        self.assertIn("[id=2]", page_two)

    def test_tag_and_kind_filters_survive_search(self):
        self._seed_three()
        tagged = self.recall(query="кухня", mode="text", tags=["дом"])
        self.assertIn("[id=1]", tagged)
        self.assertIn("[id=2]", tagged)
        self.assertNotIn("[id=3]", tagged)
        events = self.recall(query="кухня", mode="text", kinds=["event"])
        self.assertIn("[id=3]", events)
        self.assertNotIn("[id=1]", events)

    def test_plain_recall_without_query_still_works(self):
        self._seed_three()
        out = self.recall()
        self.assertIn("[id=3]", out)
        self.assertIn("[id=1]", out)


if __name__ == "__main__":
    unittest.main()
