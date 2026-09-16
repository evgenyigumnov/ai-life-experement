"""Тесты agent.run_loop: сон, архив сессии и новая нумерация."""


import json
import unittest
from unittest import mock

from tests.agent_common import (
    RunLoopTestCase, _run_loop_mocked, agent, agent_loop, agent_sleep,
)


class RunLoopSleepArchiveTests(RunLoopTestCase):
    """Интеграция: сессии по 2 итерации — сон с архивом и пробуждение."""

    def test_sleep_cycle_archives_history_and_restarts_numbering(self):
        """Интеграция: сессии по 2 итерации — предупреждение, сон с архивом, пробуждение."""
        captured = []
        logs = []

        def fake_call_llm(client, model, messages, tools, temperature=0.7,
                          reasoning_effort=None):
            captured.append(json.dumps(messages, ensure_ascii=False))
            if len(captured) <= 5:
                return {"role": "assistant", "content": f"ответ {len(captured)}"}
            raise KeyboardInterrupt

        with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
             mock.patch.object(agent_loop, "call_llm", fake_call_llm), \
             mock.patch.object(agent_sleep, "SESSION_ITERATIONS", 2), \
             mock.patch.object(agent_sleep, "SLEEP_WARN_REMAINING", 1), \
             mock.patch.object(agent_loop, "_log", logs.append):
            agent.run_loop(self.paths, self.cfg)

        # 1-я итерация первой жизни: осталось 1 итерацию — предупреждение есть
        self.assertIn("осталось 1 итерацию", captured[0])
        self.assertNotIn("проснулся", captured[0])
        # 2-я итерация: последняя перед сном — вместо тика user-директива
        self.assertIn("Последняя итерация перед сном", captured[1])
        self.assertIn(agent.LAST_ITERATION_MESSAGE, captured[1])
        self.assertIn("ответ 1", captured[1])  # история текущей сессии видна
        # 3-я итерация: пробуждение — истории прошлой сессии в запросе нет
        self.assertIn("проснулся", captured[2])
        self.assertNotIn("ответ 1", captured[2])
        self.assertNotIn("ответ 2", captured[2])
        # 4-я итерация: вторая сессия, видна только её первая итерация
        self.assertNotIn("ответ 2", captured[3])
        self.assertIn("ответ 3", captured[3])
        self.assertIn("Последняя итерация перед сном", captured[3])
        # 5-я итерация: снова пробуждение
        self.assertIn("проснулся", captured[4])
        self.assertNotIn("ответ 3", captured[4])

        # консоль наблюдения: по два сообщения о сне и пробуждении
        sleep_logs = [entry for entry in logs if "😴 Сон" in entry]
        wake_logs = [entry for entry in logs if "🌞 Пробуждение" in entry]
        self.assertEqual(len(sleep_logs), 2)
        self.assertEqual(len(wake_logs), 2)
        self.assertIn("сессия 1 завершена", sleep_logs[0])
        self.assertIn("заархивирована", sleep_logs[0])
        self.assertIn("сессия 2", wake_logs[0])
        self.assertIn("сессия 3", wake_logs[1])

        # два архива: в каждом своя сессия, отсчёт итераций с 1
        archives = sorted(
            self.folder.glob("mind-loop-*.json"),
            key=lambda p: json.loads(p.read_text(encoding="utf-8")).get("session") or 1,
        )
        self.assertEqual(len(archives), 2)
        for path in archives:
            self.assertRegex(path.name, r"^mind-loop-\d{8}-\d{6}(-\d+)?\.json$")
        first, second = (json.loads(p.read_text(encoding="utf-8")) for p in archives)
        self.assertEqual(first["session"], 1)
        self.assertEqual([it["n"] for it in first["iterations"]], [1, 2])
        self.assertEqual(
            [it["assistant_message"]["content"] for it in first["iterations"]],
            ["ответ 1", "ответ 2"],
        )
        # user-поле записи хранит фактически отправленное сообщение:
        # обычный тик и директиву последней итерации
        self.assertEqual(first["iterations"][0]["user"], agent.USER_MESSAGE)
        self.assertEqual(first["iterations"][1]["user"], agent.LAST_ITERATION_MESSAGE)
        self.assertEqual(second["session"], 2)
        self.assertEqual([it["n"] for it in second["iterations"]], [1, 2])
        self.assertEqual(
            [it["assistant_message"]["content"] for it in second["iterations"]],
            ["ответ 3", "ответ 4"],
        )

        # текущая (третья) жизнь: свежий mind-loop.json, отсчёт с 1
        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual(data["session"], 3)
        self.assertIn("woke_up_at", data)
        self.assertEqual([it["n"] for it in data["iterations"]], [1])
        self.assertEqual(
            data["iterations"][0]["assistant_message"]["content"], "ответ 5"
        )

        # round-trip: в запросе — только итерация текущей сессии
        messages = agent.build_messages(data, self.paths)
        assistant = [m["content"] for m in messages if m["role"] == "assistant"]
        self.assertEqual(assistant, ["ответ 5"])

        # без остаточных tmp-файлов
        self.assertEqual([p.name for p in self.folder.glob("*.tmp")], [])

    def test_agent_can_sleep_before_thirty_iterations(self):
        reason = "устал: контекст стал слишком большим по токенам"
        sleep_response = {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": "sleep-1", "type": "function",
                "function": {
                    "name": "sleep",
                    "arguments": json.dumps({"reason": reason}),
                },
            }],
        }
        logs, _ = _run_loop_mocked(
            self.paths,
            self.cfg,
            [sleep_response, {"role": "assistant", "content": "после сна"}],
        )

        archives = list(self.folder.glob("mind-loop-*.json"))
        self.assertEqual(len(archives), 1)
        archived = json.loads(archives[0].read_text(encoding="utf-8"))
        self.assertEqual(archived["session"], 1)
        self.assertEqual(archived["sleep_reason"], reason)
        self.assertEqual([item["n"] for item in archived["iterations"]], [1])
        self.assertEqual(archived["iterations"][0]["user"], agent.USER_MESSAGE)
        sleep_result = archived["iterations"][0]["tool_results"][0]
        self.assertEqual(sleep_result["tool"], "sleep")
        self.assertIn(reason, sleep_result["result"])

        current = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual(current["session"], 2)
        self.assertEqual([item["n"] for item in current["iterations"]], [1])
        self.assertEqual(
            current["iterations"][0]["assistant_message"]["content"],
            "после сна",
        )
        self.assertEqual(len([entry for entry in logs if "😴 Сон" in entry]), 1)

if __name__ == "__main__":
    unittest.main()
