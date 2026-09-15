"""Tools get_memory / set_memory: «рабочий стол» текущей сессии.

memory.md — короткая рабочая память агента между итерациями: чтение и
полная перезапись (атомарность обеспечивает storage.write_memory).
"""

from agent_paths import AgentPaths
from storage import read_memory, write_memory

GET_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "get_memory",
        "description": "Прочитать текущую память",
        "parameters": {"type": "object", "properties": {}},
    },
}

SET_MEMORY_TOOL = {
    "type": "function",
    "function": {
        "name": "set_memory",
        "description": "Заменить память полным новым текстом",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Новое полное содержимое памяти"
                }
            },
            "required": ["content"],
        },
    },
}


def handle_get_memory(args: dict, paths: AgentPaths) -> str:
    """get_memory: текущее содержимое memory.md (или «память пуста»)."""
    content = read_memory(paths.memory)
    return content if content.strip() else "(память пуста)"


def handle_set_memory(args: dict, paths: AgentPaths) -> str:
    """set_memory: полная перезапись memory.md новым текстом."""
    content = args.get("content")
    if not isinstance(content, str):
        return "Error: invalid arguments: ожидается строка 'content'"
    write_memory(paths.memory, content)
    return f"Memory updated ({len(content.encode('utf-8'))} bytes)"
