"""Кошелёк: раздельные speed- и creativity-резервы."""

import shutil
import tempfile
import unittest
from pathlib import Path

import wallet
from wallet_reconcile import format_credit_message
from wallet_storage import ensure_wallet_file, load_wallet


class CreativityWalletTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-wallet-creativity-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.path = self.root / "bot" / "wallet.json"
        ensure_wallet_file(self.path, "bot")

    def test_spend_and_consume_creativity_cycles(self):
        wallet.credit(self.path, 5, "задача", payment_id="p-1")
        transaction = wallet.spend(
            self.path, 3, "придумать варианты", "creativity"
        )
        self.assertEqual(transaction["spend_type"], "creativity")
        state = wallet.wallet_summary(self.path)
        self.assertEqual(
            (state["balance"], state["acceleration_cycles"],
             state["creativity_cycles"]),
            (2, 0, 3),
        )
        self.assertTrue(wallet.consume_creativity_cycle(self.path))
        self.assertEqual(wallet.wallet_summary(self.path)["creativity_cycles"], 2)
        data = load_wallet(self.path, "bot")
        self.assertEqual(data["transactions"][1]["spend_type"], "creativity")

    def test_credit_notice_lists_both_spend_types(self):
        notice = format_credit_message(2, "идеи")
        self.assertIn("type=speed", notice)
        self.assertIn("type=creativity", notice)

    def test_old_spend_without_type_remains_speed(self):
        wallet.credit(self.path, 1, "работа", payment_id="p-1")
        data = load_wallet(self.path, "bot")
        data["transactions"].append({
            "id": 2, "timestamp": "t", "type": "spend", "units": 1,
            "purpose": "старый формат", "actor": "agent",
        })
        data["next_id"] = 3
        data["acceleration_cycles"] = 1
        self.assertEqual(wallet.wallet_summary(data)["acceleration_cycles"], 1)


if __name__ == "__main__":
    unittest.main()
