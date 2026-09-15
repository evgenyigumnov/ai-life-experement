"""Фильтрация и курсорная пагинация дневника."""

from diary_validation import (
    DEFAULT_RECALL_LIMIT,
    MAX_RECALL_LIMIT,
    RECALL_ORDERS,
    ValidationError,
    normalize_kinds,
    normalize_tags,
    validate_entry_id,
    validate_limit,
)


def recall(
    data: dict,
    query=None,
    tags=None,
    kinds=None,
    limit=DEFAULT_RECALL_LIMIT,
    order="new",
    after_id=None,
    before_id=None,
) -> list[dict]:
    """Отфильтровать записи дневника без сохранения."""
    return recall_page(
        data, query, tags, kinds, limit, order, after_id, before_id
    )[0]


def recall_page(
    data: dict,
    query=None,
    tags=None,
    kinds=None,
    limit=DEFAULT_RECALL_LIMIT,
    order="new",
    after_id=None,
    before_id=None,
) -> tuple[list[dict], int | None]:
    """Вернуть страницу записей и курсор следующей страницы."""
    if query is not None:
        if not isinstance(query, str) or not query.strip():
            raise ValidationError("'query' должен быть непустой строкой")
        needle = query.strip().lower()
    else:
        needle = None
    wanted_tags = normalize_tags(tags)
    wanted_kinds = normalize_kinds(kinds)
    validated_limit = validate_limit(limit, DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT)
    if order not in RECALL_ORDERS:
        raise ValidationError(f"'order' должен быть одним из: {', '.join(RECALL_ORDERS)}")
    if after_id is not None:
        after_id = validate_entry_id(after_id, name="'after_id'")
    if before_id is not None:
        before_id = validate_entry_id(before_id, name="'before_id'")

    matched: list[dict] = []
    for entry in data.get("entries") or []:
        entry_id = entry.get("id")
        if isinstance(entry_id, bool) or not isinstance(entry_id, int):
            entry_id = None
        if after_id is not None and (entry_id is None or entry_id <= after_id):
            continue
        if before_id is not None and (entry_id is None or entry_id >= before_id):
            continue
        if needle is not None and needle not in str(entry.get("text", "")).lower():
            continue
        entry_tags = [str(tag).lower() for tag in entry.get("tags") or []]
        if any(tag not in entry_tags for tag in wanted_tags):
            continue
        if wanted_kinds and entry.get("kind") not in wanted_kinds:
            continue
        matched.append(entry)

    matched.sort(key=lambda entry: entry.get("id", 0), reverse=(order == "new"))
    page = matched[:validated_limit]
    next_cursor = page[-1].get("id") if len(matched) > validated_limit and page else None
    return page, next_cursor
