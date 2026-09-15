"""Статус непрочитанных сообщений создателя для очередного тика."""

from agent_pause import _creator_messages
from agent_text import _plural_messages
from agent_paths import AgentPaths
from storage import is_message_read


def _unread_creator_count(paths: AgentPaths) -> int:
    """Вернуть число непрочитанных сообщений создателя.

    Единственный источник статуса — флаг ``read`` в ``messages.json``.
    Тексты сообщений здесь не извлекаются в prompt: агент сам вызывает
    ``get_messages``, когда хочет прочитать переписку.
    """
    return sum(
        not is_message_read(message) for message in _creator_messages(paths)
    )


def _creator_messages_status_note(paths: AgentPaths) -> dict | None:
    """Вернуть user-заметку только при наличии непрочитанных сообщений."""
    unread_count = _unread_creator_count(paths)
    if not unread_count:
        return None
    return {
        "role": "user",
        "content": (
            "У тебя есть непрочитанные сообщения от создателя: "
            f"{_plural_messages(unread_count)}. "
            "Прочитай их через get_messages."
        ),
    }
