"""Tools send_message / get_messages: переписка с создателем.

send_message дописывает сообщение в messages.json от имени агента (вся
переписка хранится целиком). get_messages показывает страницу всей переписки и помечает показанные
непрочитанные сообщения прочитанными; переход виден в выдаче как «не
прочитано» и «стало прочитанным». cursor — номер
сообщения [N] из прошлого ответа — листает к более старым сообщениям (как
before_id в дневнике). Человек пишет через `python main.py <имя> reply`.
"""

from agent_paths import AgentPaths
from storage import SENDER_AGENT, append_message
from message_pages import read_messages_page
from tools_chat_schema import (
    GET_MESSAGES_TOOL,
    MESSAGES_DEFAULT_LIMIT,
    MESSAGES_MAX_LIMIT,
    SEND_MESSAGE_TOOL,
)


def handle_send_message(args: dict, paths: AgentPaths) -> str:
    """send_message: дописать в messages.json от имени агента."""
    text = args.get("text")
    if not isinstance(text, str) or not text.strip():
        return "Error: invalid arguments: ожидается непустая строка 'text'"
    append_message(paths.messages, SENDER_AGENT, text)
    return "Сообщение отправлено создателю"


def handle_get_messages(args: dict, paths: AgentPaths) -> str:
    """get_messages: страница переписки от старых к новым.

    Сначала формируются строки с исходным статусом. Непрочитанные сообщения
    затем помечаются прочитанными, а в выдаче получают отметку «стало
    прочитанным».
    """
    limit = args.get("limit")
    if limit is None:
        limit = MESSAGES_DEFAULT_LIMIT
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= MESSAGES_MAX_LIMIT
    ):
        return (
            f"Error: invalid arguments: 'limit' должен быть целым "
            f"от 1 до {MESSAGES_MAX_LIMIT}"
        )
    cursor = args.get("cursor")
    if cursor is not None and (
        isinstance(cursor, bool) or not isinstance(cursor, int) or cursor < 0
    ):
        return (
            "Error: invalid arguments: 'cursor' должен быть целым неотрицательным "
            "номером сообщения [N] из ответа"
        )

    return read_messages_page(
        paths.messages, limit, cursor, getattr(paths, "name", "") or "ИИ"
    )
