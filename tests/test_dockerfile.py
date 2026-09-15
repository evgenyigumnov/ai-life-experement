"""Тесты Dockerfile: поддержка UTF-8 (кириллица) в vi внутри контейнера.

busybox vi из базового alpine не умеет multibyte и печатает точки вместо
русских букв. Тесты проверяют, что образ:
  * ставит полноценный vim (+multibyte),
  * перекрывает команду vi ссылкой на vim,
  * задаёт локаль C.UTF-8.
"""

import unittest
from pathlib import Path

from tests.helpers import PROJECT_ROOT

DOCKERFILE = PROJECT_ROOT / "Dockerfile"


def _text() -> str:
    return DOCKERFILE.read_text(encoding="utf-8")


class TestDockerfileUtf8(unittest.TestCase):
    def test_file_exists(self):
        self.assertTrue(DOCKERFILE.is_file(), "Dockerfile отсутствует в корне проекта")

    def test_vim_installed(self):
        self.assertIn("vim", _text().split())

    def test_vi_overridden_by_symlink_to_vim(self):
        text = _text()
        self.assertIn("/usr/bin/vim", text)
        self.assertIn("/usr/local/bin/vi", text)

    def test_utf8_locale_set(self):
        text = _text()
        self.assertIn("LANG=C.UTF-8", text)
        self.assertIn("LC_ALL=C.UTF-8", text)


if __name__ == "__main__":
    unittest.main()
