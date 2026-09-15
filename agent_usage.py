"""Извлечение статистики и размышлений из ответа LLM.

Работает с объектами OpenAI ChatCompletionMessage (usage — в атрибуте
`.usage`), SimpleNamespace / dict из моков или тестов.
"""


def _extract_usage(response):
    """Достать объект usage из ответа LLM (SDK-объект, dict, None).

    Обёртка `_MessageWithUsage` отдаёт usage атрибутом; dict-ответы
    (моки, сообщения из call_llm) — ключом "usage".
    """
    if response is None:
        return None
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    return usage


def _extract_prompt_tokens(response) -> int | None:
    """Извлечь число входных токенов (prompt_tokens) из ответа LLM."""
    usage = _extract_usage(response)
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage.get("prompt_tokens")
    return getattr(usage, "prompt_tokens", None)


def _extract_completion_tokens(response) -> int | None:
    """Извлечь число сгенерированных токенов (completion_tokens)."""
    usage = _extract_usage(response)
    if usage is None:
        return None
    if isinstance(usage, dict):
        return usage.get("completion_tokens")
    return getattr(usage, "completion_tokens", None)


def _extract_reasoning_tokens(response) -> int | None:
    """Извлечь число токенов размышлений (completion_tokens_details.reasoning_tokens).

    OpenAI-совместимые серверы (LM Studio и др.) для reasoning-моделей отдают
    `usage.completion_tokens_details.reasoning_tokens`; если поля нет — None.
    """
    usage = _extract_usage(response)
    if usage is None:
        return None
    details = (
        usage.get("completion_tokens_details")
        if isinstance(usage, dict)
        else getattr(usage, "completion_tokens_details", None)
    )
    if details is None:
        return None
    if isinstance(details, dict):
        return details.get("reasoning_tokens")
    return getattr(details, "reasoning_tokens", None)


def _extract_reasoning(response) -> str | None:
    """Извлечь текст размышлений модели, если сервер его отдаёт.

    Reasoning-модели (Qwen3 и др. за LM Studio / OpenRouter) выносят thinking
    в отдельное поле сообщения — `reasoning_content` или `reasoning` — а не в
    `content`. В историю это поле не попадает (нормализатор его отбрасывает
    и в повторные запросы оно не отправляется), но в консоли наблюдения
    видно, что модель «думала», — в том числе на пустых итерациях.
    """
    if response is None:
        return None
    if isinstance(response, dict):
        candidates = (response.get("reasoning_content"), response.get("reasoning"))
    else:
        # обёртка _MessageWithUsage делегирует неизвестные атрибуты исходному сообщению
        candidates = (
            getattr(response, "reasoning_content", None),
            getattr(response, "reasoning", None),
        )
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value
    return None
