"""Тесты llm.py: ретраи, backoff, ошибки и передача параметров."""

import copy
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import httpx2
from openai import APIConnectionError, APIStatusError, InternalServerError, RateLimitError

from tests.helpers import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))
import llm  # noqa: E402
from model_support import (  # noqa: E402
    DEEPSEEK_FLASH_MODEL, DEEPSEEK_V41_FLASH_MODEL, GLM_53_FLASH_MODEL,
)


def _msg(content="ок", tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _resp(message, usage=None):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _http_err(cls, status: int):
    request = httpx2.Request("POST", "http://test/v1")
    return cls("http error", response=httpx2.Response(status, request=request), body=None)


class FakeClient:
    """Клиент, разыгрывающий сценарий: исключение или объект ответа."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def chat(self):
        client = self

        class _Completions:
            @staticmethod
            def create(**kwargs):
                return client.create(**kwargs)

        class _Chat:
            completions = _Completions()

        return _Chat()


class CallLlmTests(unittest.TestCase):
    def _run(self, script, tools=None, **kwargs):
        client = FakeClient(script)
        sleeps = []
        with mock.patch.object(llm.time, "sleep", side_effect=lambda s: sleeps.append(s)):
            message = llm.call_llm(
                client, "model-x", [{"role": "user", "content": "?"}], tools, **kwargs
            )
        return message, client, sleeps

    def test_success_first_try(self):
        message, client, sleeps = self._run([_resp(_msg("привет"))])
        self.assertEqual(message.content, "привет")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(sleeps, [])

    def test_tools_and_messages_passed_through(self):
        tools = [{"type": "function", "function": {"name": "run_bash"}}]
        messages = [{"role": "user", "content": "?"}]
        _, client, _ = self._run([_resp(_msg())], tools=tools)
        self.assertEqual(client.calls[0]["tools"], tools)
        self.assertEqual(client.calls[0]["model"], "model-x")
        self.assertEqual(client.calls[0]["messages"], messages)

    def test_empty_tools_not_sent(self):
        _, client, _ = self._run([_resp(_msg())], tools=[])
        self.assertNotIn("tools", client.calls[0])

    def test_messages_forwarded_unchanged(self):
        messages = [
            {"role": "system", "content": "Ты — агент.\nПравила:\n"},
            {"role": "user", "content": "шаг"},
        ]
        snapshot = copy.deepcopy(messages)
        client = FakeClient([_resp(_msg("ок"))])
        llm.call_llm(client, "model-x", messages, None)
        self.assertEqual(client.calls[0]["messages"], snapshot)
        self.assertEqual(messages, snapshot)

    def test_temperature_defaults_and_custom_value(self):
        _, client, _ = self._run([_resp(_msg())])
        self.assertEqual(client.calls[0]["temperature"], 0.7)
        _, client, _ = self._run([_resp(_msg())], temperature=0.7)
        self.assertEqual(client.calls[0]["temperature"], 0.7)

    def test_reasoning_effort(self):
        for value in ("max", "xhigh"):
            with self.subTest(effort=value):
                _, client, _ = self._run([_resp(_msg())], reasoning_effort=value)
                self.assertEqual(client.calls[0]["reasoning_effort"], value)
        _, client, _ = self._run([_resp(_msg())])
        self.assertNotIn("reasoning_effort", client.calls[0])

    def test_known_models_get_compatible_reasoning_values(self):
        cases = (
            (GLM_53_FLASH_MODEL, "xhigh", "max"),
            (GLM_53_FLASH_MODEL, "none", "low"),
            (DEEPSEEK_V41_FLASH_MODEL, "xhigh", "xhigh"),
            (DEEPSEEK_FLASH_MODEL, "xhigh", "high"),
        )
        for model, configured, expected in cases:
            with self.subTest(model=model, configured=configured):
                client = FakeClient([_resp(_msg())])
                llm.call_llm(
                    client, model, [{"role": "user", "content": "?"}],
                    None, reasoning_effort=configured,
                )
                self.assertEqual(client.calls[0]["reasoning_effort"], expected)

    def test_deepseek_api_uses_v41_alias_and_thinking_mode(self):
        client = FakeClient([_resp(_msg())])
        llm.call_llm(
            client, "DeepSeek-V4.1-Flash", [{"role": "user", "content": "?"}],
            None, reasoning_effort="max",
        )
        call = client.calls[0]
        self.assertEqual(call["model"], DEEPSEEK_FLASH_MODEL)
        self.assertEqual(call["reasoning_effort"], "max")
        self.assertEqual(call["extra_body"], {"thinking": {"type": "enabled"}})

    def test_deepseek_api_none_disables_thinking(self):
        client = FakeClient([_resp(_msg())])
        llm.call_llm(
            client, DEEPSEEK_FLASH_MODEL, [{"role": "user", "content": "?"}],
            None, reasoning_effort="none",
        )
        self.assertNotIn("reasoning_effort", client.calls[0])
        self.assertEqual(
            client.calls[0]["extra_body"], {"thinking": {"type": "disabled"}}
        )

    def test_retry_on_429(self):
        message, client, sleeps = self._run([_http_err(RateLimitError, 429), _resp(_msg())])
        self.assertEqual(message.content, "ок")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(sleeps, [2.0])

    def test_retry_on_network_error(self):
        request = httpx2.Request("POST", "http://test/v1")
        message, _, sleeps = self._run(
            [APIConnectionError(request=request), APIConnectionError(request=request), _resp(_msg())]
        )
        self.assertEqual(message.content, "ок")
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_retry_on_500_and_nonstandard_502(self):
        message, _, sleeps = self._run(
            [_http_err(InternalServerError, 500), _http_err(APIStatusError, 502), _resp(_msg())]
        )
        self.assertEqual(message.content, "ок")
        self.assertEqual(sleeps, [2.0, 4.0])

    def test_permanent_400_raised_immediately(self):
        with self.assertRaises(APIStatusError):
            self._run([_http_err(APIStatusError, 400), _resp(_msg())])

    def test_empty_choices_is_retryable(self):
        message, client, sleeps = self._run([SimpleNamespace(choices=[]), _resp(_msg())])
        self.assertEqual(message.content, "ок")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(sleeps, [2.0])

    def test_full_backoff_sequence_and_long_pause(self):
        err = _http_err(RateLimitError, 429)
        message, client, sleeps = self._run([err] * 12 + [_resp(_msg("наконец-то"))])
        self.assertEqual(message.content, "наконец-то")
        self.assertEqual(len(client.calls), 13)
        self.assertEqual(
            sleeps,
            [2.0, 4.0, 8.0, 16.0, 60.0, 2.0, 4.0, 8.0, 16.0, 60.0, 2.0, 4.0],
        )

    def test_keyboard_interrupt_during_pause_propagates(self):
        client = FakeClient([_http_err(RateLimitError, 429)] * 5)

        def fake_sleep(seconds):
            if seconds == llm.LONG_PAUSE:
                raise KeyboardInterrupt

        with mock.patch.object(llm.time, "sleep", side_effect=fake_sleep):
            with self.assertRaises(KeyboardInterrupt):
                llm.call_llm(client, "m", [], None)

    def test_usage_is_preserved(self):
        usage = SimpleNamespace(prompt_tokens=142, completion_tokens=58, total_tokens=200)
        message, _, _ = self._run([_resp(_msg("ответ с usage"), usage=usage)])
        self.assertEqual(message.content, "ответ с usage")
        self.assertEqual(message.usage.prompt_tokens, 142)

    def test_dict_message_gets_usage_key(self):
        message_dict = {"role": "assistant", "content": "привет", "tool_calls": None}
        usage = SimpleNamespace(prompt_tokens=10, total_tokens=12)
        result, _, _ = self._run([_resp(message_dict, usage=usage)])
        self.assertIs(result, message_dict)
        self.assertEqual(result["usage"], usage)


if __name__ == "__main__":
    unittest.main()
