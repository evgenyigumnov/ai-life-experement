"""Схема OpenAI function calling для internet_search."""


INTERNET_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "internet_search",
        "description": "Найти свежую информацию в интернете и вернуть ссылки.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Текст запроса"},
                "count": {
                    "type": "integer",
                    "description": "Количество результатов (1–10, по умолчанию 5)",
                },
                "offset": {
                    "type": "integer",
                    "description": "Страница результатов (0–9, по умолчанию 0)",
                },
                "country": {"type": "string", "description": "Двухбуквенный код страны"},
                "search_lang": {"type": "string", "description": "Код языка поиска"},
                "freshness": {
                    "type": "string",
                    "enum": ["pd", "pm", "pw", "py"],
                    "description": "Свежесть: pd, pw, pm или py",
                },
            },
            "required": ["query"],
        },
    },
}
