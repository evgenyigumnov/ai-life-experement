"""Общие утилиты тестов: временное окружение, subprocess, папки агентов."""

import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@contextmanager
def env(**kwargs):
    """Временно установить переменные окружения (None — удалить переменную).

    Восстанавливает прежние значения даже при падении теста.
    """
    saved = {}
    try:
        for key, value in kwargs.items():
            saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_python(code: str, *, cwd=None, env_extra: dict | None = None,
               timeout: int = 120) -> subprocess.CompletedProcess:
    """Запустить python-сниппет в subprocess.

    `env_extra` накладывается поверх текущего окружения; значение None
    удаляет переменную. Позволяет тестировать sys.exit-ветки и изолированные
    импорты (свой cwd, свои переменные) без влияния на тестовый процесс.
    """
    env_vars = dict(os.environ)
    for key, value in (env_extra or {}).items():
        if value is None:
            env_vars.pop(key, None)
        else:
            env_vars[key] = str(value)
    return subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(cwd or PROJECT_ROOT),
        env=env_vars,
        timeout=timeout,
    )


def make_agent_dir(tmp_root, name: str = "bot",
                   prompt: str = "Ты — тестовый агент.") -> Path:
    """Создать папку агента с system-prompt.md во временной директории."""
    folder = Path(tmp_root) / name
    folder.mkdir(parents=True)
    (folder / "system-prompt.md").write_text(prompt, encoding="utf-8")
    return folder
