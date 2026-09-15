"""Нормализация assistant-сообщений для хранения и повторной отправки."""

import json


_REASONING_FIELDS = ("reasoning_content", "reasoning")


def _normalize_tool_call(raw, index: int) -> dict | None:
    """Привести один tool-call к формату OpenAI messages."""
    if not isinstance(raw, dict):
        return None
    function = raw.get("function")
    if not isinstance(function, dict):
        return None
    name = function.get("name")
    if not isinstance(name, str) or not name:
        return None
    arguments = function.get("arguments", "")
    if not isinstance(arguments, str):
        arguments = json.dumps(arguments, ensure_ascii=False)
    return {
        "id": raw.get("id") or f"call_{index}",
        "type": raw.get("type") or "function",
        "function": {"name": name, "arguments": arguments},
    }


def _reasoning_fields(raw: dict) -> dict:
    """Сохранить поддерживаемые провайдерские поля reasoning без переименования."""
    return {
        name: raw[name]
        for name in _REASONING_FIELDS
        if isinstance(raw.get(name), str) and raw[name].strip()
    }


def _normalize_assistant_message(raw) -> dict | None:
    """Нормализовать assistant-сообщение, сохранив reasoning для следующего тика.

    Reasoning передаётся обратно под тем же именем, под которым его вернул
    провайдер: `reasoning_content` или `reasoning`. Reasoning-only ответ тоже
    сохраняется, чтобы следующий тик мог продолжить незавершённое мышление.
    """
    if isinstance(raw, str):
        raw = {"content": raw}
    if not isinstance(raw, dict):
        return None

    content = raw.get("content")
    if not isinstance(content, str) or not content.strip():
        content = None

    tool_calls = [
        call
        for call in (
            _normalize_tool_call(tc, i) for i, tc in enumerate(raw.get("tool_calls") or [])
        )
        if call is not None
    ]
    reasoning = _reasoning_fields(raw)

    if content is None and not tool_calls and not reasoning:
        return None

    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    message.update(reasoning)
    return message
