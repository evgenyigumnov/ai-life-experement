"""Сборка полного массива messages для очередного запроса LLM."""

from agent_paths import AgentPaths
from agent_prompt_context import append_cycle_context, build_final_user_message
from storage import read_system_prompt


def build_messages(data: dict, paths: AgentPaths) -> list[dict]:
    """Собрать system, историю, служебные заметки и финальный user-тик."""
    messages: list[dict] = [
        {"role": "system", "content": read_system_prompt(paths.system_prompt)}
    ]
    iterations, upcoming_n = append_cycle_context(messages, data, paths)
    messages.append(
        build_final_user_message(messages, iterations, paths, upcoming_n)
    )
    return messages
