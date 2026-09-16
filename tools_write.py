"""Tool write: создать или полностью перезаписать файл в песочнице."""

from __future__ import annotations

import base64
import json

from agent_paths import AgentPaths
from file_mutation_queue import with_file_mutation_queue
from tools_file_common import (
    FILE_TOOL_TIMEOUT, disabled, error_from_data, json_text,
    resolve_container_path, run_json,
)
from tools_sandbox import sandbox_container_name

WRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "write",
        "description": "Создать или полностью перезаписать файл",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Путь к файлу"},
                "content": {"type": "string", "description": "Новое содержимое"},
            },
            "required": ["path", "content"],
        },
    },
}

_WRITE_SCRIPT = r'''
import base64, json, os, sys
path = sys.argv[1]
content = base64.b64decode(__CONTENT__).decode("utf-8")
try:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as stream:
        stream.write(content)
except OSError as exc:
    print(json.dumps({"error": "io", "message": str(exc)}))
    raise SystemExit
print(json.dumps({"ok": True, "path": path,
                  "bytes": len(content.encode("utf-8"))}))
'''


def _script(content: str) -> str:
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    return _WRITE_SCRIPT.replace("__CONTENT__", json.dumps(encoded), 1)


def create_write_tool_definition(*_args, **_kwargs) -> dict:
    return WRITE_TOOL


def create_write_tool(*_args, **_kwargs):
    return handle_write


createWriteToolDefinition = create_write_tool_definition
createWriteTool = create_write_tool


def handle_write(args: dict, paths: AgentPaths | None) -> str:
    blocked = disabled("write")
    if blocked:
        return blocked
    path, content = args.get("path"), args.get("content")
    if not isinstance(path, str) or not path.strip():
        return "Error: invalid arguments: ожидается непустая строка 'path'"
    if not isinstance(content, str):
        return "Error: invalid arguments: ожидается строка 'content'"
    if paths is None:
        return "Error: paths не заданы"
    resolved, error = resolve_container_path(path, paths)
    if error:
        return error
    key = resolved.get("path") if resolved else path
    container = sandbox_container_name(paths)

    def mutate() -> str:
        data, run_error = run_json(
            _script(content), [path], container, FILE_TOOL_TIMEOUT,
        )
        if run_error:
            return run_error
        if data.get("error"):
            return error_from_data(data, path) or json_text(data)
        return json_text(data)

    return with_file_mutation_queue(path, mutate, key=key)
