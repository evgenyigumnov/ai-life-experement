"""Загрузка переменных окружения и валидируемая конфигурация."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from errors import die
from prompts_template import DEFAULT_SESSION_ITERATIONS, DEFAULT_SLEEP_WARN_REMAINING

REASONING_EFFORTS = frozenset(
    {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
)
BOOL_TRUE = frozenset({"1", "true", "yes", "on"})
BOOL_FALSE = frozenset({"0", "false", "no", "off", ""})


def parse_bool_env(raw: str | None) -> bool | None:
    """Преобразовать булево значение окружения; неизвестное вернуть как None."""
    if raw is None:
        return None
    value = raw.strip().lower()
    if value in BOOL_TRUE:
        return True
    if value in BOOL_FALSE:
        return False
    return None


@dataclass
class Config:
    """Настройки LLM, цикла и окружения агента."""

    base_url: str
    model: str
    api_key: str
    agents_root: str | None
    loop_delay: float = 1.0
    loop_pause: float | None = None
    temperature: float = 0.7
    reasoning_effort: str | None = None
    enable_bash_tool: bool = False
    session_iterations: int = DEFAULT_SESSION_ITERATIONS
    sleep_warn_remaining: int = DEFAULT_SLEEP_WARN_REMAINING


def _config_error(message: str) -> None:
    die(message, "Ошибка конфигурации")


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        _config_error(f"{name} должна быть целым числом")
        raise AssertionError("die завершает процесс")


def load_config() -> Config:
    """Прочитать .env и окружение, проверив диапазоны параметров."""
    load_dotenv()
    base_url = os.environ.get("OPENAI_BASE_URL", "").strip()
    if not base_url:
        _config_error("не задана переменная OPENAI_BASE_URL в .env")
    model = os.environ.get("OPENAI_MODEL", "").strip()
    if not model:
        _config_error("не задана переменная OPENAI_MODEL в .env")

    loop_delay_raw = os.environ.get("LOOP_DELAY", "").strip()
    try:
        loop_delay = float(loop_delay_raw) if loop_delay_raw else 1.0
    except ValueError:
        _config_error("LOOP_DELAY должна быть числом секунд, например 1.5")
    temperature_raw = os.environ.get("TEMPERATURE", "").strip()
    try:
        temperature = float(temperature_raw) if temperature_raw else 0.7
    except ValueError:
        _config_error("TEMPERATURE должна быть числом от 0.0 до 2.0, например 0.7")
    if not 0.0 <= temperature <= 2.0:
        _config_error("TEMPERATURE должна быть числом от 0.0 до 2.0, например 0.7")

    reasoning_effort = os.environ.get("REASONING_EFFORT", "").strip().lower() or None
    if reasoning_effort is not None and reasoning_effort not in REASONING_EFFORTS:
        _config_error(
            "REASONING_EFFORT должна быть none, minimal, low, medium, high, "
            "xhigh или max"
        )
    enable_bash = parse_bool_env(os.environ.get("ENABLE_BASH_TOOL", ""))
    if enable_bash is None:
        _config_error("ENABLE_BASH_TOOL должна быть 1/true или 0/false")

    session_iterations = _int_env("SESSION_ITERATIONS", DEFAULT_SESSION_ITERATIONS)
    if not 1 <= session_iterations <= 10_000:
        _config_error("SESSION_ITERATIONS должна быть в диапазоне 1..10000")
    sleep_warn_remaining = _int_env(
        "SLEEP_WARN_REMAINING", DEFAULT_SLEEP_WARN_REMAINING
    )
    if not 0 <= sleep_warn_remaining < session_iterations:
        _config_error(
            "SLEEP_WARN_REMAINING должна быть в диапазоне 0..SESSION_ITERATIONS-1"
        )

    return Config(
        base_url=base_url,
        model=model,
        api_key=os.environ.get("OPENAI_API_KEY", "").strip() or "dummy",
        agents_root=os.environ.get("AGENTS_ROOT", "").strip() or None,
        loop_delay=loop_delay,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        enable_bash_tool=enable_bash,
        session_iterations=session_iterations,
        sleep_warn_remaining=sleep_warn_remaining,
    )
