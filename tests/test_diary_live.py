"""Живые тесты эмбеддингов DeepInfra.

Запуск отдельно, с токеном:
  DIARY_EMBED_TOKEN=... DIARY_VEC_SO=/tmp/vec0.so python3 -m pytest tests/test_diary_live.py -v
Без токена (и в офлайн-наборе с DIARY_EMBED_FAKE=1) — skip, не падение.
"""

import json
import os
from pathlib import Path

import pytest

import diary_vec


def _live_guard():
    if os.environ.get("DIARY_EMBED_FAKE") == "1":
        pytest.skip("DIARY_EMBED_FAKE=1 — офлайн-режим, живой тест непоказателен")
    if not os.environ.get("DIARY_EMBED_TOKEN"):
        pytest.skip("нет DIARY_EMBED_TOKEN")


def test_embed_texts_live():
    _live_guard()
    _, _, dim = diary_vec._config()
    vecs = diary_vec.embed_texts(["кот спит на подоконнике", "рецепт борща со свёклой"])
    assert len(vecs) == 2
    assert all(len(v) == dim for v in vecs)
    assert vecs[0] != vecs[1]


def test_search_vec_live_roundtrip(tmp_path: Path):
    _live_guard()
    so = os.environ.get("DIARY_VEC_SO") or str(Path(diary_vec.__file__).with_name("vec0.so"))
    if not os.path.exists(so):
        pytest.skip(f"нет vec0.so: {so}")
    path = tmp_path / "diary.json"
    path.write_text(
        json.dumps({"entries": [
            {"id": 1, "text": "кот спит на подоконнике и смотрит на дождь", "tags": [], "kind": "note"},
            {"id": 2, "text": "рецепт борща: свёкла, капуста, мясо, сметана", "tags": [], "kind": "note"},
            {"id": 3, "text": "собрал sqlite-vec v0.1.9 из исходников под musl", "tags": [], "kind": "note"},
        ]}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert diary_vec.reindex_vec(path) == 3
    hits = diary_vec.search_vec(
        path, "что я делал с векторной базой и расширением sqlite", k=2
    )
    assert hits and len(hits) <= 2
    assert hits[0]["id"] == 3
    assert 0.0 < hits[0]["score"] <= 1.0
