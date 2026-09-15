"""Служебные мелочи цикла жизни: SIGTERM→Ctrl+C."""

import signal


def _install_sigterm_handler() -> None:
    """SIGTERM обрабатывается как Ctrl+C — аккуратный выход."""

    def _handler(signum, frame):
        raise KeyboardInterrupt

    try:
        signal.signal(signal.SIGTERM, _handler)
    except (ValueError, OSError):
        # не главный поток или платформа без SIGTERM — обработчик не ставим
        pass
