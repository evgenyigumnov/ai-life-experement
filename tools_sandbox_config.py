"""Общие настройки и helpers Docker-инструментов."""

import os

from agent_paths import AgentPaths
from config_env import parse_bool_env

ENABLE_BASH_TOOL_ENV = "ENABLE_BASH_TOOL"
DEFAULT_BASH_TIMEOUT = 5
MAX_BASH_TIMEOUT = 300


def bash_tool_enabled() -> bool:
    return parse_bool_env(os.environ.get(ENABLE_BASH_TOOL_ENV, "")) is True


def sandbox_container_name(paths: AgentPaths | None) -> str:
    if paths is not None:
        return (
            getattr(paths, "name", None)
            or (paths.folder.name if getattr(paths, "folder", None) else None)
            or "default"
        )
    return "default"
