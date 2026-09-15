"""Общие помощники живых тестов LLM."""

import os
import unittest
from unittest import mock

import httpx2

from config_env import Config, load_config


class LiveUnavailable(Exception):
    """Живой сервер или обязательная инфраструктура недоступны."""


def _load_live_config() -> Config:
    try:
        return load_config()
    except SystemExit as exc:
        raise LiveUnavailable(f"нет валидного .env: {exc}") from exc


def _check_reachable(cfg: Config) -> None:
    """Проверить /models коротким запросом без вызова модели."""
    url = cfg.base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {cfg.api_key}"} if cfg.api_key else {}
    try:
        response = httpx2.get(url, headers=headers, timeout=5.0)
    except Exception as exc:
        raise LiveUnavailable(f"{url} недоступен: {exc!r}") from exc
    if response.status_code >= 500:
        raise LiveUnavailable(f"{url} отвечает {response.status_code} — сервер нездоров")


def _required() -> bool:
    return os.environ.get("AI_LIVE_REQUIRED") == "1"


def _skip_or_fail(exc: Exception):
    if _required():
        raise AssertionError(f"боевой LLM обязателен, но недоступен: {exc}") from exc
    raise unittest.SkipTest(str(exc))


def _fail_fast_sleep(seconds):
    raise LiveUnavailable(
        f"боевой сервер временно отвечает сбоями: пауза {seconds} сек "
        "после неуспешных попыток"
    )


def fail_fast_retries(module):
    """Патчер sleep для call_llm: временный сбой не уводит тест в вечный retry."""
    return mock.patch.object(module.time, "sleep", side_effect=_fail_fast_sleep)
