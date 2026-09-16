"""Эмбеддинги DeepInfra и загрузка расширения sqlite-vec."""

import hashlib
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from diary_validation import DiaryError

_API_URL = "https://api.deepinfra.com/v1/openai/embeddings"
DEFAULT_EMBED_BASE_URL = "https://api.deepinfra.com/v1/openai"
DEFAULT_MODEL = "Qwen/Qwen3-Embedding-0.6B"
DEFAULT_DIM = 1024


class DiarySearchUnavailable(DiaryError):
    """Векторный поиск недоступен: нет токена, расширения или сети."""


def _config() -> tuple[str | None, str, int]:
    """Считать конфигурацию эмбеддера из окружения."""
    token = os.environ.get("DIARY_EMBED_TOKEN")
    model = os.environ.get("DIARY_EMBED_MODEL", DEFAULT_MODEL)
    dim = int(os.environ.get("DIARY_EMBED_DIM", str(DEFAULT_DIM)))
    return token, model, dim


def _embedding_url() -> str:
    base = os.environ.get("DIARY_EMBED_BASE_URL", DEFAULT_EMBED_BASE_URL).strip().rstrip("/")
    return base if base.endswith("/embeddings") else f"{base}/embeddings"


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Превратить тексты в векторы; fake-режим — для офлайн-тестов."""
    if os.environ.get("DIARY_EMBED_FAKE") == "1":
        return [_fake_vector(text, _config()[2]) for text in texts]
    token, model, _ = _config()
    if not token:
        raise DiarySearchUnavailable(
            "нет DIARY_EMBED_TOKEN: живой поиск по смыслу требует токен DeepInfra"
        )
    body = json.dumps(
        {"input": texts, "model": model, "encoding_format": "float"}
    ).encode("utf-8")
    request = urllib.request.Request(
        _embedding_url(),
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DiarySearchUnavailable(f"DeepInfra недоступен: {exc}") from exc
    data = payload.get("data") or []
    if len(data) != len(texts):
        raise DiarySearchUnavailable(
            f"DeepInfra вернул {len(data)} векторов вместо {len(texts)}"
        )
    return [item["embedding"] for item in data]


def _fake_vector(text: str, dim: int) -> list[float]:
    """Детерминированный вектор из хэша текста (только для тестов)."""
    seed = hashlib.sha256(text.encode("utf-8")).digest()
    return [((seed[i % len(seed)] - 128) / 128) for i in range(dim)]


def _extension_path(diary_path) -> str:
    """Получить путь расширения, не создавая vec-базу при его отсутствии."""
    configured = os.environ.get("DIARY_VEC_SO")
    candidates = [configured] if configured else [
        str(Path(diary_path).parent / "vec0.so"),
        str(Path(__file__).with_name("vec0.so")),
    ]
    for path in candidates:
        if not path:
            continue
        if Path(path).exists():
            return path[:-3] if path.endswith(".so") else path
        if path.endswith(".so") and Path(path[:-3]).exists():
            return path[:-3]
        if not path.endswith(".so") and Path(path + ".so").exists():
            return path
    raise DiarySearchUnavailable(
        "sqlite-vec не найден: положите релизный vec0.so рядом с diary.json"
        " или укажите DIARY_VEC_SO"
    )


def _load_vec_extension(db, path: str) -> None:
    """Загрузить расширение sqlite-vec в соединение."""
    db.enable_load_extension(True)
    db.load_extension(path)
    db.enable_load_extension(False)
