"""Векторный поиск «по смыслу» на sqlite-vec + эмбеддинги DeepInfra.

Эмбеддер: Qwen3-Embedding-0.6B через OpenAI-совместимый API DeepInfra
(проверено живьём: 1024d, $0.01/1M токенов). Хранилище — sqlite-vec,
расширение одним .so файлом рядом с diary.json, ноль серверов.
Конфигурация только через переменные окружения, токен в код не попадает.
"""

import json
import os
import sqlite3
import struct
import urllib.error
import urllib.request
from pathlib import Path

from diary_validation import DiaryError, ValidationError

_API_URL = "https://api.deepinfra.com/v1/openai/embeddings"
DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_DIM = 1024


class DiarySearchUnavailable(DiaryError):
    """Векторный поиск недоступен: нет токена, расширения или сети."""


def vec_db_path(diary_path) -> Path:
    """Путь к векторному индексу: рядом с diary.json, diary.vec.db."""
    return Path(diary_path).with_suffix(".vec.db")


def _config() -> tuple[str | None, str, int]:
    """Считать конфигурацию эмбеддера из окружения."""
    token = os.environ.get("DIARY_EMBED_TOKEN")
    model = os.environ.get("DIARY_EMBED_MODEL", DEFAULT_MODEL)
    dim = int(os.environ.get("DIARY_EMBED_DIM", str(DEFAULT_DIM)))
    return token, model, dim


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Превратить тексты в векторы; fake-режим — для офлайн-тестов."""
    if os.environ.get("DIARY_EMBED_FAKE") == "1":
        return [_fake_vector(text, _config()[2]) for text in texts]
    token, model, _ = _config()
    if not token:
        raise DiarySearchUnavailable(
            "нет DIARY_EMBED_TOKEN: живой поиск по смыслу требует токен DeepInfra"
        )
    body = json.dumps(
        {"input": texts, "model": model, "encoding_format": "float"}
    ).encode("utf-8")
    request = urllib.request.Request(
        _API_URL,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DiarySearchUnavailable(f"DeepInfra недоступен: {exc}") from exc
    data = payload.get("data") or []
    if len(data) != len(texts):
        raise DiarySearchUnavailable(
            f"DeepInfra вернул {len(data)} векторов вместо {len(texts)}"
        )
    return [item["embedding"] for item in data]


def _fake_vector(text: str, dim: int) -> list[float]:
    """Детерминированный вектор из хэша текста (только для тестов)."""
    import hashlib

    seed = hashlib.sha256(text.encode("utf-8")).digest()
    return [((seed[i % len(seed)] - 128) / 128) for i in range(dim)]


def _load_vec_extension(db: sqlite3.Connection, diary_path) -> None:
    """Загрузить vec0.so: env DIARY_VEC_SO или файл рядом с diary.json."""
    path = os.environ.get("DIARY_VEC_SO")
    if not path:
        neighbor = Path(diary_path).parent / "vec0.so"
        path = str(neighbor)
    if not Path(path).exists() and not Path(str(path)[:-3] if path.endswith(".so") else path).exists():
        raise DiarySearchUnavailable(
            "sqlite-vec не найден: положите релизный vec0.so рядом с diary.json"
            " или укажите DIARY_VEC_SO"
        )
    without_suffix = path[:-3] if path.endswith(".so") else path
    db.enable_load_extension(True)
    db.load_extension(without_suffix)
    db.enable_load_extension(False)


def _connect(diary_path, db_path) -> sqlite3.Connection:
    """Открыть базу с загруженным vec0 и таблицей entries_vec."""
    _, _, dim = _config()
    db = sqlite3.connect(str(db_path))
    _load_vec_extension(db, diary_path)
    db.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS entries_vec USING vec0("
        f"embedding float[{dim}] distance_metric=cosine)"
    )
    return db


def reindex_vec(diary_path, db_path=None) -> int:
    """Переиндексировать дневник векторами; вернуть число записей."""
    diary_path = Path(diary_path)
    db_path = Path(db_path) if db_path is not None else vec_db_path(diary_path)
    data = json.loads(diary_path.read_text(encoding="utf-8"))
    entries = data.get("entries") or []
    texts = [str(entry.get("text", "")) for entry in entries]
    vectors = embed_texts(texts) if texts else []
    db = _connect(diary_path, db_path)
    try:
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
    vector = embed_texts([query])[0]
    blob = struct.pack(f"<{len(vector)}f", *vector)
    db = _connect(diary_path, db_path)
    try:
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
    vector = embed_texts([str(entry.get("text", ""))])[0]
    blob = struct.pack(f"<{len(vector)}f", *vector)
    db = _connect(diary_path, db_path)
    try:
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
