"""Фоновое наблюдение за новыми ответами агента."""

from collections.abc import Callable
from pathlib import Path
from threading import Event, Thread

from storage import SENDER_AGENT, load_messages


class ReplyWatcher:
    """Показывает сообщения агента, дописанные после открытия reply-режима."""

    def __init__(
        self,
        path: Path,
        seen_count: int,
        on_agent_message: Callable[[dict, int], None],
        interval: float = 1.0,
    ) -> None:
        self.path = Path(path)
        self.seen_count = max(0, seen_count)
        self.on_agent_message = on_agent_message
        self.interval = max(0.01, interval)
        self._stop = Event()
        self._thread: Thread | None = None

    def start(self) -> None:
        """Запустить watcher; повторный вызов ничего не делает."""
        if self._thread is not None:
            return
        self._thread = Thread(target=self._run, name="reply-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Остановить watcher и дождаться завершения короткого чтения."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self.interval * 2))

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._poll()

    def _poll(self) -> None:
        try:
            messages = load_messages(self.path).get("messages") or []
        except Exception:
            return
        if len(messages) < self.seen_count:
            self.seen_count = len(messages)
            return
        start = self.seen_count
        new_messages = messages[start:]
        self.seen_count = len(messages)
        for index, message in enumerate(new_messages, start=start):
            if isinstance(message, dict) and message.get("from") == SENDER_AGENT:
                try:
                    self.on_agent_message(message, index)
                except Exception:
                    # Ошибка форматирования не должна убить интерактивный режим.
                    continue
