"""Tool run_bash: исполнение bash-команд в Docker-песочнице агента.

ВЫКЛЮЧЕН ПО УМОЛЧАНИЮ (ENABLE_BASH_TOOL в .env): в схему tools для LLM не
попадает и не исполняется, пока флаг не включён. Включённый run_bash
исполняется в изолированном контейнере агента (см. sandbox_docker) через
RUNNER_SCRIPT с контролем таймаута; вывод обрезается до MAX_OUTPUT_CHARS.
"""

import json
import os

from agent_paths import AgentPaths
from config_env import parse_bool_env
from sandbox_scripts import RUNNER_SCRIPT, exec_python

ENABLE_BASH_TOOL_ENV = "ENABLE_BASH_TOOL"  # имя переменной в .env/окружении
DEFAULT_BASH_TIMEOUT = 5  # таймаут команды по умолчанию, сек
MAX_BASH_TIMEOUT = 300  # верхняя граница таймаута, сек
MAX_OUTPUT_CHARS = 10_000  # лимит вывода run_bash до обрезки

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
                    "description": (
                        "Необязательный таймаут в секундах "
                        f"(по умолчанию {DEFAULT_BASH_TIMEOUT}, "
                        f"максимум {MAX_BASH_TIMEOUT})"
                    ),
                },
            },
            "required": ["command"],
        },
    },
}


def bash_tool_enabled() -> bool:
    """Включён ли tool run_bash (ENABLE_BASH_TOOL; по умолчанию выключен).

    Строгая валидация значения выполняется в config_env.load_config при запуске
    агента; здесь нераспознанное значение трактуется как «выключен» —
    безопасное поведение по умолчанию.
    """
    return parse_bool_env(os.environ.get(ENABLE_BASH_TOOL_ENV, "")) is True


def sandbox_container_name(paths: AgentPaths | None) -> str:
    """Имя Docker-контейнера агента: имя агента или дефолт."""
    if paths is not None:
        return (
            getattr(paths, "name", None)
            or (paths.folder.name if getattr(paths, "folder", None) else None)
            or "default"
        )
    return "default"


def truncate(text: str) -> str:
    """Обрезать длинный вывод с пометкой (чтобы не раздувать историю)."""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    cut = text[:MAX_OUTPUT_CHARS]
    return f"{cut}\n...output truncated ({len(text) - MAX_OUTPUT_CHARS} chars)..."


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
        return truncate("\n".join([
            f"$ {command}",
            f"returncode: {proc.returncode}",
            "--- stdout ---",
            "(пусто)",
            "--- stderr ---",
            stderr.strip() or "(пусто)",
        ]))

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

    return truncate("\n".join([
        f"$ {command}",
        f"returncode: {returncode}",
        "--- stdout ---",
        out_str or "(пусто)",
        "--- stderr ---",
        err_str or "(пусто)",
    ]))


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
        or timeout <= 0
        or timeout > MAX_BASH_TIMEOUT
    ):
        return (
            f"Error: invalid arguments: 'timeout' должен быть числом "
            f"от 1 до {MAX_BASH_TIMEOUT} секунд"
        )
    return run_bash(
        command, float(timeout), container_name=sandbox_container_name(paths)
    )
