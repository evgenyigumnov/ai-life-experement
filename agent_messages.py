"""Сборка messages для очередной итерации (шаг 6 плана).

Роль `system` используется только для системного промпта — он всегда
сообщение № 1: chat-шаблоны ряда моделей (например, Qwen3.8 GGUF в
LM Studio) отвергают запрос ошибкой «System message must be at the
beginning», если system-сообщение встречается не первым, поэтому все
заметки (пробуждение, сон, зацикливание, непрочитанные сообщения и статус
переписки) отправляются ролью `user`.
"""

from agent_history import _iteration_messages
from agent_repeat import _repeat_streak, _repeat_alert_message
from agent_sleep import (
    _just_woke_up,
    _memory_stale,
    _sleep_warning_message,
    _tick_user_message,
    _wake_up_message,
    iterations_remaining,
    should_warn,
)
from agent_unread import _creator_messages_status_note
from agent_paths import AgentPaths
from context_weight import weight_note
from storage import read_system_prompt


def build_messages(data: dict, paths: AgentPaths) -> list[dict]:
    """Собрать массив messages для очередной итерации (шаг 6 плана).

    1. system — системный промпт, перечитывается с диска при каждом вызове
       (промпт можно менять на живом агенте); единственное сообщение
       с ролью system;
    2. сразу после сна (свежий mind-loop.json с меткой woke_up_at и без
       итераций) — user-заметка «ты проснулся» (wake-up-message.md):
       история прошлой сессии недоступна, надо читать память;
    3. воспроизведение всех итераций текущей сессии (mind-loop.json хранит
       только текущую «жизнь», а её длина ограничена сном —
       SESSION_ITERATIONS, поэтому запрос не урезается);
    4. приближение конца сессии (осталось <= SLEEP_WARN_REMAINING итераций,
       кроме самой последней) — user-заметка «скоро сон» (sleep-warning.md);
       текст заметки зависит от того, отстала ли память от работы;
    5. при серии одинаковых tool-вызовов — user-заметка «ты зациклился»
       (repeat-alert.md);
    6. при наличии непрочитанных сообщений создателя — короткая user-заметка
       со статусом; текст сообщения не вставляется, агент читает его через
       get_messages;
    7. финальное user-сообщение «сделай следующее действие» (user-message.md;
       на последней итерации сессии — специальная директива сохранить память
       из last-iteration-message.md); между статусом (если он есть) и тиком —
       строка о весе собранного контекста: «(контекст запроса: ~12.4 КБ,
       18 итераций)»,
       бюджет контекста виден самому агенту.

    Все заметки (2, 4, 5, 6) отправляются ролью user. Все тексты, кроме
    системного промпта, тоже перечитываются с диска при каждом вызове —
    см. prompts_messages.py и prompts_template.py.
    """
    system_prompt = read_system_prompt(paths.system_prompt)
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # пробуждение: свежий файл после сна ещё без итераций — истории нет,
    # единственный способ вспомнить жизнь — память (get_memory)
    if _just_woke_up(data):
        messages.append(_wake_up_message(paths))

    iterations = data.get("iterations") or []
    upcoming_n = len(iterations) + 1  # номер итерации внутри текущей сессии

    for record in iterations:
        messages.extend(_iteration_messages(record, paths))

    # приближение конца сессии: «осталось N итераций» (N > 0), с усилением,
    # если память отстала от работы. Сама последняя итерация (remaining == 0)
    # заметки не получает — вместо обычного тика ей приходит специальное
    # user-сообщение с требованием сохранить память
    remaining = iterations_remaining(upcoming_n)
    if should_warn(remaining):
        messages.append(
            _sleep_warning_message(remaining, _memory_stale(iterations), paths)
        )

    # анти-ступор: серия одинаковых tool-вызовов в конце истории —
    # просим модель очнуться и сделать что-то другое
    streak_info = _repeat_streak(iterations)
    if streak_info is not None:
        messages.append(_repeat_alert_message(*streak_info, paths))

    # Статус по фактическим read-флагам добавляется только при наличии
    # непрочитанных сообщений. Сам текст сообщения остаётся в messages.json:
    # агент получает его через get_messages по собственной инициативе.
    status_note = _creator_messages_status_note(paths)
    status = status_note["content"] if status_note else ""
    tick = _tick_user_message(upcoming_n, paths)
    final = {
        "role": "user",
        "content": "\n\n".join(filter(None, (status, tick))),
    }
    # Заметка о весе контекста считается по messages + финальному сообщению;
    # второй проход стабилизирует число — заметка включает и саму себя.
    for _ in range(2):
        note = weight_note(messages + [final], upcoming_n)
        final = {
            "role": "user",
            "content": "\n\n".join(filter(None, (status, note, tick))),
        }
    messages.append(final)
    return messages
