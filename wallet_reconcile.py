"""Сверка начислений кошелька с входящими сообщениями."""

from pathlib import Path

from agent_lock import agent_lock
from storage_messages import _load_messages_unlocked, _save_messages_unlocked
from time_utils import now_iso
from wallet_storage import _load_wallet_unlocked


def format_credit_message(units: int, reason: str) -> str:
    return (
        f"Создатель начислил тебе {units} единиц за: «{reason}».\n"
        "Единицы можно потратить через `money_spend` с type=speed или "
        "type=creativity; баланс — через `money_balance`."
    )


def reconcile_payment_messages(wallet_path: Path, messages_path: Path,
                                agent: str | None = None) -> int:
    """Дописать отсутствующие уведомления о credit, не создавая credit."""
    wallet_path, messages_path = Path(wallet_path), Path(messages_path)
    with agent_lock(wallet_path):
        wallet_data = _load_wallet_unlocked(wallet_path, agent)
        messages_data = _load_messages_unlocked(messages_path)
        known = {
            message.get("payment_id")
            for message in messages_data.get("messages") or []
            if isinstance(message, dict)
        }
        missing = [
            tx for tx in wallet_data["transactions"]
            if tx["type"] == "credit" and tx["payment_id"] not in known
        ]
        if not missing:
            return 0
        for transaction in missing:
            messages_data["messages"].append({
                "timestamp": now_iso(),
                "from": "creator",
                "text": format_credit_message(
                    transaction["units"], transaction["reason"]
                ),
                "read": False,
                "payment_id": transaction["payment_id"],
            })
        _save_messages_unlocked(messages_path, messages_data)
        return len(missing)
