"""Рамочные блоки консоли наблюдения: промпт, ответ LLM, размышления, tools, сбой.

Все блоки рисуются общим помощником `_box`: рамка из символов-заполнителей
(═/─/━), цвет и ширина параметризуются — вывод побайтово совпадает
с исходными отдельными реализациями.
"""

import json
from urllib.parse import urlsplit, urlunsplit

from agent_console import _Colors, _colorize, _supports_color

MAX_REASONING_LOG_CHARS = 4000  # лимит текста размышлений в консоли (с пометкой об обрезке)

_VERTICAL = {"═": "║", "─": "│", "━": "┃"}
_BOTTOM_LEFT = {"═": "╚", "─": "└", "━": "┗"}


def _std_right(title: str) -> int:
    """Ширина правой части шапки рамки: рамка не короче 2 символов заполнителя."""
    return max(2, 68 - len(title))


def _box(color: str, head: str, fill: str, title: str, text: str,
         right: int, bottom_width: int) -> str:
    """Рамочный блок: шапка `head + title`, тело с вертикальной чертой, низ.

    `fill` — символ заполнителя рамки (═/─/━); вертикальная черта и левый
    нижний угол подбираются по нему. Цвет включается через _supports_color.
    """
    vert = _VERTICAL[fill]
    if _supports_color():
        reset = _Colors.RESET
        top = f"{color}{head}{title} {fill * right}{reset}"
        body = [
            f"{color}{vert}{reset} {line}" if line else f"{color}{vert}{reset}"
            for line in text.splitlines()
        ]
        bottom = f"{color}{_BOTTOM_LEFT[fill]}{fill * bottom_width}{reset}"
    else:
        top = f"{head}{title} {fill * right}"
        body = [f"{vert} {line}" if line else vert for line in text.splitlines()]
        bottom = f"{_BOTTOM_LEFT[fill]}{fill * bottom_width}"
    return "\n".join([top, *body, bottom])


def _format_system_prompt_block(n: int, prompt: str) -> str:
    """Блок системного промпта (рамка ╔═║╚, иконка 📜, цвет cyan).

    system-prompt.md перечитывается с диска при каждой итерации и каждый
    раз заново уходит в LLM первым сообщением запроса. Полный блок
    печатается только при первом показе и после правки файла (промпт
    можно менять на живом агенте — изменение сразу видно в консоли),
    в остальных случаях — короткая строка `_format_system_prompt_unchanged`.
    Текст выводится целиком, без обрезки.
    """
    text = prompt.rstrip("\n")
    if not text.strip():
        text = "(пусто)"
    title = f"[итерация {n}] 📜 System prompt"
    return _box(_Colors.CYAN, "╔══ ", "═", title, text, _std_right(title), 70)


def _format_system_prompt_unchanged(n: int) -> str:
    """Короткая строка вместо полного блока: промпт не менялся с прошлого показа.

    system-prompt.md всё равно уходит в LLM первым сообщением каждого
    запроса — в консоли достаточно упомянуть этот факт, не повторяя текст.
    """
    return _colorize(f"[итерация {n}] 📜 System prompt без изменений", _Colors.CYAN)


def _format_llm_stats(
    duration: float,
    prompt_tokens: int | None,
    completion_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> str:
    """Строка статистики ответа LLM: секунды, посланные и сгенерированные токены."""
    parts = [f"{duration:.2f} сек"]
    if prompt_tokens is not None:
        parts.append(f"токенов послано: {prompt_tokens}")
    if completion_tokens is not None:
        extra = f" (из них reasoning: {reasoning_tokens})" if reasoning_tokens else ""
        parts.append(f"токенов сгенерировано: {completion_tokens}{extra}")
    return " | ".join(parts)


def _format_llm_block(
    n: int,
    content: str | None,
    duration: float,
    prompt_tokens: int | None,
    completion_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> str:
    """Блок ответа LLM (лёгкая рамка ┌─│└, иконка 💬, цвет magenta)."""
    stats = _format_llm_stats(duration, prompt_tokens, completion_tokens, reasoning_tokens)
    text = (content or "").strip() or "(без текста)"
    title = f"[итерация {n}] 💬 LLM ({stats})"
    return _box(_Colors.MAGENTA, "┌── ", "─", title, text, _std_right(title), 70)


def _format_reasoning_block(n: int, reasoning: str) -> str:
    """Блок размышлений модели (рамка ┌─│└, иконка 🧠, цвет blue).

    Длинный thinking обрезается до MAX_REASONING_LOG_CHARS символов с пометкой
    о полном размере — консоль наблюдения не должна захламляться тысячами
    символов размышлений на каждом тике.
    """
    text = reasoning.strip()
    if len(text) > MAX_REASONING_LOG_CHARS:
        text = (
            text[:MAX_REASONING_LOG_CHARS]
            + f"\n... (обрезано: показано {MAX_REASONING_LOG_CHARS}"
            + f" из {len(text)} символов)"
        )
    title = f"[итерация {n}] 🧠 Reasoning"
    return _box(_Colors.BLUE, "┌── ", "─", title, text, _std_right(title), 70)


def _format_tool_args(arguments) -> str:
    """Форматирование аргументов tool (красивый JSON с отступами)."""
    if isinstance(arguments, dict):
        return json.dumps(arguments, ensure_ascii=False, indent=2)
    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, (dict, list)):
                return json.dumps(parsed, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return arguments
    return str(arguments)


def _redact_tool_arguments(name: str, arguments):
    """Не показывать query/fragment URL inspect_image в консоли."""
    if name != "inspect_image":
        return arguments
    data = arguments
    encoded = isinstance(arguments, str)
    if encoded:
        try:
            data = json.loads(arguments)
        except (TypeError, ValueError, json.JSONDecodeError):
            return arguments
    if not isinstance(data, dict) or not isinstance(data.get("source"), str):
        return arguments
    source = data["source"]
    try:
        parts = urlsplit(source.strip())
    except ValueError:
        return arguments
    if parts.scheme.lower() not in {"http", "https"}:
        return arguments
    safe_netloc = parts.netloc.rsplit("@", 1)[-1]
    safe = urlunsplit((parts.scheme, safe_netloc, parts.path, "", ""))
    data = dict(data)
    data["source"] = safe
    return json.dumps(data, ensure_ascii=False) if encoded else data


def _format_tool_call_block(n: int, name: str, arguments) -> str:
    """Блок вызова tool (жирная рамка ┏━┃┗, иконка ⚙️, цвет yellow)."""
    args_str = _format_tool_args(_redact_tool_arguments(name, arguments))
    title = f"[итерация {n}] ⚙️  Tool: {name} [вызов]"
    return _box(_Colors.YELLOW, "┏━━ ", "━", title, args_str, _std_right(title), 70)


def _format_tool_result_block(n: int, name: str, result: str | None) -> str:
    """Блок результата tool (двойная рамка ╔═║╚, иконка 📥, цвет green)."""
    res_str = result.strip() if (result and result.strip()) else "(пусто)"
    title = f"[итерация {n}] 📥 Tool: {name} [результат]"
    return _box(_Colors.GREEN, "╔══ ", "═", title, res_str, _std_right(title), 70)


def _format_failed_iteration(exc: Exception) -> str:
    """Блок ошибки итерации (двойная рамка с ❌, цвет red)."""
    note = f"{type(exc).__name__}: {exc}"
    text = f"{note}\nЗафиксировано в истории, жизнь продолжается"
    return _box(_Colors.RED, "╔══ ❌ ", "═", "[сбой]", text, 58, 67)
