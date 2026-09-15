"""Редактируемые сообщения цикла и внутренние fallback-строки."""

from pathlib import Path

from prompts_template import _placeholder_names

FILE_USER_MESSAGE = "user-message.md"
FILE_LAST_ITERATION_MESSAGE = "last-iteration-message.md"
FILE_WAKE_UP_MESSAGE = "wake-up-message.md"
FILE_SLEEP_WARNING = "sleep-warning.md"
FILE_REPEAT_ALERT = "repeat-alert.md"

EDITABLE_MESSAGE_FILES: tuple[str, ...] = (
    FILE_USER_MESSAGE,
    FILE_LAST_ITERATION_MESSAGE,
    FILE_WAKE_UP_MESSAGE,
    FILE_SLEEP_WARNING,
    FILE_REPEAT_ALERT,
)

FILE_ITERATION_FAILED = "iteration-failed.md"
FILE_TOOL_RESULT_MISSING = "tool-result-missing.md"

DEFAULT_PROMPTS_FOLDER = Path(__file__).resolve().parent / "default-prompts"

INTERNAL_MESSAGES: dict[str, str] = {
    FILE_ITERATION_FAILED: "[сбой итерации: {error}]",
    FILE_TOOL_RESULT_MISSING: "Error: результат этого tool-call не найден в истории",
}

ALLOWED_PLACEHOLDERS: dict[str, frozenset[str]] = {
    FILE_USER_MESSAGE: frozenset(),
    FILE_LAST_ITERATION_MESSAGE: frozenset(),
    FILE_WAKE_UP_MESSAGE: frozenset(),
    FILE_SLEEP_WARNING: frozenset({"remaining", "memory_note"}),
    FILE_REPEAT_ALERT: frozenset({"streak", "examples"}),
    FILE_ITERATION_FAILED: frozenset({"error"}),
    FILE_TOOL_RESULT_MISSING: frozenset(),
}


def read_default_message(filename: str) -> str:
    """Прочитать дефолт редактируемого сообщения из общего файла."""
    if filename not in EDITABLE_MESSAGE_FILES:
        raise KeyError(filename)
    path = DEFAULT_PROMPTS_FOLDER / filename
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise OSError(f"не удалось прочитать дефолтное сообщение {path}: {exc}") from exc
    if not text:
        raise ValueError(f"дефолтное сообщение пусто: {path}")
    return text


def _default_message(filename: str) -> str:
    if filename in EDITABLE_MESSAGE_FILES:
        return read_default_message(filename)
    if filename in INTERNAL_MESSAGES:
        return INTERNAL_MESSAGES[filename]
    raise KeyError(filename)


def _template_is_valid(filename: str, template: str) -> bool:
    names = _placeholder_names(template)
    allowed = ALLOWED_PLACEHOLDERS.get(filename)
    return names is not None and allowed is not None and names <= allowed


def _format_params(filename: str, params: dict) -> dict:
    result = dict(params)
    if filename == FILE_SLEEP_WARNING:
        result.setdefault("memory_note", "")
    return result


def read_message(folder, filename: str) -> str:
    """Перечитать файл сообщения; при ошибке вернуть его fallback."""
    default = _default_message(filename)
    try:
        text = (Path(folder) / filename).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return default
    return text or default


def format_message(folder, filename: str, **params) -> str:
    """Перечитать, проверить и отформатировать сообщение без падения агента."""
    template = read_message(folder, filename)
    params = _format_params(filename, params)
    if not _template_is_valid(filename, template):
        template = _default_message(filename)
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError, TypeError):
        fallback = _default_message(filename)
        try:
            return fallback.format(**params)
        except (KeyError, IndexError, ValueError, TypeError):
            return fallback


def ensure_message_files(folder) -> list[Path]:
    """Создать отсутствующие редактируемые файлы, не трогая существующие."""
    folder = Path(folder)
    created: list[Path] = []
    for filename in EDITABLE_MESSAGE_FILES:
        path = folder / filename
        if not path.exists():
            path.write_text(read_default_message(filename) + "\n", encoding="utf-8")
            created.append(path)
    return created
