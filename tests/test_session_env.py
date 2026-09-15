"""Настройки длины сессии из Config применяются до запуска цикла."""

import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import agent_sleep
import main as main_mod
import main_banner
import prompts_template as prompts
from agent_paths import AgentPaths
from config_env import Config
from main_banner import _print_banner
from session_env import apply_session_config


def _paths(folder: Path) -> AgentPaths:
    return AgentPaths(folder, folder / "system-prompt.md", folder / "mind-loop.json", folder / "memory.md")


class SessionEnvTests(unittest.TestCase):
    def setUp(self):
        self.old_values = agent_sleep.SESSION_ITERATIONS, agent_sleep.SLEEP_WARN_REMAINING
        self.addCleanup(self._restore)

    def _restore(self):
        agent_sleep.SESSION_ITERATIONS, agent_sleep.SLEEP_WARN_REMAINING = self.old_values

    def test_apply_changes_all_session_predicates(self):
        cfg = Config("http://x", "m", "k", None, session_iterations=5, sleep_warn_remaining=2)
        apply_session_config(cfg)
        self.assertEqual(agent_sleep.iterations_remaining(4), 1)
        self.assertTrue(agent_sleep.is_session_end(5))
        self.assertTrue(agent_sleep.should_warn(2))
        self.assertFalse(agent_sleep.should_warn(3))

    def test_banner_and_last_tick_use_override(self):
        folder = Path(tempfile.mkdtemp(prefix="ai-session-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        paths = _paths(folder)
        paths.system_prompt.write_text("тест", encoding="utf-8")
        cfg = Config("http://x", "m", "k", None, session_iterations=4, sleep_warn_remaining=1)
        apply_session_config(cfg)
        with redirect_stdout(StringIO()) as out:
            _print_banner("bot", cfg, paths, 3)
        self.assertIn("осталось 1 итерацию (сессия из 4)", out.getvalue())
        self.assertIn("Сохрани в памяти итог и следующий шаг", agent_sleep._tick_user_message(4, paths))

    def test_main_applies_config_before_banner_and_loop(self):
        folder = Path(tempfile.mkdtemp(prefix="ai-main-session-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        paths = _paths(folder)
        cfg = Config("http://x", "m", "k", None, session_iterations=7, sleep_warn_remaining=3)
        seen = {}

        def banner(*args):
            seen["iterations"] = agent_sleep.SESSION_ITERATIONS
            seen["warn"] = agent_sleep.SLEEP_WARN_REMAINING

        with mock.patch.object(main_mod, "load_config", return_value=cfg), \
             mock.patch.object(main_mod, "find_agent_folder", return_value=paths), \
             mock.patch.object(main_banner, "_print_banner", side_effect=banner), \
             mock.patch.object(main_mod, "run_loop"), \
             mock.patch.object(main_mod.sys, "argv", ["main.py", "bot"]):
            main_mod.main()
        self.assertEqual(seen, {"iterations": 7, "warn": 3})

    def test_defaults_are_synchronised(self):
        fields = Config.__dataclass_fields__
        self.assertEqual(fields["session_iterations"].default, prompts.DEFAULT_SESSION_ITERATIONS)
        self.assertEqual(fields["sleep_warn_remaining"].default, prompts.DEFAULT_SLEEP_WARN_REMAINING)
        self.assertEqual(agent_sleep.SESSION_ITERATIONS, prompts.DEFAULT_SESSION_ITERATIONS)
        self.assertEqual(agent_sleep.SLEEP_WARN_REMAINING, prompts.DEFAULT_SLEEP_WARN_REMAINING)


if __name__ == "__main__":
    unittest.main()
