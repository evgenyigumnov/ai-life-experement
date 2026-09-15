"""Применение настроек сессии к предикатам жизненного цикла."""

import agent_sleep


def apply_session_config(cfg) -> None:
    """Установить длину сессии и порог предупреждения из Config."""
    agent_sleep.SESSION_ITERATIONS = cfg.session_iterations
    agent_sleep.SLEEP_WARN_REMAINING = cfg.sleep_warn_remaining
