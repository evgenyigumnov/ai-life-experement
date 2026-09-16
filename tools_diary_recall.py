"""Обработчик diary_recall и интеграция поиска с прежним форматом ответа."""

import re

import diary
import diary_index
from agent_paths import AgentPaths


def _format_entry(entry: dict) -> str:
    """Запись дневника для ответа tool."""
    header = (
        f"[id={entry.get('id')}] {entry.get('timestamp', '')} "
        f"{entry.get('kind', diary.DEFAULT_KIND)}"
    )
    tags = entry.get("tags") or []
    if tags:
        header += " " + " ".join(f"#{tag}" for tag in tags)
    if entry.get("edit_count"):
        header += " (изменена)"
    return f"{header}\n{entry.get('text', '')}"


def _recall_page_by_mode(
    diary_path,
    data: dict,
    *,
    query,
    mode,
    tags,
    kinds,
    limit,
    order,
    after_id,
    before_id,
):
    """Получить страницу: поиск при query, прежний список без него."""
    if query is None:
        return diary.recall_page(
            data,
            tags=tags,
            kinds=kinds,
            limit=limit,
            order=order,
            after_id=after_id,
            before_id=before_id,
        )
    if not isinstance(query, str) or not query.strip():
        raise diary.ValidationError("'query' должен быть непустой строкой")
    chosen = mode or diary_index.DEFAULT_MODE
    if chosen not in diary_index.MODES:
        raise diary.ValidationError(
            f"'mode' должен быть одним из: {', '.join(diary_index.MODES)}"
        )
    try:
        total_entries = len(data.get("entries") or [])
        ranked = diary_index.search_ranked(
            diary_path,
            query,
            k=diary_index.candidate_k(limit, total_entries),
            mode=chosen,
        )
    except Exception:
        return diary.recall_page(
            data,
            query=query,
            tags=tags,
            kinds=kinds,
            limit=limit,
            order=order,
            after_id=after_id,
            before_id=before_id,
        )
    return diary.recall_page_by_ids(
        data,
        [item["id"] for item in ranked],
        tags=tags,
        kinds=kinds,
        limit=limit,
        order=order,
        after_id=after_id,
        before_id=before_id,
        preserve_order=chosen != "text",
    )


def handle_diary_recall(args: dict, paths: AgentPaths) -> str:
    """diary_recall: найти записи по фильтрам, словам или смыслу."""
    try:
        data = diary.load_diary(paths.diary)
        order = args.get("order") or "new"
        entries, next_cursor = _recall_page_by_mode(
            paths.diary,
            data,
            query=args.get("query"),
            mode=args.get("mode"),
            tags=args.get("tags"),
            kinds=args.get("kinds"),
            limit=(
                diary.DEFAULT_RECALL_LIMIT
                if args.get("limit") is None
                else args.get("limit")
            ),
            order=order,
            after_id=args.get("after_id"),
            before_id=args.get("before_id"),
        )
    except diary.ValidationError as exc:
        return f"Error: invalid arguments: {exc}"
    total = diary.live_entries_count(data)
    if not entries:
        return f"(в дневнике нет записей по этому фильтру; всего записей: {total})"
    header = f"Дневник: показано {len(entries)} записей (всего: {total}):"
    parts = [header + "\n" + "\n---\n".join(_format_entry(e) for e in entries)]
    if next_cursor is not None:
        cursor_param = "before_id" if order == "new" else "after_id"
        parts.append(
            f"(есть ещё записи по фильтру: следующая страница — "
            f"diary_recall({cursor_param}={next_cursor}))"
        )
    return "\n".join(parts)
