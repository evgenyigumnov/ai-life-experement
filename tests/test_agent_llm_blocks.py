"""Тесты блока ответа LLM и вывода reasoning."""


import json
import unittest

from tests.test_agent_iteration_logging import _IterationLoggingBase


class LlmBlockTests(_IterationLoggingBase):
    """Тайминг, токены и reasoning ответа LLM."""

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

    def test_reasoning_only_response_is_logged_and_saved(self):
        """Reasoning-only ответ сохраняется и становится историей тика."""
        response = {
            "role": "assistant",
            "content": None,
            "reasoning_content": "думал, но ничего не решил",
        }
        logs = self._run(response)
        reasoning_blocks = [b for b in logs if "🧠 Reasoning" in b]
        self.assertEqual(len(reasoning_blocks), 1)
        self.assertIn("думал, но ничего не решил", reasoning_blocks[0])
        record = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual(
            record["iterations"][0]["assistant_message"]["reasoning_content"],
            "думал, но ничего не решил",
        )

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


if __name__ == "__main__":
    unittest.main()
