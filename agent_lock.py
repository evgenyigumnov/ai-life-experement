"""Общая блокировка файлового состояния одного агента."""

import fcntl
from contextlib import contextmanager
from pathlib import Path

LOCK_FILENAME = ".agent.lock"


def _folder(target) -> Path:
    folder = getattr(target, "folder", None)
    if folder is not None:
        return Path(folder)
    path = Path(target)
    return path if not path.suffix else path.parent


def lock_path(target) -> Path:
    """Путь к lock-файлу для папки или файла состояния агента."""
    return _folder(target) / LOCK_FILENAME


@contextmanager
def agent_lock(target):
    """Взять общую эксклюзивную блокировку состояния агента."""
    folder = _folder(target)
    folder.mkdir(parents=True, exist_ok=True)
    with lock_path(folder).open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


state_lock = agent_lock
