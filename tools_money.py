"""Исполнители money_balance и money_spend."""

from agent_paths import AgentPaths
import wallet
from tools_money_schema import MONEY_BALANCE_TOOL, MONEY_SPEND_TOOL


def _error(exc: Exception, invalid: bool = False) -> str:
    prefix = "Error: invalid arguments" if invalid else "Error: wallet unavailable"
    return f"{prefix}: {exc}"


def _summary(paths: AgentPaths) -> dict:
    wallet.ensure_wallet_file(paths.wallet, paths.name or paths.folder.name)
    return wallet.wallet_summary(paths)


def handle_money_balance(args: dict, paths: AgentPaths) -> str:
    """Вернуть доступные единицы и число ожидающих оплаченных циклов."""
    try:
        state = _summary(paths)
    except wallet.WalletValidationError as exc:
        return _error(exc, invalid=True)
    except (wallet.WalletError, OSError) as exc:
        return _error(exc)
    except Exception:
        return "Error: wallet unavailable: операция не выполнена"
    return (
        f"Баланс агента «{paths.name or paths.folder.name}»:\n"
        f"Доступно: {state['balance']} единиц.\n"
        f"Оплаченных циклов: {state['acceleration_cycles']} (type=speed).\n"
        f"Циклов creativity (TEMPERATURE=1.4): {state['creativity_cycles']}.\n"
        "1 единица = 1 следующий цикл/тик LLM без паузы перед ним.\n"
        "Адаптивное расписание без оплаченных единиц: 0 → 30 сек → 1 мин → "
        "2 мин → 5 мин → 10 мин → 20 мин → 40 мин → 1 час → 2 часа → 4 часа.\n"
    )


def handle_money_spend(args: dict, paths: AgentPaths) -> str:
    """Списать единицы и добавить выбранный эффект в запас циклов."""
    units = args.get("units")
    purpose = args.get("purpose")
    spend_type = args.get("type")
    if (isinstance(units, bool) or not isinstance(units, int)
            or not 1 <= units <= wallet.MAX_UNITS):
        return _error(f"'units' должно быть положительным целым не больше "
                      f"{wallet.MAX_UNITS}", invalid=True)
    if not isinstance(purpose, str) or not purpose.strip():
        return _error("'purpose' должен быть непустой строкой", invalid=True)
    if not isinstance(spend_type, str) or spend_type not in wallet.SPEND_TYPES:
        return _error("'type' должен быть speed или creativity", invalid=True)
    try:
        wallet.spend(paths, units, purpose, spend_type)
        state = _summary(paths)
    except wallet.InsufficientBalance as exc:
        return _error(exc)
    except wallet.WalletValidationError as exc:
        return _error(exc, invalid=True)
    except (wallet.WalletError, OSError) as exc:
        return _error(exc)
    except Exception:
        return "Error: wallet unavailable: операция не выполнена"
    return (
        f"Потрачено {units} единиц на: «{purpose.strip()}» (type={spend_type}).\n"
        f"Доступно: {state['balance']} единиц.\n"
        f"Оплаченных циклов: {state['acceleration_cycles']} (type=speed). "
        f"Циклов creativity: {state['creativity_cycles']}. "
        "Эффект начнётся после текущего завершённого цикла; дополнительная "
        "итерация не запускается."
    )
