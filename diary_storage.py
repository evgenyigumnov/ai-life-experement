"""Загрузка и атомарное сохранение diary.json."""

import json
import sys
from pathlib import Path

from storage import _atomic_write_text, _backup_corrupt
from time_utils import now_iso


def _validate_diary(data) -> dict:
    """Проверить минимальную структуру дневника."""
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError("ожидается объект с ключом 'entries' (список)")
    return data


def empty_diary(agent: str) -> dict:
    """Свежий пустой дневник."""
    timestamp = now_iso()
    return {
        "agent": agent,
        "created_at": timestamp,
        "updated_at": timestamp,
        "next_id": 1,
        "entries": [],
    }


def ensure_diary_file(path: Path, agent: str) -> bool:
    """Создать пустой diary.json, если файла ещё нет."""
    path = Path(path)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(path, json.dumps(empty_diary(agent), ensure_ascii=False, indent=2))
    return True


def load_diary(path: Path) -> dict:
    """Прочитать дневник; битый файл сохранить рядом и начать заново."""
    path = Path(path)
    if not path.exists():
        return empty_diary(path.parent.name)
    try:
        return _validate_diary(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError) as exc:
        backup = _backup_corrupt(path, exc)
        print(
            f"Предупреждение: {path.name} повреждён ({exc}); "
            + (f"битый файл сохранён как {backup.name}, " if backup else "")
            + "дневник начат заново",
            file=sys.stderr,
        )
        fresh = empty_diary(path.parent.name)
        save_diary(path, fresh)
        return fresh


def save_diary(path: Path, data: dict) -> None:
    """Атомарно сохранить дневник с новым updated_at."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = now_iso()
    _atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))
