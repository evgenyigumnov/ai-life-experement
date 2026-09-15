"""Постраничное чтение переписки с атомарной сменой read-флагов."""

from pathlib import Path

from agent_lock import agent_lock
from message_format import format_message_line
from storage_messages import _load_messages_unlocked, _save_messages_unlocked


def read_messages_page(path: Path, limit: int, cursor: int | None,
                       agent_label: str) -> str:
    """Сформировать страницу и пометить её непрочитанной до блокировки."""
    path = Path(path)
    with agent_lock(path):
        data = _load_messages_unlocked(path)
        all_messages = data.get("messages") or []
        if not all_messages:
            return "(переписки с создателем ещё нет)"
        end = len(all_messages) if cursor is None else min(cursor, len(all_messages))
        start = max(0, end - limit)
        if start == end:
            return (f"(более старых сообщений нет; всего сообщений в переписке: "
                    f"{len(all_messages)})")
        unread = {
            index for index in range(start, end)
            if not bool(all_messages[index].get("read", True))
        }
        lines = []
        for index in range(start, end):
            line = format_message_line(all_messages[index], agent_label, index=index)
            if index in unread:
                line += " (стало прочитанным)"
            lines.append(line)
        changed = False
        for index in range(start, end):
            if not bool(all_messages[index].get("read", True)):
                all_messages[index]["read"] = True
                changed = True
        if changed:
            _save_messages_unlocked(path, data)
        parts = [
            f"Переписка: показано {len(lines)} из {len(all_messages)} "
            "сообщений (от старых к новым):",
            *lines,
        ]
        if start > 0:
            parts.append(
                f"(есть более старые сообщения: следующая страница — "
                f"get_messages(cursor={start}))"
            )
        return "\n".join(parts)
