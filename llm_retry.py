"""Политика повторов для временных ошибок OpenAI-совместимого API."""

import sys

from openai import APIConnectionError, APIStatusError, InternalServerError, RateLimitError

MAX_ATTEMPTS = 5
BACKOFF_BASE = 2.0
LONG_PAUSE = 60.0


class EmptyResponseError(Exception):
    """Провайдер вернул ответ без choices."""


def is_retryable(exc: BaseException) -> bool:
    """Считать временными сетевые ошибки, 429, 5xx и пустой ответ."""
    if isinstance(exc, EmptyResponseError):
        return True
    if isinstance(exc, (APIConnectionError, RateLimitError, InternalServerError)):
        return True
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
