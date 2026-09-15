"""Клиент LLM: создание OpenAI-клиента и вызов chat.completions с ретраями (шаг 4).

Политика сбоев (по плану): сетевые ошибки, 429 и 5xx считаются временными —
попытки повторяются с экспоненциальным backoff (2, 4, 8, 16 сек; до 5 попыток
в цикле), после исчерпания цикла — пауза 60 сек и новый цикл попыток, бесконечно:
жизнь агента не должна останавливаться из-за временного сбоя API. Прерывание
(Ctrl+C) при этом остаётся возможным — `time.sleep` пробрасывает KeyboardInterrupt.

Остальные ошибки (400/401/403 и т.п. — постоянные) не ретраятся и пробрасываются
наверх: их обработает главный цикл (шаг 7 плана).

Встроенные ретраи OpenAI-клиента отключены (`max_retries=0`), чтобы весь
повторный запуск и тайминги контролировались только этим модулем.
"""

import sys
import time

from openai import (
    APIConnectionError,
    APIStatusError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)

from config_env import Config

MAX_ATTEMPTS = 5  # попыток в одном цикле ретраев
BACKOFF_BASE = 2.0  # первая пауза (сек), далее ×2: 2, 4, 8, 16
LONG_PAUSE = 60.0  # пауза после исчерпания цикла попыток (сек)
REQUEST_TIMEOUT = 300.0  # таймаут одного HTTP-запроса к API (сек): локальный GPU может генерировать ответ дольше облачных API


class _EmptyResponseError(Exception):
    """Пустой ответ провайдера (нет choices) — считаем временным сбоем."""


class _MessageWithUsage:
    """Обёртка ответа ассистента с дополнительным полем `usage`.

    Мутить SDK-объект нельзя: у моделей openai `model_config` имеет
    `extra="allow"` + `defer_build=True`, и присвоение «лишнего» атрибута
    ломает сериализатор — последующий `model_dump()` падает с
    `TypeError: 'MockValSer' object is not an instance of 'SchemaSerializer'`.
    Поэтому usage прокидывается через делегирующую обёртку, а исходное
    сообщение остаётся нетронутым.
    """

    __slots__ = ("_message", "usage")

    def __init__(self, message, usage):
        self._message = message
        self.usage = usage

    def __getattr__(self, name):
        # content, tool_calls и прочие атрибуты исходного сообщения
        return getattr(self._message, name)

    def model_dump(self):
        """Сериализация как у исходного сообщения (поле `usage` не входит)."""
        dump = getattr(self._message, "model_dump", None)
        if callable(dump):
            return dump()
        # сообщение без model_dump (SimpleNamespace и т.п.) — минимальный dict
        return {
            "role": "assistant",
            "content": getattr(self._message, "content", None),
            "tool_calls": getattr(self._message, "tool_calls", None),
        }


def make_client(cfg: Config) -> OpenAI:
    """Создать OpenAI-клиент (работает с любым OpenAI-совместимым API)."""
    return OpenAI(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        timeout=REQUEST_TIMEOUT,
        max_retries=0,
    )


def _is_retryable(exc: BaseException) -> bool:
    """Временный ли сбой: сеть/таймаут, 429, 5xx, пустой ответ."""
    if isinstance(exc, _EmptyResponseError):
        return True
    if isinstance(exc, (APIConnectionError, RateLimitError, InternalServerError)):
        return True
    # на случай нестандартных 5xx, которые SDK не отобразил на InternalServerError
    return isinstance(exc, APIStatusError) and exc.status_code >= 500


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def call_llm(
    client: OpenAI,
    model: str,
    messages: list,
    tools: list | None,
    temperature: float = 0.7,
    reasoning_effort: str | None = None,
):
    """Вызвать chat.completions с ретраями и вернуть сообщение ассистента
    (распарсенное `choices[0].message`: `content` + `tool_calls`) — именно оно
    нужно главному циклу (шаг 7). Если ответ содержит `usage`, он доступен
    в атрибуте `.usage` возвращённого объекта: для SDK-сообщений — через
    обёртку `_MessageWithUsage` (исходный объект не мутируется), для
    dict-сообщений — просто ключом `"usage"`. `tools` — стандартный формат
    OpenAI function calling; если передан None/пустой список, параметр не
    отправляется вовсе (некоторые серверы не принимают `tools: null`).
    По умолчанию температура 0.7 (`temperature=0.7`): для автономного агента
    в бесконечном цикле жадное декодирование (temperature=0) опасно — на
    повторяющемся контексте модель детерминированно воспроизводит тот же
    tool-call бесконечно (дегенеративная репетиция). Значение можно
    переопределить переменной TEMPERATURE в .env (прокидывается через
    Config.temperature в agent_loop.run_loop).
    `reasoning_effort` — уровень «размышлений» reasoning-моделей;
    значение уходит в API без изменений: шкала OpenAI-совместимых серверов
    "none" | "minimal" | "low" | "medium" | "high" | "xhigh" (например,
    LM Studio) либо "max" (GLM-5.3-Flash через DeepInfra — максимальный
    бюджет thinking; без параметра сервер не гарантирует размышлений).
    Передаётся, только если задан явно: без параметра сервер решает сам
    (DeepInfra для GLM-5.3-Flash по умолчанию может не включать размышления
    вовсе), а «чужим» локальным серверам лишний параметр не нужен.
    Прокидывается через Config.reasoning_effort (REASONING_EFFORT в .env).
    """
    while True:
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                kwargs = {"tools": tools} if tools else {}
                if reasoning_effort:
                    kwargs["reasoning_effort"] = reasoning_effort
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
