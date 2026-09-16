"""Контекст, который уже созданный агент передаёт вложенному tool-вызову."""

from dataclasses import dataclass


@dataclass
class ToolContext:
    """Параметры LLM и сигналы, передаваемые из tool в текущий цикл."""

    client: object
    model: str
    temperature: float
    reasoning_effort: str | None = None
    sleep_requested: bool = False
    sleep_reason: str | None = None

    def request_sleep(self, reason: str) -> None:
        """Попросить цикл уснуть после записи текущей итерации."""
        self.sleep_requested = True
        self.sleep_reason = reason
