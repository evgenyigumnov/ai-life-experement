"""Режим переписки создателя с агентом."""

import os
import sys

from dotenv import load_dotenv

from agent_console import _Colors, _colorize
from agent_paths import find_agent_folder
from config_env import Config
from message_format import format_message_line
from reply_input import REPLY_PROMPT
from reply_session import run_reply_session
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


def _is_interactive_terminal() -> bool:
    """Только настоящий терминал может безопасно перерисовывать редактор."""
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def _print_new_agent_message(message: dict, index: int, agent_label: str) -> None:
    """Показать ответ, который агент дописал уже после открытия режима."""
    print(_colorize("\n📥 Новый ответ агента:", AGENT_REPLY_COLOR), flush=True)
    print(_format_reply_message(message, agent_label, index), flush=True)


def _send_once(paths, prompt: str = REPLY_PROMPT) -> None:
    """Одноразовый fallback для pipe/тестов без интерактивного терминала."""
    try:
        text = input(_colorize(prompt, _Colors.CYAN)).strip()
    except EOFError:
        text = ""
    if text:
        append_message(paths.messages, SENDER_CREATOR, text)
        print(_colorize("✅ Сообщение отправлено агенту.", _Colors.GREEN), flush=True)
    else:
        print(_colorize("Пустой ввод — сообщение не отправлено.", _Colors.YELLOW), flush=True)


def _reply_mode(name: str) -> None:
    """Открыть переписку; в терминале оставаться в режиме до Ctrl+C/Ctrl+D."""
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
    if not _is_interactive_terminal():
        _send_once(paths)
        return
    run_reply_session(
        paths,
        len(history),
        lambda message, index: _print_new_agent_message(
            message, index, paths.name
        ),
    )
