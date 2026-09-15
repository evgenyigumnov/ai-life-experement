"""Tool web_fetch: прямая загрузка страницы без поискового API."""

from web_fetch_format import (
    MAX_RESULT_CHARS,
    decode_body,
    format_page_full,
    paginate_text,
)
from web_fetch_http import WebFetchError, fetch_url, is_valid_url

MAX_URL_CHARS = 4_000
WEB_FETCH_DEFAULT_LIMIT = MAX_RESULT_CHARS
WEB_FETCH_MAX_LIMIT = MAX_RESULT_CHARS

WEB_FETCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_fetch",
        "description": "Получить страницу по URL и читать её текст частями.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL страницы http или https"},
                "offset": {
                    "type": "number",
                    "description": "Номер первого символа страницы, начиная с 1",
                },
                "limit": {
                    "type": "number",
                    "description": (
                        f"Сколько символов вернуть (1-{WEB_FETCH_MAX_LIMIT}, "
                        f"по умолчанию {WEB_FETCH_DEFAULT_LIMIT})"
                    ),
                },
            },
            "required": ["url"],
        },
    },
}


def validate_web_fetch_args(args: dict) -> str:
    if not isinstance(args, dict):
        raise ValueError("ожидается JSON-объект аргументов")
    unknown = set(args) - {"url", "offset", "limit"}
    if unknown:
        raise ValueError(f"неизвестные аргументы: {', '.join(sorted(map(str, unknown)))}")
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("ожидается непустая строка 'url'")
    url = url.strip()
    if len(url) > MAX_URL_CHARS:
        raise ValueError(f"'url' не должен быть длиннее {MAX_URL_CHARS} символов")
    if not is_valid_url(url):
        raise ValueError("нужен URL с поддерживаемой схемой http или https")
    return url


def validate_web_fetch_page_args(args: dict) -> tuple[int, int, str | None]:
    """Проверить offset/limit и привести limit к безопасной границе."""
    offset = args.get("offset", 1)
    offset = 1 if offset is None else offset
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 1:
        raise ValueError(
            "'offset' должен быть целым числом от 1 (номер первого символа)"
        )

    limit = args.get("limit", WEB_FETCH_DEFAULT_LIMIT)
    limit = WEB_FETCH_DEFAULT_LIMIT if limit is None else limit
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError(
            f"'limit' должен быть целым числом от 1 до {WEB_FETCH_MAX_LIMIT}"
        )
    effective_limit = max(1, min(limit, WEB_FETCH_MAX_LIMIT))
    limit_note = None
    if effective_limit != limit:
        direction = "уменьшен" if limit > effective_limit else "увеличен"
        limit_note = f"limit {direction} до {effective_limit}"
    return offset, effective_limit, limit_note


def handle_web_fetch(args: dict, paths=None) -> str:
    """Загрузить URL и вернуть ограниченную страницу текста."""
    try:
        url = validate_web_fetch_args(args)
        offset, limit, limit_note = validate_web_fetch_page_args(args)
    except ValueError as exc:
        return f"Error: invalid arguments: {exc}"
    try:
        page = fetch_url(url)
        source = decode_body(page.body, page.content_type)
        answer = format_page_full(source, page.url, page.content_type)
        return paginate_text(answer, offset, limit, limit_note or "")
    except WebFetchError as exc:
        return f"Error: web_fetch: {exc}"
    except ValueError as exc:
        return f"Error: web_fetch: {exc}"
    except Exception:
        return "Error: web_fetch: не удалось обработать страницу"
