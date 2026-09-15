"""Общие функции времени."""

from datetime import datetime


def now_iso() -> str:
    """Текущее локальное время в компактном ISO-формате."""
    return datetime.now().isoformat(timespec="seconds")
