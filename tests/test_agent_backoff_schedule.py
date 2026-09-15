"""Тесты адаптивной паузы: расписание и чистые функции."""


import unittest

from tests.agent_common import agent


class IdleBackoffScheduleTests(unittest.TestCase):
    """Расписание IDLE_BACKOFF_SCHEDULE и функции паузы без прогона цикла."""

    def test_schedule_matches_required_timings(self):
        # расписание из задачи: 0, 30 сек, 1 мин, 2 мин, 5 мин, 10 мин,
        # 20 мин, 40 мин, 1 час, 2 часа, 4 часа
        self.assertEqual(
            agent.IDLE_BACKOFF_SCHEDULE,
            (0.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1200.0,
             2400.0, 3600.0, 7200.0, 14400.0),
        )

    def test_backoff_delay_by_step(self):
        for step, expected in enumerate(agent.IDLE_BACKOFF_SCHEDULE, start=1):
            self.assertEqual(agent._backoff_delay(step), expected)

    def test_backoff_delay_capped_at_four_hours(self):
        # дальше последней ступени пауза не растёт — цикл продолжает
        # просыпаться раз в 4 часа, но не реже
        top = agent.IDLE_BACKOFF_SCHEDULE[-1]
        self.assertEqual(agent._backoff_delay(len(agent.IDLE_BACKOFF_SCHEDULE)), top)
        self.assertEqual(agent._backoff_delay(len(agent.IDLE_BACKOFF_SCHEDULE) + 7), top)
        self.assertEqual(agent._backoff_delay(1000), top)

    def test_backoff_delay_fresh_step_is_zero(self):
        # первая после сообщения создателя (или стартовая) пауза — нулевая
        self.assertEqual(agent._backoff_delay(1), 0.0)

    def test_pause_seconds_subtracts_iteration_duration(self):
        # отсчёт паузы — от начала итерации: сама итерация «съедает» её часть
        self.assertAlmostEqual(agent._pause_seconds(30.0, 12.0), 18.0)
        self.assertAlmostEqual(agent._pause_seconds(30.0, 30.0), 0.0)
        # долгая итерация не даёт отрицательного сна — следующая сразу
        self.assertEqual(agent._pause_seconds(30.0, 45.5), 0.0)

    def test_pause_log_shows_planned_delay_consumed_by_iteration(self):
        # плановая пауза целиком истекла за время самой итерации: строка
        # объясняет это и показывает плановую паузу и длительность итерации,
        # а не сухое «сразу» без указания времени (наблюдатель должен
        # видеть ритм цикла и на старте, когда итерации длиннее паузы)
        line = agent._format_pause_log(
            step=2, sleep_for=0.0, creator_wrote=False,
            planned_delay=30.0, iteration_duration=63.0,
        )
        self.assertIn("2 итерации подряд", line)
        self.assertIn(
            "плановая пауза 30 сек истекла за время итерации (1 мин 3 сек)", line)
        self.assertIn("следующая итерация сразу", line)

    def test_pause_log_zero_step_without_planned_delay(self):
        # нулевая ступень расписания (первая тихая итерация): плановой
        # паузы нет — короткое «сразу» без упоминания плановой паузы
        line = agent._format_pause_log(
            step=1, sleep_for=0.0, creator_wrote=False,
            planned_delay=0.0, iteration_duration=5.0,
        )
        self.assertIn("1 итерацию подряд", line)
        self.assertIn("следующая итерация — сразу", line)
        self.assertNotIn("плановая пауза", line)

    def test_pause_log_positive_sleep_ignores_planned_delay(self):
        # реальный сон есть — показывается только он, плановая пауза
        # (уже частично съеденная итерацией) не упоминается
        line = agent._format_pause_log(
            step=3, sleep_for=18.0, creator_wrote=False,
            planned_delay=60.0, iteration_duration=42.0,
        )
        self.assertIn("3 итерации подряд", line)
        self.assertIn("пауза до следующей итерации: 18 сек", line)
        self.assertNotIn("плановая пауза", line)

    def test_pause_log_creator_reset_consumed_delay(self):
        # создатель написал (расписание сброшено), но плановая пауза
        # (минимум LOOP_DELAY) истекла за время итерации — и это видно
        line = agent._format_pause_log(
            step=1, sleep_for=0.0, creator_wrote=True,
            planned_delay=5.0, iteration_duration=12.0,
        )
        self.assertIn("расписание паузы сброшено", line)
        self.assertIn("плановая пауза 5 сек истекла", line)

if __name__ == "__main__":
    unittest.main()
