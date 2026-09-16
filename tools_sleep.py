"""Tool sleep: добровольное завершение текущей сессии."""

from agent_paths import AgentPaths
from tool_context import ToolContext


SLEEP_TOOL = {
    "type": "function",
    "function": {
        "name": "sleep",
        "description": "Добровольно завершить текущую сессию и начать новую",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "Почему пора спать: усталость или большой контекст",
                },
            },
            "required": ["reason"],
        },
    },
}


def handle_sleep(
    args: dict, _paths: AgentPaths, context: ToolContext | None = None
) -> str:
    """Запланировать сон после сохранения текущей итерации."""
    reason = args.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return "Error: invalid arguments: ожидается непустая строка 'reason'"
    if context is None:
        return "Error: sleep: отсутствует контекст текущего цикла"
    reason = reason.strip()
    context.request_sleep(reason)
    return f"Сон запрошен: {reason}"
