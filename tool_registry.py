"""Схемы и диспетчеризация инструментов агента.

Каждый инструмент реализован в собственном feature-модуле. Этот модуль
собирает их схемы, фильтрует песочницу и переводит ошибки вызова в строку,
которую можно вернуть модели.
"""

import json
import os

from agent_paths import AgentPaths
from tools_chat import GET_MESSAGES_TOOL, SEND_MESSAGE_TOOL
from tools_chat import handle_get_messages, handle_send_message
from tools_diary import (
    handle_diary_edit,
    handle_diary_recall,
    handle_diary_remember,
    handle_diary_tags,
)
from tools_diary_schema import EDIT_TOOL, RECALL_TOOL, REMEMBER_TOOL, TAGS_TOOL
from tools_memory import GET_MEMORY_TOOL, SET_MEMORY_TOOL
from tools_memory import handle_get_memory, handle_set_memory
from tools_readfile import READ_FILE_TOOL, handle_read_file
from tools_sandbox import RUN_BASH_TOOL, bash_tool_enabled, handle_run_bash
from tools_vision import INSPECT_IMAGE_TOOL, handle_inspect_image
from tools_search import (
    BRAVE_KEY_ENV,
    INTERNET_SEARCH_TOOL,
    handle_internet_search,
)
from tools_web_fetch import WEB_FETCH_TOOL, handle_web_fetch
from tools_money import handle_money_balance, handle_money_spend
from tools_money_schema import MONEY_BALANCE_TOOL, MONEY_SPEND_TOOL


TOOLS_SCHEMA = [
    RUN_BASH_TOOL,
    READ_FILE_TOOL,
    SEND_MESSAGE_TOOL,
    GET_MESSAGES_TOOL,
    GET_MEMORY_TOOL,
    SET_MEMORY_TOOL,
    REMEMBER_TOOL,
    RECALL_TOOL,
    EDIT_TOOL,
    TAGS_TOOL,
    INTERNET_SEARCH_TOOL,
    WEB_FETCH_TOOL,
    INSPECT_IMAGE_TOOL,
    MONEY_BALANCE_TOOL,
    MONEY_SPEND_TOOL,
]

SANDBOX_TOOLS = ("run_bash", "read_file")
PATHLESS_TOOLS = (
    *SANDBOX_TOOLS, "internet_search", "web_fetch", "inspect_image"
)

_HANDLERS = {
    "run_bash": handle_run_bash,
    "read_file": handle_read_file,
    "send_message": handle_send_message,
    "get_messages": handle_get_messages,
    "get_memory": handle_get_memory,
    "set_memory": handle_set_memory,
    "diary_remember": handle_diary_remember,
    "diary_recall": handle_diary_recall,
    "diary_edit": handle_diary_edit,
    "diary_tags": handle_diary_tags,
    "internet_search": handle_internet_search,
    "web_fetch": handle_web_fetch,
    "inspect_image": handle_inspect_image,
    "money_balance": handle_money_balance,
    "money_spend": handle_money_spend,
}


def build_tools_schema(enable_bash: bool | None = None) -> list[dict]:
    """Вернуть схемы tools, доступные модели."""
    if enable_bash is None:
        enable_bash = bash_tool_enabled()
    hidden = set() if enable_bash else set(SANDBOX_TOOLS)
    if not os.environ.get(BRAVE_KEY_ENV, "").strip():
        hidden.add("internet_search")
    return [
        tool for tool in TOOLS_SCHEMA
        if tool["function"]["name"] not in hidden
    ]


def parse_arguments(arguments) -> dict:
    """Распарсить JSON-строку или словарь аргументов."""
    if arguments is None or (isinstance(arguments, str) and not arguments.strip()):
        return {}
    if isinstance(arguments, str):
        parsed = json.loads(arguments)
    elif isinstance(arguments, dict):
        parsed = arguments
    else:
        raise ValueError(
            f"аргументы должны быть JSON-строкой или объектом, "
            f"получено {type(arguments).__name__}"
        )
    if not isinstance(parsed, dict):
        raise ValueError("аргументы должны быть JSON-объектом")
    return parsed


def dispatch_tool(
    name: str, args: dict, paths: AgentPaths | None, context=None
) -> str:
    """Вызвать обработчик инструмента по распарсенным аргументам."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"Error: unknown tool: {name}"
    if paths is None and name not in PATHLESS_TOOLS:
        return "Error: paths не заданы"
    if name == "inspect_image":
        return handler(args, paths, context)
    return handler(args, paths)


def execute_tool(
    name: str, arguments, paths: AgentPaths | None = None, context=None
) -> str:
    """Выполнить tool и всегда вернуть строковый результат."""
    try:
        args = parse_arguments(arguments)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return f"Error: invalid arguments: {exc}"
    return dispatch_tool(name, args, paths, context)
