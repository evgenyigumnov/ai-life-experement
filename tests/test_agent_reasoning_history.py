"""Проверка сохранения reasoning и его передачи в следующий тик."""

import copy
import json
import unittest
from unittest import mock

from tests.agent_common import RunLoopTestCase, agent, agent_loop


class ReasoningHistoryTests(RunLoopTestCase):
    """Reasoning проходит путь ответ → mind-loop.json → следующий payload."""

    def test_reasoning_is_replayed_in_next_llm_request(self):
        reasoning = "проверил план и выбрал следующий шаг"
        responses = [
            {"role": "assistant", "content": "готово",
             "reasoning_content": reasoning},
            {"role": "assistant", "content": "продолжаю"},
        ]
        requests = []

        def fake_call(client, model, messages, tools, **kwargs):
            requests.append(copy.deepcopy(messages))
            if responses:
                return responses.pop(0)
            raise KeyboardInterrupt

        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call):
            agent.run_loop(self.paths, self.cfg)

        saved = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["iterations"][0]["assistant_message"]["reasoning_content"],
            reasoning,
        )
        historical = [m for m in requests[1] if m.get("role") == "assistant"]
        self.assertEqual(historical[0]["content"], "готово")
        self.assertEqual(historical[0]["reasoning_content"], reasoning)

    def test_reasoning_alias_is_replayed_without_renaming(self):
        reasoning = "альтернативное поле провайдера"
        record = {
            "assistant_message": {
                "role": "assistant", "content": "ответ", "reasoning": reasoning,
            },
            "tool_results": [],
        }
        messages = agent.build_messages({"iterations": [record]}, self.paths)
        assistant = next(m for m in messages if m["role"] == "assistant")
        self.assertEqual(assistant["reasoning"], reasoning)
        self.assertNotIn("reasoning_content", assistant)

    def test_sdk_extra_reasoning_attribute_survives_model_dump(self):
        class SdkMessage:
            reasoning_content = "мысль из атрибута"

            @staticmethod
            def model_dump():
                return {"role": "assistant", "content": "ответ"}

        self.assertEqual(
            agent._serialize_message(SdkMessage())["reasoning_content"],
            "мысль из атрибута",
        )


if __name__ == "__main__":
    unittest.main()
