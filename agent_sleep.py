"""Циклы жизни: сессии по SESSION_ITERATIONS итераций, сон и пробуждение.

Жизнь агента разбита на сессии по `SESSION_ITERATIONS` итераций. Когда до
конца сессии остаётся не больше `SLEEP_WARN_REMAINING` итераций, в запрос
добавляется user-заметка «скоро сон» с требованием сохранить в память
(set_memory) достигнутое и планы; если память отстала от работы, заметка
усиливается. На самой последней итерации заметки нет — вместо обычного
тика приходит специальное user-сообщение с требованием немедленно
сохранить память: финальное user-сообщение сильнее промежуточных заметок,
а обычный тик конкурировал с напоминанием и побеждал — агент засыпал без
пересохранения. После последней итерации агент «засыпает»: история
архивируется в `mind-loop-<ГГГГММДД>-<ЧЧММСС>.json`, а `mind-loop.json`
начинается заново — с увеличенным счётчиком `session` и меткой `woke_up_at`
(storage.archive_mind_loop). Первая итерация после сна видит только эту
метку: нумерация идёт с 1, история прошлой сессии в запрос не попадает,
вместо неё — user-заметка «ты проснулся» с указанием осмотреться.

Константы сессии патчатся в этом модуле — функции-предикаты ниже читают
свои глобалы в момент вызова.
"""

from agent_history import _iteration_tool_calls
from agent_text import _plural_iterations
from agent_paths import AgentPaths
from prompts_messages import (
    FILE_LAST_ITERATION_MESSAGE,
    FILE_SLEEP_WARNING,
    FILE_USER_MESSAGE,
    FILE_WAKE_UP_MESSAGE,
    format_message,
    read_default_message,
    read_message,
)

# Длина одной «жизни» (сессии) в итерациях: после SESSION_ITERATIONS-й
# итерации агент «засыпает» — история этой сессии больше не попадает в
# запросы (полный журнал по-прежнему хранится в mind-loop.json).
SESSION_ITERATIONS = 30

# За сколько итераций до конца сессии начинать предупреждать агента о сне.
# При SESSION_ITERATIONS=30 предупреждение приходит начиная с 20-й итерации
# («прошло 20 — осталось 10») и повторяется с уменьшающимся счётчиком
# на каждой следующей итерации до конца сессии.
SLEEP_WARN_REMAINING = 10

# User-сообщение каждой итерации. Фактический текст берётся из файла
# user-message.md в папке агента (перечитывается при каждой итерации);
# эта константа загружается из общего файла default-prompts.
USER_MESSAGE = read_default_message(FILE_USER_MESSAGE)

# User-сообщение последней итерации сессии (см. докстринг модуля).
# Текст — из файла last-iteration-message.md в папке агента;
# константа загружается из общего файла default-prompts.
LAST_ITERATION_MESSAGE = read_default_message(FILE_LAST_ITERATION_MESSAGE)


def iterations_remaining(n: int) -> int:
    """Сколько итераций сессии остаётся после n-й (0 — сама n-я последняя)."""
    return SESSION_ITERATIONS - n


def is_session_end(n: int) -> bool:
    """n-я итерация — последняя в сессии: сразу после неё агент «засыпает»."""
    return n >= SESSION_ITERATIONS


def should_warn(remaining: int) -> bool:
    """Показывать ли заметку «скоро сон»: осталось мало, но это ещё не последняя."""
    return 0 < remaining <= SLEEP_WARN_REMAINING


def _just_woke_up(data: dict) -> bool:
    """Агент только что проснулся: свежий mind-loop.json после сна.

    Файл, созданный `archive_mind_loop` после сна, содержит метку
    `woke_up_at` и пустые `iterations`. После первой же итерации сессии
    история непуста — заметка о пробуждении больше не нужна.
    """
    return not (data.get("iterations") or []) and bool(data.get("woke_up_at"))


def _memory_stale(iterations: list) -> bool:
    """Память отстала от работы сессии: не отражает последние изменения.

    True, если set_memory в сессии не было вовсе, либо после последнего
    set_memory были вызовы run_bash — их результаты в память не попали.
    Вызовы обходятся в порядке следования: set_memory в середине итерации
    и run_bash в той же итерации после него — тоже несохранённая работа.
    Повторное set_memory сбрасывает «отставание»: сравнение идёт
    с последним сохранением, а не с первым; раннего выхода нет.
    """
    saved = False
    stale = False
    for record in iterations:
        for call in _iteration_tool_calls(record):
            name = call["function"]["name"]
            if name == "set_memory":
                saved = True
                stale = False  # сохранение сбрасывает «отставание»
            elif name == "run_bash" and saved:
                stale = True  # работа после сохранения
    return not saved or stale


def _tick_user_message(upcoming_n: int, paths: AgentPaths) -> str:
    """User-сообщение очередной итерации: обычный тик или директива последней.

    Текст перечитывается из файлов user-message.md / last-iteration-message.md
    в папке агента при каждой итерации. На последней итерации сессии вместо
    «сделай следующее действие» приходит требование сохранить память.
    """
    if is_session_end(upcoming_n):
        return read_message(paths.folder, FILE_LAST_ITERATION_MESSAGE)
    return read_message(paths.folder, FILE_USER_MESSAGE)


def _sleep_warning_message(remaining: int, stale: bool, paths: AgentPaths) -> dict:
    """User-заметка «скоро сон».

    Роль именно user, не system: chat-шаблоны ряда моделей допускают
    system-сообщение только первым в запросе, а заметка встаёт в середину
    истории. `remaining` — сколько итераций сессии осталось до сна (всегда
    > 0); `stale` — память отстала от работы: значение `{memory_note}`
    усиливается соответственно. Текст — из файла sleep-warning.md в папке
    агента, перечитывается при каждой итерации.
    """
    memory_note = (
        "Память не отражает последние действия — обнови её сейчас."
        if stale
        else "Проверь, что в памяти есть итог и следующий шаг."
    )
    content = format_message(
        paths.folder,
        FILE_SLEEP_WARNING,
        remaining=_plural_iterations(remaining),
        memory_note=memory_note,
    )
    return {"role": "user", "content": content}


def _wake_up_message(paths: AgentPaths) -> dict:
    """User-заметка «ты проснулся»: осмотрись (look around), прежде чем действовать.

    Роль user, не system: это всё равно второе сообщение запроса —
    chat-шаблоны ряда моделей допускают system только первым. История
    прошлой сессии недоступна, единственная точка опоры — память, но и
    окружение за время сна могло измениться: заметка требует прочитать
    память (get_memory), осмотреться вокруг и вычеркнуть из планов
    выполненное или потерявшее смысл (set_memory); следующее дело
    выбирается по важности. Текст — из файла wake-up-message.md.
    """
    return {
        "role": "user",
        "content": read_message(paths.folder, FILE_WAKE_UP_MESSAGE),
    }
