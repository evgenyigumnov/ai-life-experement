"""Извлечение только видимого текста ответа vision-модели."""

import re

_OPEN_THINK = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
_CLOSE_THINK = re.compile(r"</think\s*>", re.IGNORECASE)
_DATA_URL = re.compile(
    r"data:image/[^\s;,]+;base64,[A-Za-z0-9+/=_-]+", re.IGNORECASE
)


class VisionAnswerError(ValueError):
    """Вложенная модель не вернула безопасный видимый ответ."""


def _content(response):
    if isinstance(response, str):
        return response
    return response.get("content") if isinstance(response, dict) else getattr(response, "content", None)


def extract_visible_answer(response) -> str:
    """Взять только content и удалить рассуждения из текста ответа."""
    content = _content(response)
    if not isinstance(content, str):
        raise VisionAnswerError("вложенная модель не вернула текстовый content")

    result, cursor = [], 0
    while cursor < len(content):
        opening = _OPEN_THINK.search(content, cursor)
        closing = _CLOSE_THINK.search(content, cursor)
        if closing and (opening is None or closing.start() < opening.start()):
            result = []
            cursor = closing.end()
            continue
        if opening is None:
            result.append(content[cursor:])
            break
        result.append(content[cursor:opening.start()])
        closing = _CLOSE_THINK.search(content, opening.end())
        if closing is None:
            raise VisionAnswerError("ответ содержит незакрытый <think>")
        cursor = closing.end()

    answer = _DATA_URL.sub("", "".join(result)).strip()
    if not answer:
        raise VisionAnswerError("видимый ответ пуст")
    return answer


def safe_error(exc: Exception) -> str:
    """Сократить ошибку и удалить случайно попавший Data URL."""
    text = str(exc).replace("\n", " ").strip() or type(exc).__name__
    text = _DATA_URL.sub("[данные изображения скрыты]", text)
    if len(text) > 500:
        text = text[:500] + "…"
    return text


_extract_visible_answer = extract_visible_answer
