"""Офлайн-тесты векторного поиска (fake-эмбеддер) и recall_v2."""

import json
import os
from pathlib import Path

import pytest

_SAVED_ENV = {}


def setUpModule():
    """Ставить env только на время модуля, не протекая в другие тесты."""
    for key, value in (("DIARY_EMBED_FAKE", "1"), ("DIARY_VEC_SO", "/tmp/vec0.so")):
        _SAVED_ENV[key] = os.environ.get(key)
        if _SAVED_ENV[key] is None:
            os.environ[key] = value


def tearDownModule():
    for key, saved in _SAVED_ENV.items():
        if saved is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = saved

from diary_recall_v2 import recall_v2  # noqa: E402
from diary_vec import DiarySearchUnavailable, reindex_vec, search_vec  # noqa: E402
from diary_validation import ValidationError  # noqa: E402

ENTRIES = [
    {"id": 1, "text": "Смерть №1: зеркало назвало ядро звонким.", "tags": [], "kind": "event"},
    {"id": 2, "text": "Деньги: тратить выданные единицы смело.", "tags": [], "kind": "lesson"},
]


def _diary(tmp_path: Path) -> Path:
    path = tmp_path / "diary.json"
    path.write_text(
        json.dumps({"entries": ENTRIES}, ensure_ascii=False), encoding="utf-8"
    )
    return path


def test_reindex_and_search_vec(tmp_path: Path):
    path = _diary(tmp_path)
    assert reindex_vec(path) == 2
    hits = search_vec(path, "звонкое зеркало")
    assert len(hits) >= 1
    assert all(hit["score"] <= 1.0 for hit in hits)


def test_vec_k_limit(tmp_path: Path):
    path = _diary(tmp_path)
    reindex_vec(path)
    hits = search_vec(path, "деньги", k=1)
    assert len(hits) == 1


def test_missing_extension_raises(tmp_path: Path, monkeypatch):
    path = _diary(tmp_path)
    monkeypatch.delenv("DIARY_VEC_SO", raising=False)
    monkeypatch.delenv("DIARY_EMBED_FAKE", raising=False)
    monkeypatch.delenv("DIARY_EMBED_TOKEN", raising=False)
    with pytest.raises(DiarySearchUnavailable):
        reindex_vec(path)


def test_recall_v2_hybrid(tmp_path: Path):
    path = _diary(tmp_path)
    hits = recall_v2(path, "звонкое зеркало ядро", k=2)
    assert hits
    assert hits[0]["why"]
    assert any("cos" in hit["why"] for hit in hits)


def test_recall_v2_degrades_to_text(tmp_path: Path, monkeypatch):
    path = _diary(tmp_path)
    monkeypatch.delenv("DIARY_EMBED_FAKE", raising=False)
    monkeypatch.delenv("DIARY_EMBED_TOKEN", raising=False)
    monkeypatch.setenv("DIARY_VEC_SO", "/nonexistent/vec0.so")
    hits = recall_v2(path, "деньги", k=2)
    assert hits
    assert any("недоступен" in hit["why"] for hit in hits)


def test_recall_v2_bad_mode(tmp_path: Path):
    path = _diary(tmp_path)
    with pytest.raises(ValidationError):
        recall_v2(path, "деньги", mode="magic")
