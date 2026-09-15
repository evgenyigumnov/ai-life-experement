"""Анти-ступор: детектор серий одинаковых tool-вызовов и заметка о зацикливании."""

from agent_history import _iteration_tool_calls
from agent_text import _plural_iterations
from agent_paths import AgentPaths
from prompts_messages import FILE_REPEAT_ALERT, format_message

# Сколько одинаковых подряд итераций (по набору tool-вызовов) триггерят
# user-заметку «ты зациклился» в следующем запросе к LLM (анти-ступор:
# даже с температурой > 0 модель может залипнуть на одном tool-call).
REPEAT_STREAK_ALERT = 3

# Длина примера аргументов в тексте заметки о повторах (чтобы не раздувать промпт)
REPEAT_ALERT_ARG_LIMIT = 120


def _tool_call_signature(record) -> tuple | None:
    """Сигнатура набора tool-вызовов итерации: ((имя, аргументы), ...).

    None — если итерация без tool-вызовов (текст, ошибка, битая запись):
    такие итерации прерывают серию повторов. Аргументы сравниваются как есть
    (порядок ключей в JSON-строке стабилен — она приходит от одного сервера).
    """
    calls = _iteration_tool_calls(record)
    if not calls:
        return None
    return tuple(
        (call["function"]["name"], call["function"].get("arguments", ""))
        for call in calls
    )


def _repeat_streak(iterations: list) -> tuple[tuple, int] | None:
    """Одинаковые tool-вызовы в последних итерациях, если серия достаточно длинная.

    Считается серия подряд идущих итераций с идентичной сигнатурой,
    заканчивающаяся последней итерацией. Возвращает (сигнатура, длина серии),
    если длина >= REPEAT_STREAK_ALERT, иначе None.
    """
    signature = None
    streak = 0
    for record in reversed(iterations):
        current = _tool_call_signature(record)
        if current is None:
            break
        if signature is None:
            signature = current
            streak = 1
        elif current == signature:
            streak += 1
        else:
            break
    if signature is not None and streak >= REPEAT_STREAK_ALERT:
        return signature, streak
    return None


def _repeat_alert_message(signature: tuple, streak: int, paths: AgentPaths) -> dict:
    """User-заметка о зацикливании для следующего запроса к LLM.

    Роль user, не system: заметка встаёт в середину истории, а chat-шаблоны
    ряда моделей допускают system-сообщение только первым в запросе.
    Текст — из файла repeat-alert.md в папке агента (перечитывается
    при каждой итерации).
    """
    examples = "; ".join(
        f"{name}({args if len(args) <= REPEAT_ALERT_ARG_LIMIT else args[:REPEAT_ALERT_ARG_LIMIT] + '…'})"
        for name, args in signature[:3]
    )
    if len(signature) > 3:
        examples += " и т.д."
    content = format_message(
        paths.folder,
        FILE_REPEAT_ALERT,
        streak=_plural_iterations(streak),
        examples=examples,
    )
    return {"role": "user", "content": content}
