"""Проверка кошелька."""

MAX_UNITS = 2**63 - 1
SPEND_TYPES = frozenset({"speed", "creativity"})
DEFAULT_SPEND_TYPE = "speed"


class WalletError(Exception):
    """Безопасная для пользователя ошибка работы с кошельком."""


class WalletCorruptError(WalletError):
    """Кошелёк не прошёл проверку структуры."""


class WalletValidationError(WalletError):
    """Неверные данные операции или кошелька."""


WalletCorruptionError = WalletCorruptError

def _text(value, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"поле {field!r} должно быть непустой строкой")


def _positive(value, field: str, maximum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"поле {field!r} должно быть положительным целым")
    if maximum is not None and value > maximum:
        raise ValueError(f"поле {field!r} превышает допустимый размер")


def validate_wallet(data, expected_agent: str | None = None) -> dict:
    """Проверить кошелёк."""
    if not isinstance(data, dict):
        raise ValueError("корень кошелька должен быть объектом")
    version = data.get("schema_version")
    if isinstance(version, bool) or version != 1:
        raise ValueError("неподдерживаемая версия кошелька")
    _text(data.get("agent"), "agent")
    if expected_agent and data["agent"] != expected_agent:
        raise ValueError("кошелёк принадлежит другому агенту")
    _text(data.get("created_at"), "created_at")
    _text(data.get("updated_at"), "updated_at")
    cycles = data.get("acceleration_cycles")
    if (isinstance(cycles, bool) or not isinstance(cycles, int)
            or not 0 <= cycles <= MAX_UNITS):
        raise ValueError("acceleration_cycles имеет недопустимое значение")
    creativity_cycles = data.get("creativity_cycles", 0)
    if (isinstance(creativity_cycles, bool)
            or not isinstance(creativity_cycles, int)
            or not 0 <= creativity_cycles <= MAX_UNITS):
        raise ValueError("creativity_cycles имеет недопустимое значение")
    next_id = data.get("next_id")
    _positive(next_id, "next_id")
    transactions = data.get("transactions")
    if not isinstance(transactions, list):
        raise ValueError("transactions должен быть списком")

    ids, balance, spent, max_id = set(), 0, 0, 0
    speed_spent = creativity_spent = 0
    for transaction in transactions:
        if not isinstance(transaction, dict):
            raise ValueError("операция кошелька должна быть объектом")
        tx_id = transaction.get("id")
        _positive(tx_id, "id")
        if tx_id in ids:
            raise ValueError(f"дубликат id операции: {tx_id}")
        ids.add(tx_id)
        max_id = max(max_id, tx_id)
        _text(transaction.get("timestamp"), "timestamp")
        kind = transaction.get("type")
        if kind not in {"credit", "spend"}:
            raise ValueError(f"неизвестный тип операции: {kind!r}")
        units = transaction.get("units")
        _positive(units, "units", MAX_UNITS)
        actor = "creator" if kind == "credit" else "agent"
        if transaction.get("actor") != actor:
            raise ValueError(f"неверный actor для операции {kind}")
        if kind == "credit":
            _text(transaction.get("reason"), "reason")
            _text(transaction.get("payment_id"), "payment_id")
            balance += units
        else:
            _text(transaction.get("purpose"), "purpose")
            spend_type = transaction.get("spend_type", DEFAULT_SPEND_TYPE)
            if not isinstance(spend_type, str) or spend_type not in SPEND_TYPES:
                raise ValueError(f"неизвестный тип траты: {spend_type!r}")
            balance -= units
            spent += units
            if spend_type == "speed":
                speed_spent += units
            else:
                creativity_spent += units
            if balance < 0:
                raise ValueError("итоговый баланс не может быть отрицательным")
    if next_id <= max_id:
        raise ValueError("next_id должен быть больше всех id операций")
    if cycles > speed_spent:
        raise ValueError("оплаченных циклов больше суммы трат speed")
    if creativity_cycles > creativity_spent:
        raise ValueError("циклов creativity больше суммы соответствующих трат")
    return data
