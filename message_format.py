"""Единый формат строки сообщения для CLI и get_messages."""

def format_message_line(
    message: dict, agent_label: str, index: int | None = None
) -> str:
    """Отформатировать сообщение; index добавляет номер в общей переписке."""
    # Ленивый импорт не создаёт цикл: storage.py реэкспортирует API
    # storage_messages.py.
    from storage import SENDER_CREATOR, is_message_read

    number = f"[{index}] " if index is not None else ""
    sender = (
        "Создатель"
        if message.get("from") == SENDER_CREATOR
        else (agent_label or "ИИ")
    )
    return (
        f"{number}[{message.get('timestamp', '')}] {sender}: "
        f"{message.get('text', '')} "
        f"({'прочитано' if is_message_read(message) else 'не прочитано'})"
    )
