"""tools дневника: diary_remember / diary_recall (запись и поиск)."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import diary  # noqa: E402
import tool_registry as tools  # noqa: E402
from tests.tools_testkit import _paths  # noqa: E402

class DiaryToolsTests(unittest.TestCase):
    """tools дневника: diary_remember/recall — запись и поиск записей."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-diarytool-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.paths = _paths(self.tmp / "memory.md")

    def _call(self, name, **kwargs):
        return tools.execute_tool(name, json.dumps(kwargs), self.paths)

    def test_remember_returns_id_and_persists(self):
        out = self._call(
            "diary_remember",
            text="Создатель впервые спросил о моих мечтах",
            tags=["создатель", "диалог"],
            kind="event",
        )
        self.assertEqual(out, "Записано в дневник: id=1 (kind=event; tags: создатель, диалог)")
        data = json.loads(self.paths.diary.read_text(encoding="utf-8"))
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["kind"], "event")
        self.assertEqual(data["entries"][0]["tags"], ["создатель", "диалог"])

    def test_remember_without_tags_and_kind(self):
        out = self._call("diary_remember", text="просто заметка")
        self.assertEqual(out, "Записано в дневник: id=1 (kind=note)")

    def test_remember_validates_arguments(self):
        for kwargs in (
            {},
            {"text": ""},
            {"text": "   "},
            {"text": 42},
            {"text": "x" * (diary.MAX_ENTRY_CHARS + 1)},
            {"text": "ок", "kind": "мечта"},
            {"text": "ок", "tags": "список"},
            {"text": "ок", "tags": [42]},
        ):
            with self.subTest(kwargs=kwargs):
                out = self._call("diary_remember", **kwargs)
                self.assertTrue(out.startswith("Error: invalid arguments"), out)

    def test_recall_empty_diary(self):
        out = self._call("diary_recall")
        self.assertEqual(out, "(в дневнике нет записей по этому фильтру; всего записей: 0)")

    def test_recall_formats_entries(self):
        self._call("diary_remember", text="Первая запись", tags=["работа"])
        self._call("diary_remember", text="Docker снова упал", kind="lesson")
        out = self._call("diary_recall", query="docker")
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("Дневник: показано 1 записей"), out)
        self.assertIn("Docker снова упал", out)
        # формат записи: id, время, kind, теги, текст
        self.assertRegex(lines[1], r"^\[id=2\] \S+ lesson$")
        self.assertEqual(lines[2], "Docker снова упал")
        # разделитель между записями
        out_all = self._call("diary_recall")
        self.assertIn("\n---\n", out_all)
        self.assertIn("#работа", out_all)

    def test_recall_filters(self):
        self._call("diary_remember", text="Развернул docker", tags=["ops"], kind="lesson")
        self._call("diary_remember", text="Диалог о мечтах", tags=["диалог"], kind="event")
        out = self._call("diary_recall", tags=["диалог"], kinds=["event"])
        self.assertIn("Диалог о мечтах", out)
        self.assertNotIn("docker", out)
        out = self._call("diary_recall", limit=1, order="old")
        self.assertIn("Развернул docker", out)
        self.assertNotIn("Диалог о мечтах", out)

    def test_recall_validates_arguments(self):
        for kwargs in (
            {"query": ""},
            {"query": 42},
            {"limit": 0},
            {"limit": diary.MAX_RECALL_LIMIT + 1},
            {"order": "сначала"},
            {"kinds": ["мечта"]},
            {"tags": "тег"},
            {"before_id": 0},
            {"after_id": -1},
            {"before_id": "abc"},
        ):
            with self.subTest(kwargs=kwargs):
                out = self._call("diary_recall", **kwargs)
                self.assertTrue(out.startswith("Error: invalid arguments"), out)

    def test_recall_pagination_new_order(self):
        total = diary.DEFAULT_RECALL_LIMIT + 5  # больше одной страницы
        for i in range(1, total + 1):
            self._call("diary_remember", text=f"запись {i}")
        first = self._call("diary_recall")
        self.assertIn(f"показано {diary.DEFAULT_RECALL_LIMIT} записей", first)
        # последняя запись страницы — id=6 (новые сверху), курсор — на неё
        self.assertIn("diary_recall(before_id=6)", first)
        self.assertIn("есть ещё записи", first)
        second = self._call("diary_recall", before_id=6)
        self.assertIn("запись 1", second)
        self.assertIn("запись 5", second)
        self.assertNotIn("запись 6", second)
        self.assertNotIn("запись 7", second)
        # хвост короче лимита — подсказки больше нет
        self.assertNotIn("есть ещё записи", second)

    def test_recall_pagination_old_order(self):
        for i in range(1, 11):
            self._call("diary_remember", text=f"запись {i}")
        first = self._call("diary_recall", order="old", limit=4)
        self.assertIn("diary_recall(after_id=4)", first)
        second = self._call("diary_recall", order="old", limit=4, after_id=4)
        self.assertIn("запись 5", second)
        self.assertIn("запись 8", second)
        self.assertNotIn("запись 4", second)

    def test_recall_no_pagination_hint_when_fits(self):
        for i in range(3):
            self._call("diary_remember", text=f"запись {i}")
        out = self._call("diary_recall")
        self.assertNotIn("есть ещё записи", out)
        self.assertNotIn("before_id=", out)



if __name__ == "__main__":
    unittest.main()
