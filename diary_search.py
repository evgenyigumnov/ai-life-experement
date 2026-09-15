"""Полнотекстовый поиск по дневнику на SQLite FTS5 (ступень А).

BM25-ранжирование, сниппеты, поиск по любому слову запроса вместо
точной подстроки. Индекс — отдельный файл рядом с diary.json; при
записи дневник индексируется целиком (при 10К записей — секунды).
Ноль новых зависимостей: FTS5 встроен в стандартный sqlite3.
"""

import json
import sqlite3
from pathlib import Path

from diary_validation import ValidationError

_SCHEMA = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS entries_fts USING fts5("
    "text, tags, kind UNINDEXED, entry_id UNINDEXED)"
)


def search_db_path(diary_path) -> Path:
    """Путь к индексу: рядом с diary.json, имя diary.search.db."""
    return Path(diary_path).with_suffix(".search.db")


def _connect(db_path) -> sqlite3.Connection:
    """Открыть базу индекса и убедиться в наличии fts5-таблицы."""
    db = sqlite3.connect(str(db_path))
    db.executescript(_SCHEMA)
    return db


def reindex(diary_path, db_path=None) -> int:
    """Пересобрать индекс целиком из diary.json; вернуть число записей."""
    diary_path = Path(diary_path)
    db_path = Path(db_path) if db_path is not None else search_db_path(diary_path)
    data = json.loads(diary_path.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    db = _connect(db_path)
    try:
        with db:
            db.execute("DELETE FROM entries_fts")
            for entry in entries:
                db.execute(
                    "INSERT INTO entries_fts(text, tags, kind, entry_id)"
                    " VALUES (?, ?, ?, ?)",
                    (
                        str(entry.get("text", "")),
                        " ".join(str(t) for t in entry.get("tags") or []),
                        str(entry.get("kind", "note")),
                        entry.get("id"),
                    ),
                )
    finally:
        db.close()
    return len(entries)


def index_entry(diary_path, entry, db_path=None) -> None:
    """Добавить или обновить одну запись в индексе (после remember/edit)."""
    entry_id = entry.get("id")
    if entry_id is None:
        raise ValidationError("запись без id нельзя проиндексировать")
    db_path = Path(db_path) if db_path is not None else search_db_path(diary_path)
    db = _connect(db_path)
    try:
        with db:
            db.execute("DELETE FROM entries_fts WHERE entry_id = ?", (entry_id,))
            db.execute(
                "INSERT INTO entries_fts(text, tags, kind, entry_id)"
                " VALUES (?, ?, ?, ?)",
                (
                    str(entry.get("text", "")),
                    " ".join(str(t) for t in entry.get("tags") or []),
                    str(entry.get("kind", "note")),
                    entry_id,
                ),
            )
    finally:
        db.close()


def _fts_query(query: str) -> str:
    """Собрать FTS5-запрос: термы через OR, кавычки удваиваются."""
    terms = []
    for raw in query.split():
        term = raw.replace('"', '""')
        if term:
            terms.append(f'"{term}"')
    if not terms:
        raise ValidationError("запрос не содержит слов")
    return " OR ".join(terms)


def search(diary_path, query, k=5, db_path=None) -> list[dict]:
    """Найти записи по BM25.

    Возвращает [{'id', 'score', 'snippet'}], лучшие первыми; score —
    -bm25, то есть больше = лучше (единый знак с векторным поиском).
    Пустой индекс собирается из diary.json автоматически.
    """
    diary_path = Path(diary_path)
    db_path = Path(db_path) if db_path is not None else search_db_path(diary_path)
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("запрос должен быть непустой строкой")
    if not db_path.exists():
        reindex(diary_path, db_path)
    db = _connect(db_path)
    try:
        rows = db.execute(
            "SELECT entry_id, bm25(entries_fts),"
            " snippet(entries_fts, 0, '[', ']', '…', 12)"
            " FROM entries_fts WHERE entries_fts MATCH ?"
            " ORDER BY rank LIMIT ?",
            (_fts_query(query), int(k)),
        ).fetchall()
    finally:
        db.close()
    return [{"id": row[0], "score": -row[1], "snippet": row[2]} for row in rows]
