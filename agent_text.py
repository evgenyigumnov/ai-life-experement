"""Русская плюрализация числительных для промптов и консоли наблюдения."""


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Согласовать слово с числом по правилам русского языка."""
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"


def _plural_iterations(n: int) -> str:
    """Число с согласованным словом «итерация»."""
    return _plural(n, "итерацию", "итерации", "итераций")


def _plural_messages(n: int) -> str:
    """Число с согласованным словом «сообщение»."""
    return _plural(n, "сообщение", "сообщения", "сообщений")


def _plural_entries(n: int) -> str:
    """Число с согласованным словом «запись»."""
    return _plural(n, "запись", "записи", "записей")
