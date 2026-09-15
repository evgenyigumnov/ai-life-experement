"""Баннер запуска и чтение счётчиков текущей сессии."""

from agent_console import _Colors, _colorize
import agent_sleep
from agent_text import _plural_iterations
from agent_paths import AgentPaths
from config_env import Config
from storage import load_mind_loop

BANNER_WIDTH = 62


def _iterations_done(paths: AgentPaths) -> int:
    try:
        return len(load_mind_loop(paths.mind_loop).get("iterations") or [])
    except Exception:
        return 0


def _session_number(paths: AgentPaths) -> int:
    try:
        session = load_mind_loop(paths.mind_loop).get("session")
        return session if isinstance(session, int) and session > 0 else 1
    except Exception:
        return 1


def _print_banner(
    name: str,
    cfg: Config,
    paths: AgentPaths,
    iterations: int,
    session: int = 1,
    session_iterations: int | None = None,
) -> None:
    """Напечатать баннер с текущим обратным отсчётом до сна."""
    total = (
        agent_sleep.SESSION_ITERATIONS
        if session_iterations is None
        else session_iterations
    )
    inner = BANNER_WIDTH - 4
    side = _colorize("║", _Colors.CYAN)
    remaining = max(0, total - iterations)

    def border(left: str, right: str) -> str:
        return _colorize(f"{left}{'═' * (BANNER_WIDTH - 2)}{right}", _Colors.CYAN)

    def row(text: str, *, bold: bool = False, center: bool = False) -> str:
        if center and len(text) < inner:
            text = " " * ((inner - len(text)) // 2) + text
        if bold:
            text = _colorize(text, _Colors.BOLD)
        return f"{side} {text.ljust(inner)} {side}"

    rows = [
        row(f"Модель:   {cfg.model}"),
        row(f"Base URL: {cfg.base_url}"),
        row(f"Папка:    {paths.folder}"),
        row(f"Сессия:   {session}"),
        row(f"История:  {iterations} итераций ({paths.mind_loop.name})"),
        row(f"До сна:   осталось {_plural_iterations(remaining)} (сессия из {total})"),
    ]
    if cfg.loop_pause is not None:
        rows.append(row(
            f"Пауза:    фиксированная {cfg.loop_pause:g} сек (--loop-pause), "
            "расписание отключено"
        ))
    print(
        border("╔", "╗"),
        row(f"AI Life — агент «{name}»", bold=True, center=True),
        border("╠", "╣"),
        *rows,
        border("╠", "╣"),
        row("Ctrl+C — аккуратный останов"),
        border("╚", "╝"),
        "",
        sep="\n",
        flush=True,
    )
