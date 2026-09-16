"""Tool ls: краткий список содержимого каталога."""

from __future__ import annotations

import json

from agent_paths import AgentPaths
from tools_file_common import (
    FILE_TOOL_TIMEOUT, disabled, error_from_data, json_text, run_json,
)
from tools_sandbox import sandbox_container_name
from tools_truncate import truncate_head

LS_TOOL = {
    "type": "function",
    "function": {
        "name": "ls",
        "description": "Показать содержимое каталога",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Каталог"},
            },
        },
    },
}

_LS_SCRIPT = r'''
import json, os, sys
root = sys.argv[1]
if not os.path.exists(root):
    print(json.dumps({"error": "not_found"}))
    raise SystemExit
if not os.path.isdir(root):
    print(json.dumps({"error": "not_dir"}))
    raise SystemExit
try:
    entries = []
    for name in sorted(os.listdir(root), key=lambda value: (value.lower(), value)):
        entries.append(name + ("/" if os.path.isdir(os.path.join(root, name)) else ""))
except OSError as exc:
    print(json.dumps({"error": "io", "message": str(exc)}))
    raise SystemExit
print(json.dumps({"ok": True, "content": "\n".join(entries)}))
'''


def create_ls_tool_definition(*_args, **_kwargs) -> dict:
    return LS_TOOL


def create_ls_tool(*_args, **_kwargs):
    return handle_ls


createLsToolDefinition = create_ls_tool_definition
createLsTool = create_ls_tool


def handle_ls(args: dict, paths: AgentPaths | None) -> str:
    blocked = disabled("ls")
    if blocked:
        return blocked
    path = args.get("path", ".")
    path = "." if path is None else path
    if not isinstance(path, str) or not path.strip():
        return "Error: invalid arguments: 'path' должен быть строкой"
    if paths is None:
        return "Error: paths не заданы"
    data, error = run_json(
        _LS_SCRIPT, [path], sandbox_container_name(paths), FILE_TOOL_TIMEOUT,
    )
    if error:
        return error
    if data.get("error"):
        return error_from_data(data, path) or json_text(data)
    truncation = truncate_head(data.get("content", ""))
    result = {
        "ok": True,
        "entries": truncation["content"].splitlines(),
        "truncated": truncation["truncated"],
        "truncatedBy": truncation["truncatedBy"],
        "totalLines": truncation["totalLines"],
        "totalBytes": truncation["totalBytes"],
    }
    if not truncation["totalLines"]:
        result["message"] = "(empty directory)"
    return json_text(result)
