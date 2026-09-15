"""Тесты цветового оформления и форматирования блоков консоли."""


import sys
import unittest
from io import StringIO
from unittest import mock

from tests.agent_common import agent, agent_console, agent_console_blocks, env


class ColorFormattingTests(unittest.TestCase):
    """Цветовое оформление: вкл/выкл через USE_COLOR, NO_COLOR, не-tty."""

    def _block(self) -> str:
        return agent._format_llm_block(1, "текст", 0.5, 10)

    def test_colorize_disabled_returns_plain_text(self):
        with mock.patch.object(agent_console, "USE_COLOR", False):
            self.assertEqual(
                agent._colorize("x", agent._Colors.CYAN), "x"
            )
            self.assertNotIn("\x1b[", self._block())

    def test_colorize_enabled_wraps_with_ansi(self):
        with mock.patch.object(agent_console, "USE_COLOR", True):
            self.assertEqual(
                agent._colorize("x", agent._Colors.CYAN),
                f"{agent._Colors.CYAN}x{agent._Colors.RESET}",
            )
            self.assertIn("\x1b[", self._block())

    def test_blocks_use_own_colors(self):
        with mock.patch.object(agent_console, "USE_COLOR", True):
            self.assertIn(agent._Colors.CYAN, agent._format_iteration_header(1))
            self.assertIn(
                agent._Colors.CYAN,
                agent._format_iteration_command(
                    agent.USER_MESSAGE, agent.SESSION_ITERATIONS - 1
                ),
            )
            self.assertIn(agent._Colors.MAGENTA, agent._format_llm_block(1, "т", 1.0, None))
            self.assertIn(
                agent._Colors.YELLOW,
                agent._format_tool_call_block(1, "run_bash", "{}"),
            )
            self.assertIn(
                agent._Colors.GREEN,
                agent._format_tool_result_block(1, "run_bash", "ок"),
            )
            self.assertIn(
                agent._Colors.RED,
                agent._format_failed_iteration(RuntimeError("ой")),
            )

    def test_no_color_env_disables_color(self):
        fake_stdout = StringIO()
        with mock.patch.object(agent_console, "USE_COLOR", None), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             env(NO_COLOR="1"):
            self.assertFalse(agent._supports_color())

    def test_dumb_term_disables_color(self):
        fake_stdout = StringIO()
        with mock.patch.object(agent_console, "USE_COLOR", None), \
             mock.patch.object(sys, "stdout", fake_stdout), \
             env(NO_COLOR=None, TERM="dumb"):
            self.assertFalse(agent._supports_color())

    def test_tty_enables_color(self):
        class FakeTty(StringIO):
            def isatty(self):
                return True

        with mock.patch.object(agent_console, "USE_COLOR", None), \
             mock.patch.object(sys, "stdout", FakeTty()), \
             env(NO_COLOR=None, TERM="xterm"):
            self.assertTrue(agent._supports_color())

    def test_use_color_global_overrides_everything(self):
        with mock.patch.object(agent_console, "USE_COLOR", True), env(NO_COLOR="1"):
            self.assertTrue(agent._supports_color())


class FormatToolArgsTests(unittest.TestCase):
    """`_format_tool_args`: dict, JSON-строка, произвольная строка, прочее."""

    def test_dict_indented(self):
        formatted = agent._format_tool_args({"command": "ls"})
        self.assertEqual(formatted, '{\n  "command": "ls"\n}')

    def test_json_string_reindented(self):
        formatted = agent._format_tool_args('{"command":"ls"}')
        self.assertEqual(formatted, '{\n  "command": "ls"\n}')

    def test_plain_string_kept_as_is(self):
        self.assertEqual(agent._format_tool_args("не JSON"), "не JSON")

    def test_non_json_scalar_stringified(self):
        self.assertEqual(agent._format_tool_args(42), "42")


class FormatReasoningBlockTests(unittest.TestCase):
    """`_format_reasoning_block`: рамка, обрезка, цвет (blue)."""

    def test_block_contains_framed_text(self):
        block = agent._format_reasoning_block(7, "  мысль модели  ")
        self.assertTrue(block.startswith("┌──"))
        self.assertIn("[итерация 7] 🧠 Reasoning", block)
        self.assertIn("│ мысль модели", block)  # strip() отрезал пробелы
        self.assertTrue(block.splitlines()[-1].startswith("└"))

    def test_long_reasoning_truncated_with_note(self):
        with mock.patch.object(agent_console_blocks, "MAX_REASONING_LOG_CHARS", 100):
            block = agent._format_reasoning_block(1, "Х" * 500)
        self.assertIn("Х" * 100, block)
        self.assertNotIn("Х" * 101, block)
        self.assertIn("обрезано: показано 100 из 500 символов", block)

    def test_short_reasoning_not_truncated(self):
        block = agent._format_reasoning_block(1, "коротко")
        self.assertNotIn("обрезано", block)

    def test_multiline_reasoning_each_line_framed(self):
        block = agent._format_reasoning_block(2, "строка 1\n\nстрока 3")
        self.assertIn("│ строка 1", block)
        self.assertIn("\n│\n", block)
        self.assertIn("│ строка 3", block)

    def test_uses_blue_color(self):
        with mock.patch.object(agent_console, "USE_COLOR", True):
            block = agent._format_reasoning_block(1, "текст")
        self.assertIn(agent._Colors.BLUE, block)
        self.assertIn(agent._Colors.RESET, block)

    def test_no_ansi_when_color_disabled(self):
        with mock.patch.object(agent_console, "USE_COLOR", False):
            block = agent._format_reasoning_block(1, "текст")
        self.assertNotIn("\x1b[", block)


class FormatSystemPromptBlockTests(unittest.TestCase):
    """`_format_system_prompt_block`: рамка, полный текст, цвет (cyan)."""

    def test_block_contains_framed_text(self):
        block = agent._format_system_prompt_block(3, "Ты — агент.\nСледуй правилам.")
        self.assertTrue(block.startswith("╔══"))
        self.assertIn("[итерация 3] 📜 System prompt", block)
        self.assertIn("║ Ты — агент.", block)
        self.assertIn("║ Следуй правилам.", block)
        self.assertTrue(block.splitlines()[-1].startswith("╚"))

    def test_multiline_prompt_with_blank_lines(self):
        block = agent._format_system_prompt_block(1, "строка 1\n\nстрока 3")
        self.assertIn("║ строка 1", block)
        self.assertIn("\n║\n", block)  # пустая строка — просто «║»
        self.assertIn("║ строка 3", block)

    def test_empty_prompt_placeholder(self):
        block = agent._format_system_prompt_block(1, "")
        self.assertIn("(пусто)", block)

    def test_full_text_not_truncated(self):
        long_prompt = "P" * 5000
        block = agent._format_system_prompt_block(1, long_prompt)
        self.assertIn("P" * 5000, block)
        self.assertNotIn("обрезано", block)

    def test_uses_cyan_color(self):
        with mock.patch.object(agent_console, "USE_COLOR", True):
            block = agent._format_system_prompt_block(1, "текст")
        self.assertIn(agent._Colors.CYAN, block)
        self.assertIn(agent._Colors.RESET, block)

    def test_no_ansi_when_color_disabled(self):
        with mock.patch.object(agent_console, "USE_COLOR", False):
            block = agent._format_system_prompt_block(1, "текст")
        self.assertNotIn("\x1b[", block)


class FormatSystemPromptUnchangedTests(unittest.TestCase):
    """`_format_system_prompt_unchanged`: короткая строка вместо блока."""

    def test_line_contains_title_without_frame(self):
        line = agent._format_system_prompt_unchanged(5)
        self.assertEqual(line, "[итерация 5] 📜 System prompt без изменений")
        self.assertNotIn("\n", line)
        self.assertNotIn("╔", line)

    def test_uses_cyan_color(self):
        with mock.patch.object(agent_console, "USE_COLOR", True):
            line = agent._format_system_prompt_unchanged(1)
        self.assertIn(agent._Colors.CYAN, line)
        self.assertIn(agent._Colors.RESET, line)

    def test_no_ansi_when_color_disabled(self):
        with mock.patch.object(agent_console, "USE_COLOR", False):
            line = agent._format_system_prompt_unchanged(1)
        self.assertNotIn("\x1b[", line)

if __name__ == "__main__":
    unittest.main()
