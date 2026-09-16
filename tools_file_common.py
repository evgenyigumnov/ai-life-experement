"""Обвязка файловых tools вокруг Docker-раннера."""

from __future__ import annotations

import json

from agent_paths import AgentPaths
from sandbox_scripts import exec_python
from tools_sandbox import bash_tool_enabled, sandbox_container_name

FILE_TOOL_TIMEOUT = 30

PATH_RESOLVER_SCRIPT = r'''
import json, os, sys
path = sys.argv[1]
try:
    canonical = os.path.realpath(path, strict=True)
    exists = True
except (FileNotFoundError, NotADirectoryError):
    canonical = os.path.abspath(path)
    exists = False
print(json.dumps({"path": canonical, "exists": exists}))
'''


def disabled(name: str) -> str | None:
    if not bash_tool_enabled():
        return f"Error: tool {name} выключен (ENABLE_BASH_TOOL в .env)"
    return None


def json_text(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


def run_json(script: str, args: list[str], container_name: str,
             timeout: float = FILE_TOOL_TIMEOUT) -> tuple[dict | None, str | None]:
    error, proc, stdout, stderr = exec_python(
        container_name, script, args, timeout,
    )
    if error == "TIMEOUT":
        return None, f"TIMEOUT after {timeout}s (операция прервана)"
    if error is not None:
        return None, error
    try:
        data = json.loads((stdout or "").strip())
    except (TypeError, ValueError, json.JSONDecodeError):
        detail = (stderr or stdout or "пустой ответ").strip()
        return None, f"Error: файловый tool вернул некорректный ответ: {detail}"
    if not isinstance(data, dict):
        return None, "Error: файловый tool вернул не объект"
    return data, None


def resolve_container_path(path: str, paths: AgentPaths) -> tuple[dict | None, str | None]:
    """Получить realpath в контейнере; ENOENT не считать ошибкой."""
    return run_json(
        PATH_RESOLVER_SCRIPT, [path], sandbox_container_name(paths),
    )


def error_from_data(data: dict, path: str) -> str | None:
    kind = data.get("error")
    if not kind:
        return None
    messages = {
        "not_found": f"Error: file not found: {path}",
        "is_dir": f"Error: это директория, а не файл: {path}",
        "not_dir": f"Error: это не директория: {path}",
        "binary": f"Error: двоичный файл: {path}",
        "invalid_regex": f"Error: invalid pattern: {data.get('message', '')}".rstrip(),
    }
    if kind == "occurrences":
        return (
            f"Error: old text must occur exactly once in {path}; "
            f"found {data.get('count', 0)} occurrences"
        )
    if kind == "empty_old":
        return f"Error: old text must not be empty in {path}"
    if kind == "io":
        return f"Error: {data.get('message', 'file operation failed')}"
    return messages.get(kind, f"Error: {kind}")


def result_with_truncation(ok: bool, key: str, text: str,
                           truncation: dict) -> dict:
    """Добавить к ответу инструмента общий набор метаданных лимита."""
    result = {
        "ok": ok,
        key: text,
        "truncated": truncation["truncated"],
        "truncatedBy": truncation["truncatedBy"],
        "totalLines": truncation["totalLines"],
        "totalBytes": truncation["totalBytes"],
    }
    if truncation["truncated"]:
        result["outputLines"] = truncation["outputLines"]
        result["outputBytes"] = truncation["outputBytes"]
    return result
