"""Каталог расширяемых файловых инструментов."""

from __future__ import annotations

import importlib
import pkgutil


def discover_tools() -> list[tuple[dict, object]]:
    """Найти в каталоге пары definition/handler в стабильном порядке."""
    found = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        definition = getattr(module, "create_tool_definition", None)
        factory = getattr(module, "create_tool", None)
        if callable(definition) and callable(factory):
            found.append((getattr(module, "TOOL_ORDER", 100), definition(), factory()))
    return [(definition, handler) for _, definition, handler in sorted(found)]
