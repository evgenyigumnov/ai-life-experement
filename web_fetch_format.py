"""Форматирование результата web_fetch и списка ссылок."""

import re

from web_fetch_html import extract_html, normalize_text

MAX_RESULT_CHARS = 8_000
_TRUNCATION = "\n…(ответ обрезан по размеру)…"
_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_HTML_TYPES = {"text/html", "application/xhtml+xml"}


def truncate(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(_TRUNCATION))].rstrip() + _TRUNCATION


def decode_body(raw: bytes, content_type: str = "") -> str:
    """Декодировать HTML с charset из заголовка или UTF-8 по умолчанию."""
    match = re.search(r"charset\s*=\s*[\"']?\s*([\w.-]+)", content_type, re.I)
    encoding = match.group(1) if match else "utf-8"
    try:
        return raw.decode(encoding, errors="replace")
    except (LookupError, UnicodeError):
        return raw.decode("utf-8", errors="replace")


def _plain_with_links(source: str):
    links, link_ids = [], {}

    def replace(match):
        value = match.group(0)
        while value and value[-1] in ".,;:!?)]}":
            value = value[:-1]
        if not value:
            return match.group(0)
        if value not in link_ids:
            link_ids[value] = len(links) + 1
            links.append(value)
        suffix = match.group(0)[len(value):]
        return f"{value} [{link_ids[value]}]{suffix}"

    return normalize_text(_URL_RE.sub(replace, source)), links


def _is_html(content_type: str) -> bool:
    media_type = content_type.split(";", 1)[0].strip().lower()
    return not media_type or media_type in _HTML_TYPES


def _compose_page(source: str, base_url: str, content_type: str, max_chars: int | None):
    if _is_html(content_type):
        body, links = extract_html(source, base_url)
    else:
        body, links = _plain_with_links(source)
    body = body or "(страница не содержит видимого текста)"
    if not links:
        return truncate(body, max_chars) if max_chars is not None else body
    references = "\n\nСсылки:\n" + "\n".join(
        f"[{index}] {url}" for index, url in enumerate(links, 1)
    )
    if max_chars is not None:
        available = max_chars - len(references)
        if len(body) > available:
            body = truncate(body, max(1, available))
    result = body + references
    return truncate(result, max_chars) if max_chars is not None else result


def format_page(source: str, base_url: str, content_type: str = "") -> str:
    """Извлечь текст страницы с безопасным размером обычного результата."""
    return _compose_page(source, base_url, content_type, MAX_RESULT_CHARS)


def format_page_full(source: str, base_url: str, content_type: str = "") -> str:
    """Извлечь полный текст страницы перед постраничной выдачей."""
    return _compose_page(source, base_url, content_type, None)


def paginate_text(text: str, offset: int, limit: int, note: str = "") -> str:
    """Вернуть безопасную страницу текста, используя offset с единицы."""
    total = len(text)
    if offset > total:
        raise ValueError(f"offset={offset} за пределами страницы (всего {total} символов)")
    start = offset - 1
    requested_end = min(total, start + limit)

    def render(end: int) -> str:
        header = f"web_fetch: символы {offset}–{end} из {total}"
        if note:
            header += f" ({note})"
        if end < total:
            header += f"\nпродолжение — web_fetch offset={end + 1}"
        else:
            header += "\n(конец страницы)"
        return header + "\n\n" + text[start:end]

    result = render(requested_end)
    if len(result) > MAX_RESULT_CHARS:
        low, high = start, requested_end
        while low < high:
            middle = (low + high + 1) // 2
            if len(render(middle)) <= MAX_RESULT_CHARS:
                low = middle
            else:
                high = middle - 1
        result = render(low)
    return truncate(result, MAX_RESULT_CHARS)
