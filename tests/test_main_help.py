"""Тесты справки командной строки."""

import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest import mock

import main


class HelpTests(unittest.TestCase):
    def test_help_lists_money_commands_without_starting_agent(self):
        with mock.patch.object(sys, "argv", ["main.py", "Evgeny", "--help"]), \
             mock.patch.object(main, "run_loop") as mock_run_loop, \
             redirect_stdout(StringIO()) as out, redirect_stderr(StringIO()) as err:
            main.main()

        output = out.getvalue()
        self.assertIn("pay <единицы>", output)
        self.assertIn("balance", output)
        self.assertIn("history", output)
        self.assertIn("Денежные команды", output)
        self.assertIn("не создают новых агентов", output)
        self.assertEqual(err.getvalue(), "")
        mock_run_loop.assert_not_called()


if __name__ == "__main__":
    unittest.main()
