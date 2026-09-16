"""Сборка истории и служебных user-заметок для очередного запроса."""

from agent_history import _iteration_messages
from agent_paths import AgentPaths
from agent_repeat import _repeat_alert_message, _repeat_streak
from agent_sleep import (
    _just_woke_up,
    _memory_stale,
    _sleep_warning_message,
    _tick_user_message,
    _wake_up_message,
    iterations_remaining,
    should_warn,
)
from agent_timing import last_llm_duration_note
from agent_unread import _creator_messages_status_note
from context_weight import weight_note


def append_cycle_context(messages: list[dict], data: dict,
                         paths: AgentPaths) -> tuple[list, int]:
    """Добавить к запросу пробуждение, историю, предупреждения и anti-stupor."""
    if _just_woke_up(data):
        messages.append(_wake_up_message(paths))

    iterations = data.get("iterations") or []
    upcoming_n = len(iterations) + 1
    for record in iterations:
        messages.extend(_iteration_messages(record, paths))

    remaining = iterations_remaining(upcoming_n)
    if should_warn(remaining):
        messages.append(
            _sleep_warning_message(remaining, _memory_stale(iterations), paths)
        )

    streak_info = _repeat_streak(iterations)
    if streak_info is not None:
        messages.append(_repeat_alert_message(*streak_info, paths))
    return iterations, upcoming_n


def _join(*parts: str) -> str:
    return "\n\n".join(filter(None, parts))


def build_final_user_message(messages: list[dict], iterations: list,
                             paths: AgentPaths, upcoming_n: int) -> dict:
    """Собрать финальный тик, вес контекста и время прошлого ответа."""
    status_note = _creator_messages_status_note(paths)
    status = status_note["content"] if status_note else ""
    duration = last_llm_duration_note(iterations)
    tick = _tick_user_message(upcoming_n, paths)
    final = {"role": "user", "content": _join(status, duration, tick)}

    # Два прохода включают саму заметку о весе в измерение запроса.
    for _ in range(2):
        note = weight_note(messages + [final], upcoming_n)
        final = {
            "role": "user",
            "content": _join(status, note, duration, tick),
        }
    return final
