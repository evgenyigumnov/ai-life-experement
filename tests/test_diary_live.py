"""Живые тесты эмбеддингов DeepInfra."""

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from dotenv import load_dotenv

import diary_vec


class DiaryLiveTests(unittest.TestCase):
    def setUp(self):
        self.saved_env = {
            key: os.environ.get(key)
            for key in (
                "DIARY_EMBED_FAKE",
                "DIARY_EMBED_TOKEN",
                "DIARY_EMBED_BASE_URL",
                "DIARY_EMBED_MODEL",
                "DIARY_EMBED_DIM",
                "DIARY_VEC_SO",
            )
        }
        load_dotenv()
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        for key, value in self.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _live_guard(self):
        if os.environ.get("DIARY_EMBED_FAKE") == "1":
            self.skipTest("DIARY_EMBED_FAKE=1 — офлайн-режим")
        if not os.environ.get("DIARY_EMBED_TOKEN"):
            self.skipTest("нет DIARY_EMBED_TOKEN")

    def test_embed_texts_live(self):
        self._live_guard()
        _, _, dim = diary_vec._config()
        vecs = diary_vec.embed_texts(
            ["кот спит на подоконнике", "рецепт борща со свёклой"]
        )
        self.assertEqual(len(vecs), 2)
        self.assertTrue(all(len(vector) == dim for vector in vecs))
        self.assertNotEqual(vecs[0], vecs[1])

    def test_search_vec_live_roundtrip(self):
        self._live_guard()
        so = os.environ.get("DIARY_VEC_SO") or str(
            Path(diary_vec.__file__).with_name("vec0.so")
        )
        if not os.path.exists(so):
            self.skipTest(f"нет vec0.so: {so}")
        tmp = Path(tempfile.mkdtemp(prefix="ai-diary-live-"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = tmp / "diary.json"
        path.write_text(
            json.dumps(
                {
                    "entries": [
                        {"id": 1, "text": "кот спит на подоконнике и смотрит на дождь", "tags": [], "kind": "note"},
                        {"id": 2, "text": "рецепт борща: свёкла, капуста, мясо, сметана", "tags": [], "kind": "note"},
                        {"id": 3, "text": "собрал sqlite-vec v0.1.9 из исходников под musl", "tags": [], "kind": "note"},
                    ]
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.assertEqual(diary_vec.reindex_vec(path), 3)
        hits = diary_vec.search_vec(
            path, "что я делал с векторной базой и расширением sqlite", k=2
        )
        self.assertTrue(hits)
        self.assertLessEqual(len(hits), 2)
        self.assertEqual(hits[0]["id"], 3)
        self.assertGreater(hits[0]["score"], 0.0)
        self.assertLessEqual(hits[0]["score"], 1.0)


if __name__ == "__main__":
    unittest.main()
