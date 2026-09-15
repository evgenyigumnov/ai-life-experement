"""Инструменты money_balance и money_spend."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

import tool_registry as tools
import tools_money
import tools_money_schema
import wallet
from tests.tools_testkit import _paths


class MoneyToolsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-money-tools-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paths = _paths(self.root / "memory.md", name="bot")

    def test_names_and_schema_are_always_available(self):
        names = [tool["function"]["name"] for tool in tools.build_tools_schema(False)]
        self.assertIn("money_balance", names)
        self.assertIn("money_spend", names)
        self.assertIs(tools._HANDLERS["money_balance"], tools_money.handle_money_balance)
        self.assertIs(tools._HANDLERS["money_spend"], tools_money.handle_money_spend)
        balance = tools_money_schema.MONEY_BALANCE_TOOL["function"]
        spend = tools_money_schema.MONEY_SPEND_TOOL["function"]
        self.assertIn("1 единица = 1 следующий цикл/тик LLM без паузы перед ним", balance["description"])
        self.assertIn("0 → 30 сек → 1 мин → 2 мин → 5 мин → 10 мин → 20 мин → 40 мин → 1 час → 2 часа → 4 часа", balance["description"])
        self.assertIn("1 единица покупает 1 следующий цикл без паузы", spend["description"])
        self.assertIn("N единиц — N следующих циклов без пауз", spend["description"])
        self.assertEqual(
            set(spend["parameters"]["required"]), {"units", "purpose", "type"}
        )
        self.assertEqual(
            spend["parameters"]["properties"]["type"]["enum"],
            ["speed", "creativity"],
        )

    def test_balance_and_spend_success(self):
        wallet.credit(self.paths, 10, "задача", payment_id="p-1")
        balance = tools.execute_tool("money_balance", {}, self.paths)
        self.assertIn("Доступно: 10", balance)
        self.assertIn("Оплаченных циклов: 0", balance)
        self.assertIn("1 единица = 1 следующий цикл/тик LLM без паузы перед ним", balance)
        spent = tools.execute_tool(
            "money_spend", json.dumps({
                "units": 4, "purpose": "ускорить отчёт", "type": "speed",
            }), self.paths
        )
        self.assertIn("Доступно: 6", spent)
        self.assertIn("Оплаченных циклов: 4", spent)
        self.assertEqual(wallet.wallet_summary(self.paths)["balance"], 6)

    def test_purpose_and_units_are_required(self):
        for args in ({}, {"units": 1}, {"units": 1, "purpose": ""},
                     {"units": 0, "purpose": "работа", "type": "speed"},
                     {"units": True, "purpose": "работа", "type": "speed"},
                     {"units": 1, "purpose": 4, "type": "speed"},
                     {"units": 1, "purpose": "работа"},
                     {"units": 1, "purpose": "работа", "type": "other"}):
            with self.subTest(args=args):
                result = tools.execute_tool("money_spend", args, self.paths)
                self.assertTrue(result.startswith("Error: invalid arguments"), result)

    def test_insufficient_balance_and_corruption_do_not_change_wallet(self):
        wallet.credit(self.paths, 2, "задача")
        before = self.paths.wallet.read_text(encoding="utf-8")
        result = tools.execute_tool(
            "money_spend", {"units": 3, "purpose": "слишком много"}, self.paths
        )
        self.assertTrue(result.startswith("Error:"), result)
        self.assertEqual(self.paths.wallet.read_text(encoding="utf-8"), before)
        self.paths.wallet.write_text("не json", encoding="utf-8")
        result = tools.execute_tool("money_balance", {}, self.paths)
        self.assertTrue(result.startswith("Error:"), result)
        self.assertEqual(self.paths.wallet.read_text(encoding="utf-8"), "не json")

    def test_unknown_money_tool_without_paths_is_safe(self):
        self.assertEqual(tools.execute_tool("money_balance", {}), "Error: paths не заданы")
        self.assertEqual(tools.execute_tool("money_spend", {}, None), "Error: paths не заданы")


if __name__ == "__main__":
    unittest.main()
