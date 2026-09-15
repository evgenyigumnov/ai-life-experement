"""Расходование отложенных эффектов кошелька по одному циклу."""

from agent_lock import agent_lock
from wallet_access import agent_name as _agent, path as _path
from wallet_storage import _load_wallet_unlocked, _save_wallet_unlocked


def _consume_reserve(target, field: str, agent=None) -> bool:
    path = _path(target)
    with agent_lock(path):
        name = _agent(target, agent)
        data = _load_wallet_unlocked(path, name)
        if not data.get(field, 0):
            return False
        data[field] -= 1
        _save_wallet_unlocked(path, data, name)
        return True


def consume_acceleration_cycle(target, agent=None) -> bool:
    """Списать один оплаченный speed-цикл."""
    return _consume_reserve(target, "acceleration_cycles", agent)


def consume_creativity_cycle(target, agent=None) -> bool:
    """Списать один оплаченный creativity-цикл."""
    return _consume_reserve(target, "creativity_cycles", agent)
