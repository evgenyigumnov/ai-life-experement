"""Режим переписки создателя с агентом."""

import os

from dotenv import load_dotenv

from agent_console import _Colors, _colorize
from agent_paths import find_agent_folder
from config_env import Config
from message_format import format_message_line
from storage import SENDER_CREATOR, append_message, load_messages

AGENT_REPLY_COLOR = _Colors.BLUE
REPLY_DIVIDER = "─" * 72


def _format_reply_header(name: str, total: int) -> str:
    """Заголовок переписки в стиле консоли наблюдения."""
    title = f"{'═' * 24} [ 💬 {name} ] {'═' * 24}"
    details = (
        f"Переписка с «{name}» (всего сообщений: {total}), "
        "вся переписка (номера совпадают с get_messages):"
    )
    return _colorize(f"\n{title}\n{details}", _Colors.CYAN)


def _format_reply_message(message: dict, agent_label: str, index: int) -> str:
    """Строка сообщения с номером и цветом отправителя."""
    creator = message.get("from") == SENDER_CREATOR
    icon = "👤" if creator else "🤖"
    color = _Colors.GREEN if creator else AGENT_REPLY_COLOR
    line = format_message_line(message, agent_label, index=index)
    return _colorize(f"{icon} {line}", color)


def _reply_mode(name: str) -> None:
    """Показать всю переписку и дописать ответ создателя."""
    load_dotenv()
    cfg = Config(
        base_url="reply-mode",
        model="reply-mode",
        api_key="reply-mode",
        agents_root=os.environ.get("AGENTS_ROOT", "").strip() or None,
    )
    paths = find_agent_folder(name, cfg)
    history = load_messages(paths.messages).get("messages") or []
    print(_format_reply_header(name, len(history)), flush=True)
    if history:
        print(_colorize(REPLY_DIVIDER, _Colors.CYAN), flush=True)
        for index, message in enumerate(history):
            print(_format_reply_message(message, paths.name, index), flush=True)
        print(_colorize(REPLY_DIVIDER, _Colors.CYAN), flush=True)
    else:
        print(
            _colorize(
                "(переписки ещё нет — вы напишете первое сообщение)",
                _Colors.YELLOW,
            ),
            flush=True,
        )
    try:
        text = input(
            _colorize("\n✍️ Ваш ответ (Enter — отправить): ", _Colors.CYAN)
        ).strip()
    except EOFError:
        text = ""
    if text:
        append_message(paths.messages, SENDER_CREATOR, text)
        print(_colorize("✅ Сообщение отправлено агенту.", _Colors.GREEN), flush=True)
    else:
        print(
            _colorize("Пустой ввод — сообщение не отправлено.", _Colors.YELLOW),
            flush=True,
        )
