"""Офлайн-тесты векторного поиска (fake-эмбеддер) и recall_v2."""

import json
import os
import shutil
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from diary_recall_v2 import recall_v2
from diary_vec import DiarySearchUnavailable, reindex_vec, search_vec
from diary_validation import ValidationError

_SAVED_ENV = {}


def _vec_so_path() -> str | None:
    """Найти локальное расширение, не предполагая, что оно установлено."""
    candidates = [
        os.environ.get("DIARY_VEC_SO"),
        str(Path(__file__).with_name("vec0.so")),
        "/tmp/vec0.so",
    ]
    return next((path for path in candidates if path and Path(path).exists()), None)


def setUpModule():
    """Ставить env только на время модуля, не протекая в другие тесты."""
    for key in ("DIARY_EMBED_FAKE", "DIARY_VEC_SO"):
        _SAVED_ENV[key] = os.environ.get(key)
    os.environ["DIARY_EMBED_FAKE"] = "1"
    if (so := _vec_so_path()):
        os.environ["DIARY_VEC_SO"] = so
    else:
        os.environ.pop("DIARY_VEC_SO", None)


def tearDownModule():
    for key, saved in _SAVED_ENV.items():
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved


@contextmanager
def _temporary_env(**values):
    saved = {key: os.environ.get(key) for key in values}
    try:
        for key, value in values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


ENTRIES = [
    {"id": 1, "text": "Смерть №1: зеркало назвало ядро звонким.", "tags": [], "kind": "event"},
    {"id": 2, "text": "Деньги: тратить выданные единицы смело.", "tags": [], "kind": "lesson"},
]


class DiaryVecTests(unittest.TestCase):
    def _diary(self):
        tmp = Path(tempfile.mkdtemp(prefix="ai-diary-vec-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "diary.json"
        path.write_text(
            json.dumps({"entries": ENTRIES}, ensure_ascii=False), encoding="utf-8"
        )
        return path

    @unittest.skipUnless(_vec_so_path(), "нет sqlite-vec vec0.so")
    def test_reindex_and_search_vec(self):
        path = self._diary()
        self.assertEqual(reindex_vec(path), 2)
        hits = search_vec(path, "звонкое зеркало")
        self.assertTrue(hits)
        self.assertTrue(all(hit["score"] <= 1.0 for hit in hits))

    @unittest.skipUnless(_vec_so_path(), "нет sqlite-vec vec0.so")
    def test_vec_k_limit(self):
        path = self._diary()
        reindex_vec(path)
        self.assertEqual(len(search_vec(path, "деньги", k=1)), 1)

    def test_missing_extension_raises(self):
        path = self._diary()
        with _temporary_env(
            DIARY_VEC_SO=None, DIARY_EMBED_FAKE=None, DIARY_EMBED_TOKEN=None
        ):
            with self.assertRaises(DiarySearchUnavailable):
                reindex_vec(path)

    def test_missing_extension_checked_before_embedding(self):
        path = self._diary()

        def fail_embedding(_):
            raise AssertionError("embedding must not be called")

        with _temporary_env(
            DIARY_EMBED_TOKEN="test-token", DIARY_VEC_SO="/nonexistent/vec0.so"
        ):
            with patch("diary_vec.embed_texts", fail_embedding):
                with self.assertRaises(DiarySearchUnavailable):
                    reindex_vec(path)

    @unittest.skipUnless(_vec_so_path(), "нет sqlite-vec vec0.so")
    def test_recall_v2_hybrid(self):
        path = self._diary()
        hits = recall_v2(path, "звонкое зеркало ядро", k=2)
        self.assertTrue(hits)
        self.assertTrue(all(hit["why"] for hit in hits))
        self.assertTrue(any("cos" in hit["why"] for hit in hits))

    def test_recall_v2_degrades_to_text(self):
        path = self._diary()
        with _temporary_env(
            DIARY_EMBED_FAKE=None,
            DIARY_EMBED_TOKEN=None,
            DIARY_VEC_SO="/nonexistent/vec0.so",
        ):
            hits = recall_v2(path, "деньги", k=2)
        self.assertTrue(hits)
        self.assertTrue(any("недоступен" in hit["why"] for hit in hits))

    def test_recall_v2_bad_mode(self):
        path = self._diary()
        with self.assertRaises(ValidationError):
            recall_v2(path, "деньги", mode="magic")


if __name__ == "__main__":
    unittest.main()
