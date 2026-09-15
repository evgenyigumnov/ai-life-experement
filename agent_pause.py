"""Адаптивная пауза между итерациями: создатель молчит — цикл замедляется.

После каждой «тихой» итерации (в messages.json не появилось новых сообщений
создателя) пауза до следующей итерации растёт по расписанию IDLE_BACKOFF_SCHEDULE:
0 сек → 30 сек → 1 мин → 2 мин → 5 мин → 10 мин → 20 мин → 40 мин → 1 час →
2 часа → 4 часа. Дальше последней ступени пауза не растёт. Если создатель не
интересуется агентом, цикл не жжёт токены впустую; любое новое сообщение
создателя сбрасывает расписание в начало — агент отвечает почти сразу.
Сообщение, написанное прямо во время паузы, прерывает её немедленно
(см. `_wait_pause` и PAUSE_POLL_INTERVAL ниже).
"""

import time

from agent_paths import AgentPaths
from storage import SENDER_CREATOR, load_messages

# Прогрессивная пауза между итерациями, пока создатель молчит в переписке
# (значения — см. докстринг модуля).
IDLE_BACKOFF_SCHEDULE: tuple[float, ...] = (
    0.0,      # 1-я тихая итерация — продолжить сразу
    30.0,     # 30 сек
    60.0,     # 1 мин
    120.0,    # 2 мин
    300.0,    # 5 мин
    600.0,    # 10 мин
    1200.0,   # 20 мин
    2400.0,   # 40 мин
    3600.0,   # 1 час
    7200.0,   # 2 часа
    14400.0,  # 4 часа
)

# Как часто во время паузы перечитывать переписку (messages.json), чтобы
# поймать новое сообщение создателя: пауза прерывается сразу, а не
# дожидается конца. Файл маленький — чтение раз в секунду ничего не стоит.
PAUSE_POLL_INTERVAL: float = 1.0


def _creator_messages(paths: AgentPaths) -> list[dict]:
    """Все сообщения создателя в переписке (messages.json), по порядку.

    Интерес к агенту проявляет только человек: сообщения самого агента
    (send_message) не считаются — иначе агент своим ответом сбрасывал бы
    паузу и «читал» сам себя. Отсутствующий или битый файл — как пустая
    переписка: сбой чтения не должен ронять цикл жизни.
    """
    try:
        data = load_messages(paths.messages or paths.folder / "messages.json")
    except Exception:
        return []
    return [
        message
        for message in data.get("messages") or []
        if isinstance(message, dict) and message.get("from") == SENDER_CREATOR
    ]


def _creator_messages_count(paths: AgentPaths) -> int:
    """Сколько сообщений создателя сейчас в переписке (messages.json)."""
    return len(_creator_messages(paths))


def _backoff_delay(step: int) -> float:
    """Пауза (сек) после `step`-й подряд итерации без сообщений создателя.

    step=1 — первая тихая итерация (пауза 0 сек: продолжить сразу), дальше
    по расписанию IDLE_BACKOFF_SCHEDULE. За последней ступенью пауза
    не растёт: любой step больше длины расписания даёт максимум (4 часа).
    """
    index = min(max(step, 1), len(IDLE_BACKOFF_SCHEDULE)) - 1
    return IDLE_BACKOFF_SCHEDULE[index]


def _pause_seconds(delay: float, iteration_duration: float) -> float:
    """Сколько реально спать: пауза минус время, занятое самой итерацией.

    Отсчёт паузы ведётся от начала итерации: долгий ответ LLM «съедает»
    часть паузы, поэтому суммарный ритм цикла не растёт сверх расписания.
    Отрицательный сон невозможен — долгая итерация просто продолжается
    сразу следующей.
    """
    return max(0.0, delay - iteration_duration)


def _wait_pause(
    seconds: float, paths: AgentPaths, known_creator_count: int
) -> bool:
    """Пауза до следующей итерации, прерываемая сообщением создателя.

    Спит не дольше `seconds` кусками по PAUSE_POLL_INTERVAL и после каждого
    куска перечитывает переписку: создатель написал что-то новое (число его
    сообщений в `_creator_messages_count` изменилось с
    `known_creator_count`) — сон прерывается сразу и возвращается True:
    следующая итерация запускается немедленно. False — пауза истекла
    целиком, создатель молчал. Нулевая пауза переписку не проверяет:
    сообщение и так увидит следующая итерация. Ctrl+C (KeyboardInterrupt
    из time.sleep) пробрасывается наверх как и раньше — история к этому
    моменту уже сохранена после прошлой итерации.
    """
    if seconds <= 0:
        return False
    deadline = time.monotonic() + seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        time.sleep(min(PAUSE_POLL_INTERVAL, remaining))
        if _creator_messages_count(paths) != known_creator_count:
            return True
