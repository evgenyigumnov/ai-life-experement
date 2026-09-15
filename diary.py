"""Дневник — долгая личная память агента (diary.json).

Новые записи накапливаются, а не перезаписывают старые. Агент может
добавить запись, найти её по фильтрам и при необходимости точечно
исправить текст; удаления и отдельного журнала изменений нет.
"""

from pathlib import Path

from diary_query import recall, recall_page
from diary_storage import empty_diary, ensure_diary_file, load_diary, save_diary
from diary_validation import (
    DEFAULT_KIND,
    DEFAULT_RECALL_LIMIT,
    DIARY_KINDS,
    EntryNotFound,
    MAX_ENTRY_CHARS,
    MAX_RECALL_LIMIT,
    MAX_TAGS_PER_ENTRY,
    MAX_TAG_CHARS,
    RECALL_ORDERS,
    DiaryError,
    ValidationError,
    normalize_kinds,
    normalize_tags,
    validate_entry_id,
    validate_kind,
    validate_limit,
    validate_text,
)
from time_utils import now_iso


def _next_entry_id(data: dict) -> int:
    """Вернуть следующий id, учитывая повреждённый next_id."""
    max_id = max(
        (
            entry.get("id", 0)
            for entry in data.get("entries") or []
            if isinstance(entry.get("id"), int) and not isinstance(entry.get("id"), bool)
        ),
        default=0,
    )
    stored_next = data.get("next_id")
    if isinstance(stored_next, bool) or not isinstance(stored_next, int):
        stored_next = 1
    return max(max_id + 1, stored_next, 1)


def get_entry(data: dict, entry_id: int) -> dict | None:
    """Найти запись по id или вернуть None."""
    return next(
        (entry for entry in data.get("entries") or [] if entry.get("id") == entry_id),
        None,
    )


def remember(path: Path, text, tags=None, kind=DEFAULT_KIND) -> dict:
    """Добавить запись в дневник и сохранить её."""
    text, tags, kind = validate_text(text), normalize_tags(tags), validate_kind(kind)
    path = Path(path)
    data = load_diary(path)
    entry_id = _next_entry_id(data)
    entry = {
        "id": entry_id,
        "timestamp": now_iso(),
        "kind": kind,
        "tags": tags,
        "text": text,
        "edited_at": None,
        "edit_count": 0,
    }
    data.setdefault("entries", []).append(entry)
    data["next_id"] = entry_id + 1
    save_diary(path, data)
    return entry


def live_entries_count(data: dict) -> int:
    """Количество записей в дневнике."""
    return len(data.get("entries") or [])


def edit_entry(path: Path, entry_id, text) -> dict:
    """Точечно изменить текст записи, не затрагивая остальные."""
    entry_id = validate_entry_id(entry_id)
    text = validate_text(text)
    path = Path(path)
    data = load_diary(path)
    entry = get_entry(data, entry_id)
    if entry is None:
        raise EntryNotFound(f"запись id={entry_id} не найдена")
    entry["text"] = text
    entry["edited_at"] = now_iso()
    entry["edit_count"] = int(entry.get("edit_count") or 0) + 1
    save_diary(path, data)
    return entry
