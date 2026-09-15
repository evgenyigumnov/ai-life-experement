"""Тесты извлечения usage и reasoning из ответов LLM."""


import unittest
from types import SimpleNamespace

from tests.agent_common import agent


class ExtractPromptTokensTests(unittest.TestCase):
    """`_extract_prompt_tokens`: SDK-объект, dict, отсутствие usage."""

    def test_sdk_style_object(self):
        response = SimpleNamespace(
            usage=SimpleNamespace(prompt_tokens=142, total_tokens=200)
        )
        self.assertEqual(agent._extract_prompt_tokens(response), 142)

    def test_dict_response(self):
        response = {"usage": {"prompt_tokens": 7}}
        self.assertEqual(agent._extract_prompt_tokens(response), 7)

    def test_usage_missing(self):
        self.assertIsNone(agent._extract_prompt_tokens(SimpleNamespace(usage=None)))
        self.assertIsNone(agent._extract_prompt_tokens({"content": "ок"}))

    def test_usage_without_prompt_tokens(self):
        self.assertIsNone(
            agent._extract_prompt_tokens({"usage": {"completion_tokens": 5}})
        )

    def test_none_response(self):
        self.assertIsNone(agent._extract_prompt_tokens(None))


class ExtractCompletionTokensTests(unittest.TestCase):
    """`_extract_completion_tokens` и `_extract_reasoning_tokens` (usage от LLM)."""

    def test_sdk_style_object_with_details(self):
        response = SimpleNamespace(
            usage=SimpleNamespace(
                prompt_tokens=786,
                completion_tokens=58,
                completion_tokens_details=SimpleNamespace(reasoning_tokens=40),
            )
        )
        self.assertEqual(agent._extract_completion_tokens(response), 58)
        self.assertEqual(agent._extract_reasoning_tokens(response), 40)

    def test_dict_usage_with_details(self):
        response = {
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 7,
                "completion_tokens_details": {"reasoning_tokens": 3},
            }
        }
        self.assertEqual(agent._extract_completion_tokens(response), 7)
        self.assertEqual(agent._extract_reasoning_tokens(response), 3)

    def test_no_details_yields_none_reasoning_tokens(self):
        response = {"usage": {"prompt_tokens": 1, "completion_tokens": 2}}
        self.assertEqual(agent._extract_completion_tokens(response), 2)
        self.assertIsNone(agent._extract_reasoning_tokens(response))

    def test_zero_reasoning_tokens_kept(self):
        response = {"usage": {"completion_tokens": 2,
                               "completion_tokens_details": {"reasoning_tokens": 0}}}
        self.assertEqual(agent._extract_reasoning_tokens(response), 0)

    def test_usage_missing(self):
        self.assertIsNone(agent._extract_completion_tokens(SimpleNamespace(usage=None)))
        self.assertIsNone(agent._extract_reasoning_tokens(SimpleNamespace(usage=None)))
        self.assertIsNone(agent._extract_completion_tokens({"content": "ок"}))

    def test_none_response(self):
        self.assertIsNone(agent._extract_completion_tokens(None))
        self.assertIsNone(agent._extract_reasoning_tokens(None))


class ExtractReasoningTests(unittest.TestCase):
    """`_extract_reasoning`: reasoning_content / reasoning, обёртка, пустые."""

    def test_reasoning_content_attr(self):
        response = SimpleNamespace(reasoning_content="шаг за шагом…")
        self.assertEqual(agent._extract_reasoning(response), "шаг за шагом…")

    def test_reasoning_dict_key(self):
        self.assertEqual(agent._extract_reasoning({"reasoning": "думаю"}), "думаю")

    def test_reasoning_content_preferred_over_reasoning(self):
        response = {
            "reasoning_content": "основное",
            "reasoning": "запасное",
        }
        self.assertEqual(agent._extract_reasoning(response), "основное")

    def test_wrapper_delegation(self):
        """Реальный путь: call_llm возвращает _MessageWithUsage поверх SDK-сообщения."""
        from llm import _MessageWithUsage

        wrapped = _MessageWithUsage(
            SimpleNamespace(content=None, tool_calls=[], reasoning_content="внутри обёртки"),
            SimpleNamespace(prompt_tokens=1),
        )
        self.assertEqual(agent._extract_reasoning(wrapped), "внутри обёртки")

    def test_whitespace_only_is_none(self):
        self.assertIsNone(agent._extract_reasoning({"reasoning_content": "   \n"}))

    def test_missing_and_none(self):
        self.assertIsNone(agent._extract_reasoning(SimpleNamespace(content="ок")))
        self.assertIsNone(agent._extract_reasoning({"role": "assistant"}))
        self.assertIsNone(agent._extract_reasoning(None))

if __name__ == "__main__":
    unittest.main()
