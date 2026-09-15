"""Общие фикстуры тестов tools-модулей (бывший единый test_tools.py).

Разбит по правилу AGENTS.md: каждый .py ≤ 10 KB. Здесь — шапка импортов
и хелперы, общие для всех test_tools_*.py.
"""

import json
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.helpers import env  # noqa: E402
from agent_paths import AgentPaths  # noqa: E402
import tool_registry as tools  # noqa: E402


@contextmanager
def bash_tool_on():
    """Временно включить ENABLE_BASH_TOOL (run_bash по умолчанию выключен)."""
    with env(ENABLE_BASH_TOOL="1"):
        yield


def _paths(memory: Path, name: str = "test-agent") -> AgentPaths:
    return AgentPaths(
        folder=memory.parent,
        system_prompt=memory.parent / "system-prompt.md",
        mind_loop=memory.parent / "mind-loop.json",
        memory=memory,
        name=name,
    )


def _bash(command: str, timeout=None, paths=None) -> str:
    args = {"command": command}
    if timeout is not None:
        args["timeout"] = timeout
    return tools.execute_tool("run_bash", json.dumps(args), paths)
