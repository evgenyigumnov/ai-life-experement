"""Метаданные свежести индексов дневника."""

import hashlib
import json
from pathlib import Path

from storage import _atomic_write_text


def meta_path(diary_path) -> Path:
    """Служебный файл свежести индексов рядом с diary.json."""
    return Path(diary_path).with_suffix(".index-meta.json")


def diary_fingerprint(diary_path) -> str:
    """Отпечаток содержимого diary.json; пустая строка, если файла нет."""
    path = Path(diary_path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def entry_fingerprint(entry: dict) -> str:
    payload = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def entry_fingerprints(diary_path) -> dict[str, str]:
    data = json.loads(Path(diary_path).read_text(encoding="utf-8"))
    return {
        str(entry.get("id")): entry_fingerprint(entry)
        for entry in data.get("entries") or []
    }


def incremental_safe(meta, prefix, current, changed_id) -> bool:
    previous = meta.get(f"{prefix}_entries_fp")
    if not isinstance(previous, dict) or not isinstance(current, dict):
        return False
    key = str(changed_id)
    return (
        {k: v for k, v in previous.items() if k != key}
        == {k: v for k, v in current.items() if k != key}
    )


def read_meta(diary_path) -> dict:
    try:
        data = json.loads(meta_path(diary_path).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_meta(diary_path, meta: dict) -> None:
    try:
        _atomic_write_text(
            meta_path(diary_path), json.dumps(meta, ensure_ascii=False, indent=2)
        )
    except OSError:
        pass


def live_count(diary_path) -> int:
    """Число записей в diary.json; 0, если прочитать нельзя."""
    try:
        data = json.loads(Path(diary_path).read_text(encoding="utf-8"))
        return len(data.get("entries") or [])
    except (OSError, ValueError):
        return 0


def mark_fresh(meta, prefix, fingerprint, fingerprints) -> None:
    meta[f"{prefix}_fp"] = fingerprint
    meta[f"{prefix}_entries_fp"] = fingerprints
