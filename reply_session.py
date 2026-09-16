"""Долгоживущая интерактивная сессия reply-режима."""

from collections.abc import Callable

from agent_paths import AgentPaths
from reply_input import (
    REPLY_PROMPT,
    create_reply_session,
    read_reply,
    reply_output,
)
from reply_watcher import ReplyWatcher
from storage import SENDER_CREATOR, append_message


EMPTY_REPLY = "Пустой ввод — сообщение не отправлено."
EXIT_REPLY = "\nВыход из режима reply. Переписка сохранена."
SENT_REPLY = "✅ Сообщение отправлено агенту."


def run_reply_session(
    paths: AgentPaths,
    seen_count: int,
    on_agent_message: Callable[[dict, int], None],
) -> None:
    """Не закрывать prompt после отправки и показывать новые ответы файла."""
    session = create_reply_session()
    watcher = ReplyWatcher(paths.messages, seen_count, on_agent_message)
    with reply_output(session is not None):
        watcher.start()
        try:
            _run_until_exit(paths, session)
        finally:
            watcher.stop()


def _run_until_exit(paths: AgentPaths, session) -> None:
    """Обрабатывать сообщения до EOF/прерывания, не закрывая редактор после send."""
    while True:
        try:
            text = read_reply(session, REPLY_PROMPT)
        except KeyboardInterrupt:
            print(EXIT_REPLY, flush=True)
            return
        if text is None:
            print(EXIT_REPLY, flush=True)
            return
        text = text.strip()
        if not text:
            print(EMPTY_REPLY, flush=True)
            continue
        try:
            append_message(paths.messages, SENDER_CREATOR, text)
        except Exception as exc:
            print(f"Не удалось отправить сообщение: {exc}", flush=True)
            continue
        print(SENT_REPLY, flush=True)
