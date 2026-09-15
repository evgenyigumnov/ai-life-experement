"""Общие ошибки командной строки."""

import sys
from typing import NoReturn


def die(message: str, prefix: str = "Ошибка") -> NoReturn:
    """Напечатать ошибку и завершить процесс единым способом."""
    print(f"{prefix}: {message}", file=sys.stderr)
    raise SystemExit(1)
