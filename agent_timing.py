"""Длительность последнего ответа LLM для служебной заметки цикла."""

import math


_DURATION_FIELD = "llm_duration"


def _valid_duration(value) -> float | None:
    """Нормализовать сохранённую длительность или вернуть None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    duration = float(value)
    if not math.isfinite(duration) or duration < 0:
        return None
    return duration


def last_llm_duration(iterations) -> float | None:
    """Вернуть длительность самого свежего успешно сохранённого ответа."""
    if not isinstance(iterations, list):
        return None
    for record in reversed(iterations):
        if isinstance(record, dict):
            duration = _valid_duration(record.get(_DURATION_FIELD))
            if duration is not None:
                return duration
    return None


def last_llm_duration_note(iterations) -> str:
    """Сформировать заметку для LLM или пустую строку при отсутствии данных."""
    duration = last_llm_duration(iterations)
    if duration is None:
        return ""
    return f"(последний ответ LLM генерировался {duration:.2f} сек)"
