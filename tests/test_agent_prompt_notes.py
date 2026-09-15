"""Тесты agent.build_messages: роли заметок и анти-ступор."""


import json
import shutil
import tempfile
import unittest

from tests.agent_common import (
    agent, make_agent_dir, _paths, _text_iter, _tool_iter,
)


class SystemRolePlacementTests(unittest.TestCase):
    """Роль system — только у первого сообщения запроса (системного промпта).

    Chat-шаблоны ряда моделей (Qwen3.8 GGUF в LM Studio и др.) отвергают
    запрос ошибкой 400 «System message must be at the beginning», если
    system-сообщение встречается не первым. Все служебные заметки —
    пробуждение, «скоро сон», «ты зациклился» — обязаны уходить ролью user.
    """

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-role-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def _assert_system_only_first(self, messages):
        self.assertEqual(
            [i for i, m in enumerate(messages) if m["role"] == "system"], [0]
        )

    def test_plain_tick_has_single_system_message(self):
        data = {"iterations": [_text_iter("дело", n=1)]}
        messages = agent.build_messages(data, self.paths)
        self._assert_system_only_first(messages)

    def test_wake_up_note_is_user(self):
        data = {
            "agent": "bot", "session": 2,
            "woke_up_at": "2026-09-09T00:00:00", "iterations": [],
        }
        messages = agent.build_messages(data, self.paths)
        self._assert_system_only_first(messages)
        self.assertEqual(messages[1]["role"], "user")  # заметка — не system

    def test_sleep_warning_note_is_user(self):
        # следующая итерация — 20-я: впервые появляется заметка «скоро сон»
        data = {"iterations": [_text_iter("шаг", n=i) for i in range(1, 20)]}
        messages = agent.build_messages(data, self.paths)
        self._assert_system_only_first(messages)
        self.assertEqual(messages[-2]["role"], "user")

    def test_repeat_alert_note_is_user(self):
        data = {"iterations": [_tool_iter(n=i) for i in range(1, 4)]}
        messages = agent.build_messages(data, self.paths)
        self._assert_system_only_first(messages)
        self.assertEqual(messages[-2]["role"], "user")


class RepeatAlertTests(unittest.TestCase):
    """Анти-ступор: user-заметка при серии одинаковых tool-вызовов."""

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-repeat-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def test_no_alert_below_threshold(self):
        # 2 одинаковые итерации — порог REPEAT_STREAK_ALERT (3) не достигнут
        data = {"iterations": [_tool_iter(n=1), _tool_iter(n=2)]}
        messages = agent.build_messages(data, self.paths)
        self.assertEqual([m["role"] for m in messages],
                         ["system", "assistant", "tool", "assistant", "tool", "user"])

    def test_alert_after_three_identical_iterations(self):
        data = {"iterations": [_tool_iter(n=1), _tool_iter(n=2), _tool_iter(n=3)]}
        messages = agent.build_messages(data, self.paths)
        # заметка стоит последней перед финальным user-сообщением
        self.assertEqual(messages[-2]["role"], "user")
        self.assertIn("Одинаковое действие повторяется 3 итерации", messages[-2]["content"])
        self.assertIn("run_bash", messages[-2]["content"])
        self.assertIn("echo hi", messages[-2]["content"])
        self.assertTrue(messages[-1]["content"].endswith(agent.USER_MESSAGE))

    def test_alert_mentions_multiple_repeats_in_streak(self):
        data = {"iterations": [_tool_iter(n=i) for i in range(1, 8)]}
        messages = agent.build_messages(data, self.paths)
        self.assertIn("Одинаковое действие повторяется 7 итераций", messages[-2]["content"])

    def test_streak_broken_by_different_call(self):
        other = _tool_iter(n=2)
        other["assistant_message"]["tool_calls"][0]["function"]["arguments"] = '{"command": "ls"}'
        data = {"iterations": [_tool_iter(n=1), other, _tool_iter(n=3)]}
        messages = agent.build_messages(data, self.paths)
        # серия считается только с конца: после отличающегося вызова — одна итерация,
        # заметки нет; сообщение перед user — tool-результат
        self.assertEqual(messages[-1]["role"], "user")
        self.assertEqual(messages[-2]["role"], "tool")
        self.assertEqual(len(messages), 8)

    def test_streak_broken_by_text_iteration(self):
        data = {"iterations": [_tool_iter(n=1), _text_iter("думал", n=2), _tool_iter(n=3)]}
        messages = agent.build_messages(data, self.paths)
        system_messages = [m for m in messages if m["role"] == "system"]
        self.assertEqual(len(system_messages), 1)  # только основной промпт

    def test_alert_not_triggered_by_text_iterations(self):
        data = {"iterations": [_text_iter("а", n=1), _text_iter("а", n=2), _text_iter("а", n=3)]}
        messages = agent.build_messages(data, self.paths)
        self.assertEqual(len(messages), 5)  # system + 3 assistant + user, без заметки

    def test_long_arguments_truncated_in_alert(self):
        long_call = {
            "n": 1,
            "timestamp": "2026-09-09T00:00:00",
            "user": agent.USER_MESSAGE,
            "assistant_message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "run_bash",
                                 "arguments": json.dumps({"command": "echo " + "B" * 500})},
                }],
            },
            "tool_results": [],
        }
        data = {"iterations": [dict(long_call), dict(long_call), dict(long_call)]}
        messages = agent.build_messages(data, self.paths)
        alert = messages[-2]["content"]
        self.assertNotIn("B" * 200, alert)
        self.assertIn("…", alert)

if __name__ == "__main__":
    unittest.main()
