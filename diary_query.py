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


def _filters(query, tags, kinds, limit, order, after_id, before_id):
    if query is not None:
        if not isinstance(query, str) or not query.strip():
            raise ValidationError("'query' должен быть непустой строкой")
        query = query.strip().lower()
    if order not in RECALL_ORDERS:
        raise ValidationError(f"'order' должен быть одним из: {', '.join(RECALL_ORDERS)}")
    return (
        query,
        normalize_tags(tags),
        normalize_kinds(kinds),
        validate_limit(limit, DEFAULT_RECALL_LIMIT, MAX_RECALL_LIMIT),
        order,
        _validate_cursor(after_id, "'after_id'"),
        _validate_cursor(before_id, "'before_id'"),
    )


def _validate_cursor(value, name):
    return validate_entry_id(value, name=name) if value is not None else None


def _entry_id(entry):
    value = entry.get("id")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _matches(entry, needle, wanted_tags, wanted_kinds):
    if needle is not None and needle not in str(entry.get("text", "")).lower():
        return False
    entry_tags = [str(tag).lower() for tag in entry.get("tags") or []]
    return not any(tag not in entry_tags for tag in wanted_tags) and (
        not wanted_kinds or entry.get("kind") in wanted_kinds
    )


def _page(matched, limit, order):
    matched.sort(key=lambda entry: entry.get("id", 0), reverse=(order == "new"))
    page = matched[:limit]
    cursor = page[-1].get("id") if len(matched) > limit and page else None
    return page, cursor


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
    needle, wanted_tags, wanted_kinds, limit, order, after_id, before_id = _filters(
        query, tags, kinds, limit, order, after_id, before_id
    )
    matched = []
    for entry in data.get("entries") or []:
        entry_id = _entry_id(entry)
        if after_id is not None and (entry_id is None or entry_id <= after_id):
            continue
        if before_id is not None and (entry_id is None or entry_id >= before_id):
            continue
        if _matches(entry, needle, wanted_tags, wanted_kinds):
            matched.append(entry)
    return _page(matched, limit, order)


def recall_page_by_ids(
    data: dict,
    ids,
    tags=None,
    kinds=None,
    limit=DEFAULT_RECALL_LIMIT,
    order="new",
    after_id=None,
    before_id=None,
    preserve_order=False,
) -> tuple[list[dict], int | None]:
    """Страница записей по id; preserve_order сохраняет порядок поиска."""
    ordered_ids = [
        value for value in (ids or [])
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    wanted_ids = set(ordered_ids)
    _, wanted_tags, wanted_kinds, limit, order, after_id, before_id = _filters(
        None, tags, kinds, limit, order, after_id, before_id
    )
    matched = [
        entry
        for entry in data.get("entries") or []
        if _entry_id(entry) in wanted_ids
        and _matches(entry, None, wanted_tags, wanted_kinds)
    ]
    if not preserve_order:
        matched = [
            entry for entry in matched
            if (after_id is None or _entry_id(entry) > after_id)
            and (before_id is None or _entry_id(entry) < before_id)
        ]
        return _page(matched, limit, order)

    rank = {value: position for position, value in enumerate(ordered_ids)}
    anchor = before_id if order == "new" else after_id
    if anchor in rank:
        matched = [entry for entry in matched if rank[_entry_id(entry)] > rank[anchor]]
    else:
        matched = [
            entry for entry in matched
            if (after_id is None or _entry_id(entry) > after_id)
            and (before_id is None or _entry_id(entry) < before_id)
        ]
    matched.sort(key=lambda entry: rank[_entry_id(entry)])
    page = matched[:limit]
    cursor = page[-1].get("id") if len(matched) > limit and page else None
    return page, cursor
