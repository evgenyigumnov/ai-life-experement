"""Очереди мутаций: один realpath изменяется строго последовательно."""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from pathlib import Path


class _MutationQueue:
    def __init__(self) -> None:
        self.condition = threading.Condition()
        self.next_ticket = 0
        self.serving = 0

    def run(self, callback: Callable):
        with self.condition:
            ticket = self.next_ticket
            self.next_ticket += 1
            while ticket != self.serving:
                self.condition.wait()
        try:
            return callback()
        finally:
            with self.condition:
                self.serving += 1
                self.condition.notify_all()


_queues: dict[str, _MutationQueue] = {}
_queues_lock = threading.Lock()


def mutation_queue_key(path: str | os.PathLike[str]) -> str:
    """Вернуть canonical path; для отсутствующего файла сохранить absolute path."""
    candidate = os.fspath(path)
    try:
        return str(Path(candidate).resolve(strict=True))
    except (FileNotFoundError, NotADirectoryError):
        return os.path.abspath(candidate)


def _queue_for(key: str) -> _MutationQueue:
    with _queues_lock:
        queue = _queues.get(key)
        if queue is None:
            queue = _MutationQueue()
            _queues[key] = queue
        return queue


def with_file_mutation_queue(path: str | os.PathLike[str], callback: Callable,
                             *, key: str | None = None):
    """Выполнить callback после всех предыдущих мутаций этого realpath."""
    return _queue_for(key or mutation_queue_key(path)).run(callback)


# Короткий alias для обработчиков инструментов.
run_mutation = with_file_mutation_queue
