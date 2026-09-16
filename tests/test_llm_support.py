"""Тесты сериализации SDK-сообщений и создания клиента."""

import sys
import unittest
from types import SimpleNamespace

from tests.helpers import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))
import llm  # noqa: E402
from config_env import Config  # noqa: E402
from tests.test_llm import FakeClient, _msg, _resp  # noqa: E402


class SdkUsageSerializationTests(unittest.TestCase):
    """usage не должен ломать сериализацию SDK-сообщения."""

    def _call(self):
        from openai.types.chat import ChatCompletionMessage
        from openai.types.completion_usage import CompletionUsage

        sdk_message = ChatCompletionMessage(role="assistant", content="живой ответ")
        usage = CompletionUsage(prompt_tokens=469, completion_tokens=5, total_tokens=474)
        client = FakeClient([_resp(sdk_message, usage=usage)])
        return llm.call_llm(
            client, "model-x", [{"role": "user", "content": "?"}], None
        ), sdk_message

    def test_model_dump_after_usage_still_works(self):
        message, _ = self._call()
        dumped = message.model_dump()
        self.assertEqual(dumped["content"], "живой ответ")
        self.assertNotIn("usage", dumped)

    def test_usage_and_content_accessible(self):
        message, _ = self._call()
        self.assertEqual(message.content, "живой ответ")
        self.assertEqual(message.usage.prompt_tokens, 469)
        self.assertEqual(message.usage.total_tokens, 474)

    def test_original_sdk_message_not_mutated(self):
        message, sdk_message = self._call()
        self.assertNotIsInstance(message, type(sdk_message))
        self.assertFalse(hasattr(sdk_message, "usage"))
        sdk_message.model_dump()

    def test_wrapper_dump_for_plain_namespace_message(self):
        wrapper = llm._MessageWithUsage(
            _msg("простой ответ", tool_calls=None), SimpleNamespace(prompt_tokens=3)
        )
        dumped = wrapper.model_dump()
        self.assertEqual(dumped["role"], "assistant")
        self.assertEqual(dumped["content"], "простой ответ")


class MakeClientTests(unittest.TestCase):
    def test_client_configured_from_cfg(self):
        cfg = Config(
            base_url="http://localhost:9/v1",
            model="m",
            api_key="sk-test",
            agents_root=None,
        )
        client = llm.make_client(cfg)
        self.assertEqual(client.api_key, "sk-test")
        self.assertTrue(str(client.base_url).startswith("http://localhost:9/v1"))
        self.assertEqual(client.max_retries, 0)
        self.assertEqual(llm.REQUEST_TIMEOUT, 600.0)
        self.assertEqual(client.timeout, llm.REQUEST_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
