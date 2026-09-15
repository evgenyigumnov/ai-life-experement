"""Частоты тегов дневника — оглавление тем агента за все жизни.

Чистые функции поверх уже загруженного дневника: только чтение, на диск
ничего не пишется.
"""

import diary

DEFAULT_TAGS_LIMIT = 10
MAX_TAGS_LIMIT = 50


def validate_min_count(value) -> int:
    """min_count: целое ≥ 1 (None — 1; верхней границы нет)."""
    if value is None:
        return 1
    if isinstance(value, bool) or not isinstance(value, int):
        raise diary.ValidationError("'min_count' должен быть целым числом")
    if value < 1:
        raise diary.ValidationError("'min_count' должен быть не меньше 1")
    return value


def count_tags(data: dict, kinds=None) -> dict[str, int]:
    """Число записей по каждому тегу (один проход, без сортировки).

    Теги приводятся к нижнему регистру — как в recall_page. kinds —
    фильтр типов записей (валидация diary.normalize_kinds).
    """
    wanted = diary.normalize_kinds(kinds)
    counts: dict[str, int] = {}
    for entry in data.get("entries") or []:
        if wanted and entry.get("kind") not in wanted:
            continue
        for tag in entry.get("tags") or []:
            name = str(tag).strip().lower()
            if name:
                counts[name] = counts.get(name, 0) + 1
    return counts


def tags_stats(data: dict, kinds=None, limit=None) -> list[tuple[str, int]]:
    """Топ тегов: пары (тег, count).

    Сортировка: count по убыванию, при равенстве — по алфавиту.
    limit — сколько тегов вернуть (валидация diary.validate_limit,
    по умолчанию DEFAULT_TAGS_LIMIT, максимум MAX_TAGS_LIMIT).
    """
    counts = count_tags(data, kinds=kinds)
    validated = diary.validate_limit(limit, DEFAULT_TAGS_LIMIT, MAX_TAGS_LIMIT)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:validated]
