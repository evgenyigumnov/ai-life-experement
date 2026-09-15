"""Тесты адаптивной паузы в живом цикле run_loop."""


import json
import shutil
import tempfile
import unittest
from unittest import mock

from tests.agent_common import (
    agent, agent_console, Config, make_agent_dir, _paths, _run_loop_mocked,
)


class IdleBackoffLoopTests(unittest.TestCase):
    """Пауза растёт при молчании создателя и сбрасывается его сообщением;

    сообщение во время паузы будит агента немедленно (_wait_pause).
    """

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-backoff-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)
        self.cfg = Config(base_url="http://mock/v1", model="mock-model",
                          api_key="k", agents_root=None, loop_delay=0)

    def _run(self, responses, on_iteration=None, on_pause=None):
        """Прогнать run_loop с моком LLM; вернуть (логи, длительности пауз)."""
        return _run_loop_mocked(self.paths, self.cfg, responses,
                                on_iteration=on_iteration, on_pause=on_pause)

    @staticmethod
    def _text_responses(count):
        return [{"role": "assistant", "content": f"ответ {i}"}
                for i in range(1, count + 1)]

    def test_pause_grows_while_creator_silent(self):
        # создатель ничего не пишет: паузы 0, 30, 60, 120 сек
        logs, sleeps = self._run(self._text_responses(4))
        self.assertEqual(sleeps, [0.0, 30.0, 60.0, 120.0])
        pause_logs = [l for l in logs if "Создатель молчит" in l]
        self.assertEqual(len(pause_logs), 4)
        # первая тихая итерация — продолжить сразу, дальше пауза растёт
        self.assertIn("1 итерацию подряд", pause_logs[0])
        self.assertIn("следующая итерация — сразу", pause_logs[0])
        self.assertIn("2 итерации подряд", pause_logs[1])
        self.assertIn("30 сек", pause_logs[1])
        self.assertIn("3 итерации подряд", pause_logs[2])
        self.assertIn("1 мин", pause_logs[2])
        self.assertIn("4 итерации подряд", pause_logs[3])
        self.assertIn("2 мин", pause_logs[3])

    def test_creator_messages_count_ignores_agent_messages(self):
        from storage import SENDER_AGENT, SENDER_CREATOR, append_message

        self.assertEqual(agent._creator_messages_count(self.paths), 0)
        append_message(self.paths.messages, SENDER_AGENT, "привет, я агент")
        append_message(self.paths.messages, SENDER_CREATOR, "привет, это создатель")
        append_message(self.paths.messages, SENDER_AGENT, "ещё ответ агента")
        append_message(self.paths.messages, SENDER_CREATOR, "второе сообщение")
        self.assertEqual(agent._creator_messages_count(self.paths), 2)

    def test_creator_message_resets_schedule(self):
        # создатель пишет во время 3-й итерации: пауза после неё — снова 0,
        # а не продолжает расти до 60 сек
        from storage import SENDER_CREATOR, append_message

        def on_iteration(n):
            if n == 3:
                append_message(self.paths.messages, SENDER_CREATOR, "как дела?")

        logs, sleeps = self._run(self._text_responses(4), on_iteration)
        self.assertEqual(sleeps, [0.0, 30.0, 0.0, 30.0])
        reset_logs = [l for l in logs if "расписание паузы сброшено" in l]
        self.assertEqual(len(reset_logs), 1)
        # история не пострадала: все 4 итерации записаны
        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual([it["n"] for it in data["iterations"]], [1, 2, 3, 4])

    def test_agent_message_does_not_reset_schedule(self):
        # агент сам пишет в переписку (send_message) — интерес это не
        # проявляет: пауза продолжает расти
        from storage import SENDER_AGENT, append_message

        def on_iteration(n):
            if n == 2:
                append_message(self.paths.messages, SENDER_AGENT, "я сам написал")

        logs, sleeps = self._run(self._text_responses(3), on_iteration)
        self.assertEqual(sleeps, [0.0, 30.0, 60.0])
        self.assertNotIn("расписание паузы сброшено", "\n".join(logs))

    def test_loop_delay_is_minimum_pause(self):
        # LOOP_DELAY задаёт нижнюю границу: даже нулевая ступень расписания
        # не даёт паузу меньше настраиваемого минимума
        self.cfg.loop_delay = 5.0
        logs, sleeps = self._run(self._text_responses(2))
        self.assertEqual(sleeps, [5.0, 30.0])

    def test_creator_message_during_pause_wakes_agent_immediately(self):
        # создатель пишет прямо во время 3-й паузы (60 сек, максимальная
        # точка теста): пауза прерывается немедленно — итерация 4 идёт
        # без ожидания, расписание обнуляется (после ответа — снова
        # минимальная пауза, дальше растёт заново)
        from storage import SENDER_CREATOR, append_message

        def on_pause(n):
            if n == 3:
                append_message(self.paths.messages, SENDER_CREATOR, "эй, проснись")

        logs, sleeps = self._run(self._text_responses(5), on_pause=on_pause)
        self.assertEqual(sleeps, [0.0, 30.0, 60.0, 0.0, 30.0])
        wake_logs = [l for l in logs if "во время паузы" in l]
        self.assertEqual(len(wake_logs), 1)
        # история не пострадала: все 5 итераций записаны
        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual([it["n"] for it in data["iterations"]], [1, 2, 3, 4, 5])

    def test_agent_message_during_pause_does_not_wake(self):
        # агент сам пишет в переписку во время паузы — интереса это не
        # проявляет: пауза не прерывается, расписание продолжает расти
        from storage import SENDER_AGENT, append_message

        def on_pause(n):
            append_message(self.paths.messages, SENDER_AGENT, "я тут сам")

        logs, sleeps = self._run(self._text_responses(4), on_pause=on_pause)
        self.assertEqual(sleeps, [0.0, 30.0, 60.0, 120.0])
        self.assertNotIn("во время паузы", "\n".join(logs))

    def test_pause_interrupted_log_format(self):
        # строка пробуждения говорит, что случилось и что агент делает
        with mock.patch.object(agent_console, "USE_COLOR", False):
            line = agent._format_pause_interrupted_log()
        self.assertIn("Создатель написал во время паузы", line)
        self.assertIn("просыпаюсь сразу", line)

if __name__ == "__main__":
    unittest.main()
