"""Хранение: работа с mind-loop.json и memory.md (шаг 3).

Все функции рассчитаны на путь к файлу (`pathlib.Path`). Записи выполняются
атомарно (временный файл + `os.replace`), чтобы прерывание процесса не могло
оставить битый файл.
"""

import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from time_utils import now_iso


def _atomic_write_text(path: Path, text: str) -> None:
    """Атомарно записать текст в файл.

    Пишем во временный файл в той же папке (чтобы `os.replace` был
    атомарным в пределах одной файловой системы), затем переименовываем.
    """
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_name, path)
    except BaseException:
        # не оставляем временный файл, если что-то пошло не так
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# --- mind-loop.json ---


def _backup_corrupt(path: Path, exc: Exception) -> Path | None:
    """Переименовать битый JSON-файл в бэкап `<имя>.corrupt-<ts>`.

    При коллизии имён в ту же секунду добавляется суффикс `-1`, `-2`, ...
    Возвращает путь к бэкапу или None, если переименовать не удалось
    (файл остаётся на месте — его перезапишет свежая структура).
    """
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt-{ts}")
    counter = 0
    while backup.exists():  # не затирать предыдущие бэкапы той же секунды
        counter += 1
        backup = path.with_name(f"{path.name}.corrupt-{ts}-{counter}")
    try:
        os.replace(path, backup)
    except OSError:
        return None
    return backup


def _empty_mind_loop(agent: str) -> dict:
    """Свежая структура истории (первый запуск или после повреждения)."""
    return {
        "agent": agent,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "session": 1,
        "iterations": [],
    }


def load_mind_loop(path: Path) -> dict:
    """Прочитать `mind-loop.json` (шаг 3 плана).

    - файла нет — вернуть пустую структуру (имя агента — имя папки);
    - JSON битой или структура неверна — не падать: сделать бэкап
      `mind-loop.json.corrupt-<ts>`, записать чистую историю и вернуть её
      (с предупреждением в stderr).
    """
    path = Path(path)
    if not path.exists():
        return _empty_mind_loop(path.parent.name)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("iterations"), list):
            raise ValueError("ожидается объект с ключом 'iterations' (список)")
        # Счётчик доставки был частью удалённого механизма вставки текстов.
        data.pop("seen_creator_messages", None)
        return data
    except (OSError, ValueError) as exc:
        backup = _backup_corrupt(path, exc)
        print(
            f"Предупреждение: {path.name} повреждён ({exc}); "
            + (f"битый файл сохранён как {backup.name}, " if backup else "")
            + "история начата заново",
            file=sys.stderr,
        )
        fresh = _empty_mind_loop(path.parent.name)
        save_mind_loop(path, fresh)
        return fresh


def save_mind_loop(path: Path, data: dict) -> None:
    """Атомарно сохранить историю, обновив `updated_at`."""
    data.pop("seen_creator_messages", None)
    data["updated_at"] = now_iso()
    _atomic_write_text(Path(path), json.dumps(data, ensure_ascii=False, indent=2))


def append_iteration(path: Path, data: dict, iteration: dict) -> dict:
    """Добавить итерацию в `data["iterations"]` (`n = len + 1`) и сохранить.

    Если итерация пришла без `n` или `timestamp`, они проставляются здесь.
    Возвращает обновлённый `data`.
    """
    iterations = data.setdefault("iterations", [])
    iteration = dict(iteration)
    iteration.setdefault("n", len(iterations) + 1)
    iteration.setdefault("timestamp", now_iso())
    iterations.append(iteration)
    save_mind_loop(Path(path), data)
    return data


def archive_mind_loop(path: Path, data: dict) -> Path:
    """Заархивировать историю завершённой сессии и начать новую «жизнь» (сон).

    Текущее содержимое (весь `data`) атомарно копируется в
    `mind-loop-<ГГГГММДД>-<ЧЧММСС>.json` рядом с оригиналом (при коллизии
    имён в ту же секунду — суффикс `-1`, `-2`, ...), а `mind-loop.json`
    атомарно заменяется свежей структурой: пустые `iterations`, счётчик
    `session` = старый + 1 и метка `woke_up_at` — время пробуждения.
    Благодаря ей следующая итерация понимает, что только что проснулась,
    и начинает нумерацию с 1. Возвращает путь к файлу архива.
    """
    path = Path(path)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = path.with_name(f"{path.stem}-{ts}.json")
    counter = 0
    while archive.exists():  # не затирать архивы, созданные в ту же секунду
        counter += 1
        archive = path.with_name(f"{path.stem}-{ts}-{counter}.json")
    _atomic_write_text(archive, json.dumps(data, ensure_ascii=False, indent=2))

    fresh = _empty_mind_loop(data.get("agent") or path.parent.name)
    fresh["session"] = (data.get("session") or 1) + 1
    fresh["woke_up_at"] = now_iso()
    save_mind_loop(path, fresh)
    return archive


# --- memory.md ---


def read_memory(path: Path) -> str:
    """Содержимое `memory.md` (пустая строка, если файла нет)."""
    path = Path(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_memory(path: Path, text: str) -> None:
    """Атомарно перезаписать `memory.md`."""
    _atomic_write_text(Path(path), text)


# --- messages.json ---

# Реэкспортируем API переписки из отдельного модуля, сохраняя прежний импорт
# `from storage import ...` для остальных частей приложения.
from storage_messages import (
    SENDER_AGENT,
    SENDER_CREATOR,
    _empty_messages,
    append_message,
    ensure_messages_file,
    is_message_read,
    last_messages,
    load_messages,
    mark_messages_read,
    unread_creator_positions,
)


# --- system-prompt.md ---


def read_system_prompt(path: Path) -> str:
    """Прочитать системный промпт (файл обязан существовать — проверен на шаге 2)."""
    return Path(path).read_text(encoding="utf-8")
