"""Пакет тестов проекта ai-life.

При импорте через пакет добавляет корень проекта в sys.path, чтобы тесты
можно было запускать и как `python -m unittest discover` из корня,
и как `python -m unittest discover -s tests` из папки tests.
"""

import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
