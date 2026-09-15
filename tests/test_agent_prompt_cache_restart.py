"""Тесты кеша промпта: холодный перезапуск и кеш консоли."""


import json
import unittest

from tests.agent_common import append_message, SENDER_CREATOR
from tests.test_agent_prompt_cache import _PromptCacheBase


class SystemPromptCacheRestartTests(_PromptCacheBase):
    """Перезапуск процесса и кеш показа промпта в консоли (console_state)."""

    def test_cold_restart_replays_exact_next_request_after_three_iterations(self):
        # Отдельно пишем сериализованный текст каждого запроса: это эталон
        # фактического payload, а не только восстановленной структуры.
        continuation_trace = self.folder / "continuation-llm.jsonl"
        restart_trace = self.folder / "restart-llm.jsonl"
        creator_text = "сообщение создателя на третьей итерации"

        def creator_writes_on_third_iteration(n):
            if n == 3:
                append_message(self.paths.messages, SENDER_CREATOR, creator_text)

        responses = [
            self._tool_response(1),
            self._text_response(2),
            self._tool_response(3),
        ]
        self._run_loop(
            responses,
            request_trace_path=continuation_trace,
            on_iteration=creator_writes_on_third_iteration,
        )
        continuation_payloads = continuation_trace.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(continuation_payloads), 4)
        self.assertIn("У тебя есть непрочитанные сообщения", continuation_payloads[2])
        self.assertNotIn(creator_text, continuation_payloads[2])

        mind_loop_text = self.paths.mind_loop.read_text(encoding="utf-8")
        self.assertNotIn(creator_text, mind_loop_text)
        stored = json.loads(mind_loop_text)
        self.assertEqual(len(stored["iterations"]), 3)

        # Новый вызов run_loop создаёт состояние процесса заново, но читает
        # тот же mind-loop.json. Первый запрос после такого «перезапуска»
        # должен быть тем же текстом, что и запрос при продолжении без
        # перезапуска. Статус берётся из messages.json, а текст сообщения
        # не попадает ни в один запрос.
        self._run_loop(
            [self._text_response(4)], request_trace_path=restart_trace
        )
        restarted_payloads = restart_trace.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(restarted_payloads), 2)
        self.assertEqual(restarted_payloads[0], continuation_payloads[3])
        self.assertNotIn(creator_text, restarted_payloads[0])

    def test_console_cache_hits_while_prompt_unchanged(self):
        # консоль наблюдения: полный блок промпта печатается один раз,
        # все следующие итерации — короткая строка «без изменений»
        # (кеш console_state), при этом промпт уходит в LLM каждым запросом
        logs: list[str] = []
        responses = [self._text_response(i) for i in range(1, 6)]
        copies, _ = self._run_loop(responses, logs=logs)
        full_blocks = [b for b in logs
                       if "📜 System prompt" in b and "без изменений" not in b]
        short_lines = [b for b in logs if "без изменений" in b]
        self.assertEqual(len(full_blocks), 1)
        self.assertIn("Ты — тестовый агент.", full_blocks[0])
        # итерации 2–6: кеш сработал, полный текст не повторяется
        self.assertEqual(len(short_lines), 5)
        self.assertTrue(short_lines[0].startswith("[итерация 2]"))
        self.assertTrue(short_lines[-1].startswith("[итерация 6]"))
        # но в каждом из 6 запросов промпт реально отправлен и идентичен
        self.assertEqual(len(copies), 6)
        self.assertEqual({c[0]["content"] for c in copies}, {self.PROMPT_TEXT})

if __name__ == "__main__":
    unittest.main()
