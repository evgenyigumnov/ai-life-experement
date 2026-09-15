"""Консоль наблюдения за «жизнью» агента: цвета и короткие строки-события.

Рамочные блоки (системный промпт, ответ LLM, размышления, tool-вызовы) —
в agent_console_blocks.py.
"""

import os
import sys

from agent_text import _plural_iterations

USE_COLOR: bool | None = None


class _Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[1;36m"
    MAGENTA = "\033[1;35m"
    YELLOW = "\033[1;33m"
    GREEN = "\033[1;32m"
    RED = "\033[1;31m"
    BLUE = "\033[1;34m"


def _supports_color() -> bool:
    """Проверяет, включено ли цветовое оформление вывода."""
    if USE_COLOR is not None:
        return USE_COLOR
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _colorize(text: str, color: str) -> str:
    if not _supports_color():
        return text
    return f"{color}{text}{_Colors.RESET}"


def _log(message: str) -> None:
    """Печать строки в консоль наблюдения за «жизнью» агента."""
    print(message, flush=True)


def _format_iteration_header(n: int) -> str:
    """Оформление заголовка итерации (двойная горизонтальная черта, цвет cyan)."""
    line = f"{'═' * 24} [ Итерация {n} ] {'═' * 24}"
    return _colorize(f"\n{line}", _Colors.CYAN)


def _format_iteration_command(user_message: str, remaining: int) -> str:
    """Команда итерации: что отправлено в LLM и сколько осталось до сна.

    `user_message` — фактический текст из user-message.md или директива
    последней итерации из last-iteration-message.md; `remaining` — сколько
    итераций осталось, включая текущую (0 — сама последняя итерация,
    сразу после неё сон).
    """
    if remaining > 0:
        tail = f"до сна осталось {_plural_iterations(remaining)}"
    else:
        tail = "после этой итерации — сон"
    return _colorize(f"📤 → LLM: «{user_message}» ({tail})", _Colors.CYAN)


def _format_stop_message(total: str, path: str) -> str:
    """Оформление финального сообщения об останове."""
    msg = f"🛑 Останов (Ctrl+C/SIGTERM). История сохранена: {total} итераций в {path}"
    return _colorize(f"\n{msg}", _Colors.CYAN)


def _format_sleep_message(session: int, archive_name: str) -> str:
    """Оформление сообщения о сне: сессия завершена, история в архиве."""
    msg = (
        f"😴 Сон: сессия {session} завершена — история заархивирована в {archive_name}. "
        "Следующая итерация — пробуждение: свежий mind-loop.json, отсчёт с 1"
    )
    return _colorize(f"\n{msg}", _Colors.CYAN)


def _format_wake_up_log(session) -> str:
    """Оформление сообщения о пробуждении (в консоль наблюдения)."""
    session_str = str(session) if isinstance(session, int) and session > 0 else "?"
    msg = (
        f"🌞 Пробуждение: сессия {session_str}. История итераций прошлой жизни "
        "недоступна — продолжение по памяти (memory.md)"
    )
    return _colorize(msg, _Colors.CYAN)


def _format_duration(seconds: float) -> str:
    """Человекочитаемая длительность для консоли: 30 сек, 5 мин, 2 ч 30 мин."""
    total = int(round(seconds))
    if total < 60:
        return f"{total} сек"
    minutes, rest = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} мин" + (f" {rest} сек" if rest else "")
    hours, minutes = divmod(minutes, 60)
    return f"{hours} ч" + (f" {minutes} мин" if minutes else "")


def _format_pause_log(
    step: int,
    sleep_for: float,
    creator_wrote: bool,
    planned_delay: float = 0.0,
    iteration_duration: float = 0.0,
    fixed_pause: bool = False,
) -> str:
    """Строка консоли наблюдения о паузе до следующей итерации.

    Показывает причину паузы: создатель написал (расписание сброшено —
    следующая итерация почти сразу), создатель молчит уже `step` итераций
    подряд (пауза растёт) или фиксированный режим (`fixed_pause=True`,
    --loop-pause=N). `sleep_for` — реальный сон после вычета длительности
    самой итерации, `planned_delay` — плановая пауза до вычета,
    `iteration_duration` — сколько заняла сама итерация.

    Если плановая пауза целиком истекла за время итерации (sleep_for == 0
    при planned_delay > 0), строка объясняет это: без пояснения «следующая
    итерация — сразу» выглядит как пропавшая информация о времени, хотя
    на деле ждать нечего.
    """
    if fixed_pause:
        head = "⏳ Фиксированная пауза (--loop-pause): расписание отключено"
    elif creator_wrote:
        head = "💬 Создатель написал — расписание паузы сброшено"
    else:
        head = f"⏳ Создатель молчит: {_plural_iterations(step)} подряд"
    if sleep_for > 0:
        tail = f"пауза до следующей итерации: {_format_duration(sleep_for)}"
    elif planned_delay > 0:
        tail = (
            f"плановая пауза {_format_duration(planned_delay)} истекла за время "
            f"итерации ({_format_duration(iteration_duration)}) — "
            "следующая итерация сразу"
        )
    else:
        tail = "следующая итерация — сразу"
    return _colorize(f"{head}, {tail}", _Colors.CYAN)


def _format_pause_interrupted_log() -> str:
    """Строка консоли наблюдения: пауза прервана сообщением создателя.

    Создатель написал прямо во время сна — агент просыпается отвечать
    немедленно, не дожидаясь конца запланированной паузы.
    """
    return _colorize(
        "💬 Создатель написал во время паузы — просыпаюсь сразу",
        _Colors.CYAN,
    )


def _format_unread_log(count: int) -> str:
    """Строка консоли наблюдения: агенту сообщён статус переписки."""
    return _colorize(
        f"💬 Непрочитанных сообщений от создателя: {count} — "
        "агенту предложено прочитать через get_messages",
        _Colors.YELLOW,
    )
