import json
import shutil
import tempfile
import threading
import unittest
from pathlib import Path

import wallet
import wallet_storage


class WalletTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-wallet-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.path = self.root / "bot" / "wallet.json"
        self.path.parent.mkdir()

    def test_missing_wallet_starts_at_zero(self):
        data = wallet_storage.load_wallet(self.path, "bot")
        self.assertEqual(data["schema_version"], 1)
        self.assertEqual(wallet.wallet_summary(data)["balance"], 0)
        self.assertEqual(data["acceleration_cycles"], 0)
        wallet_storage.ensure_wallet_file(self.path, "bot")
        self.assertTrue(self.path.is_file())

    def test_credit_spend_and_consume_keep_only_financial_types(self):
        wallet_storage.ensure_wallet_file(self.path, "bot")
        credit = wallet.credit(self.path, 10, "за эту работу", payment_id="p-1")
        spend = wallet.spend(self.path, 4, "ускорить отчёт")
        self.assertEqual((credit["type"], spend["type"]), ("credit", "spend"))
        self.assertEqual(wallet.wallet_summary(self.path)["balance"], 6)
        self.assertEqual(wallet.wallet_summary(self.path)["acceleration_cycles"], 4)
        self.assertTrue(wallet.consume_acceleration_cycle(self.path))
        data = wallet_storage.load_wallet(self.path)
        self.assertEqual(data["acceleration_cycles"], 3)
        self.assertEqual({tx["type"] for tx in data["transactions"]}, {"credit", "spend"})
        self.assertEqual(len(data["transactions"]), 2)
        self.assertEqual(data["transactions"][0]["payment_id"], "p-1")
        self.assertEqual(data["transactions"][1]["purpose"], "ускорить отчёт")

    def test_spend_requires_balance_and_does_not_mutate(self):
        wallet_storage.ensure_wallet_file(self.path, "bot")
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(wallet.InsufficientBalance):
            wallet.spend(self.path, 1, "работа")
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)
        for units in (0, -1, True, 1.5, "1"):
            with self.subTest(units=units):
                with self.assertRaises(wallet.WalletValidationError):
                    wallet.credit(self.path, units, "причина")

    def test_history_contains_only_newest_agent_spends(self):
        wallet.credit(self.path, 8, "работа", payment_id="p-1")
        wallet.spend(self.path, 2, "первый отчёт")
        wallet.spend(self.path, 1, "второй отчёт")
        history = wallet.format_spend_history(self.path)
        self.assertIn("второй отчёт", history)
        self.assertIn("первый отчёт", history)
        self.assertLess(history.index("второй отчёт"), history.index("первый отчёт"))
        self.assertNotIn("работа", history)
        self.assertIn("осталось ускорение: 3", history)

    def test_corrupt_wallet_is_backed_up_and_not_replaced(self):
        raw = "{это не кошелёк"
        self.path.write_text(raw, encoding="utf-8")
        with self.assertRaises(wallet_storage.WalletCorruptError):
            wallet_storage.load_wallet(self.path, "bot")
        self.assertEqual(self.path.read_text(encoding="utf-8"), raw)
        backups = list(self.path.parent.glob("wallet.json.corrupt-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), raw)

    def test_invalid_ledger_is_rejected(self):
        data = wallet_storage.empty_wallet("bot")
        data["transactions"] = [{
            "id": 1, "timestamp": "t", "type": "boost_consume", "units": 1,
            "actor": "agent",
        }]
        self.path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(wallet_storage.WalletCorruptError):
            wallet_storage.load_wallet(self.path, "bot")

    def test_concurrent_credits_are_not_lost(self):
        wallet_storage.ensure_wallet_file(self.path, "bot")
        errors = []

        def add_credit(index):
            try:
                wallet.credit(self.path, 1, f"работа {index}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add_credit, args=(i,)) for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        data = wallet_storage.load_wallet(self.path, "bot")
        self.assertEqual(wallet.wallet_summary(data)["balance"], 20)
        self.assertEqual(len(data["transactions"]), 20)
        self.assertEqual(len({tx["id"] for tx in data["transactions"]}), 20)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

