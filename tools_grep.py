"""Tool grep: поиск regexp без shell-опций и busybox-зависимости."""

from __future__ import annotations

import json

from agent_paths import AgentPaths
from tools_file_common import (
    FILE_TOOL_TIMEOUT, disabled, error_from_data, json_text, run_json,
)
from tools_sandbox import sandbox_container_name
from tools_truncate import GREP_MAX_LINE_LENGTH, truncate_head

GREP_TOOL = {
    "type": "function",
    "function": {
        "name": "grep",
        "description": "Найти строки по регулярному выражению",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Регулярное выражение"},
                "path": {"type": "string", "description": "Файл или каталог"},
                "include": {"type": "string", "description": "Шаблон имён файлов"},
            },
            "required": ["pattern"],
        },
    },
}

_GREP_SCRIPT = r'''
import fnmatch, json, os, re, sys
pattern, root, include = json.loads(sys.argv[1])
try:
    matcher = re.compile(pattern)
except re.error as exc:
    print(json.dumps({"error": "invalid_regex", "message": str(exc)}))
    raise SystemExit
if not os.path.exists(root):
    print(json.dumps({"error": "not_found"}))
    raise SystemExit
if not os.path.isdir(root) and not os.path.isfile(root):
    print(json.dumps({"error": "io", "message": "unsupported search path"}))
    raise SystemExit

def candidates():
    if os.path.isfile(root):
        yield root
        return
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__"})
        for filename in sorted(files):
            yield os.path.join(directory, filename)

def matches_glob(value, pattern):
    return (fnmatch.fnmatch(value, pattern) or
            (pattern.startswith("**/") and fnmatch.fnmatch(value, pattern[3:])))

MAX_LINE = __MAX_LINE__
matches = []
for filename in candidates():
    relative = os.path.relpath(filename, root)
    if include and not (matches_glob(os.path.basename(filename), include) or
                         matches_glob(relative, include)):
        continue
    try:
        with open(filename, "rb") as stream:
            raw = stream.read()
        if b"\x00" in raw[:8192]:
            continue
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        continue
    shown = os.path.basename(filename) if os.path.isfile(root) else os.path.relpath(filename, root)
    shown = shown.replace(os.sep, "/")
    for number, line in enumerate(text.splitlines(), 1):
        if matcher.search(line):
            marker = "... [truncated]"
            if len(line) > MAX_LINE:
                line = line[:MAX_LINE - len(marker)] + marker
            matches.append(f"{shown}:{number}: {line}")
print(json.dumps({"ok": True, "content": "\n".join(matches)}))
'''


def _script() -> str:
    return _GREP_SCRIPT.replace("__MAX_LINE__", str(GREP_MAX_LINE_LENGTH), 1)


def create_grep_tool_definition(*_args, **_kwargs) -> dict:
    return GREP_TOOL


def create_grep_tool(*_args, **_kwargs):
    return handle_grep


createGrepToolDefinition = create_grep_tool_definition
createGrepTool = create_grep_tool


def handle_grep(args: dict, paths: AgentPaths | None) -> str:
    blocked = disabled("grep")
    if blocked:
        return blocked
    pattern = args.get("pattern")
    path = args.get("path", ".")
    path = "." if path is None else path
    include = args.get("include")
    if not isinstance(pattern, str) or not pattern:
        return "Error: invalid arguments: ожидается непустая строка 'pattern'"
    if not isinstance(path, str) or not path.strip():
        return "Error: invalid arguments: 'path' должен быть строкой"
    if include is not None and not isinstance(include, str):
        return "Error: invalid arguments: 'include' должен быть строкой"
    if paths is None:
        return "Error: paths не заданы"
    payload = json.dumps([pattern, path, include or ""], ensure_ascii=True)
    data, error = run_json(
        _script(), [payload], sandbox_container_name(paths), FILE_TOOL_TIMEOUT,
    )
    if error:
        return error
    if data.get("error"):
        return error_from_data(data, path) or json_text(data)
    truncation = truncate_head(data.get("content", ""))
    result = {
        "ok": True,
        "matches": truncation["content"],
        "truncated": truncation["truncated"],
        "truncatedBy": truncation["truncatedBy"],
        "totalLines": truncation["totalLines"],
        "totalBytes": truncation["totalBytes"],
    }
    if not truncation["totalLines"]:
        result["message"] = "No matches found"
    return json_text(result)
