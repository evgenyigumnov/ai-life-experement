"""Атомарное хранение переписки агента."""

import json
import sys
from pathlib import Path

from agent_lock import agent_lock
from time_utils import now_iso


def _atomic_write_text(*args, **kwargs):
    from storage import _atomic_write_text as write
    return write(*args, **kwargs)


def _backup_corrupt(*args, **kwargs):
    from storage import _backup_corrupt as backup
    return backup(*args, **kwargs)

SENDER_CREATOR = "creator"
SENDER_AGENT = "agent"


def _empty_messages(agent: str) -> dict:
    timestamp = now_iso()
    return {"agent": agent, "created_at": timestamp, "updated_at": timestamp,
            "messages": []}


def _save_messages_unlocked(path: Path, data: dict) -> None:
    data["updated_at"] = now_iso()
    _atomic_write_text(Path(path), json.dumps(data, ensure_ascii=False, indent=2))


def ensure_messages_file(path: Path, agent: str) -> bool:
    path = Path(path)
    with agent_lock(path):
        if path.exists():
            return False
        _atomic_write_text(path, json.dumps(_empty_messages(agent), ensure_ascii=False, indent=2))
        return True


def _load_messages_unlocked(path: Path) -> dict:
    path = Path(path)
    if not path.exists():
        return _empty_messages(path.parent.name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
            raise ValueError("ожидается объект с ключом 'messages' (список)")
        return data
    except (OSError, UnicodeError, ValueError) as exc:
        backup = _backup_corrupt(path, exc)
        print(
            f"Предупреждение: {path.name} повреждён ({exc}); "
            + (f"битый файл сохранён как {backup.name}, " if backup else "")
            + "переписка начата заново",
            file=sys.stderr,
        )
        fresh = _empty_messages(path.parent.name)
        _save_messages_unlocked(path, fresh)
        return fresh


def load_messages(path: Path) -> dict:
    with agent_lock(path):
        return _load_messages_unlocked(Path(path))


def append_message(path: Path, sender: str, text: str, payment_id: str | None = None) -> dict:
    if sender not in (SENDER_CREATOR, SENDER_AGENT):
        raise ValueError(f"неизвестный отправитель: {sender!r}")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("текст сообщения не может быть пустым")
    if payment_id is not None and (not isinstance(payment_id, str) or not payment_id.strip()):
        raise ValueError("payment_id должен быть непустой строкой")
    path = Path(path)
    with agent_lock(path):
        data = _load_messages_unlocked(path)
        message = {"timestamp": now_iso(), "from": sender, "text": text,
                   "read": sender == SENDER_AGENT}
        if payment_id is not None:
            message["payment_id"] = payment_id
        data.setdefault("messages", []).append(message)
        _save_messages_unlocked(path, data)
        return data


def is_message_read(message: dict) -> bool:
    return bool(message.get("read", True))


def unread_creator_positions(data: dict) -> list[int]:
    return [
        index for index, message in enumerate(data.get("messages") or [])
        if message.get("from") == SENDER_CREATOR and not is_message_read(message)
    ]


def mark_messages_read(path: Path, data: dict, indices) -> dict:
    path = Path(path)
    requested = list(indices)
    with agent_lock(path):
        current = _load_messages_unlocked(path)
        messages = current.setdefault("messages", [])
        changed = False
        for index in requested:
            if (isinstance(index, int) and not isinstance(index, bool)
                    and 0 <= index < len(messages)
                    and not is_message_read(messages[index])):
                messages[index]["read"] = True
                changed = True
        if changed:
            _save_messages_unlocked(path, current)
            supplied = data.get("messages") if isinstance(data, dict) else None
            for index in requested:
                if (isinstance(supplied, list) and isinstance(index, int)
                        and 0 <= index < len(supplied)):
                    supplied[index]["read"] = True
        return current


def last_messages(path: Path, limit: int = 10) -> list[dict]:
    messages = load_messages(Path(path)).get("messages") or []
    return [] if limit <= 0 else messages[-limit:]
