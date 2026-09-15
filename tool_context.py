"""Контекст, который уже созданный агент передаёт вложенному tool-вызову."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolContext:
    """Параметры общего клиента для tool, которому нужен дополнительный LLM."""

    client: object
    model: str
    temperature: float
    reasoning_effort: str | None = None
