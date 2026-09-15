"""Тесты блоков консоли итерации: LLM, Reasoning, tool-вызовы."""


import json
import unittest
from unittest import mock

from tests.agent_common import agent, agent_console, agent_loop
from tests.test_agent_iteration_logging import _IterationLoggingBase


class LlmBlockTests(_IterationLoggingBase):
    """Блоки ответа LLM: тайминг, токены, reasoning, tool-вызовы и результаты."""

    def test_llm_block_contains_timing_tokens_and_full_content(self):
        long_content = "Текст ассистента: " + "A" * 300
        response = {
            "role": "assistant",
            "content": long_content,
            "usage": {"prompt_tokens": 142, "total_tokens": 200},
        }
        logs = self._run(response)
        llm_block = logs[3]
        self.assertTrue(llm_block.startswith("┌──"))
        self.assertIn("💬 LLM", llm_block)
        self.assertRegex(
            llm_block.splitlines()[0],
            r"\[итерация 1\] 💬 LLM \(\d+\.\d{2} сек \| токенов послано: 142\)",
        )
        self.assertIn(f"│ {long_content}", llm_block)  # полный текст, без обрезки
        self.assertNotIn("…", llm_block)
        self.assertIn("└", llm_block)

    def test_llm_block_without_usage_omits_tokens(self):
        logs = self._run({"role": "assistant", "content": "ок"})
        first_line = logs[3].splitlines()[0]
        self.assertRegex(first_line, r"💬 LLM \(\d+\.\d{2} сек\)")
        self.assertNotIn("токенов", first_line)

    def test_llm_block_with_completion_and_reasoning_tokens(self):
        response = {
            "role": "assistant",
            "content": "готово",
            "usage": {
                "prompt_tokens": 142,
                "completion_tokens": 58,
                "completion_tokens_details": {"reasoning_tokens": 40},
            },
        }
        logs = self._run(response)
        first_line = logs[3].splitlines()[0]
        self.assertRegex(
            first_line,
            r"токенов послано: 142 \| токенов сгенерировано: 58 \(из них reasoning: 40\)",
        )

    def test_llm_block_with_completion_without_reasoning_tokens(self):
        response = {
            "role": "assistant",
            "content": "ок",
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        }
        logs = self._run(response)
        first_line = logs[3].splitlines()[0]
        self.assertIn("токенов сгенерировано: 3", first_line)
        self.assertNotIn("reasoning", first_line)

    def test_reasoning_block_logged_before_llm_block(self):
        response = {
            "role": "assistant",
            "content": "готово",
            "reasoning_content": "осмотрелся и решил проверить память",
            "tool_calls": [],
        }
        logs = self._run(response)
        # заголовок, команда, system prompt, блок Reasoning, блок LLM
        self.assertEqual(len(logs), 5)
        self.assertIn("🧠 Reasoning", logs[3])
        self.assertIn("│ осмотрелся и решил проверить память", logs[3])
        self.assertIn("💬 LLM", logs[4])

    def test_reasoning_logged_when_serialize_returns_none(self):
        """Пустой ответ (ни content, ни tool_calls) + thinking → блок 🧠 в логе.

        Регрессия к «пустым» итерациям: раньше было непонятно, что модель
        думала, но ничего не выдала.
        """
        response = {
            "role": "assistant",
            "content": None,
            "reasoning_content": "думал, но ничего не решил",
        }
        logs_sink = []
        with mock.patch.object(agent_loop, "_log", logs_sink.append), \
             mock.patch.object(agent_console, "USE_COLOR", False), \
             mock.patch.object(agent_loop, "call_llm", return_value=response):
            with self.assertRaises(RuntimeError):
                agent._run_iteration(self.paths, self.cfg, client=object())
        reasoning_blocks = [b for b in logs_sink if "🧠 Reasoning" in b]
        self.assertEqual(len(reasoning_blocks), 1)
        self.assertIn("думал, но ничего не решил", reasoning_blocks[0])

    def test_multiline_content_each_line_framed(self):
        content = "Строка 1\n\nСтрока 3"
        logs = self._run({"role": "assistant", "content": content})
        llm_block = logs[3]
        self.assertIn("│ Строка 1", llm_block)
        self.assertIn("\n│\n", llm_block)  # пустая строка — просто «│»
        self.assertIn("│ Строка 3", llm_block)

    def test_empty_content_shows_bez_texta(self):
        response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "get_memory", "arguments": "{}"},
            }],
        }
        logs = self._run(response, tool_result="память")
        self.assertIn("(без текста)", logs[3])

    def test_tool_blocks_not_truncated(self):
        long_arg = json.dumps({"command": "echo " + "B" * 300})
        long_result = "Результат:\n" + "C" * 300
        response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "run_bash", "arguments": long_arg},
            }],
        }
        logs = self._run(response, tool_result=long_result)
        # Лог 0: заголовок итерации, 1: команда, 2: system prompt, 3: блок LLM,
        # 4: вызов tool, 5: результат
        self.assertEqual(len(logs), 6)

        call_block = logs[4]
        self.assertIn("Tool: run_bash [вызов]", call_block)
        self.assertIn("┏━━", call_block)
        self.assertIn("┗", call_block)
        self.assertIn("B" * 300, call_block)  # аргументы полностью
        self.assertNotIn("…", call_block)

        result_block = logs[5]
        self.assertIn("Tool: run_bash [результат]", result_block)
        self.assertIn("╔══", result_block)
        self.assertIn("╚", result_block)
        self.assertIn(long_result.replace("\n", "\n║ "), result_block)
        self.assertNotIn("…", result_block)

    def test_no_ansi_codes_when_color_disabled(self):
        response = {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "get_memory", "arguments": "{}"},
            }],
        }
        logs = self._run(response, tool_result="ок")
        for block in logs:
            self.assertNotIn("\x1b[", block)

if __name__ == "__main__":
    unittest.main()
