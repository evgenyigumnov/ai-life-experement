"""Клиент OpenAI-совместимого LLM с бесконечными retry-циклами."""

import time

from openai import OpenAI

from config_env import Config
from llm_message import MessageWithUsage as _MessageWithUsage
from llm_retry import (
    BACKOFF_BASE,
    LONG_PAUSE,
    MAX_ATTEMPTS,
    EmptyResponseError as _EmptyResponseError,
    is_retryable as _is_retryable,
    log as _log,
)
from model_support import normalize_reasoning_effort

REQUEST_TIMEOUT = 600.0


def make_client(cfg: Config) -> OpenAI:
    """Создать OpenAI-клиент для любого OpenAI-совместимого API."""
    return OpenAI(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        timeout=REQUEST_TIMEOUT,
        max_retries=0,
    )


def call_llm(
    client: OpenAI,
    model: str,
    messages: list,
    tools: list | None,
    temperature: float = 0.7,
    reasoning_effort: str | None = None,
):
    """Вызвать chat.completions и вернуть assistant message.

    `tools` не отправляется, если список пуст. Временные ошибки повторяются
    с backoff; постоянные ошибки пробрасываются вызывающему циклу. Usage
    доступен у результата через `.usage`, не мутируя SDK-сообщение.
    """
    while True:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                kwargs = {"tools": tools} if tools else {}
                effort = normalize_reasoning_effort(model, reasoning_effort)
                if effort:
                    kwargs["reasoning_effort"] = effort
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    **kwargs,
                )
                if not getattr(response, "choices", None):
                    raise _EmptyResponseError("пустой ответ API: нет choices")
                message = response.choices[0].message
                usage = getattr(response, "usage", None)
                if usage is not None:
                    if isinstance(message, dict):
                        message["usage"] = usage
                    else:
                        message = _MessageWithUsage(message, usage)
                return message
            except Exception as exc:
                if not _is_retryable(exc):
                    raise
                _log(f"llm: попытка {attempt}/{MAX_ATTEMPTS} не удалась: {exc!r}")
                if attempt < MAX_ATTEMPTS:
                    delay = BACKOFF_BASE * (2 ** (attempt - 1))
                    _log(f"llm: ждём {delay:.0f} сек и повторяем...")
                    time.sleep(delay)
        _log(
            f"llm: {MAX_ATTEMPTS} попыток не удалось — "
            f"пауза {LONG_PAUSE:.0f} сек, затем новый цикл попыток"
        )
        time.sleep(LONG_PAUSE)
