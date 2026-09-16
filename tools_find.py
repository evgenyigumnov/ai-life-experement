"""Tool find: поиск файлов по glob-шаблону."""

from __future__ import annotations

import json

from agent_paths import AgentPaths
from tools_file_common import (
    FILE_TOOL_TIMEOUT, disabled, error_from_data, json_text, run_json,
)
from tools_sandbox import sandbox_container_name
from tools_truncate import truncate_head

FIND_TOOL = {
    "type": "function",
    "function": {
        "name": "find",
        "description": "Найти файлы по glob-шаблону имени",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Glob-шаблон имени"},
                "path": {"type": "string", "description": "Каталог поиска"},
            },
            "required": ["pattern"],
        },
    },
}

_FIND_SCRIPT = r'''
import fnmatch, json, os, sys
pattern, root = json.loads(sys.argv[1])
if not os.path.exists(root):
    print(json.dumps({"error": "not_found"}))
    raise SystemExit
if not os.path.isdir(root) and not os.path.isfile(root):
    print(json.dumps({"error": "io", "message": "unsupported search path"}))
    raise SystemExit
def matches(value):
    return (fnmatch.fnmatch(value, pattern) or
            (pattern.startswith("**/") and fnmatch.fnmatch(value, pattern[3:])))

found = []
if os.path.isfile(root):
    if matches(os.path.basename(root)) or matches(root):
        found.append(os.path.basename(root))
else:
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__"})
        for filename in sorted(files):
            absolute = os.path.join(directory, filename)
            relative = os.path.relpath(absolute, root).replace(os.sep, "/")
            if matches(filename) or matches(relative):
                found.append(relative)
print(json.dumps({"ok": True, "content": "\n".join(found)}))
'''


def create_find_tool_definition(*_args, **_kwargs) -> dict:
    return FIND_TOOL


def create_find_tool(*_args, **_kwargs):
    return handle_find


createFindToolDefinition = create_find_tool_definition
createFindTool = create_find_tool


def handle_find(args: dict, paths: AgentPaths | None) -> str:
    blocked = disabled("find")
    if blocked:
        return blocked
    pattern = args.get("pattern")
    path = args.get("path", ".")
    path = "." if path is None else path
    if not isinstance(pattern, str) or not pattern:
        return "Error: invalid arguments: ожидается непустая строка 'pattern'"
    if not isinstance(path, str) or not path.strip():
        return "Error: invalid arguments: 'path' должен быть строкой"
    if paths is None:
        return "Error: paths не заданы"
    payload = json.dumps([pattern, path], ensure_ascii=True)
    data, error = run_json(
        _FIND_SCRIPT, [payload], sandbox_container_name(paths), FILE_TOOL_TIMEOUT,
    )
    if error:
        return error
    if data.get("error"):
        return error_from_data(data, path) or json_text(data)
    truncation = truncate_head(data.get("content", ""))
    result = {
        "ok": True,
        "files": truncation["content"].splitlines(),
        "truncated": truncation["truncated"],
        "truncatedBy": truncation["truncatedBy"],
        "totalLines": truncation["totalLines"],
        "totalBytes": truncation["totalBytes"],
    }
    if not truncation["totalLines"]:
        result["message"] = "No files found matching pattern"
    return json_text(result)
