"""Оплаченные циклы отменяют только адаптивное ожидание."""

import json
import shutil
import tempfile
import unittest
from unittest import mock

from tests.agent_common import (
    Config, _paths, _run_loop_mocked, agent, agent_console, make_agent_dir,
)
import wallet


class PaidPauseTests(unittest.TestCase):
    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-paid-pause-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)
        self.cfg = Config(base_url="http://mock/v1", model="m", api_key="k",
                          agents_root=None, loop_delay=0)

    def test_one_unit_is_consumed_by_one_next_cycle(self):
        wallet.credit(self.paths.wallet, 4, "работа", payment_id="p-1")
        wallet.spend(self.paths.wallet, 3, "ускорить работу")
        logs, sleeps = _run_loop_mocked(
            self.paths, self.cfg,
            [{"role": "assistant", "content": str(i)} for i in range(4)],
        )
        self.assertEqual(sleeps, [0.0, 0.0, 0.0, 120.0])
        self.assertEqual(wallet.wallet_summary(self.paths.wallet)["acceleration_cycles"], 0)
        data = json.loads(self.paths.wallet.read_text(encoding="utf-8"))
        self.assertEqual([tx["type"] for tx in data["transactions"]], ["credit", "spend"])
        self.assertNotIn("boost_consume", self.paths.wallet.read_text(encoding="utf-8"))
        paid_logs = [line for line in logs if "оплаченная единица" in line]
        self.assertEqual(len(paid_logs), 3)
        self.assertIn("осталось 0", paid_logs[-1])

    def test_spend_tool_does_not_start_an_extra_iteration(self):
        wallet.credit(self.paths, 2, "работа")
        tool_response = {
            "role": "assistant", "content": None,
            "tool_calls": [{"id": "money", "type": "function", "function": {
                "name": "money_spend",
                "arguments": '{"units": 1, "purpose": "срочный шаг", "type": "speed"}',
            }}],
        }
        _, sleeps = _run_loop_mocked(
            self.paths, self.cfg,
            [tool_response, {"role": "assistant", "content": "готово"}],
        )
        self.assertEqual(sleeps, [0.0, 30.0])
        data = json.loads(self.paths.mind_loop.read_text(encoding="utf-8"))
        self.assertEqual(len(data["iterations"]), 2)

    def test_fixed_loop_pause_has_priority_and_does_not_consume(self):
        wallet.credit(self.paths.wallet, 2, "работа")
        wallet.spend(self.paths.wallet, 2, "фиксированный режим")
        self.cfg.loop_pause = 7.0
        _, sleeps = _run_loop_mocked(
            self.paths, self.cfg,
            [{"role": "assistant", "content": "x"} for _ in range(2)],
        )
        self.assertEqual(sleeps, [7.0, 7.0])
        self.assertEqual(wallet.wallet_summary(self.paths.wallet)["acceleration_cycles"], 2)

    def test_paid_cycle_log_explains_pause_and_remaining_reserve(self):
        with mock.patch.object(agent_console, "USE_COLOR", False):
            line = agent._format_paid_cycle_log(2)
        self.assertIn("оплаченная единица", line)
        self.assertIn("пауза отменена", line)
        self.assertIn("осталось 2 оплаченных циклов", line)

    def test_corrupt_wallet_falls_back_to_regular_backoff(self):
        self.paths.wallet.write_text("broken", encoding="utf-8")
        _, sleeps = _run_loop_mocked(
            self.paths, self.cfg,
            [{"role": "assistant", "content": "x"} for _ in range(2)],
        )
        self.assertEqual(sleeps, [0.0, 30.0])
        self.assertEqual(self.paths.wallet.read_text(encoding="utf-8"), "broken")

    def test_paid_reserve_survives_restart_and_sleep(self):
        wallet.credit(self.paths.wallet, 5, "надолго")
        wallet.spend(self.paths.wallet, 5, "запас")
        self.assertEqual(wallet.wallet_summary(self.paths.wallet)["acceleration_cycles"], 5)
        self.assertTrue(wallet.consume_acceleration_cycle(self.paths.wallet))
        # Перечитывание файла — имитация рестарта процесса/сессии.
        reread = wallet.wallet_summary(self.paths.wallet)
        self.assertEqual(reread["acceleration_cycles"], 4)
        self.assertEqual(reread["balance"], 0)


if __name__ == "__main__":
    unittest.main()
