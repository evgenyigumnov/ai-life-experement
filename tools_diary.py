"""Исполнители diary-инструментов: дневник (diary.json) — долгая память.

Исполнители тонкие: валидация и хранение — в модуле diary, здесь —
форматирование ответов и перевод ошибок в «Error: ...». Схемы — в
`tools_diary_schema.py`.
"""

import diary
import diary_index
from agent_text import _plural_entries
from agent_paths import AgentPaths
from diary_tags import count_tags, tags_stats, validate_min_count


def _format_entry(entry: dict) -> str:
    """Запись дневника для ответа tool: шапка (id/время/kind/теги) + текст."""
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


def handle_diary_remember(args: dict, paths: AgentPaths) -> str:
    """diary_remember: добавить запись в дневник, вернуть её id."""
    try:
        entry = diary.remember(
            paths.diary,
            args.get("text"),
            tags=args.get("tags"),
            kind=args.get("kind"),
        )
    except diary.ValidationError as exc:
        return f"Error: invalid arguments: {exc}"
    details = [f"kind={entry['kind']}"]
    if entry.get("tags"):
        details.append(f"tags: {', '.join(entry['tags'])}")
    return f"Записано в дневник: id={entry['id']} ({'; '.join(details)})"


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
    """Страница recall: новый поиск (text/vector/hybrid) при query, иначе прежний.

    Если поисковая машина недоступна, честно падаем на прежний подстрочный
    поиск: diary_recall не должен ломаться из-за индекса.
    """
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
        ranked = diary_index.search_ranked(
            diary_path, query, k=diary_index.candidate_k(limit), mode=chosen
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
    )


def handle_diary_recall(args: dict, paths: AgentPaths) -> str:
    """diary_recall: найти записи дневника по фильтрам (с пагинацией).

    С query работает поиск по режиму (text/vector/hybrid, по умолчанию
    hybrid) с автоиндексацией; без query — прежний список записей по id.
    """
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
    blocks = [_format_entry(entry) for entry in entries]
    parts = [header + "\n" + "\n---\n".join(blocks)]
    if next_cursor is not None:
        cursor_param = "before_id" if order == "new" else "after_id"
        parts.append(
            f"(есть ещё записи по фильтру: следующая страница — "
            f"diary_recall({cursor_param}={next_cursor}))"
        )
    return "\n".join(parts)


def handle_diary_edit(args: dict, paths: AgentPaths) -> str:
    """diary_edit: править текст одной записи по id."""
    try:
        entry = diary.edit_entry(paths.diary, args.get("id"), args.get("text"))
    except diary.ValidationError as exc:
        return f"Error: invalid arguments: {exc}"
    except diary.DiaryError as exc:
        return f"Error: {exc}"
    return f"Запись id={entry['id']} обновлена (правок: {entry['edit_count']})"


def handle_diary_tags(args: dict, paths: AgentPaths) -> str:
    """diary_tags: частые теги записей — оглавление тем (только чтение)."""
    try:
        data = diary.load_diary(paths.diary)
        min_count = validate_min_count(args.get("min_count"))
        kinds = args.get("kinds")
        stats = tags_stats(data, kinds=kinds, limit=args.get("limit"))
        filtered = count_tags(data, kinds=kinds)
    except diary.ValidationError as exc:
        return f"Error: invalid arguments: {exc}"
    total_entries = diary.live_entries_count(data)
    if not total_entries:
        return "(дневник пуст)"
    shown = [pair for pair in stats if pair[1] >= min_count]
    if not shown:
        return f"(нет тегов по этому фильтру; всего тегов: {len(count_tags(data))})"
    header = (
        f"Дневник, темы: всего записей {total_entries}, "
        f"всего тегов {len(count_tags(data))}."
    )
    parts = [header]
    parts.extend(f"#{tag} — {_plural_entries(count)}" for tag, count in shown)
    if min_count > 1 or len(shown) < len(filtered):
        threshold = (
            f"{min_count} записью"
            if min_count % 10 == 1 and min_count % 100 != 11
            else f"{min_count} записями"
        )
        parts.append(f"(показаны топ-{len(shown)} тегов с не менее чем {threshold})")
    return "\n".join(parts)
