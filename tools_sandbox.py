"""Tool run_bash: исполнение bash-команд в Docker-песочнице агента.

ВЫКЛЮЧЕН ПО УМОЛЧАНИЮ (ENABLE_BASH_TOOL в .env): в схему tools для LLM не
попадает и не исполняется, пока флаг не включён. Включённый run_bash
исполняется в изолированном контейнере агента (см. sandbox_docker) через
RUNNER_SCRIPT с контролем таймаута; вывод проходит общий лимит 2000 строк/50 КБ.
"""

import json

from agent_paths import AgentPaths
from sandbox_scripts import RUNNER_SCRIPT, exec_python
from tools_bash_output import MAX_OUTPUT_CHARS, format_bash_result, truncate
from tools_sandbox_config import (
    DEFAULT_BASH_TIMEOUT, ENABLE_BASH_TOOL_ENV, MAX_BASH_TIMEOUT,
    bash_tool_enabled, sandbox_container_name,
)

RUN_BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "run_bash",
        "description": "Выполнить команду в изолированной среде и вернуть результат.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Команда для выполнения",
                },
                "timeout": {
                    "type": "number",
                    "minimum": 1,
                    "maximum": MAX_BASH_TIMEOUT,
                    "description": (
                        "Необязательный таймаут в секундах "
                        f"(по умолчанию {DEFAULT_BASH_TIMEOUT}, "
                        f"допустимо 1-{MAX_BASH_TIMEOUT})"
                    ),
                },
            },
            "required": ["command"],
        },
    },
}


def run_bash(command: str, timeout: float, container_name: str = "default") -> str:
    """Выполнить bash-команду в контейнере агента, вернуть текстовый результат.

    Host-таймаут — с запасом сверх таймаута команды. Ошибки Docker
    возвращаются строкой «Error: ...» / «TIMEOUT ...».
    """
    error, proc, stdout, stderr = exec_python(
        container_name, RUNNER_SCRIPT, [command, str(timeout)], timeout + 15.0
    )
    if error == "TIMEOUT":
        return f"TIMEOUT after {timeout}s (команда убита)"
    if error is not None:
        return error

    if proc.returncode != 0 and not stdout.strip():
        return format_bash_result(
            command, proc.returncode, "", stderr.strip() or "(пусто)"
        )

    try:
        data = json.loads(stdout.strip())
    except Exception:
        data = None

    if isinstance(data, dict):
        if data.get("timed_out"):
            return f"TIMEOUT after {timeout}s (команда убита)"
        returncode = data.get("returncode", proc.returncode)
        out_str = data.get("stdout", "")
        err_str = data.get("stderr", "")
    else:
        returncode = proc.returncode
        out_str = stdout
        err_str = stderr

    return format_bash_result(command, returncode, out_str, err_str)


def handle_run_bash(args: dict, paths: AgentPaths | None) -> str:
    """Валидация аргументов и исполнение run_bash (вызывается диспетчером)."""
    if not bash_tool_enabled():
        return "Error: tool run_bash выключен (ENABLE_BASH_TOOL в .env)"
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        return "Error: invalid arguments: ожидается непустая строка 'command'"
    timeout = args.get("timeout", DEFAULT_BASH_TIMEOUT)
    if timeout is None:
        timeout = DEFAULT_BASH_TIMEOUT
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout < 1
        or timeout > MAX_BASH_TIMEOUT
    ):
        return (
            f"Error: invalid arguments: 'timeout' должен быть числом "
            f"от 1 до {MAX_BASH_TIMEOUT} секунд"
        )
    return run_bash(
        command, float(timeout), container_name=sandbox_container_name(paths)
    )
