"""Форматирование результатов Brave без HTML и раздувания контекста."""

import html
import re

MAX_RESULT_CHARS = 8_000
MAX_OFFSET = 9
_TRUNCATED = "…(результаты обрезаны по размеру ответа)…"
_TAG_RE = re.compile(r"<[^>]*>")


def clean_search_text(value) -> str:
    """Убрать HTML-разметку, декодировать сущности и свернуть пробелы."""
    if not isinstance(value, str):
        return ""
    return " ".join(html.unescape(_TAG_RE.sub("", value)).split())


def _truncate(text: str, limit: int) -> str:
    marker = "\n…(ответ обрезан)…"
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(marker))].rstrip() + marker


def format_search_results(
    query: str,
    results: list[dict],
    more_results_available: bool = False,
    offset: int = 0,
) -> str:
    """Вернуть заголовки, ссылки, сниппеты и при необходимости next offset."""
    header = f"Результаты поиска: {clean_search_text(query)}"
    if not results:
        return f"{header}\n(нет результатов: ничего не найдено)"

    note = (
        f"Есть ещё результаты: следующий offset={offset + 1}"
        if more_results_available and offset < MAX_OFFSET
        else ""
    )
    body_limit = MAX_RESULT_CHARS - len(note) - bool(note) - len(_TRUNCATED) - 1
    lines = [header]
    truncated = False
    for index, item in enumerate(results, 1):
        title = clean_search_text(item.get("title")) or "(без заголовка)"
        url = item.get("url") if isinstance(item.get("url"), str) else ""
        block = [f"{index}. {title}", f"   {url.strip()}"]
        description = clean_search_text(item.get("description"))
        if description:
            block.append(f"   {description}")
        if len("\n".join([*lines, *block])) > body_limit:
            truncated = True
            break
        lines.extend(block)
    if truncated:
        lines.append(_TRUNCATED)
    if note:
        lines.append(note)
    return _truncate("\n".join(lines), MAX_RESULT_CHARS)
