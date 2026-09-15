"""Тесты фиксированной паузы --loop-pause=N (Config.loop_pause)."""


import json
import shutil
import tempfile
import unittest

from tests.agent_common import (
    agent, append_message, Config, make_agent_dir, SENDER_CREATOR,
    _paths, _run_loop_mocked,
)


class FixedLoopPauseTests(unittest.TestCase):
    """Фиксированная пауза --loop-pause=N (Config.loop_pause): расписание отключено.

    Пауза всегда одна и та же: при молчании создателя она не растёт,
    после его сообщений — не сбрасывается, LOOP_DELAY не применяется.
    Сообщение, написанное прямо во время паузы, по-прежнему прерывает
    её немедленно — фиксированный режим меняет длительность пауз,
    а не отзывчивость агента.
    """

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-fixed-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)
        self.cfg = Config(base_url="http://mock/v1", model="mock-model",
                          api_key="k", agents_root=None, loop_delay=0,
                          loop_pause=7.0)

    @staticmethod
    def _responses(count):
        return [{"role": "assistant", "content": f"ответ {i}"}
                for i in range(1, count + 1)]

    def test_pause_constant_while_creator_silent(self):
        # создатель молчит — пауза не растёт по расписанию, а всегда 7 сек
        logs, sleeps = _run_loop_mocked(self.paths, self.cfg, self._responses(3))
        self.assertEqual(sleeps, [7.0, 7.0, 7.0])
        pause_logs = [l for l in logs if "Фиксированная пауза" in l]
        self.assertEqual(len(pause_logs), 3)
        self.assertNotIn("Создатель молчит", "\n".join(logs))

    def test_creator_message_does_not_change_pause(self):
        # создатель пишет во время 2-й итерации: статус виден агенту,
        # но пауза не сбрасывается — она по-прежнему 7 сек
        def on_iteration(n):
            if n == 2:
                append_message(self.paths.messages, SENDER_CREATOR, "как дела?")

        logs, sleeps = _run_loop_mocked(
            self.paths, self.cfg, self._responses(3), on_iteration=on_iteration)
        self.assertEqual(sleeps, [7.0, 7.0, 7.0])
        self.assertNotIn("расписание паузы сброшено", "\n".join(logs))
        # сообщение при этом остаётся непрочитанным до вызова get_messages
        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertNotIn("seen_creator_messages", data)
        messages = json.loads(self.paths.messages.read_text(encoding="utf-8"))
        self.assertFalse(messages["messages"][0]["read"])
        self.assertEqual([it["n"] for it in data["iterations"]], [1, 2, 3])

    def test_fixed_pause_overrides_loop_delay(self):
        # LOOP_DELAY больше фиксированной паузы — не применяется:
        # фиксированное значение важнее настраиваемого минимума
        self.cfg.loop_delay = 60.0
        _, sleeps = _run_loop_mocked(self.paths, self.cfg, self._responses(2))
        self.assertEqual(sleeps, [7.0, 7.0])

    def test_message_during_pause_still_wakes_agent(self):
        # создатель пишет прямо во время 2-й паузы — пауза прерывается
        # немедленно (как и в адаптивном режиме), но следующая пауза —
        # всё те же 7 сек, расписание не растёт
        def on_pause(n):
            if n == 2:
                append_message(self.paths.messages, SENDER_CREATOR, "эй, проснись")

        logs, sleeps = _run_loop_mocked(
            self.paths, self.cfg, self._responses(3), on_pause=on_pause)
        self.assertEqual(sleeps, [7.0, 7.0, 7.0])
        wake_logs = [l for l in logs if "во время паузы" in l]
        self.assertEqual(len(wake_logs), 1)

    def test_pause_log_fixed_mode(self):
        # строка консоли в фиксированном режиме: причина паузы — флаг,
        # а не молчание создателя
        line = agent._format_pause_log(
            step=0, sleep_for=7.0, creator_wrote=False,
            planned_delay=7.0, iteration_duration=0.0, fixed_pause=True,
        )
        self.assertIn("Фиксированная пауза (--loop-pause)", line)
        self.assertIn("пауза до следующей итерации: 7 сек", line)
        self.assertNotIn("Создатель молчит", line)

    def test_pause_log_fixed_mode_ignores_creator_reset(self):
        # создатель написал между итерациями — в фиксированном режиме
        # это на паузу не влияет: строка всё равно про фиксированную паузу
        line = agent._format_pause_log(
            step=1, sleep_for=7.0, creator_wrote=True,
            planned_delay=7.0, iteration_duration=0.0, fixed_pause=True,
        )
        self.assertIn("Фиксированная пауза", line)
        self.assertNotIn("расписание паузы сброшено", line)

if __name__ == "__main__":
    unittest.main()
