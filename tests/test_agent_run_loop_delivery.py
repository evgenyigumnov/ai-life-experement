"""Тесты agent.run_loop: статус непрочитанных сообщений создателя."""


import json
import unittest
from unittest import mock

from tests.agent_common import (
    agent, agent_loop, append_message, SENDER_CREATOR, RunLoopTestCase,
)


class RunLoopDeliveryTests(RunLoopTestCase):
    """Каждый тик сообщает о непрочитанном, не вставляя его текст."""

    def test_unread_creator_message_announced_without_text(self):
        message_text = "привет, займись отчётом"
        append_message(self.paths.messages, SENDER_CREATOR, message_text)
        captured = []
        logs = []

        def fake_call_llm(client, model, messages, tools, temperature=0.7,
                          reasoning_effort=None):
            captured.append(json.dumps(messages, ensure_ascii=False))
            if len(captured) <= 2:
                return {"role": "assistant", "content": f"ответ {len(captured)}"}
            raise KeyboardInterrupt

        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm), \
             mock.patch.object(agent_loop, "_log", logs.append):
            agent.run_loop(self.paths, self.cfg)

        for payload in captured[:2]:
            self.assertIn("У тебя есть непрочитанные сообщения", payload)
            self.assertNotIn(message_text, payload)
        self.assertTrue(any("Непрочитанных сообщений" in entry for entry in logs))
        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertNotIn("seen_creator_messages", data)
        self.assertEqual(len(data["iterations"]), 2)
        messages = json.loads(self.paths.messages.read_text(encoding="utf-8"))
        self.assertFalse(messages["messages"][0]["read"])

    def test_failed_llm_call_keeps_message_unread(self):
        """Сбойный запрос не меняет read-флаг сообщения."""
        message_text = "важное сообщение"
        append_message(self.paths.messages, SENDER_CREATOR, message_text)

        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm",
                               side_effect=[ValueError("сбой сервера"), KeyboardInterrupt]):
            agent.run_loop(self.paths, self.cfg)

        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual(len(data["iterations"]), 1)
        self.assertIn("error", data["iterations"][0])
        self.assertNotIn("seen_creator_messages", data)
        messages = agent.build_messages(data, self.paths)
        payload = json.dumps(messages, ensure_ascii=False)
        self.assertIn("У тебя есть непрочитанные сообщения", payload)
        self.assertNotIn(message_text, payload)
        stored_messages = json.loads(self.paths.messages.read_text(encoding="utf-8"))
        self.assertFalse(stored_messages["messages"][0]["read"])

    def test_old_delivery_counter_is_removed_without_affecting_status(self):
        """Старый счётчик мигрирует без вставки текстов переписки."""
        message_text = "старое сообщение"
        append_message(self.paths.messages, SENDER_CREATOR, message_text)
        data = {
            "agent": "bot", "session": 1, "seen_creator_messages": 999,
            "iterations": [],
        }
        self.paths.mind_loop.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm",
                               side_effect=[{"role": "assistant", "content": "готово"},
                                            KeyboardInterrupt]):
            agent.run_loop(self.paths, self.cfg)

        updated = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertNotIn("seen_creator_messages", updated)
        payload = json.dumps(agent.build_messages(updated, self.paths), ensure_ascii=False)
        self.assertIn("У тебя есть непрочитанные сообщения", payload)
        self.assertNotIn(message_text, payload)


if __name__ == "__main__":
    unittest.main()
