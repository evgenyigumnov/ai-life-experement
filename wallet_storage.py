"""Версионированное атомарное хранение wallet.json."""

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from agent_lock import agent_lock
from time_utils import now_iso
from wallet_validation import (
    MAX_UNITS, SPEND_TYPES, DEFAULT_SPEND_TYPE,
    WalletCorruptError, WalletCorruptionError, WalletError, WalletValidationError,
    validate_wallet,
)

SCHEMA_VERSION = 1


def empty_wallet(agent: str) -> dict:
    """Создать пустую структуру кошелька версии 1."""
    timestamp = now_iso()
    return {"schema_version": SCHEMA_VERSION, "agent": agent,
            "created_at": timestamp, "updated_at": timestamp,
            "acceleration_cycles": 0, "creativity_cycles": 0,
            "next_id": 1, "transactions": []}


def _atomic_write(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _backup_corrupt(path: Path) -> Path | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    for old in path.parent.glob(f"{path.name}.corrupt-*"):
        try:
            if old.read_bytes() == raw:
                return old
        except OSError:
            continue
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    index = 0
    while backup.exists():
        index += 1
        backup = path.with_name(f"{path.name}.corrupt-{stamp}-{index}")
    try:
        shutil.copy2(path, backup)
    except OSError:
        return None
    return backup


def _load_wallet_unlocked(path: Path, agent: str | None = None) -> dict:
    path = Path(path)
    if not path.exists():
        return empty_wallet(agent or path.parent.name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return validate_wallet(data, agent)
    except (OSError, UnicodeError, TypeError, ValueError) as exc:
        backup = _backup_corrupt(path)
        suffix = f"; копия сохранена как {backup.name}" if backup else ""
        raise WalletCorruptError(f"wallet.json повреждён: {exc}{suffix}") from None


def load_wallet(path: Path, agent: str | None = None) -> dict:
    """Загрузить и проверить кошелёк; битый файл не заменяется."""
    with agent_lock(path):
        return _load_wallet_unlocked(Path(path), agent)


def _save_wallet_unlocked(path: Path, data: dict, agent: str | None = None) -> None:
    validate_wallet(data, agent)
    data["updated_at"] = now_iso()
    _atomic_write(Path(path), data)


def save_wallet(path: Path, data: dict, agent: str | None = None) -> None:
    """Проверить и атомарно сохранить кошелёк под общей блокировкой."""
    with agent_lock(path):
        _save_wallet_unlocked(Path(path), data, agent)


def load_or_create_wallet(path: Path, agent: str | None = None) -> dict:
    """Загрузить кошелёк, создав отсутствующий с нулевым балансом."""
    ensure_wallet_file(path, agent)
    return load_wallet(path, agent)


def ensure_wallet_file(path: Path, agent: str | None = None) -> bool:
    """Создать нулевой кошелёк, если файла ещё нет."""
    path = Path(path)
    with agent_lock(path):
        if path.exists():
            _load_wallet_unlocked(path, agent)
            return False
        _save_wallet_unlocked(path, empty_wallet(agent or path.parent.name), agent)
        return True


load = load_wallet
load_or_create = load_or_create_wallet
ensure = ensure_wallet_file
