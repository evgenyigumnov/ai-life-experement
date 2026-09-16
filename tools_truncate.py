"""Общие лимиты вывода tools."""

DEFAULT_MAX_LINES = 2_000
DEFAULT_MAX_BYTES = 50 * 1024
MAX_LINES = DEFAULT_MAX_LINES
MAX_BYTES = DEFAULT_MAX_BYTES
GREP_MAX_LINE_LENGTH = 500


def _lines(text: str) -> list[str]:
    if not text:
        return []
    result = text.split("\n")
    if text.endswith("\n"):
        result.pop()
    return result


def _bytes(text: str) -> int:
    return len(text.encode("utf-8", errors="replace"))


def _result(content: str, *, truncated: bool, by: str | None,
            total_lines: int, total_bytes: int,
            max_lines: int, max_bytes: int) -> dict:
    return {
        "content": content,
        "truncated": truncated,
        "truncatedBy": by,
        "totalLines": total_lines,
        "totalBytes": total_bytes,
        "outputLines": len(_lines(content)),
        "outputBytes": _bytes(content),
        "maxLines": max_lines,
        "maxBytes": max_bytes,
    }


def _limits(max_lines: int | None, max_bytes: int | None) -> tuple[int, int]:
    lines = DEFAULT_MAX_LINES if max_lines is None else max(0, int(max_lines))
    size = DEFAULT_MAX_BYTES if max_bytes is None else max(0, int(max_bytes))
    return lines, size


def truncate_head(text: str, max_lines: int | None = None,
                  max_bytes: int | None = None) -> dict:
    max_lines, max_bytes = _limits(max_lines, max_bytes)
    lines = _lines(text)
    total_lines, total_bytes = len(lines), _bytes(text)
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return _result(text, truncated=False, by=None, total_lines=total_lines,
                       total_bytes=total_bytes, max_lines=max_lines,
                       max_bytes=max_bytes)
    if not lines or max_lines == 0:
        return _result("", truncated=True, by="lines", total_lines=total_lines,
                       total_bytes=total_bytes, max_lines=max_lines,
                       max_bytes=max_bytes)
    if _bytes(lines[0]) > max_bytes:
        return _result("", truncated=True, by="bytes", total_lines=total_lines,
                       total_bytes=total_bytes, max_lines=max_lines,
                       max_bytes=max_bytes)

    chosen: list[str] = []
    used = 0
    by = "lines"
    for index, line in enumerate(lines[:max_lines]):
        cost = _bytes(line) + (1 if index else 0)
        if used + cost > max_bytes:
            by = "bytes"
            break
        chosen.append(line)
        used += cost
    if len(chosen) == max_lines and len(lines) > max_lines and used <= max_bytes:
        by = "lines"
    elif len(chosen) == len(lines) and total_bytes > max_bytes:
        by = "bytes"
    return _result("\n".join(chosen), truncated=True, by=by,
                   total_lines=total_lines, total_bytes=total_bytes,
                   max_lines=max_lines, max_bytes=max_bytes)


def truncate_tail(text: str, max_lines: int | None = None,
                  max_bytes: int | None = None) -> dict:
    max_lines, max_bytes = _limits(max_lines, max_bytes)
    lines = _lines(text)
    total_lines, total_bytes = len(lines), _bytes(text)
    if total_lines <= max_lines and total_bytes <= max_bytes:
        return _result(text, truncated=False, by=None, total_lines=total_lines,
                       total_bytes=total_bytes, max_lines=max_lines,
                       max_bytes=max_bytes)
    if not lines or max_lines == 0:
        return _result("", truncated=True, by="lines", total_lines=total_lines,
                       total_bytes=total_bytes, max_lines=max_lines,
                       max_bytes=max_bytes)

    chosen: list[str] = []
    used = 0
    by = "lines"
    for line in reversed(lines):
        if len(chosen) >= max_lines:
            by = "lines"
            break
        cost = _bytes(line) + (1 if chosen else 0)
        if used + cost > max_bytes:
            by = "bytes"
            break
        chosen.insert(0, line)
        used += cost
    if len(chosen) == max_lines and len(lines) > max_lines and used <= max_bytes:
        by = "lines"
    elif len(chosen) == len(lines) and total_bytes > max_bytes:
        by = "bytes"
    return _result("\n".join(chosen), truncated=True, by=by,
                   total_lines=total_lines, total_bytes=total_bytes,
                   max_lines=max_lines, max_bytes=max_bytes)


def truncate(text: str, *, tail: bool = False, max_lines: int | None = None,
             max_bytes: int | None = None) -> dict:
    fn = truncate_tail if tail else truncate_head
    return fn(text, max_lines=max_lines, max_bytes=max_bytes)


def truncate_line(line: str, max_chars: int = GREP_MAX_LINE_LENGTH) -> str:
    marker = "... [truncated]"
    if len(line) <= max_chars:
        return line
    return line[:max_chars - len(marker)] + marker


def truncation_notice(result: dict) -> str:
    return (
        "...output truncated "
        f"(truncatedBy={result['truncatedBy']}, "
        f"totalLines={result['totalLines']}, totalBytes={result['totalBytes']})..."
    )
