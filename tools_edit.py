"""Tool edit: точечная замена единственного совпадения."""

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

EDIT_TOOL = {
    "type": "function",
    "function": {
        "name": "edit",
        "description": "Заменить ровно одно точное совпадение в файле",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Путь к файлу"},
                "old": {"type": "string", "description": "Точный старый текст"},
                "new": {"type": "string", "description": "Новый текст"},
            },
            "required": ["path", "old", "new"],
        },
    },
}

_EDIT_SCRIPT = r'''
import base64, json, sys
path = sys.argv[1]
values = json.loads(base64.b64decode(__PAYLOAD__).decode("utf-8"))
old, new = values["old"], values["new"]
try:
    with open(path, "rb") as stream:
        raw = stream.read()
    content = raw.decode("utf-8")
except FileNotFoundError:
    print(json.dumps({"error": "not_found"}))
    raise SystemExit
except UnicodeDecodeError:
    print(json.dumps({"error": "binary"}))
    raise SystemExit
except OSError as exc:
    print(json.dumps({"error": "io", "message": str(exc)}))
    raise SystemExit
if not old:
    print(json.dumps({"error": "empty_old"}))
    raise SystemExit
count = content.count(old)
if count != 1:
    print(json.dumps({"error": "occurrences", "count": count}))
    raise SystemExit
try:
    with open(path, "w", encoding="utf-8", newline="") as stream:
        stream.write(content.replace(old, new, 1))
except OSError as exc:
    print(json.dumps({"error": "io", "message": str(exc)}))
    raise SystemExit
print(json.dumps({"ok": True, "replacements": 1}))
'''


def _script(old: str, new: str) -> str:
    payload = json.dumps({"old": old, "new": new}, ensure_ascii=False)
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    return _EDIT_SCRIPT.replace("__PAYLOAD__", json.dumps(encoded), 1)


def create_edit_tool_definition(*_args, **_kwargs) -> dict:
    return EDIT_TOOL


def create_edit_tool(*_args, **_kwargs):
    return handle_edit


createEditToolDefinition = create_edit_tool_definition
createEditTool = create_edit_tool


def handle_edit(args: dict, paths: AgentPaths | None) -> str:
    blocked = disabled("edit")
    if blocked:
        return blocked
    path, old, new = (args.get(name) for name in ("path", "old", "new"))
    if not isinstance(path, str) or not path.strip():
        return "Error: invalid arguments: ожидается непустая строка 'path'"
    if not isinstance(old, str) or not isinstance(new, str):
        return "Error: invalid arguments: ожидаются строки 'old' и 'new'"
    if not old:
        return "Error: invalid arguments: 'old' не должен быть пустым"
    if paths is None:
        return "Error: paths не заданы"
    resolved, error = resolve_container_path(path, paths)
    if error:
        return error
    key = resolved.get("path") if resolved else path
    container = sandbox_container_name(paths)

    def mutate() -> str:
        data, run_error = run_json(
            _script(old, new), [path], container, FILE_TOOL_TIMEOUT,
        )
        if run_error:
            return run_error
        if data.get("error"):
            return error_from_data(data, path) or json_text(data)
        return json_text(data)

    return with_file_mutation_queue(path, mutate, key=key)
