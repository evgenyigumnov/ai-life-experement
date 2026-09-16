"""Автоиндексация дневника: свежесть индексов и инкрементальные обновления.

Связывает новый поиск (diary_search: FTS5, diary_vec: sqlite-vec) с
жизненным циклом дневника: индексы собираются сами при первом поисковом
запросе, обновляются после remember/edit и пересобираются, если diary.json
изменился в обход этих операций. Ручной reindex_* не нужен.

Деградация честная: если эмбеддер (DIARY_EMBED_TOKEN / DIARY_EMBED_FAKE)
или sqlite-vec (vec0.so) недоступны, текстовый поиск работает, гибридный
переходит на текст, а векторный индекс достраивается при следующей
возможности.
"""

import hashlib
import json
from pathlib import Path

from diary_recall_v2 import recall_v2
from diary_search import (
    count_entries as _fts_count,
    index_entry as _index_fts_entry,
    reindex as _reindex_fts,
    remove_entry as _remove_fts_entry,
    search_db_path,
)
from diary_validation import ValidationError
from diary_vec import (
    count_entries as _vec_count,
    index_entry as _index_vec_entry,
    reindex_vec as _reindex_vec,
    remove_entry as _remove_vec_entry,
    vec_db_path,
)
from storage import _atomic_write_text

MODES = ("hybrid", "text", "vector")
DEFAULT_MODE = "hybrid"


def meta_path(diary_path) -> Path:
    """Служебный файл свежести индексов рядом с diary.json."""
    return Path(diary_path).with_suffix(".index-meta.json")


def diary_fingerprint(diary_path) -> str:
    """Отпечаток содержимого diary.json; пустая строка, если файла нет."""
    path = Path(diary_path)
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_k(limit) -> int:
    """Сколько кандидатов запросить у поиска под одну страницу выдачи."""
    try:
        base = int(limit)
    except (TypeError, ValueError):
        base = 10
    return max(50, min(200, base * 5))


def _read_meta(diary_path) -> dict:
    try:
        data = json.loads(meta_path(diary_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_meta(diary_path, meta: dict) -> None:
    try:
        _atomic_write_text(
            meta_path(diary_path), json.dumps(meta, ensure_ascii=False, indent=2)
        )
    except OSError:
        pass


def _live_count(diary_path) -> int:
    """Число записей в diary.json; 0, если прочитать нельзя."""
    try:
        data = json.loads(Path(diary_path).read_text(encoding="utf-8"))
        return len(data.get("entries") or [])
    except (OSError, ValueError):
        return 0


def ensure_indexes(diary_path) -> dict:
    """Довести индексы до состояния, соответствующего diary.json.

    Возвращает {'fts': bool, 'vec': bool} — что реально свежо и доступно;
    ошибки не пробрасываются: текстовый поиск должен работать всегда.
    """
    diary_path = Path(diary_path)
    result = {"fts": False, "vec": False}
    if not diary_path.exists():
        return result
    fingerprint = diary_fingerprint(diary_path)
    meta = _read_meta(diary_path)
    try:
        if (
            meta.get("fts_fp") != fingerprint
            or not search_db_path(diary_path).exists()
        ):
            _reindex_fts(diary_path)
        meta["fts_fp"] = fingerprint
        _write_meta(diary_path, meta)
        result["fts"] = True
    except Exception:
        meta.pop("fts_fp", None)
    try:
        if meta.get("vec_fp") != fingerprint or not vec_db_path(diary_path).exists():
            _reindex_vec(diary_path)
        meta["vec_fp"] = fingerprint
        _write_meta(diary_path, meta)
        result["vec"] = True
    except Exception:
        pass
    return result


def search_ranked(diary_path, query, k=5, mode=DEFAULT_MODE) -> list[dict]:
    """Поиск по дневнику: автоиндексация + честная деградация режимов."""
    if mode not in MODES:
        raise ValidationError(f"'mode' должен быть одним из: {', '.join(MODES)}")
    ensure_indexes(diary_path)
    if mode == "vector":
        try:
            return recall_v2(diary_path, query, k=k, mode="vector")
        except Exception:
            return recall_v2(diary_path, query, k=k, mode="text")
    return recall_v2(diary_path, query, k=k, mode=mode)


def update_entry(diary_path, entry) -> None:
    """Обновить индексы одной записью после remember/edit.

    Быстрый путь — точечный апсерт; если число записей в индексе разошлось
    с дневником, индекс пересобирается целиком. Любая ошибка индексации
    глотается: сохранение записи не должно ломаться.
    """
    diary_path = Path(diary_path)
    fingerprint = diary_fingerprint(diary_path)
    live = _live_count(diary_path)
    meta = _read_meta(diary_path)
    try:
        if search_db_path(diary_path).exists():
            _index_fts_entry(diary_path, entry)
            if _fts_count(diary_path) != live:
                _reindex_fts(diary_path)
        else:
            _reindex_fts(diary_path)
        meta["fts_fp"] = fingerprint
        _write_meta(diary_path, meta)
    except Exception:
        pass
    try:
        if vec_db_path(diary_path).exists() and meta.get("vec_fp"):
            _index_vec_entry(diary_path, entry)
            if _vec_count(diary_path) != live:
                _reindex_vec(diary_path)
        else:
            _reindex_vec(diary_path)
        meta["vec_fp"] = fingerprint
        _write_meta(diary_path, meta)
    except Exception:
        pass


def remove_entry(diary_path, entry_id) -> None:
    """Убрать запись из обоих индексов (заготовка для будущих удалений)."""
    diary_path = Path(diary_path)
    fingerprint = diary_fingerprint(diary_path)
    meta = _read_meta(diary_path)
    try:
        _remove_fts_entry(diary_path, entry_id)
        if _fts_count(diary_path) == _live_count(diary_path):
            meta["fts_fp"] = fingerprint
            _write_meta(diary_path, meta)
    except Exception:
        pass
    try:
        _remove_vec_entry(diary_path, entry_id)
        if _vec_count(diary_path) == _live_count(diary_path):
            meta["vec_fp"] = fingerprint
            _write_meta(diary_path, meta)
    except Exception:
        pass
