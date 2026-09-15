"""Использование оплаченной единицы в адаптивном расписании."""

from agent_console import _Colors, _colorize
from agent_paths import AgentPaths
import wallet

CREATIVITY_TEMPERATURE = 1.4


def creativity_temperature(paths: AgentPaths, default: float) -> float:
    """Забрать creativity-цикл и вернуть температуру для текущего тика."""
    try:
        active = wallet.consume_creativity_cycle(paths)
    except (wallet.WalletError, OSError, ValueError):
        active = False
    except Exception:
        active = False
    return CREATIVITY_TEMPERATURE if active else default


def use_paid_cycle(paths: AgentPaths, fixed_pause: bool = False) -> int | None:
    """Атомарно использовать одну единицу; вернуть остаток или None."""
    if fixed_pause:
        return None
    try:
        if not wallet.consume_acceleration_cycle(paths):
            return None
        return wallet.wallet_summary(paths)["acceleration_cycles"]
    except (wallet.WalletError, OSError, ValueError):
        # Повреждённый кошелёк не должен останавливать жизнь или ускорять её.
        return None
    except Exception:
        return None


apply_paid_cycle = use_paid_cycle


def format_paid_cycle_log(remaining: int) -> str:
    return _colorize(
        f"💰 Использована 1 оплаченная единица: пауза отменена, "
        f"осталось {remaining} оплаченных циклов", _Colors.GREEN
    )
