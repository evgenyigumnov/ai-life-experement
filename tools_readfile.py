"""Tool read_file: постраничное чтение файла из песочницы агента.

Под тем же флагом ENABLE_BASH_TOOL, что и run_bash. Сначала объём файла
(строки/байты) и сколько прочитано, затем запрошенный диапазон строк с
номерами: большие файлы модель листает страницами через offset — это
защищает контекст LLM от раздувания. Сверхдлинные строки обрезаются до
READ_FILE_MAX_LINE_CHARS; limit вне диапазона — не ошибка, а приведение
к границе с пометкой в ответе.
"""

import json

from agent_paths import AgentPaths
from sandbox_scripts import READER_SCRIPT, exec_python
from tools_sandbox import bash_tool_enabled, sandbox_container_name, truncate

READ_FILE_DEFAULT_LIMIT = 200  # строк на страницу read_file по умолчанию
READ_FILE_MAX_LIMIT = 1000  # верхняя граница limit у read_file
READ_FILE_MAX_LINE_CHARS = 2000  # обрезка одной сверхдлинной строки в ответе
READ_FILE_TIMEOUT = 30  # host-таймаут чтения файла из песочницы, сек

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Прочитать страницу текстового файла из песочницы; большой файл "
            "листай по частям через offset"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Путь к файлу внутри песочницы",
                },
                "offset": {
                    "type": "number",
                    "description": (
                        "Номер первой строки страницы, начиная с 1 (по умолчанию 1)"
                    ),
                },
                "limit": {
                    "type": "number",
                    "description": (
                        f"Сколько строк вернуть (1-{READ_FILE_MAX_LIMIT}, по "
                        f"умолчанию {READ_FILE_DEFAULT_LIMIT}; значения вне "
                        f"диапазона приводятся к ближайшей границе)"
                    ),
                },
            },
            "required": ["path"],
        },
    },
}


def format_read_file_result(data: dict, limit_note: str | None = None) -> str:
    """Отформатировать страницу файла для ответа tool.

    Шапка — объём (всего строк/байт) и сколько реально прочитано, затем
    строки с номерами; если страница не последняя — подсказка с offset для
    продолжения. limit_note — пометка о приведении limit к границе.
    """
    total = data["total_lines"]
    start, end = data["start"], data["end"]
    width = len(str(end))
    body = []
    for n, line in zip(range(start, end + 1), data["lines"]):
        if len(line) > READ_FILE_MAX_LINE_CHARS:
            line = (
                line[:READ_FILE_MAX_LINE_CHARS]
                + f"…(строка обрезана, всего {len(line)} симв.)"
            )
        body.append(f"{str(n).rjust(width)} | {line}")
    shown = end - start + 1
    # ~ — байты приблизительные: терминаторы строк и замены невалидного
    # utf-8 в точный размер страницы не складываются.
    read_bytes = sum(
        len(line.encode("utf-8", errors="replace")) + 1 for line in data["lines"]
    )
    header = (
        f"{data['path']} — {total} строк, {data['size']} байт; "
        f"прочитано {shown} из {total} строк (~{read_bytes} из {data['size']} байт)"
    )
    notes = []
    if limit_note:
        notes.append(limit_note)
    if end < total:
        notes.append(
            f"показаны строки {start}–{end} из {total}; "
            f"продолжение — read_file offset={end + 1}"
        )
    elif start > 1:
        notes.append(f"показаны строки {start}–{end} из {total} (конец файла)")
    else:
        notes.append("(конец файла)")
    return "\n".join([header, *notes, ""] + body)


def run_read_file(
    path: str,
    offset: int,
    limit: int,
    container_name: str = "default",
    limit_note: str | None = None,
) -> str:
    """Прочитать страницу файла из контейнера агента (READER_SCRIPT).

    Хостовая файловая система агенту недоступна. Ошибки раннера (файла нет,
    директория, двоичный файл, offset за концом) переводятся в понятные
    модели «Error: ...».
    """
    error, proc, stdout, stderr = exec_python(
        container_name,
        READER_SCRIPT,
        [path, str(offset), str(limit)],
        READ_FILE_TIMEOUT,
    )
    if error == "TIMEOUT":
        return f"TIMEOUT after {READ_FILE_TIMEOUT}s (чтение прервано)"
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
            return (
                f"Error: это директория, а не файл: {path} "
                f"(список файлов — run_bash ls)"
            )
        if err_kind == "binary":
            return f"Error: двоичный файл: {path} ({data.get('size')} байт)"
        if err_kind == "offset_out_of_range":
            return (
                f"Error: offset={offset} за пределами файла "
                f"(всего {data.get('total_lines')} строк)"
            )
        if "lines" in data:
            return format_read_file_result(data, limit_note=limit_note)

    parts = [f"$ read_file {path} offset={offset} limit={limit}"]
    parts.append(f"returncode: {proc.returncode}")
    parts.append("--- stdout ---")
    parts.append(stdout.strip() or "(пусто)")
    if stderr.strip():
        parts.append("--- stderr ---")
        parts.append(stderr.strip())
    return truncate("\n".join(parts))


def handle_read_file(args: dict, paths: AgentPaths | None) -> str:
    """Валидация аргументов и исполнение read_file (вызывается диспетчером)."""
    if not bash_tool_enabled():
        return "Error: tool read_file выключен (ENABLE_BASH_TOOL в .env)"
    path = args.get("path")
    if not isinstance(path, str) or not path.strip():
        return "Error: invalid arguments: ожидается непустая строка 'path'"
    offset = args.get("offset", 1)
    if offset is None:
        offset = 1
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 1:
        return (
            "Error: invalid arguments: 'offset' должен быть целым числом "
            "от 1 (номер первой строки)"
        )
    limit = args.get("limit", READ_FILE_DEFAULT_LIMIT)
    if limit is None:
        limit = READ_FILE_DEFAULT_LIMIT
    if not isinstance(limit, int) or isinstance(limit, bool):
        return (
            f"Error: invalid arguments: 'limit' должен быть целым числом "
            f"от 1 до {READ_FILE_MAX_LIMIT} строк"
        )
    # Числовой limit вне [1, MAX] не ломает вызов: приводим к границе
    # и честно сообщаем модели об этом в ответе tool.
    effective_limit = max(1, min(limit, READ_FILE_MAX_LIMIT))
    limit_note = None
    if effective_limit != limit:
        direction = "уменьшен" if limit > effective_limit else "увеличен"
        limit_note = f"limit {direction} до {effective_limit}"
    return run_read_file(
        path,
        offset,
        effective_limit,
        container_name=sandbox_container_name(paths),
        limit_note=limit_note,
    )
