"""Температура LLM для оплаченных creativity-циклов."""

import unittest
from unittest import mock

import wallet
from tests.agent_common import RunLoopTestCase, agent, agent_loop


class CreativityTemperatureTests(RunLoopTestCase):
    def test_creativity_reserve_overrides_temperature_for_exact_cycles(self):
        wallet.credit(self.paths.wallet, 2, "творческая задача", payment_id="p-1")
        wallet.spend(
            self.paths.wallet, 2, "придумать идеи", "creativity"
        )
        self.cfg.temperature = 0.85
        temperatures = []
        responses = [
            {"role": "assistant", "content": "шаг", "tool_calls": None}
            for _ in range(3)
        ]

        def fake_call_llm(client, model, messages, tools, temperature=0.7,
                          reasoning_effort=None):
            if not responses:
                raise KeyboardInterrupt
            temperatures.append(temperature)
            return responses.pop(0)

        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm):
            agent.run_loop(self.paths, self.cfg)

        self.assertEqual(temperatures, [1.4, 1.4, 0.85])
        self.assertEqual(wallet.wallet_summary(self.paths)["creativity_cycles"], 0)

    def test_spend_tool_starts_creativity_on_next_iteration(self):
        wallet.credit(self.paths.wallet, 2, "идеи", payment_id="p-1")
        self.cfg.temperature = 0.85
        responses = [{
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "money", "type": "function", "function": {
                "name": "money_spend",
                "arguments": '{"units": 2, "purpose": "идеи", "type": "creativity"}',
            }}],
        }]
        responses.extend(
            {"role": "assistant", "content": "шаг", "tool_calls": None}
            for _ in range(2)
        )
        temperatures = []

        def fake_call_llm(client, model, messages, tools, temperature=0.7,
                          reasoning_effort=None):
            if not responses:
                raise KeyboardInterrupt
            temperatures.append(temperature)
            return responses.pop(0)

        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm):
            agent.run_loop(self.paths, self.cfg)

        self.assertEqual(temperatures, [0.85, 1.4, 1.4])
        self.assertEqual(wallet.wallet_summary(self.paths)["creativity_cycles"], 0)


if __name__ == "__main__":
    unittest.main()
