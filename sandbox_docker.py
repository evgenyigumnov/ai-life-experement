"""Низкоуровневая работа с Docker-песочницей агента.

Песочница — docker-контейнер, одноимённый агенту, на едином образе
(ai-life-sandbox). Здесь: санитизация имён под правила Docker, проверка
доступности бинарника docker, сборка образа при необходимости и гарантия
«контейнер существует и запущен» (перезапуск после ребута хоста).
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

DOCKER_BIN = os.environ.get("DOCKER_BIN", "docker")
DEFAULT_DOCKER_IMAGE = "ai-life-sandbox:latest"
DOCKER_IMAGE = os.environ.get("AI_LIFE_DOCKER_IMAGE", DEFAULT_DOCKER_IMAGE)
DOCKERFILE_PATH = Path(
    os.environ.get("AI_LIFE_DOCKERFILE", Path(__file__).resolve().parent / "Dockerfile")
)

# Транслитерация кириллицы для имён контейнеров.
TRANSLIT_MAP = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
}


def sanitize_container_name(name: str) -> str:
    """Привести имя агента к допустимому имени контейнера [a-zA-Z0-9][a-zA-Z0-9_.-]*.

    Обычные латинские имена ('oleg', 'bot', 'agent-1') не меняет; кириллицу
    транслитерирует; недопустимые символы заменяет на '_'.
    """
    if not name:
        return "default"
    if re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$", name):
        return name

    lowered = name.lower()
    res = "".join(TRANSLIT_MAP.get(ch, ch) for ch in lowered)
    res = re.sub(r"[^a-zA-Z0-9_.-]", "_", res)
    res = res.strip("._-")
    if not res:
        res = "agent"
    if not re.match(r"^[a-zA-Z0-9]", res):
        res = "a_" + res
    return res


def check_docker_available() -> str | None:
    """Проверить доступность бинарника docker; None — доступен."""
    if shutil.which(DOCKER_BIN) is None:
        return (
            f"Error: песочница docker недоступна: "
            f"не найден бинарь docker ({DOCKER_BIN!r})"
        )
    return None


def ensure_docker_image(image_name: str = DOCKER_IMAGE) -> None:
    """Проверить наличие docker-имиджа; если его нет — создать/собрать."""
    err = check_docker_available()
    if err is not None:
        raise RuntimeError(err)

    proc = subprocess.run(
        [DOCKER_BIN, "image", "inspect", image_name],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return

    if DOCKERFILE_PATH.is_file():
        build_proc = subprocess.run(
            [
                DOCKER_BIN, "build", "-t", image_name,
                "-f", str(DOCKERFILE_PATH), str(DOCKERFILE_PATH.parent),
            ],
            capture_output=True,
            text=True,
        )
    else:
        dockerfile_content = (
            "FROM alpine:latest\n"
            "RUN apk update && apk add bash busybox python3 py3-pip curl\n"
            "WORKDIR /root\n"
            'CMD ["tail", "-f", "/dev/null"]\n'
        )
        build_proc = subprocess.run(
            [DOCKER_BIN, "build", "-t", image_name, "-"],
            input=dockerfile_content,
            capture_output=True,
            text=True,
        )

    if build_proc.returncode != 0:
        raise RuntimeError(
            f"Не удалось собрать docker-образ {image_name}: "
            f"{build_proc.stderr.strip()}"
        )


def ensure_docker_container(name: str, image_name: str = DOCKER_IMAGE) -> str:
    """Создать и запустить контейнер агента (если его нет), вернуть имя.

    Имя санитизируется; контейнер перезапускается после ребута хоста
    (--restart always), использует единый образ (собирается при
    необходимости) и держится живым через `--init tail -f /dev/null`.
    """
    err = check_docker_available()
    if err is not None:
        raise RuntimeError(err)

    ensure_docker_image(image_name)
    container_name = sanitize_container_name(name)

    inspect_proc = subprocess.run(
        [DOCKER_BIN, "container", "inspect", container_name],
        capture_output=True,
        text=True,
    )
    if inspect_proc.returncode != 0:
        run_proc = subprocess.run(
            [
                DOCKER_BIN, "run", "-d", "--name", container_name,
                "--restart", "always", "--init", image_name,
                "tail", "-f", "/dev/null",
            ],
            capture_output=True,
            text=True,
        )
        if run_proc.returncode != 0:
            raise RuntimeError(
                f"Не удалось создать контейнер {container_name}: "
                f"{run_proc.stderr.strip()}"
            )
        return container_name

    # Контейнер существует — убедиться, что он запущен.
    try:
        data = json.loads(inspect_proc.stdout)
        is_running = bool(data[0].get("State", {}).get("Running", False))
    except Exception:
        is_running = False

    if not is_running:
        start_proc = subprocess.run(
            [DOCKER_BIN, "start", container_name],
            capture_output=True,
            text=True,
        )
        if start_proc.returncode != 0:
            raise RuntimeError(
                f"Не удалось запустить контейнер {container_name}: "
                f"{start_proc.stderr.strip()}"
            )

    return container_name
