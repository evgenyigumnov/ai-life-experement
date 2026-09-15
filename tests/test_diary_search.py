"""Тесты полнотекстового поиска по дневнику (FTS5)."""

import json
from pathlib import Path

import pytest

from diary_search import index_entry, reindex, search
from diary_validation import ValidationError

ENTRIES = [
    {"id": 1, "text": "Смерть №1: зеркало назвало ядро звонким, боевой аврал.", "tags": ["смерть"], "kind": "event"},
    {"id": 2, "text": "materiatura — так я назвал материю из диалога с дедом.", "tags": ["диалог"], "kind": "idea"},
    {"id": 3, "text": "Деньги: на совместную работу тратить только выданные единицы.", "tags": ["деньги"], "kind": "lesson"},
]


def _diary(tmp_path: Path) -> Path:
    path = tmp_path / "diary.json"
    path.write_text(
        json.dumps({"entries": ENTRIES}, ensure_ascii=False), encoding="utf-8"
    )
    return path


def test_reindex_and_search(tmp_path: Path):
    path = _diary(tmp_path)
    assert reindex(path) == 3
    hits = search(path, "звонким")
    assert hits and hits[0]["id"] == 1
    assert hits[0]["snippet"]
    assert hits[0]["score"] > 0


def test_any_word_query(tmp_path: Path):
    path = _diary(tmp_path)
    reindex(path)
    hits = search(path, "materiatura дед")
    assert any(hit["id"] == 2 for hit in hits)


def test_no_hit(tmp_path: Path):
    path = _diary(tmp_path)
    reindex(path)
    assert search(path, "динозавр") == []


def test_empty_query_raises(tmp_path: Path):
    path = _diary(tmp_path)
    with pytest.raises(ValidationError):
        search(path, "   ")


def test_index_entry_update(tmp_path: Path):
    path = _diary(tmp_path)
    reindex(path)
    index_entry(path, {"id": 4, "text": "Мост между агентами: письма в messages.json.", "tags": [], "kind": "note"})
    hits = search(path, "мост агентами")
    assert hits and hits[0]["id"] == 4


def test_stale_index_auto_rebuild(tmp_path: Path):
    path = _diary(tmp_path)
    hits = search(path, "деньги единицы")
    assert any(hit["id"] == 3 for hit in hits)
