"""Исполнители diary-инструментов: запись, редактирование и теги."""

import diary
from agent_text import _plural_entries
from agent_paths import AgentPaths
from diary_tags import count_tags, tags_stats, validate_min_count
from tools_diary_recall import handle_diary_recall


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
