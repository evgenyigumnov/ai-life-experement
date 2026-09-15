"""Схемы инструментов переписки для LLM (OpenAI function calling)."""

MESSAGES_DEFAULT_LIMIT = 10
MESSAGES_MAX_LIMIT = 50

SEND_MESSAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "send_message",
        "description": "Отправить сообщение создателю",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Текст сообщения создателю",
                }
            },
            "required": ["text"],
        },
    },
}

GET_MESSAGES_TOOL = {
    "type": "function",
    "function": {
        "name": "get_messages",
        "description": (
            "Показать страницу переписки; непрочитанные помечаются "
            "прочитанными с отметкой «стало прочитанным»"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "number",
                    "description": (
                        "Сколько сообщений вернуть "
                        f"(1-{MESSAGES_MAX_LIMIT}, по умолчанию {MESSAGES_DEFAULT_LIMIT})"
                    ),
                },
                "cursor": {
                    "type": "number",
                    "description": (
                        "Курсор листания к старым: показать limit сообщений "
                        "до номера [N] из прошлого ответа"
                    ),
                },
            },
        },
    },
}
