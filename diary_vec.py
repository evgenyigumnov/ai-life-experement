"""Векторный индекс дневника на sqlite-vec."""

import json
import sqlite3
import struct
from pathlib import Path

from diary_validation import ValidationError
from diary_vec_runtime import (
    DEFAULT_DIM,
    DEFAULT_MODEL,
    DiarySearchUnavailable,
    _API_URL,
    _config,
    _extension_path,
    _fake_vector,
    _load_vec_extension,
    embed_texts,
)


def vec_db_path(diary_path) -> Path:
    """Путь к векторному индексу: рядом с diary.json, diary.vec.db."""
    return Path(diary_path).with_suffix(".vec.db")


def _connect(diary_path, db_path) -> sqlite3.Connection:
    """Открыть базу с загруженным vec0 и таблицей entries_vec."""
    _, _, dim = _config()
    extension = _extension_path(diary_path)
    db = sqlite3.connect(str(db_path))
    try:
        _load_vec_extension(db, extension)
        db.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS entries_vec USING vec0("
            f"embedding float[{dim}] distance_metric=cosine)"
        )
        return db
    except BaseException:
        db.close()
        raise


def reindex_vec(diary_path, db_path=None) -> int:
    """Переиндексировать дневник векторами; вернуть число записей."""
    diary_path = Path(diary_path)
    db_path = Path(db_path) if db_path is not None else vec_db_path(diary_path)
    data = json.loads(diary_path.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    texts = [str(entry.get("text", "")) for entry in entries]
    db = _connect(diary_path, db_path)
    try:
        vectors = embed_texts(texts) if texts else []
        with db:
            db.execute("DELETE FROM entries_vec")
            for entry, vector in zip(entries, vectors):
                blob = struct.pack(f"<{len(vector)}f", *vector)
                db.execute(
                    "INSERT INTO entries_vec(rowid, embedding) VALUES (?, ?)",
                    (entry.get("id"), blob),
                )
    finally:
        db.close()
    return len(entries)


def search_vec(diary_path, query, k=5, db_path=None) -> list[dict]:
    """Найти записи по смысловому родству; score = 1 - cosine-дистанция."""
    diary_path = Path(diary_path)
    db_path = Path(db_path) if db_path is not None else vec_db_path(diary_path)
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("запрос должен быть непустой строкой")
    if not db_path.exists():
        reindex_vec(diary_path, db_path)
    db = _connect(diary_path, db_path)
    try:
        vector = embed_texts([query])[0]
        blob = struct.pack(f"<{len(vector)}f", *vector)
        rows = db.execute(
            "SELECT rowid, distance FROM entries_vec"
            " WHERE embedding MATCH ? AND k = ?",
            (blob, int(k)),
        ).fetchall()
    finally:
        db.close()
    return [{"id": row[0], "score": 1 - row[1], "distance": row[1]} for row in rows]


def index_entry(diary_path, entry, db_path=None) -> None:
    """Добавить или обновить запись в векторном индексе (remember/edit)."""
    entry_id = entry.get("id")
    if entry_id is None:
        raise ValidationError("запись без id нельзя проиндексировать")
    diary_path = Path(diary_path)
    db_path = Path(db_path) if db_path is not None else vec_db_path(diary_path)
    db = _connect(diary_path, db_path)
    try:
        vector = embed_texts([str(entry.get("text", ""))])[0]
        blob = struct.pack(f"<{len(vector)}f", *vector)
        with db:
            db.execute("DELETE FROM entries_vec WHERE rowid = ?", (entry_id,))
            db.execute(
                "INSERT INTO entries_vec(rowid, embedding) VALUES (?, ?)",
                (entry_id, blob),
            )
    finally:
        db.close()


def remove_entry(diary_path, entry_id, db_path=None) -> None:
    """Убрать запись из векторного индекса (заготовка для удаления)."""
    diary_path = Path(diary_path)
    db_path = Path(db_path) if db_path is not None else vec_db_path(diary_path)
    if not Path(db_path).exists():
        return
    db = _connect(diary_path, db_path)
    try:
        with db:
            db.execute("DELETE FROM entries_vec WHERE rowid = ?", (entry_id,))
    finally:
        db.close()


def count_entries(diary_path, db_path=None) -> int:
    """Сколько записей сейчас в векторном индексе (сверка свежести)."""
    diary_path = Path(diary_path)
    db_path = Path(db_path) if db_path is not None else vec_db_path(diary_path)
    if not Path(db_path).exists():
        return 0
    db = _connect(diary_path, db_path)
    try:
        return int(db.execute("SELECT COUNT(*) FROM entries_vec").fetchone()[0])
    finally:
        db.close()
