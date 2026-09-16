"""Форматирование и ограничение вывода run_bash."""

from tools_truncate import truncation_notice, truncate_tail

MAX_OUTPUT_CHARS = 10_000


def truncate(text: str) -> str:
    """Старый helper для совместимости с read_file и внешними вызовами."""
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return f"{text[:MAX_OUTPUT_CHARS]}\n...output truncated ({len(text) - MAX_OUTPUT_CHARS} chars)..."


def format_bash_result(command: str, returncode, stdout: str, stderr: str) -> str:
    body = "\n".join([stdout or "(пусто)", "--- stderr ---", stderr or "(пусто)"])
    result = truncate_tail(body)
    text = "\n".join([
        f"$ {command}", f"returncode: {returncode}",
        "--- stdout ---", result["content"],
    ])
    if result["truncated"]:
        text += f"\n{truncation_notice(result)}"
    return text
