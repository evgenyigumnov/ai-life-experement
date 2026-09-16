"""Схемы diary-инструментов для LLM (OpenAI function calling).

Вынесены из tools_diary.py ради размера модуля; границы значений берутся
из констант модуля diary, чтобы схемы не расходились с валидацией.
"""

import diary
from diary_index import MODES as SEARCH_MODES
from diary_tags import DEFAULT_TAGS_LIMIT, MAX_TAGS_LIMIT

REMEMBER_TOOL = {
    "type": "function",
    "function": {
        "name": "diary_remember",
        "description": (
            "Записать в дневник (долгая память): событие, урок, "
            "ценность или мысль; возвращает id записи"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": f"Текст записи (до {diary.MAX_ENTRY_CHARS} символов)",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Теги для поиска (до 10, без регистра)",
                },
                "kind": {
                    "type": "string",
                    "enum": list(diary.DIARY_KINDS),
                    "description": "Тип записи (по умолчанию note)",
                },
            },
            "required": ["text"],
        },
    },
}

RECALL_TOOL = {
    "type": "function",
    "function": {
        "name": "diary_recall",
        "description": (
            "Найти записи в дневнике: поиск по словам и смыслу, теги, типы; "
            "без параметров — последние записи; листается курсором"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Текст запроса: слова или фраза (ищется по словам и по смыслу)",
                },
                "mode": {
                    "type": "string",
                    "enum": list(SEARCH_MODES),
                    "description": (
                        "Режим поиска: hybrid — слова + смысл (по умолчанию), "
                        "text — только слова (FTS5), vector — только смысл"
                    ),
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Запись должна иметь все эти теги",
                },
                "kinds": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(diary.DIARY_KINDS)},
                    "description": "Типы записей для отбора",
                },
                "limit": {
                    "type": "number",
                    "description": (
                        "Сколько записей вернуть "
                        f"(1-{diary.MAX_RECALL_LIMIT}, по умолчанию {diary.DEFAULT_RECALL_LIMIT})"
                    ),
                },
                "order": {
                    "type": "string",
                    "enum": list(diary.RECALL_ORDERS),
                    "description": "Порядок: new — новые сначала, old — старые",
                },
                "after_id": {
                    "type": "number",
                    "description": (
                        "Курсор пагинации: записи с id больше указанного "
                        "(листание при order=old)"
                    ),
                },
                "before_id": {
                    "type": "number",
                    "description": (
                        "Курсор пагинации: записи с id меньше указанного "
                        "(листание при order=new)"
                    ),
                },
            },
        },
    },
}

EDIT_TOOL = {
    "type": "function",
    "function": {
        "name": "diary_edit",
        "description": "Править текст одной записи дневника по id",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "number", "description": "id записи (из remember/recall)"},
                "text": {
                    "type": "string",
                    "description": f"Новый текст записи (до {diary.MAX_ENTRY_CHARS} символов)",
                },
            },
            "required": ["id", "text"],
        },
    },
}

TAGS_TOOL = {
    "type": "function",
    "function": {
        "name": "diary_tags",
        "description": (
            "Частые теги дневника — оглавление твоих тем за все жизни; "
            "все записи учитываются"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "number",
                    "description": (
                        "Сколько тегов показать "
                        f"(1-{MAX_TAGS_LIMIT}, по умолчанию {DEFAULT_TAGS_LIMIT})"
                    ),
                },
                "min_count": {
                    "type": "number",
                    "description": "Показать только теги с не меньшим числом записей",
                },
                "kinds": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(diary.DIARY_KINDS)},
                    "description": "Типы записей для отбора",
                },
            },
        },
    },
}
