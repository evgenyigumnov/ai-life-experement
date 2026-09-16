"""Живой smoke-тест LLM из .env (обычный режим допускает skip)."""

import json
import sys
import unittest
from unittest import mock

import openai

from tests.helpers import PROJECT_ROOT
from tests.live_testkit import (
    LiveUnavailable as _LiveUnavailable,
    _check_reachable,
    _fail_fast_sleep,
    _load_live_config,
    _skip_or_fail,
)

sys.path.insert(0, str(PROJECT_ROOT))
import agent_history  # noqa: E402
import agent_usage  # noqa: E402
import llm  # noqa: E402


class LiveLlmSmokeTests(unittest.TestCase):
    """Один минимальный запрос к боевому серверу из .env."""

    @classmethod
    def setUpClass(cls):
        try:
            cfg = _load_live_config()
            _check_reachable(cfg)
        except _LiveUnavailable as exc:
            _skip_or_fail(exc)
        cls.cfg = cfg

    def _call_live(self):
        client = llm.make_client(self.cfg)
        messages = [{
            "role": "user",
            "content": "Ответь ровно одним словом: ок",
        }]
        with mock.patch.object(llm.time, "sleep", side_effect=_fail_fast_sleep):
            try:
                return llm.call_llm(
                    client, self.cfg.model, messages, tools=None, temperature=0.0,
                    reasoning_effort=self.cfg.reasoning_effort,
                )
            except (openai.BadRequestError, _LiveUnavailable) as exc:
                _skip_or_fail(exc)

    def test_minimal_roundtrip_serializable(self):
        response = self._call_live()
        record = agent_history._serialize_message(response)
        self.assertIsNotNone(
            record, "сервер вернул ответ без content и без tool_calls"
        )
        self.assertEqual(record["role"], "assistant")
        if record.get("content") is None:
            self.assertTrue(record.get("tool_calls"), "пустой assistant-ответ")
        else:
            self.assertIsInstance(record["content"], str)
            self.assertTrue(record["content"].strip(), "пустой текст ответа")
        prompt_tokens = agent_usage._extract_prompt_tokens(response)
        self.assertTrue(prompt_tokens is None or isinstance(prompt_tokens, int))
        json.dumps(record, ensure_ascii=False)


if __name__ == "__main__":
    unittest.main()
