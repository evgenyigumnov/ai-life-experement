"""Нормализация истории итераций и её реплей в messages для LLM.

В `assistant_message` сохраняются текст, tool-calls и провайдерские поля
`reasoning_content`/`reasoning`, чтобы reasoning переживал тик. Остальные поля
SDK отбрасываются: некоторые серверы не принимают их в следующем запросе.
Итерации с ошибками воспроизводятся внутренней заметкой, а результаты tools
ищутся по `tool_call_id` или, для старых записей, по порядку.
"""

from agent_history_normalize import (
    _normalize_assistant_message, _normalize_tool_call,
)
from agent_paths import AgentPaths
from prompts_messages import INTERNAL_MESSAGES


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
    Нормализация сохраняет `reasoning_content`/`reasoning` для следующего
    запроса и отбрасывает остальные посторонние ключи. Возвращается None,
    если ответ пустой (нет content, tool_calls и reasoning).
    """
    raw = message.model_dump() if hasattr(message, "model_dump") else message
    if isinstance(raw, dict):
        raw = dict(raw)
        # Некоторые SDK не включают нестандартные поля в model_dump(), хотя
        # они доступны атрибутами сообщения. Не теряем reasoning в таком случае.
        for name in ("reasoning_content", "reasoning"):
            value = getattr(message, name, None)
            if name not in raw and isinstance(value, str) and value.strip():
                raw[name] = value
    return _normalize_assistant_message(raw)
