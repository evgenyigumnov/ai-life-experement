"""Загрузка инструментов из каталога tools/."""

from tools import discover_tools


FILE_TOOLS = discover_tools()
DYNAMIC_SCHEMAS = [definition for definition, _handler in FILE_TOOLS]
DYNAMIC_HANDLERS = {
    definition["function"]["name"]: handler
    for definition, handler in FILE_TOOLS
}
DYNAMIC_NAMES = [definition["function"]["name"] for definition, _ in FILE_TOOLS]
