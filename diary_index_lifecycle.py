"""Поддержание FTS- и векторных индексов при изменениях дневника."""

from pathlib import Path

from diary_index_meta import (
    diary_fingerprint,
    entry_fingerprints,
    incremental_safe,
    live_count,
    mark_fresh,
    read_meta,
    write_meta,
)
from diary_search import (
    count_entries as _fts_count,
    index_entry as _index_fts_entry,
    reindex as _reindex_fts,
    remove_entry as _remove_fts_entry,
    search_db_path,
)
from diary_vec import (
    count_entries as _vec_count,
    index_entry as _index_vec_entry,
    reindex_vec as _reindex_vec,
    remove_entry as _remove_vec_entry,
    vec_db_path,
)


def ensure_indexes(diary_path) -> dict:
    """Довести индексы до состояния, соответствующего diary.json."""
    diary_path = Path(diary_path)
    result = {"fts": False, "vec": False}
    if not diary_path.exists():
        return result
    fingerprint = diary_fingerprint(diary_path)
    try:
        fingerprints = entry_fingerprints(diary_path)
    except Exception:
        return result
    meta = read_meta(diary_path)
    try:
        if (
            meta.get("fts_fp") != fingerprint
            or meta.get("fts_entries_fp") != fingerprints
            or not search_db_path(diary_path).exists()
        ):
            _reindex_fts(diary_path)
        mark_fresh(meta, "fts", fingerprint, fingerprints)
        write_meta(diary_path, meta)
        result["fts"] = True
    except Exception:
        meta.pop("fts_fp", None)
        meta.pop("fts_entries_fp", None)
    try:
        if (
            meta.get("vec_fp") != fingerprint
            or meta.get("vec_entries_fp") != fingerprints
            or not vec_db_path(diary_path).exists()
        ):
            _reindex_vec(diary_path)
        mark_fresh(meta, "vec", fingerprint, fingerprints)
        write_meta(diary_path, meta)
        result["vec"] = True
    except Exception:
        meta.pop("vec_fp", None)
        meta.pop("vec_entries_fp", None)
    return result


def update_entry(diary_path, entry) -> None:
    """Обновить индексы после remember/edit, не ломая сохранение дневника."""
    diary_path = Path(diary_path)
    fingerprint = diary_fingerprint(diary_path)
    live = live_count(diary_path)
    try:
        fingerprints = entry_fingerprints(diary_path)
    except Exception:
        fingerprints = None
    meta = read_meta(diary_path)
    try:
        if (
            search_db_path(diary_path).exists()
            and fingerprints is not None
            and incremental_safe(meta, "fts", fingerprints, entry.get("id"))
        ):
            _index_fts_entry(diary_path, entry)
            if _fts_count(diary_path) != live:
                _reindex_fts(diary_path)
        else:
            _reindex_fts(diary_path)
        mark_fresh(meta, "fts", fingerprint, fingerprints)
        write_meta(diary_path, meta)
    except Exception:
        pass
    try:
        if (
            vec_db_path(diary_path).exists()
            and fingerprints is not None
            and incremental_safe(meta, "vec", fingerprints, entry.get("id"))
        ):
            _index_vec_entry(diary_path, entry)
            if _vec_count(diary_path) != live:
                _reindex_vec(diary_path)
        else:
            _reindex_vec(diary_path)
        mark_fresh(meta, "vec", fingerprint, fingerprints)
        write_meta(diary_path, meta)
    except Exception:
        pass


def remove_entry(diary_path, entry_id) -> None:
    """Убрать запись из обоих индексов (заготовка для будущих удалений)."""
    diary_path = Path(diary_path)
    fingerprint = diary_fingerprint(diary_path)
    try:
        fingerprints = entry_fingerprints(diary_path)
    except Exception:
        fingerprints = {}
    live = live_count(diary_path)
    meta = read_meta(diary_path)
    try:
        _remove_fts_entry(diary_path, entry_id)
        if _fts_count(diary_path) == live:
            mark_fresh(meta, "fts", fingerprint, fingerprints)
            write_meta(diary_path, meta)
    except Exception:
        pass
    try:
        _remove_vec_entry(diary_path, entry_id)
        if _vec_count(diary_path) == live:
            mark_fresh(meta, "vec", fingerprint, fingerprints)
            write_meta(diary_path, meta)
    except Exception:
        pass
