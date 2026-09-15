import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import main
import main_money
import wallet
from tests.helpers import env, make_agent_dir


class MoneyCliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-main-money-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.folder = make_agent_dir(self.root, "bot")

    def run_cli(self, args):
        out, err = StringIO(), StringIO()
        with mock.patch("sys.argv", ["main.py", *args]), env(
            AGENTS_ROOT=str(self.root), OPENAI_BASE_URL=None,
            OPENAI_MODEL=None, OPENAI_API_KEY=None,
        ), redirect_stdout(out), redirect_stderr(err):
            try:
                main.main()
            except SystemExit as exc:
                return exc.code, out.getvalue(), err.getvalue()
        return 0, out.getvalue(), err.getvalue()

    def test_pay_creates_credit_and_unread_message_without_llm(self):
        code, output, error = self.run_cli(["bot", "pay", "10", "за эту работу"])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("bot", output)
        self.assertIn("за эту работу", output)
        self.assertIn("10", output)
        wallet_data = json.loads(self.folder.joinpath("wallet.json").read_text(encoding="utf-8"))
        messages = json.loads(self.folder.joinpath("messages.json").read_text(encoding="utf-8"))
        self.assertEqual(wallet_data["transactions"][0]["type"], "credit")
        self.assertFalse(messages["messages"][0]["read"])
        self.assertEqual(messages["messages"][0]["payment_id"], wallet_data["transactions"][0]["payment_id"])
        self.assertIn("Создатель начислил тебе 10 единиц", messages["messages"][0]["text"])

    def test_balance_and_history_are_read_only_commands(self):
        wallet.credit(self.folder / "wallet.json", 7, "работа", payment_id="p-1")
        wallet.spend(self.folder / "wallet.json", 3, "ускорить тест")
        before = self.folder.joinpath("wallet.json").read_text(encoding="utf-8")
        code, balance, error = self.run_cli(["bot", "balance"])
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Доступно: 4", balance)
        self.assertIn("Оплаченных циклов: 3", balance)
        code, history, error = self.run_cli(["bot", "history"])
        self.assertEqual((code, error), (0, ""))
        self.assertRegex(history, r"\d{4}-\d{2}-\d{2}T")
        self.assertIn("3", history)
        self.assertIn("ускорить тест", history)
        self.assertEqual(self.folder.joinpath("wallet.json").read_text(encoding="utf-8"), before)

    def test_money_commands_require_name_and_existing_agent(self):
        for args in (["pay", "1", "работа"], ["balance"], ["history"]):
            with self.subTest(args=args):
                code, _, error = self.run_cli(args)
                self.assertEqual(code, 1)
                self.assertIn("имя агента", error.lower())
        code, _, error = self.run_cli(["ghost", "balance"])
        self.assertEqual(code, 1)
        self.assertIn("не найден", error)
        self.assertFalse((self.root / "ghost").exists())

    def test_missing_payment_message_is_repaired_on_next_initialization(self):
        with mock.patch.object(main_money, "append_message", side_effect=OSError("disk")):
            code, _, error = self.run_cli(["bot", "pay", "3", "за сбой"])
        self.assertEqual(code, 1)
        self.assertIn("начислено", error)
        wallet_data = json.loads(self.folder.joinpath("wallet.json").read_text(encoding="utf-8"))
        self.assertEqual(len(wallet_data["transactions"]), 1)
        self.assertFalse(json.loads(self.folder.joinpath("messages.json").read_text(encoding="utf-8"))["messages"])
        code, _, error = self.run_cli(["bot", "balance"])
        self.assertEqual((code, error), (0, ""))
        messages = json.loads(self.folder.joinpath("messages.json").read_text(encoding="utf-8"))["messages"]
        self.assertEqual(messages[0]["payment_id"], wallet_data["transactions"][0]["payment_id"])
        self.assertFalse(messages[0]["read"])

    def test_pay_rejects_bad_amount_or_reason(self):
        for args in (["bot", "pay", "0", "работа"],
                     ["bot", "pay", "-1", "работа"],
                     ["bot", "pay", "1.5", "работа"],
                     ["bot", "pay", "999999999999999999999999999999", "работа"],
                     ["bot", "pay", "1", ""]):
            with self.subTest(args=args):
                code, _, error = self.run_cli(args)
                self.assertEqual(code, 1)
                self.assertIn("Ошибка", error)
        self.assertFalse((self.folder / "wallet.json").exists())

