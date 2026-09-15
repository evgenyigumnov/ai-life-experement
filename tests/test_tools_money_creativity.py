"""Инструмент money_spend: эффект creativity."""

import shutil
import tempfile
import unittest
from pathlib import Path

import tool_registry as tools
import wallet
from tests.tools_testkit import _paths


class CreativityMoneyToolTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-money-creativity-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paths = _paths(self.root / "memory.md", name="bot")

    def test_creativity_spend_reserves_creativity_cycles(self):
        wallet.credit(self.paths, 3, "задача")
        result = tools.execute_tool(
            "money_spend",
            {"units": 2, "purpose": "придумать варианты", "type": "creativity"},
            self.paths,
        )
        self.assertIn("type=creativity", result)
        state = wallet.wallet_summary(self.paths)
        self.assertEqual((state["balance"], state["creativity_cycles"]), (1, 2))
        self.assertEqual(state["acceleration_cycles"], 0)


if __name__ == "__main__":
    unittest.main()
