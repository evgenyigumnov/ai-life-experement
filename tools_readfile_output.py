"""Форматирование и защита вывода read_file."""

from tools_truncate import (
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_LINES,
    truncate_head,
    truncation_notice,
)

READ_FILE_MAX_LINE_CHARS = 2000


def _shorten_line(line: str, original_length: int | None = None) -> str:
    length = len(line) if original_length is None else original_length
    if length <= READ_FILE_MAX_LINE_CHARS:
        return line
    return (
        line[:READ_FILE_MAX_LINE_CHARS]
        + f"…(строка обрезана, всего {length} симв.)"
    )


def format_read_file_result(data: dict, limit_note: str | None = None) -> str:
    """Отформатировать страницу и ограничить весь текст ответа."""
    total = data["total_lines"]
    start = data["start"]
    raw_lines = data.get("lines", [])
    lengths = data.get("line_lengths", [])
    end = data.get("end", start + len(raw_lines) - 1)
    width = len(str(max(start, end, 1)))
    body = [
        f"{str(start + index).rjust(width)} | "
        f"{_shorten_line(line, lengths[index] if index < len(lengths) else None)}"
        for index, line in enumerate(raw_lines)
    ]
    body_result = truncate_head(
        "\n".join(body), max_lines=DEFAULT_MAX_LINES, max_bytes=DEFAULT_MAX_BYTES
    )
    visible_body = body_result["content"]
    visible_lines = visible_body.split("\n") if visible_body else []
    shown = len(visible_lines)
    shown_end = start + shown - 1 if shown else start - 1
    read_bytes = sum(
        len(line.encode("utf-8", errors="replace")) + 1 for line in raw_lines[:shown]
    )
    header = (
        f"{data['path']} — {total} строк, {data['size']} байт; "
        f"прочитано {shown} из {total} строк (~{read_bytes} из {data['size']} байт)"
    )
    notes = []
    if limit_note:
        notes.append(limit_note)
    if body_result["truncated"]:
        notes.append(truncation_notice(body_result))
    if shown_end < total:
        notes.append(
            f"показаны строки {start}–{shown_end} из {total}; "
            f"продолжение — read_file offset={shown_end + 1}"
        )
    elif start > 1 and shown:
        notes.append(f"показаны строки {start}–{shown_end} из {total} (конец файла)")
    else:
        notes.append("(конец файла)")
    return "\n".join([header, *notes, ""] + visible_lines)
