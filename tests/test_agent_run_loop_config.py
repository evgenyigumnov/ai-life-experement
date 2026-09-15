"""Тесты agent.run_loop: параметры запроса из Config и лог промпта."""


import unittest
from unittest import mock

from tests.agent_common import RunLoopTestCase, agent, agent_console, agent_loop
from tests.helpers import env
from tool_context import ToolContext


class RunLoopConfigTests(RunLoopTestCase):
    """Температура, reasoning effort и схема tools — из Config."""

    def test_temperature_passed_from_config(self):
        # температура берётся из Config (TEMPERATURE в .env), а не из дефолта llm
        seen = {}

        def fake_call_llm(client, model, messages, tools, temperature=None,
                          reasoning_effort=None):
            seen["temperature"] = temperature
            raise KeyboardInterrupt

        self.cfg.temperature = 0.85
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm):
            agent.run_loop(self.paths, self.cfg)
        self.assertEqual(seen["temperature"], 0.85)

    def test_reasoning_effort_passed_from_config(self):
        # уровень размышлений берётся из Config (REASONING_EFFORT в .env):
        # None — параметр не отправляется, "max" — максимальный бюджет GLM
        seen = {}

        def fake_call_llm(client, model, messages, tools, temperature=None,
                          reasoning_effort=None):
            seen["reasoning_effort"] = reasoning_effort
            raise KeyboardInterrupt

        self.assertIsNone(self.cfg.reasoning_effort)  # дефолт — не отправлять
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm):
            agent.run_loop(self.paths, self.cfg)
        self.assertIsNone(seen["reasoning_effort"])

        self.cfg.reasoning_effort = "max"
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm):
            agent.run_loop(self.paths, self.cfg)
        self.assertEqual(seen["reasoning_effort"], "max")

    def test_tools_schema_respects_bash_flag(self):
        # в LLM уходит схема без run_bash, когда он выключен в конфиге
        seen = {}

        def fake_call_llm(client, model, messages, tools, temperature=None,
                          reasoning_effort=None):
            seen["tools"] = tools
            raise KeyboardInterrupt

        self.cfg.enable_bash_tool = False
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm):
            agent.run_loop(self.paths, self.cfg)
        names = [t["function"]["name"] for t in seen["tools"]]
        self.assertNotIn("run_bash", names)
        self.assertIn("send_message", names)
        self.assertIn("get_messages", names)

        self.cfg.enable_bash_tool = True
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm):
            agent.run_loop(self.paths, self.cfg)
        names = [t["function"]["name"] for t in seen["tools"]]
        self.assertIn("run_bash", names)

    def test_internet_search_schema_reaches_llm_when_configured(self):
        seen = {}

        def fake_call_llm(client, model, messages, tools, temperature=None,
                          reasoning_effort=None):
            seen["tools"] = tools
            raise KeyboardInterrupt

        with env(BRAVE_KEY="test-brave-key"), \
             mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm):
            agent.run_loop(self.paths, self.cfg)
        names = [t["function"]["name"] for t in seen["tools"]]
        self.assertIn("internet_search", names)

    def test_tool_context_reaches_execution(self):
        seen = {}
        response = {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "vision-1", "type": "function",
                             "function": {"name": "inspect_image",
                                          "arguments": "{}"}}],
        }

        def fake_execute(name, arguments, paths, context):
            seen.update(name=name, arguments=arguments, paths=paths, context=context)
            return "ответ"

        self.cfg.temperature = 0.91
        self.cfg.reasoning_effort = "max"
        with mock.patch.object(agent_loop, "call_llm", return_value=response), \
             mock.patch.object(agent_loop, "execute_tool", fake_execute):
            agent_loop._run_iteration(self.paths, self.cfg, client="shared-client")

        self.assertEqual(seen["name"], "inspect_image")
        self.assertIs(seen["paths"], self.paths)
        self.assertIsInstance(seen["context"], ToolContext)
        self.assertEqual(seen["context"].client, "shared-client")
        self.assertEqual(seen["context"].model, "mock-model")
        self.assertEqual(seen["context"].temperature, 0.91)
        self.assertEqual(seen["context"].reasoning_effort, "max")

    def test_system_prompt_logged_once_until_changed(self):
        # run_loop хранит состояние консоли между итерациями: полный блок
        # системного промпта печатается на первой итерации, дальше —
        # короткая строка «без изменений»
        logs = []
        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", self._script_llm(
                 [{"role": "assistant", "content": "первая"},
                  {"role": "assistant", "content": "вторая"}])), \
             mock.patch.object(agent_loop, "_log", logs.append), \
             mock.patch.object(agent_console, "USE_COLOR", False):
            agent.run_loop(self.paths, self.cfg)  # завершится по KeyboardInterrupt
        full_blocks = [b for b in logs
                       if "📜 System prompt" in b and "без изменений" not in b]
        short_lines = [b for b in logs if "без изменений" in b]
        # полный блок — один, на первой итерации
        self.assertEqual(len(full_blocks), 1)
        self.assertIn("Ты — тестовый агент.", full_blocks[0])
        # дальше — только короткие строки: итерации 2 и 3 (третья обрывается
        # по KeyboardInterrupt уже после лога промпта, до вызова LLM)
        self.assertEqual(len(short_lines), 2)
        self.assertTrue(short_lines[0].startswith("[итерация 2]"))
        self.assertTrue(short_lines[1].startswith("[итерация 3]"))

if __name__ == "__main__":
    unittest.main()
