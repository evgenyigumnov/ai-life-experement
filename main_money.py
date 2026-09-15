import os
import re
import sys

from dotenv import load_dotenv

from agent_paths import find_existing_agent_folder
from config_env import Config
from storage import SENDER_CREATOR, append_message
import wallet
from wallet_reconcile import format_credit_message

MONEY_COMMANDS = frozenset({"pay", "balance", "history"})
MONEY_USAGE = (
    "Использование: python main.py <имя> pay <единицы> <причина>; "
    "<имя> balance|history"
)


def is_money_command(argv: list[str]) -> bool:
    return any(argument in MONEY_COMMANDS for argument in argv)

def _fail(message: str) -> None:
    print(f"Ошибка: {message}", file=sys.stderr)
    print(MONEY_USAGE, file=sys.stderr)
    raise SystemExit(1)

def _parse_pay(argv: list[str]) -> tuple[int, str]:
    if len(argv) != 4:
        _fail("pay требует имя агента, целое число и причину")
    raw_units, reason = argv[2], argv[3]
    if (not re.fullmatch(r"[0-9]+", raw_units)
            or len(raw_units) > len(str(wallet.MAX_UNITS))):
        _fail("количество единиц должно быть положительным целым числом")
    units = int(raw_units)
    if not 1 <= units <= wallet.MAX_UNITS:
        _fail("количество единиц должно быть в диапазоне 1.."
              f"{wallet.MAX_UNITS}")
    if not reason.strip():
        _fail("причина платежа не может быть пустой")
    return units, reason.strip()

def _paths(name: str):
    cfg = Config(
        base_url="money-mode", model="money-mode", api_key="money-mode",
        agents_root=os.environ.get("AGENTS_ROOT", "").strip() or None,
    )
    paths = find_existing_agent_folder(name, cfg)
    if paths is None:
        _fail(f"агент «{name}» не найден; денежные команды не создают агентов")
    return paths

def _pay(name: str, units: int, reason: str) -> None:
    paths = _paths(name)
    try:
        transaction = wallet.credit(paths, units, reason)
    except (wallet.WalletError, OSError, ValueError) as exc:
        _fail(f"не удалось начислить единицы: {exc}")
    except Exception:
        _fail("не удалось начислить единицы")
    try:
        append_message(
            paths.messages, SENDER_CREATOR, format_credit_message(units, reason),
            payment_id=transaction["payment_id"],
        )
    except Exception as exc:
        _fail(
            f"агенту начислено {units} единиц, но уведомление не записано "
            f"({exc}); оно будет восстановлено при следующем запуске"
        )
    try:
        state = wallet.wallet_summary(paths)
    except (wallet.WalletError, OSError, ValueError) as exc:
        _fail(f"начисление сохранено, но баланс не прочитан: {exc}")
    print(
        f"Платёж агенту «{name}» подтверждён: начислено {units} единиц "
        f"за: «{reason}».\nДоступно агенту: {state['balance']} единиц.",
        flush=True,
    )

def _balance(name: str) -> None:
    paths = _paths(name)
    try:
        wallet.ensure_wallet_file(paths.wallet, name)
        state = wallet.wallet_summary(paths)
    except (wallet.WalletError, OSError, ValueError) as exc:
        _fail(f"не удалось прочитать кошелёк: {exc}")
    except Exception:
        _fail("не удалось прочитать кошелёк")
    print(
        f"Баланс агента «{name}»:\n"
        f"Доступно: {state['balance']} единиц.\n"
        f"Оплаченных циклов: {state['acceleration_cycles']}.\n"
        f"Циклов creativity (TEMPERATURE=1.4): {state['creativity_cycles']}.",
        flush=True,
    )

def _history(name: str) -> None:
    paths = _paths(name)
    try:
        print(wallet.format_spend_history(paths), flush=True)
    except (wallet.WalletError, OSError, ValueError) as exc:
        _fail(f"не удалось прочитать историю кошелька: {exc}")

def run_money_command(argv: list[str]) -> None:
    load_dotenv()
    if not argv or argv[0] in MONEY_COMMANDS:
        _fail("денежная команда требует обязательное имя агента")
    if len(argv) < 2 or argv[1] not in MONEY_COMMANDS:
        _fail("неизвестный формат денежной команды")
    name, command = argv[0], argv[1]
    if command == "pay":
        units, reason = _parse_pay(argv)
        _pay(name, units, reason)
    elif command == "balance" and len(argv) == 2:
        _balance(name)
    elif command == "history" and len(argv) == 2:
        _history(name)
    else:
        _fail(f"неверные аргументы команды {command}")
