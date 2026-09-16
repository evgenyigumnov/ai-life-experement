"""Тесты редактора интерактивной переписки."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import reply_input  # noqa: E402


class ReplyInputTests(unittest.TestCase):
    def test_session_is_multiline_and_has_custom_bindings(self):
        with mock.patch.object(reply_input, "PromptSession") as prompt_session:
            session = reply_input.create_reply_session()

        self.assertIs(session, prompt_session.return_value)
        kwargs = prompt_session.call_args.kwargs
        self.assertTrue(kwargs["multiline"])
        self.assertIsNotNone(kwargs["key_bindings"])

    @unittest.skipIf(reply_input.KeyBindings is None, "prompt_toolkit не установлен")
    def test_enter_accepts_and_newline_shortcuts_insert_line_break(self):
        sequences = {
            tuple(getattr(key, "value", key) for key in binding.keys)
            for binding in reply_input.build_key_bindings().bindings
        }
        self.assertIn(("c-m",), sequences)  # обычный Enter
        self.assertIn(("c-j",), sequences)  # fallback для терминалов без CSI-u
        self.assertIn(("escape", "[", "1", "3", ";", "2", "u"), sequences)
        self.assertIn(("escape", "[", "1", "3", ";", "5", "u"), sequences)

    def test_reply_output_preserves_ansi_sequences(self):
        with mock.patch.object(reply_input, "patch_stdout") as patch_stdout:
            with reply_input.reply_output(True):
                pass

        patch_stdout.assert_called_once_with(raw=True)

    def test_read_reply_returns_none_on_eof(self):
        with mock.patch("builtins.input", side_effect=EOFError):
            self.assertIsNone(reply_input.read_reply(None, "> "))


if __name__ == "__main__":
    unittest.main()
