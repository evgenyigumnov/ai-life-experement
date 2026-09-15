"""Шаблон системного промпта."""

from pathlib import Path
from string import Formatter

FILE_SYSTEM_PROMPT = "system-prompt.md"
DEFAULT_SESSION_ITERATIONS = 30
DEFAULT_SLEEP_WARN_REMAINING = 10

_ROOT = Path(__file__).resolve().parent
SYSTEM_PROMPT_TEMPLATE_FILE = _ROOT / "default-prompts" / FILE_SYSTEM_PROMPT
SYSTEM_PROMPT_PLACEHOLDERS = frozenset(
    {"name", "session_iterations", "sleep_warn_remaining"}
)


def _placeholder_names(template: str) -> set[str] | None:
    """Вернуть имена простых полей format или None для битого шаблона."""
    names: set[str] = set()
    try:
        for _, field_name, _, _ in Formatter().parse(template):
            if field_name is None:
                continue
            if not field_name.isidentifier():
                return None
            names.add(field_name)
    except (ValueError, IndexError):
        return None
    return names


def resolve_system_prompt_template(preferred_path: Path | None = None) -> Path:
    """Выбрать шаблон системного промпта по единственному пути."""
    preferred = (
        Path(preferred_path)
        if preferred_path is not None
        else SYSTEM_PROMPT_TEMPLATE_FILE
    )
    if preferred.is_file():
        return preferred
    raise OSError(f"не найден шаблон системного промпта: {preferred}")


def read_system_prompt_template(preferred_path: Path | None = None) -> str:
    """Перечитать и проверить непустой шаблон системного промпта."""
    path = resolve_system_prompt_template(preferred_path)
    try:
        text = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise OSError(f"не удалось прочитать шаблон системного промпта {path}: {exc}") from exc
    if not text:
        raise ValueError(f"шаблон системного промпта пуст: {path}")
    return text


def render_system_prompt(
    name: str,
    session_iterations: int = DEFAULT_SESSION_ITERATIONS,
    sleep_warn_remaining: int = DEFAULT_SLEEP_WARN_REMAINING,
    *,
    template_file: Path | None = None,
) -> str:
    """Собрать системный промпт с подстановкой имени и параметров цикла."""
    if not name or not name.strip():
        raise ValueError("имя агента для системного промпта не может быть пустым")
    template = read_system_prompt_template(template_file)
    names = _placeholder_names(template)
    if names != SYSTEM_PROMPT_PLACEHOLDERS:
        found = "не удалось разобрать" if names is None else sorted(names)
        raise ValueError(
            "шаблон системного промпта должен содержать ровно плейсхолдеры "
            f"{sorted(SYSTEM_PROMPT_PLACEHOLDERS)}, получено: {found}"
        )
    return template.format(
        name=name,
        session_iterations=session_iterations,
        sleep_warn_remaining=sleep_warn_remaining,
    )


def ensure_system_prompt(
    folder,
    name: str,
    session_iterations: int = DEFAULT_SESSION_ITERATIONS,
    sleep_warn_remaining: int = DEFAULT_SLEEP_WARN_REMAINING,
    *,
    template_file: Path | None = None,
) -> Path | None:
    """Создать system-prompt.md, если его ещё нет."""
    path = Path(folder) / FILE_SYSTEM_PROMPT
    if path.exists():
        return None
    path.write_text(
        render_system_prompt(
            name,
            session_iterations,
            sleep_warn_remaining,
            template_file=template_file,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
