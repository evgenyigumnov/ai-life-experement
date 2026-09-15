"""Константы и проверка аргументов дневника."""

DIARY_KINDS = ("note", "event", "lesson", "value", "idea")
DEFAULT_KIND = "note"
MAX_ENTRY_CHARS = 2000
MAX_TAGS_PER_ENTRY = 10
MAX_TAG_CHARS = 64
DEFAULT_RECALL_LIMIT = 20
MAX_RECALL_LIMIT = 100
RECALL_ORDERS = ("new", "old")


class DiaryError(ValueError):
    """Базовая ошибка дневника."""


class ValidationError(DiaryError):
    """Неверные аргументы дневника."""


class EntryNotFound(DiaryError):
    """Записи с таким id нет."""


def validate_text(text) -> str:
    """Текст записи: непустая строка не длиннее лимита."""
    if not isinstance(text, str):
        raise ValidationError("текст записи должен быть строкой")
    stripped = text.strip()
    if not stripped:
        raise ValidationError("текст записи не может быть пустым")
    if len(stripped) > MAX_ENTRY_CHARS:
        raise ValidationError(
            f"запись длиннее {MAX_ENTRY_CHARS} символов "
            f"({len(stripped)}); сократите текст или разбейте на несколько записей"
        )
    return stripped


def normalize_tags(tags) -> list[str]:
    """Нормализовать список тегов: регистр, пустые и дубли."""
    if tags is None:
        return []
    if not isinstance(tags, (list, tuple)):
        raise ValidationError("теги должны быть списком строк")
    normalized: list[str] = []
    for tag in tags:
        if not isinstance(tag, str):
            raise ValidationError("каждый тег должен быть строкой")
        stripped = tag.strip().lower()
        if not stripped:
            continue
        if len(stripped) > MAX_TAG_CHARS:
            raise ValidationError(f"тег длиннее {MAX_TAG_CHARS} символов: {stripped!r}")
        if stripped not in normalized:
            normalized.append(stripped)
    if len(normalized) > MAX_TAGS_PER_ENTRY:
        raise ValidationError(f"не больше {MAX_TAGS_PER_ENTRY} тегов на запись")
    return normalized


def validate_kind(kind) -> str:
    """Проверить тип записи; None означает note."""
    if kind is None:
        return DEFAULT_KIND
    if not isinstance(kind, str) or kind.strip().lower() not in DIARY_KINDS:
        raise ValidationError(
            f"тип записи должен быть одним из: {', '.join(DIARY_KINDS)}"
        )
    return kind.strip().lower()


def normalize_kinds(kinds) -> list[str]:
    """Нормализовать фильтр типов записей."""
    if kinds is None:
        return []
    if not isinstance(kinds, (list, tuple)):
        raise ValidationError("типы записей должны быть списком")
    normalized: list[str] = []
    for kind in kinds:
        value = validate_kind(kind)
        if value not in normalized:
            normalized.append(value)
    return normalized


def validate_entry_id(value, name: str = "'id'") -> int:
    """Проверить положительный id; строка из цифр допустима."""
    if isinstance(value, bool):
        raise ValidationError(f"{name} должен быть целым числом")
    if isinstance(value, int):
        entry_id = value
    elif isinstance(value, str) and value.strip().isdigit():
        entry_id = int(value.strip())
    else:
        raise ValidationError(f"{name} должен быть целым числом")
    if entry_id <= 0:
        raise ValidationError(f"{name} должен быть положительным числом")
    return entry_id


def validate_limit(value, default: int, maximum: int, name: str = "limit") -> int:
    """Проверить лимит выдачи."""
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"'{name}' должен быть целым числом")
    if value < 1 or value > maximum:
        raise ValidationError(f"'{name}' должен быть от 1 до {maximum}")
    return value
