"""Главный бесконечный цикл жизни агента."""

import time

from agent_console import (
    _format_pause_interrupted_log, _format_pause_log, _format_stop_message, _log,
)
from agent_iteration import run_iteration
from agent_paid_pause import format_paid_cycle_log, use_paid_cycle
from agent_pause import (
    _backoff_delay, _creator_messages_count, _pause_seconds, _wait_pause,
)
from agent_runtime import _install_sigterm_handler
from agent_sleep import USER_MESSAGE
from agent_history import _serialize_message
from agent_messages import build_messages
from agent_usage import (
    _extract_completion_tokens, _extract_prompt_tokens, _extract_reasoning,
    _extract_reasoning_tokens,
)
from config_env import Config
from agent_paths import AgentPaths
from llm import call_llm, make_client
from storage import append_iteration, archive_mind_loop, load_mind_loop
from tool_registry import build_tools_schema, execute_tool


def _run_iteration(paths: AgentPaths, cfg: Config, client,
                   console_state: dict | None = None) -> None:
    """Одна итерация; зависимости оставлены на модуле для удобных патчей."""
    return run_iteration(
        paths, cfg, client, console_state, log=_log, llm_call=call_llm,
        tool_executor=execute_tool, tools_schema=build_tools_schema,
        message_builder=build_messages, loader=load_mind_loop,
        appender=append_iteration, archiver=archive_mind_loop,
        serializer=_serialize_message, extract_prompt=_extract_prompt_tokens,
        extract_completion=_extract_completion_tokens,
        extract_reasoning_tokens=_extract_reasoning_tokens,
        extract_reasoning=_extract_reasoning,
    )


def _record_failed_iteration(paths: AgentPaths, exc: Exception) -> None:
    """Записать неожиданную ошибку как итерацию и продолжить жизнь."""
    note = f"{type(exc).__name__}: {exc}"
    from agent_console_blocks import _format_failed_iteration
    _log(_format_failed_iteration(exc))
    try:
        data = load_mind_loop(paths.mind_loop)
        append_iteration(paths.mind_loop, data, {"user": USER_MESSAGE, "error": note})
    except Exception as record_exc:
        _log(f"[сбой] не удалось записать итерацию-ошибку: {record_exc!r}")


def run_loop(paths: AgentPaths, cfg: Config) -> None:
    """Запустить адаптивный или фиксированный цикл до остановки."""
    _install_sigterm_handler()
    client = make_client(cfg)
    console_state: dict = {}
    backoff_step = 0
    last_creator_count = _creator_messages_count(paths)
    try:
        while True:
            started = time.perf_counter()
            try:
                _run_iteration(paths, cfg, client, console_state)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                _record_failed_iteration(paths, exc)
            iteration_duration = time.perf_counter() - started
            creator_count = _creator_messages_count(paths)
            creator_wrote = creator_count != last_creator_count
            last_creator_count = creator_count
            if cfg.loop_pause is None:
                backoff_step = 1 if creator_wrote else backoff_step + 1
                delay = max(cfg.loop_delay, _backoff_delay(backoff_step))
            else:
                backoff_step, delay = 0, cfg.loop_pause
            paid_remaining = None
            if cfg.loop_pause is None:
                paid_remaining = use_paid_cycle(paths)
                if paid_remaining is not None:
                    delay = 0.0
            sleep_for = _pause_seconds(delay, iteration_duration)
            if paid_remaining is not None:
                _log(format_paid_cycle_log(paid_remaining))
            _log(_format_pause_log(
                backoff_step, sleep_for, creator_wrote, delay,
                iteration_duration, fixed_pause=cfg.loop_pause is not None,
            ))
            if paid_remaining == 0:
                # После последнего оплаченного цикла начинаем адаптивное
                # расписание заново, а не прыгаем на старую ступень.
                backoff_step = 0
            if _wait_pause(sleep_for, paths, last_creator_count):
                last_creator_count = _creator_messages_count(paths)
                backoff_step = 0
                _log(_format_pause_interrupted_log())
    except KeyboardInterrupt:
        try:
            total = str(len(load_mind_loop(paths.mind_loop).get("iterations") or []))
        except Exception:
            total = "?"
        _log(_format_stop_message(total, str(paths.mind_loop)))
