"""Поиск дневника и его публичный индексный API."""

from diary_index_lifecycle import ensure_indexes, remove_entry, update_entry
from diary_index_meta import diary_fingerprint, meta_path
from diary_recall_v2 import recall_v2
from diary_validation import ValidationError

MODES = ("hybrid", "text", "vector")
DEFAULT_MODE = "hybrid"


def candidate_k(limit, total=None) -> int:
    """Сколько кандидатов запросить, не теряя записи из фильтров."""
    try:
        base = int(limit)
    except (TypeError, ValueError):
        base = 10
    requested = max(50, min(200, base * 5))
    try:
        total = int(total or 0)
    except (TypeError, ValueError):
        total = 0
    return max(requested, total)


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
