"""Tool read_file: постраничное чтение файла из песочницы агента.

Под тем же флагом ENABLE_BASH_TOOL, что и run_bash. Сначала объём файла
(строки/байты) и сколько прочитано, затем запрошенный диапазон строк с
номерами: большие файлы модель листает страницами через offset — это
защищает контекст LLM от раздувания. Сверхдлинные строки обрезаются до
READ_FILE_MAX_LINE_CHARS, а весь ответ — общими лимитами вывода; limit вне
диапазона — не ошибка, а приведение к границе с пометкой в ответе.
"""

from agent_paths import AgentPaths
from sandbox_scripts import READER_SCRIPT, exec_python
from tools_readfile_exec import READ_FILE_TIMEOUT, run_read_file as _run_read_file
from tools_readfile_output import READ_FILE_MAX_LINE_CHARS, format_read_file_result
from tools_sandbox import bash_tool_enabled, sandbox_container_name

READ_FILE_DEFAULT_LIMIT = 200  # строк на страницу read_file по умолчанию
READ_FILE_MAX_LIMIT = 1000  # верхняя граница limit у read_file

READ_FILE_TOOL = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": (
            "Прочитать страницу текстового файла; ответ до 2000 строк или "
            "50 КБ, большой файл листай через offset"
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


def run_read_file(
    path: str,
    offset: int,
    limit: int,
    container_name: str = "default",
    limit_note: str | None = None,
) -> str:
    """Совместимый фасад чтения."""
    return _run_read_file(
        path,
        offset,
        limit,
        container_name,
        limit_note,
        executor=exec_python,
        script=READER_SCRIPT,
        timeout=READ_FILE_TIMEOUT,
    )


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
