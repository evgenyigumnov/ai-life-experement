"""Запуск read_file в контейнере и разбор ответа раннера."""

import json

from sandbox_scripts import READER_SCRIPT, exec_python
from tools_readfile_output import format_read_file_result
from tools_truncate import truncation_notice, truncate_head

READ_FILE_TIMEOUT = 30


def _fallback_output(path: str, offset: int, limit: int, proc, stdout: str, stderr: str) -> str:
    parts = [f"$ read_file {path} offset={offset} limit={limit}"]
    parts.append(f"returncode: {proc.returncode}")
    parts.append("--- stdout ---")
    parts.append(stdout.strip() or "(пусто)")
    if stderr.strip():
        parts.extend(["--- stderr ---", stderr.strip()])
    result = truncate_head("\n".join(parts))
    if result["truncated"]:
        return result["content"] + "\n" + truncation_notice(result)
    return result["content"]


def run_read_file(
    path: str,
    offset: int,
    limit: int,
    container_name: str = "default",
    limit_note: str | None = None,
    executor=None,
    script: str | None = None,
    timeout: float | None = None,
) -> str:
    """Прочитать страницу файла из контейнера агента."""
    runner = executor or exec_python
    script = READER_SCRIPT if script is None else script
    timeout = READ_FILE_TIMEOUT if timeout is None else timeout
    error, proc, stdout, stderr = runner(
        container_name, script, [path, str(offset), str(limit)], timeout
    )
    if error == "TIMEOUT":
        return f"TIMEOUT after {timeout}s (чтение прервано)"
    if error is not None:
        return error

    try:
        data = json.loads(stdout.strip())
    except Exception:
        data = None

    if isinstance(data, dict):
        err_kind = data.get("error")
        if err_kind == "not_found":
            return f"Error: file not found: {path}"
        if err_kind == "is_dir":
            return f"Error: это директория, а не файл: {path} (список файлов — run_bash ls)"
        if err_kind == "binary":
            return f"Error: двоичный файл: {path} ({data.get('size')} байт)"
        if err_kind == "offset_out_of_range":
            return (
                f"Error: offset={offset} за пределами файла "
                f"(всего {data.get('total_lines')} строк)"
            )
        if "lines" in data:
            return format_read_file_result(data, limit_note=limit_note)

    return _fallback_output(path, offset, limit, proc, stdout, stderr)
