"""Бухгалтерия баланса и оплаченных циклов агента."""

import uuid
from pathlib import Path

from agent_lock import agent_lock
from time_utils import now_iso
from wallet_format import format_spend_history
from wallet_access import (
    path as _path, agent_name as _agent, ensure_wallet_file, load_or_create_wallet,
    load_wallet,
    save_wallet,
)
from wallet_storage import (
    MAX_UNITS, SPEND_TYPES, DEFAULT_SPEND_TYPE,
    WalletCorruptError, WalletCorruptionError, WalletError, WalletValidationError,
    _load_wallet_unlocked, _save_wallet_unlocked, empty_wallet, validate_wallet,
)
from wallet_reconcile import format_credit_message, reconcile_payment_messages
from wallet_cycles import consume_acceleration_cycle, consume_creativity_cycle


class InsufficientBalance(WalletError):
    """Для траты доступно меньше единиц, чем запрошено."""



def _check_units(units) -> int:
    if (isinstance(units, bool) or not isinstance(units, int)
            or not 1 <= units <= MAX_UNITS):
        raise WalletValidationError(
            f"units должно быть положительным целым не больше {MAX_UNITS}"
        )
    return units


def _check_text(value, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WalletValidationError(f"{field} должно быть непустой строкой")
    return value.strip()


def _check_spend_type(value) -> str:
    if not isinstance(value, str) or value not in SPEND_TYPES:
        raise WalletValidationError(
            "type должно быть одним из: speed, creativity"
        )
    return value


def _open_unlocked(target, agent=None) -> tuple[Path, dict, str | None]:
    path = _path(target)
    name = _agent(target, agent)
    return path, _load_wallet_unlocked(path, name), name


def wallet_summary(source, agent=None) -> dict:
    """Рассчитать доступные единицы и запас оплаченных циклов."""
    data = (validate_wallet(source) if isinstance(source, dict)
            else load_wallet(source, agent))
    credited = sum(t["units"] for t in data["transactions"] if t["type"] == "credit")
    spent = sum(t["units"] for t in data["transactions"] if t["type"] == "spend")
    cycles = data["acceleration_cycles"]
    creativity_cycles = data.get("creativity_cycles", 0)
    return {
        "balance": credited - spent, "available_units": credited - spent,
        "credited_units": credited, "spent_units": spent,
        "used_cycles": spent - cycles - creativity_cycles,
        "acceleration_cycles": cycles, "creativity_cycles": creativity_cycles,
        "paid_cycles": cycles + creativity_cycles,
    }


summary = wallet_summary
calculate_summary = wallet_summary
ensure_wallet = ensure_wallet_file
load_or_create = load_or_create_wallet


def credit(target, units, reason, payment_id=None, agent=None) -> dict:
    """Начислить единицы и вернуть append-only запись credit."""
    units, reason = _check_units(units), _check_text(reason, "reason")
    if payment_id is None:
        payment_id = uuid.uuid4().hex
    payment_id = _check_text(payment_id, "payment_id")
    path = _path(target)
    with agent_lock(path):
        path, data, name = _open_unlocked(target, agent)
        transaction = {
            "id": data["next_id"], "timestamp": now_iso(), "type": "credit",
            "units": units, "reason": reason, "actor": "creator",
            "payment_id": payment_id,
        }
        data["transactions"].append(transaction)
        data["next_id"] += 1
        _save_wallet_unlocked(path, data, name)
    return transaction


def spend(target, units, purpose, spend_type=DEFAULT_SPEND_TYPE,
          agent=None) -> dict:
    """Атомарно списать единицы и купить эффект для следующих циклов."""
    units = _check_units(units)
    purpose = _check_text(purpose, "purpose")
    spend_type = _check_spend_type(spend_type)
    path = _path(target)
    with agent_lock(path):
        path, data, name = _open_unlocked(target, agent)
        if wallet_summary(data)["balance"] < units:
            raise InsufficientBalance("недостаточно доступных единиц агента")
        transaction = {
            "id": data["next_id"], "timestamp": now_iso(), "type": "spend",
            "units": units, "purpose": purpose, "spend_type": spend_type,
            "actor": "agent",
        }
        data["transactions"].append(transaction)
        data["next_id"] += 1
        reserve = "acceleration_cycles" if spend_type == "speed" else "creativity_cycles"
        data[reserve] = data.get(reserve, 0) + units
        _save_wallet_unlocked(path, data, name)
    return transaction


consume_cycle = consume_acceleration_cycle
format_history = format_spend_history
