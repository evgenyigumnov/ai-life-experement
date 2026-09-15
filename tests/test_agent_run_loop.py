"""Тесты agent.run_loop: запись истории и round-trip с моком LLM."""


import json
import unittest
from unittest import mock

from tests.agent_common import RunLoopTestCase, agent, agent_loop, env


class RunLoopHistoryTests(RunLoopTestCase):
    """Полный цикл с моком LLM; run_bash исполняется в реальной песочнице."""

    def test_full_loop_records_iterations(self):
        tool_response = {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "run_bash",
                             "arguments": json.dumps({"command": "echo hi-loop && pwd"})},
            }],
        }
        text_response = {"role": "assistant", "content": "готово", "tool_calls": None}

        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", self._script_llm([tool_response, text_response])), \
             env(ENABLE_BASH_TOOL="1"):  # run_bash по умолчанию выключен
            agent.run_loop(self.paths, self.cfg)  # завершится по KeyboardInterrupt

        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual([it["n"] for it in data["iterations"]], [1, 2])

        first = data["iterations"][0]
        self.assertIsNone(first["assistant_message"]["content"])
        result = first["tool_results"][0]
        self.assertEqual(result["tool_call_id"], "call_1")
        self.assertEqual(result["tool"], "run_bash")
        self.assertIn("hi-loop", result["result"])
        self.assertIn("/root", result["result"])  # песочница, а не хост

        second = data["iterations"][1]
        self.assertEqual(second["assistant_message"]["content"], "готово")
        self.assertEqual(second["tool_results"], [])

        # round-trip: история воспроизводится корректной последовательностью
        messages = agent.build_messages(data, self.paths)
        self.assertEqual([m["role"] for m in messages],
                         ["system", "assistant", "tool", "assistant", "user"])
        # без остаточных tmp-файлов
        self.assertEqual([p.name for p in self.folder.glob("*.tmp")], [])

    def test_empty_response_recorded_as_error_iteration(self):
        empty = {"role": "assistant", "content": None, "tool_calls": None}
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", self._script_llm([empty])):
            agent.run_loop(self.paths, self.cfg)

        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual(len(data["iterations"]), 1)
        record = data["iterations"][0]
        self.assertIn("error", record)
        self.assertNotIn("assistant_message", record)
        self.assertIn("пустой ответ модели", record["error"])
        messages = agent.build_messages(data, self.paths)
        self.assertIn("[сбой итерации:", messages[1]["content"])

    def test_empty_string_response_recorded_as_error_iteration(self):
        # регрессия итерации №5 из лога: content="" (только reasoning)
        # раньше записывался как валидная пустая итерация
        empty_string = {"role": "assistant", "content": "", "tool_calls": None}
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", self._script_llm([empty_string])):
            agent.run_loop(self.paths, self.cfg)

        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual(len(data["iterations"]), 1)
        record = data["iterations"][0]
        self.assertIn("error", record)
        self.assertIn("пустой ответ модели", record["error"])

    def test_restart_continues_numbering(self):
        # первая сессия: одна текстовая итерация
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", self._script_llm(
                 [{"role": "assistant", "content": "первая"}])):
            agent.run_loop(self.paths, self.cfg)
        # вторая сессия: ещё одна
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", self._script_llm(
                 [{"role": "assistant", "content": "вторая"}])):
            agent.run_loop(self.paths, self.cfg)

        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual([it["n"] for it in data["iterations"]], [1, 2])
        messages = agent.build_messages(data, self.paths)
        self.assertEqual([m["content"] for m in messages if m["role"] == "assistant"],
                         ["первая", "вторая"])

if __name__ == "__main__":
    unittest.main()
