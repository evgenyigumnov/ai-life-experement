"""Тесты agent._wait_pause: сон паузы, прерываемый сообщением создателя."""


import shutil
import tempfile
import unittest
from unittest import mock

from tests.agent_common import _paths, agent, agent_pause, make_agent_dir


class WaitPauseTests(unittest.TestCase):
    """Пауза, прерываемая сообщением создателя (_wait_pause).

    Сон идёт кусками не длиннее PAUSE_POLL_INTERVAL; после каждого куска
    перечитывается messages.json — новое сообщение создателя прерывает
    паузу немедленно (True), молчание — пауза дотягивается до конца (False).
    Часы и сон замоканы: реального времени тесты не тратят.
    """

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-waitpause-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def _wait(self, seconds, on_sleep=None):
        """Прогнать _wait_pause с фейковыми часами; вернуть (результат, куски).

        Фейковые часы тикают только внутри фиктивного time.sleep: кусок
        сна прибавляется к «сейчас» (время идёт, только пока спим).
        `on_sleep(n)` вызывается в начале n-го куска — позволяет
        симулировать сообщение создателя «во время» сна.
        """
        clock = {"now": 100.0}
        chunks: list[float] = []
        calls = {"n": 0}

        def fake_monotonic():
            return clock["now"]

        def fake_sleep(chunk):
            clock["now"] += chunk
            chunks.append(chunk)
            calls["n"] += 1
            if on_sleep is not None:
                on_sleep(calls["n"])

        known = agent._creator_messages_count(self.paths)
        with mock.patch.object(agent_pause.time, "monotonic", fake_monotonic), \
             mock.patch.object(agent_pause.time, "sleep", fake_sleep):
            result = agent._wait_pause(seconds, self.paths, known)
        return result, chunks

    def test_zero_pause_returns_false_without_sleep(self):
        # нулевая пауза не спит и не проверяет переписку — следующая
        # итерация и так увидит сообщение
        result, chunks = self._wait(0.0)
        self.assertFalse(result)
        self.assertEqual(chunks, [])

    def test_negative_pause_returns_false(self):
        # долгая итерация уже «съела» паузу — спать нечего
        result, chunks = self._wait(-5.0)
        self.assertFalse(result)
        self.assertEqual(chunks, [])

    def test_silent_creator_sleeps_full_pause_in_poll_chunks(self):
        # создатель молчит: пауза дотягивается до конца кусками
        # по PAUSE_POLL_INTERVAL, хвост — остаток
        result, chunks = self._wait(2.5)
        self.assertFalse(result)
        self.assertEqual(chunks, [1.0, 1.0, 0.5])

    def test_chunks_never_exceed_poll_interval(self):
        # даже 10-минутная пауза спит кусками не длиннее интервала
        # проверки — иначе сообщение создателя ждало бы конца паузы
        result, chunks = self._wait(10 * 60)
        self.assertFalse(result)
        self.assertTrue(chunks)
        self.assertTrue(all(c <= agent.PAUSE_POLL_INTERVAL for c in chunks))
        self.assertAlmostEqual(sum(chunks), 600.0)

    def test_creator_message_interrupts_pause_immediately(self):
        # создатель пишет после первого куска сна: просыпаемся через
        # ~2 секунды от 5-минутной паузы, а не ждём её конца
        from storage import SENDER_CREATOR, append_message

        def on_sleep(n):
            if n == 2:
                append_message(self.paths.messages, SENDER_CREATOR, "проснись!")

        result, chunks = self._wait(300.0, on_sleep)
        self.assertTrue(result)
        self.assertEqual(chunks, [1.0, 1.0])

    def test_agent_message_does_not_interrupt(self):
        # сообщения самого агента (send_message) паузу не прерывают —
        # иначе агент будил бы сам себя
        from storage import SENDER_AGENT, append_message

        def on_sleep(n):
            append_message(self.paths.messages, SENDER_AGENT, "сам себя не будишь")

        result, chunks = self._wait(2.0, on_sleep)
        self.assertFalse(result)
        self.assertEqual(chunks, [1.0, 1.0])

    def test_keyboard_interrupt_propagates(self):
        # Ctrl+C во время сна паузы — команда на выход, а не «сбой»:
        # KeyboardInterrupt пробрасывается из _wait_pause как из time.sleep
        def fake_sleep(chunk):
            raise KeyboardInterrupt

        with mock.patch.object(agent_pause.time, "monotonic", lambda: 0.0), \
             mock.patch.object(agent_pause.time, "sleep", fake_sleep):
            with self.assertRaises(KeyboardInterrupt):
                agent._wait_pause(10.0, self.paths, 0)

if __name__ == "__main__":
    unittest.main()
