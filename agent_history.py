"""Нормализация истории итераций и реплей их в messages для LLM.

Контракт хранения итерации (используется и циклом при записи):

    {
      "n": <int>,
      "timestamp": "<ISO>",
      "user": "сделай следующее действие (на последней итерации сессии — директива сохранить память)",
      "assistant_message": {
        "role": "assistant",
        "content": "<текст или null>",
        "tool_calls": [
          {"id": "...", "type": "function",
           "function": {"name": "...", "arguments": "<JSON-строка>"}}
        ]
      },
      "tool_results": [
        {"tool_call_id": "...", "tool": "...", "arguments": "...", "result": "<строка>"}
      ]
    }

Особые случаи:
- итерация-ошибка (`{"error": ...}`, пишется циклом при неожиданном исключении)
  воспроизводится текстовым сообщением ассистента «[сбой итерации: ...]»;
- «сырой» вид ассистентского сообщения (например, `model_dump()` SDK-объекта с
  `refusal`/`function_call: null`) нормализуется: лишние ключи отбрасываются,
  иначе некоторые серверы отклоняют запрос;
- результат tool-call ищется по `tool_call_id`, при отсутствии — по порядку
  (запасный вариант для старых записей без id).
"""

import json

from agent_paths import AgentPaths
from prompts_messages import INTERNAL_MESSAGES


def _normalize_tool_call(raw, index: int) -> dict | None:
    """Привести один tool-call к формату OpenAI messages.

    `arguments` иногда приходит уже распарсенным объектом (не JSON-строкой) —
    строкуем обратно: протокол ожидает строку. Битые записи (без имени
    функции) пропускаются (возвращается None).
    """
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


def _normalize_assistant_message(raw) -> dict | None:
    """Привести сохранённый ответ ассистента к формату messages.

    Принимает dict вида `{"role": "assistant", "content": ..., "tool_calls": ...}`
    (или строку — считается текстом ответа). None-поля и посторонние ключи
    отбрасываются. Если после нормализации не осталось ни текста, ни
    tool-call'ов — возвращается None (итерацию нечего воспроизводить).
    """
    if isinstance(raw, str):
        raw = {"content": raw}
    if not isinstance(raw, dict):
        return None

    content = raw.get("content")
    # пустая или из одних пробелов строка — это отсутствие текста: иначе
    # «пустой» ответ (только reasoning) записывался как валидная итерация
    if not isinstance(content, str) or not content.strip():
        content = None

    tool_calls = [
        call
        for call in (
            _normalize_tool_call(tc, i) for i, tc in enumerate(raw.get("tool_calls") or [])
        )
        if call is not None
    ]

    if content is None and not tool_calls:
        return None

    message: dict = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _iteration_tool_calls(record) -> list[dict]:
    """Нормализованные tool-вызовы итерации (может быть пусто)."""
    if not isinstance(record, dict):
        return []
    assistant = _normalize_assistant_message(record.get("assistant_message"))
    if assistant is None:
        return []
    return assistant.get("tool_calls") or []


def _tool_result_messages(record: dict, tool_calls: list[dict], paths: AgentPaths) -> list[dict]:
    """Сообщения role=`tool` для tool-call'ов итерации.

    Результат ищется по `tool_call_id`; в записях без id — по порядку вызова.
    Ненайденный результат заменяется внутренней fallback-строкой протокола.
    """
    results = record.get("tool_results") or []
    by_id = {
        entry.get("tool_call_id"): entry
        for entry in results
        if isinstance(entry, dict) and entry.get("tool_call_id")
    }

    messages: list[dict] = []
    for index, call in enumerate(tool_calls):
        call_id = call.get("id") or f"call_{index}"
        entry = by_id.get(call_id)
        if entry is None and index < len(results) and isinstance(results[index], dict):
            entry = results[index]
        result = entry.get("result") if entry else None
        if not isinstance(result, str):
            result = INTERNAL_MESSAGES["tool-result-missing.md"]
        messages.append({"role": "tool", "tool_call_id": call_id, "content": result})
    return messages


def _iteration_messages(record, paths: AgentPaths) -> list[dict]:
    """Перевести одну итерацию истории в сообщения для LLM (может быть пусто)."""
    if not isinstance(record, dict):
        return []

    # Специальная итерация-ошибка: ассистентского ответа нет,
    # фиксируем сбой внутренней fallback-строкой, чтобы история не «терялась».
    if "error" in record and "assistant_message" not in record:
        error = record.get("error") or "неизвестная ошибка"
        template = INTERNAL_MESSAGES["iteration-failed.md"]
        return [
            {
                "role": "assistant",
                "content": template.format(error=error),
            }
        ]

    assistant = _normalize_assistant_message(record.get("assistant_message"))
    if assistant is None:
        return []

    messages = [assistant]
    if assistant.get("tool_calls"):
        messages.extend(_tool_result_messages(record, assistant["tool_calls"], paths))
    return messages


def _serialize_message(message) -> dict | None:
    """Ответ LLM → сериализуемый dict для mind-loop.json.

    Принимается как SDK-объект (берётся `model_dump()`), так и готовый dict.
    Нормализация (отбрасывание None-полей и посторонних ключей) —
    `_normalize_assistant_message`. Возвращается None, если ответ пустой
    (нет ни content, ни tool_calls).
    """
    raw = message.model_dump() if hasattr(message, "model_dump") else message
    return _normalize_assistant_message(raw)
