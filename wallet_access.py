"""Приведение AgentPaths и путей к API хранения кошелька."""

from pathlib import Path

from wallet_storage import (
    ensure_wallet_file as _ensure,
    load_or_create_wallet as _load_or_create,
    load_wallet as _load,
    save_wallet as _save,
)


def path(source) -> Path:
    return Path(getattr(source, "wallet", source))


def agent_name(source, explicit=None) -> str | None:
    if explicit:
        return explicit
    if hasattr(source, "folder"):
        return getattr(source, "name", "") or None
    return None


def ensure_wallet_file(source, agent=None) -> bool:
    return _ensure(path(source), agent_name(source, agent))


def load_wallet(source, agent=None) -> dict:
    return _load(path(source), agent_name(source, agent))


def load_or_create_wallet(source, agent=None) -> dict:
    return _load_or_create(path(source), agent_name(source, agent))


def save_wallet(source, data: dict, agent=None) -> None:
    _save(path(source), data, agent_name(source, agent))
