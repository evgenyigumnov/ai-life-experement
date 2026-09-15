"""Удобный тестовый namespace для функций, разложенных по модулям."""

from types import SimpleNamespace

import agent_console
import agent_console_blocks
import agent_history
import agent_loop
import agent_messages
import agent_paid_pause
import agent_pause
import agent_sleep
import agent_unread
import agent_usage


# Имена остаются сгруппированными только для компактности тестовых сценариев;
# production-модуля agent.py больше нет.
agent = SimpleNamespace(
    run_loop=agent_loop.run_loop,
    _run_iteration=agent_loop._run_iteration,
    _record_failed_iteration=agent_loop._record_failed_iteration,
    build_messages=agent_messages.build_messages,
    _normalize_tool_call=agent_history._normalize_tool_call,
    _normalize_assistant_message=agent_history._normalize_assistant_message,
    _iteration_tool_calls=agent_history._iteration_tool_calls,
    _tool_result_messages=agent_history._tool_result_messages,
    _iteration_messages=agent_history._iteration_messages,
    _serialize_message=agent_history._serialize_message,
    IDLE_BACKOFF_SCHEDULE=agent_pause.IDLE_BACKOFF_SCHEDULE,
    PAUSE_POLL_INTERVAL=agent_pause.PAUSE_POLL_INTERVAL,
    _creator_messages=agent_pause._creator_messages,
    _creator_messages_count=agent_pause._creator_messages_count,
    _backoff_delay=agent_pause._backoff_delay,
    _pause_seconds=agent_pause._pause_seconds,
    _wait_pause=agent_pause._wait_pause,
    use_paid_cycle=agent_paid_pause.use_paid_cycle,
    _format_paid_cycle_log=agent_paid_pause.format_paid_cycle_log,
    SESSION_ITERATIONS=agent_sleep.SESSION_ITERATIONS,
    SLEEP_WARN_REMAINING=agent_sleep.SLEEP_WARN_REMAINING,
    USER_MESSAGE=agent_sleep.USER_MESSAGE,
    LAST_ITERATION_MESSAGE=agent_sleep.LAST_ITERATION_MESSAGE,
    _just_woke_up=agent_sleep._just_woke_up,
    _memory_stale=agent_sleep._memory_stale,
    _tick_user_message=agent_sleep._tick_user_message,
    _sleep_warning_message=agent_sleep._sleep_warning_message,
    _wake_up_message=agent_sleep._wake_up_message,
    iterations_remaining=agent_sleep.iterations_remaining,
    is_session_end=agent_sleep.is_session_end,
    should_warn=agent_sleep.should_warn,
    _unread_creator_count=agent_unread._unread_creator_count,
    _creator_messages_status_note=agent_unread._creator_messages_status_note,
    _extract_usage=agent_usage._extract_usage,
    _extract_prompt_tokens=agent_usage._extract_prompt_tokens,
    _extract_completion_tokens=agent_usage._extract_completion_tokens,
    _extract_reasoning_tokens=agent_usage._extract_reasoning_tokens,
    _extract_reasoning=agent_usage._extract_reasoning,
    _Colors=agent_console._Colors,
    USE_COLOR=agent_console.USE_COLOR,
    _supports_color=agent_console._supports_color,
    _colorize=agent_console._colorize,
    _log=agent_console._log,
    _format_iteration_header=agent_console._format_iteration_header,
    _format_iteration_command=agent_console._format_iteration_command,
    _format_stop_message=agent_console._format_stop_message,
    _format_sleep_message=agent_console._format_sleep_message,
    _format_wake_up_log=agent_console._format_wake_up_log,
    _format_duration=agent_console._format_duration,
    _format_pause_log=agent_console._format_pause_log,
    _format_pause_interrupted_log=agent_console._format_pause_interrupted_log,
    _format_unread_log=agent_console._format_unread_log,
    MAX_REASONING_LOG_CHARS=agent_console_blocks.MAX_REASONING_LOG_CHARS,
    _format_system_prompt_block=agent_console_blocks._format_system_prompt_block,
    _format_system_prompt_unchanged=agent_console_blocks._format_system_prompt_unchanged,
    _format_llm_stats=agent_console_blocks._format_llm_stats,
    _format_llm_block=agent_console_blocks._format_llm_block,
    _format_reasoning_block=agent_console_blocks._format_reasoning_block,
    _format_tool_args=agent_console_blocks._format_tool_args,
    _format_tool_call_block=agent_console_blocks._format_tool_call_block,
    _format_tool_result_block=agent_console_blocks._format_tool_result_block,
    _format_failed_iteration=agent_console_blocks._format_failed_iteration,
)
