"""Точка входа для запуска жизни агента и режима reply."""

import sys

from agent_loop import run_loop
from agent_paths import find_agent_folder, list_agents
from config_env import Config, load_config
import main_banner
from main_banner import _iterations_done, _session_number
from main_help import print_help
from main_reply import _reply_mode
from main_money import run_money_command, is_money_command
from session_env import apply_session_config
from sandbox_docker import ensure_docker_container

REPLY_ARG = "reply"
HELP_ARGS = frozenset({"--help", "-h"})
LOOP_PAUSE_ARG = "--loop-pause"
USAGE_LINE = "Использование: python main.py [имя_агента] [reply] [--loop-pause=N]"


def _extract_loop_pause(argv: list[str]) -> tuple[float | None, list[str]]:
    """Выделить --loop-pause из аргументов и проверить его значение."""
    rest: list[str] = []
    value: str | None = None
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == LOOP_PAUSE_ARG:
            if index + 1 >= len(argv):
                print(
                    f"Ошибка: {LOOP_PAUSE_ARG} требует значение — например, "
                    f"{LOOP_PAUSE_ARG}=30\n{USAGE_LINE}",
                    file=sys.stderr,
                )
                raise SystemExit(1)
            value = argv[index + 1]
            index += 2
            continue
        if arg.startswith(LOOP_PAUSE_ARG + "="):
            value = arg[len(LOOP_PAUSE_ARG) + 1:]
            index += 1
            continue
        rest.append(arg)
        index += 1
    if value is None:
        return None, rest
    try:
        pause = float(value)
    except ValueError:
        pause = None
    if pause is None or not pause >= 0 or pause == float("inf"):
        print(
            f"Ошибка: {LOOP_PAUSE_ARG} должна быть числом секунд >= 0, "
            "например --loop-pause=30",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return pause, rest


def _pick_agent_name(cfg: Config, argv: list[str]) -> str:
    """Выбрать явно переданное имя или единственного найденного агента."""
    if argv:
        return argv[0]
    agents = list_agents(cfg)
    if len(agents) == 1:
        name = agents[0]
        print(f"Имя агента не указано — запускаю единственного найденного: «{name}»", flush=True)
        return name
    if agents:
        listing = "\n".join(f"  python main.py {name}" for name in agents)
        print(
            f"Имя агента не указано, а найдено несколько ({len(agents)}) — "
            f"выберите одного:\n{listing}",
            file=sys.stderr,
        )
    else:
        print(
            "Агенты не найдены: нет папок с system-prompt.md "
            "(см. AGENTS_ROOT в .env или текущую директорию). Укажите имя — "
            "например, `python main.py oleg` — и новый агент будет создан "
            "из шаблона автоматически.",
            file=sys.stderr,
        )
    print(USAGE_LINE, file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    argv = sys.argv[1:]
    if any(argument in HELP_ARGS for argument in argv):
        print_help()
        return
    if is_money_command(argv):
        run_money_command(argv)
        return
    loop_pause, argv = _extract_loop_pause(argv)
    if argv and argv[0] == REPLY_ARG:
        print("Укажите имя агента: python main.py <имя_агента> reply", file=sys.stderr)
        raise SystemExit(1)
    if len(argv) == 2 and argv[1] == REPLY_ARG:
        _reply_mode(argv[0])
        return
    if len(argv) >= 2:
        print(USAGE_LINE, file=sys.stderr)
        raise SystemExit(1)

    cfg = load_config()
    apply_session_config(cfg)
    if loop_pause is not None:
        cfg.loop_pause = loop_pause
    name = _pick_agent_name(cfg, argv)
    paths = find_agent_folder(name, cfg)
    if cfg.enable_bash_tool:
        try:
            ensure_docker_container(name)
        except Exception as exc:
            print(f"Ошибка инициализации Docker-контейнера: {exc}", file=sys.stderr)
            raise SystemExit(1)
    main_banner._print_banner(
        name, cfg, paths, _iterations_done(paths), _session_number(paths)
    )
    run_loop(paths, cfg)


if __name__ == "__main__":
    main()
