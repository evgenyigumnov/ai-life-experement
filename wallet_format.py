"""Форматирование истории трат кошелька."""

from pathlib import Path

from wallet_storage import load_wallet, validate_wallet


def _source_path(source) -> tuple[Path, str | None]:
    path = Path(getattr(source, "wallet", source))
    name = getattr(source, "name", "") if hasattr(source, "folder") else None
    return path, name or None


def format_spend_history(source) -> str:
    """Показать только spend от новых к старым и итоговую сводку."""
    agent = None
    if isinstance(source, dict):
        data = validate_wallet(source)
    else:
        path, agent = _source_path(source)
        data = load_wallet(path, agent)
    spends = [t for t in data["transactions"] if t["type"] == "spend"]
    spent = sum(t["units"] for t in spends)
    cycles = data["acceleration_cycles"]
    spends.sort(key=lambda t: (t["timestamp"], t["id"]), reverse=True)
    label = f" «{agent}»" if agent else ""
    lines = [f"История трат агента{label}:"]
    lines.extend(
        f"[{t['timestamp']}] −{t['units']} единиц "
        f"(type={t.get('spend_type', 'speed')}): {t['purpose']}"
        for t in spends
    )
    if not spends:
        lines.append("(трат ещё нет)")
    creativity = data.get("creativity_cycles", 0)
    lines.append(
        f"Итого потрачено: {spent} единиц; использовано оплаченных циклов: "
        f"{spent - cycles - creativity}; осталось ускорение: {cycles} циклов; "
        f"осталось creativity: {creativity} циклов."
    )
    return "\n".join(lines)
