"""Тесты редактируемых сообщений и fallback-строк."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import prompts_messages as prompts


class DefaultsTests(unittest.TestCase):
    def test_every_file_has_nonempty_default(self):
        self.assertEqual(len(prompts.EDITABLE_MESSAGE_FILES), 5)
        for filename in prompts.EDITABLE_MESSAGE_FILES:
            self.assertTrue(prompts.read_default_message(filename).strip())
        self.assertFalse(hasattr(prompts, "DEFAULT_MESSAGES"))

    def test_expected_filenames_present(self):
        expected = {"user-message.md", "last-iteration-message.md", "wake-up-message.md",
                    "sleep-warning.md", "repeat-alert.md"}
        self.assertEqual(set(prompts.EDITABLE_MESSAGE_FILES), expected)

    def test_default_message_reads_source_file(self):
        with tempfile.TemporaryDirectory(prefix="ai-defaults-") as tmp:
            root = Path(tmp)
            filename = prompts.FILE_USER_MESSAGE
            (root / filename).write_text("из файла", encoding="utf-8")
            with mock.patch.object(prompts, "DEFAULT_PROMPTS_FOLDER", root):
                self.assertEqual(prompts.read_default_message(filename), "из файла")

    def test_internal_fallbacks_are_not_editable_defaults(self):
        self.assertEqual(set(prompts.INTERNAL_MESSAGES), {prompts.FILE_ITERATION_FAILED, prompts.FILE_TOOL_RESULT_MISSING})
        for filename in prompts.INTERNAL_MESSAGES:
            self.assertNotIn(filename, prompts.EDITABLE_MESSAGE_FILES)

    def test_default_placeholders_match_agent_usage(self):
        values = {
            prompts.FILE_SLEEP_WARNING: {"remaining": "10 итераций", "memory_note": "проверь память"},
            prompts.FILE_REPEAT_ALERT: {"streak": "3 итерации", "examples": "run_bash(...)"},
        }
        for filename, params in values.items():
            rendered = prompts.read_default_message(filename).format(**params)
            self.assertNotIn("{", rendered)
            self.assertNotIn("}", rendered)

    def test_default_placeholder_contract(self):
        self.assertEqual(prompts.ALLOWED_PLACEHOLDERS[prompts.FILE_SLEEP_WARNING], frozenset({"remaining", "memory_note"}))
        self.assertEqual(prompts.ALLOWED_PLACEHOLDERS[prompts.FILE_REPEAT_ALERT], frozenset({"streak", "examples"}))
        default = prompts.read_default_message(prompts.FILE_SLEEP_WARNING)
        self.assertNotIn("session_iterations", default)
        self.assertNotIn("advice", default)

    def test_files_without_placeholders_format_safe(self):
        for filename in (prompts.FILE_USER_MESSAGE, prompts.FILE_LAST_ITERATION_MESSAGE, prompts.FILE_WAKE_UP_MESSAGE):
            self.assertNotIn("{", prompts.read_default_message(filename))

    def test_internal_fallback_placeholders_are_complete(self):
        self.assertEqual(prompts.INTERNAL_MESSAGES[prompts.FILE_ITERATION_FAILED].format(error="RuntimeError: ой"), "[сбой итерации: RuntimeError: ой]")
        self.assertNotIn("{", prompts.INTERNAL_MESSAGES[prompts.FILE_TOOL_RESULT_MISSING])


class MessageTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="ai-prompts-"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)


class ReadMessageTests(MessageTestCase):
    def test_missing_file_falls_back_to_default(self):
        self.assertEqual(
            prompts.read_message(self._tmp, prompts.FILE_USER_MESSAGE),
            prompts.read_default_message(prompts.FILE_USER_MESSAGE),
        )

    def test_reads_file_content(self):
        path = self._tmp / prompts.FILE_USER_MESSAGE
        path.write_text("делай следующий шаг\n", encoding="utf-8")
        self.assertEqual(prompts.read_message(self._tmp, path.name), "делай следующий шаг")

    def test_rereads_on_every_call(self):
        path = self._tmp / prompts.FILE_USER_MESSAGE
        path.write_text("версия 1", encoding="utf-8")
        self.assertEqual(prompts.read_message(self._tmp, path.name), "версия 1")
        path.write_text("версия 2", encoding="utf-8")
        self.assertEqual(prompts.read_message(self._tmp, path.name), "версия 2")

    def test_empty_file_falls_back_to_default(self):
        path = self._tmp / prompts.FILE_USER_MESSAGE
        path.write_text("", encoding="utf-8")
        self.assertEqual(prompts.read_message(self._tmp, path.name), prompts.read_default_message(path.name))

    def test_whitespace_only_file_falls_back_to_default(self):
        path = self._tmp / prompts.FILE_USER_MESSAGE
        path.write_text("  \n\t \n", encoding="utf-8")
        self.assertEqual(prompts.read_message(self._tmp, path.name), prompts.read_default_message(path.name))

    def test_unreadable_path_falls_back_to_default(self):
        path = self._tmp / prompts.FILE_USER_MESSAGE
        path.mkdir()
        self.assertEqual(prompts.read_message(self._tmp, path.name), prompts.read_default_message(path.name))

    def test_unknown_filename_raises(self):
        with self.assertRaises(KeyError):
            prompts.read_message(self._tmp, "нет-такого-файла.md")


class FormatMessageTests(MessageTestCase):
    def test_fills_placeholders_from_file(self):
        path = self._tmp / prompts.FILE_ITERATION_FAILED
        path.write_text("СБОЙ: {error}", encoding="utf-8")
        self.assertEqual(prompts.format_message(self._tmp, path.name, error="ой"), "СБОЙ: ой")

    def test_default_template_used_when_file_missing(self):
        self.assertEqual(prompts.format_message(self._tmp, prompts.FILE_ITERATION_FAILED, error="ой"), "[сбой итерации: ой]")

    def test_unknown_placeholder_falls_back_to_default(self):
        path = self._tmp / prompts.FILE_ITERATION_FAILED
        path.write_text("сбой {нет_такого}", encoding="utf-8")
        self.assertEqual(prompts.format_message(self._tmp, path.name, error="ой"), "[сбой итерации: ой]")

    def test_single_brace_falls_back_to_default(self):
        path = self._tmp / prompts.FILE_ITERATION_FAILED
        path.write_text("текст { скобка и {error}", encoding="utf-8")
        self.assertEqual(prompts.format_message(self._tmp, path.name, error="ой"), "[сбой итерации: ой]")

    def test_doubled_braces_render_literal(self):
        path = self._tmp / prompts.FILE_ITERATION_FAILED
        path.write_text("код {{literal}} и {error}", encoding="utf-8")
        self.assertEqual(prompts.format_message(self._tmp, path.name, error="ой"), "код {literal} и ой")

    def test_sleep_warning_uses_new_placeholders(self):
        self.assertEqual(prompts.format_message(self._tmp, prompts.FILE_SLEEP_WARNING, remaining="10 итераций", memory_note="проверь память"), "До сна осталось 10 итераций. проверь память")

    def test_unknown_sleep_placeholder_falls_back_to_new_default(self):
        path = self._tmp / prompts.FILE_SLEEP_WARNING
        path.write_text("сон {нет_такого}", encoding="utf-8")
        expected = prompts.read_default_message(path.name).format(remaining="10 итераций", memory_note="проверь память")
        self.assertEqual(prompts.format_message(self._tmp, path.name, remaining="10 итераций", memory_note="проверь память"), expected)

    def test_missing_new_sleep_placeholder_does_not_raise(self):
        self.assertEqual(prompts.format_message(self._tmp, prompts.FILE_SLEEP_WARNING, remaining="1 итерацию"), "До сна осталось 1 итерацию. ")

    def test_placeholderless_file_formatted_verbatim(self):
        path = self._tmp / prompts.FILE_USER_MESSAGE
        path.write_text('json {"a": 1}', encoding="utf-8")
        self.assertEqual(prompts.read_message(self._tmp, path.name), 'json {"a": 1}')


class EnsureMessageFilesTests(MessageTestCase):
    def test_creates_all_missing_files_with_defaults(self):
        created = prompts.ensure_message_files(self._tmp)
        self.assertEqual(len(created), 5)
        self.assertEqual({path.name for path in created}, set(prompts.EDITABLE_MESSAGE_FILES))
        for filename in prompts.EDITABLE_MESSAGE_FILES:
            self.assertTrue((self._tmp / filename).is_file())
            self.assertEqual(
                (self._tmp / filename).read_text(encoding="utf-8").strip(),
                prompts.read_default_message(filename),
            )
        for filename in prompts.INTERNAL_MESSAGES:
            self.assertFalse((self._tmp / filename).exists())

    def test_second_run_creates_nothing(self):
        self.assertTrue(prompts.ensure_message_files(self._tmp))
        self.assertEqual(prompts.ensure_message_files(self._tmp), [])

    def test_existing_file_not_overwritten(self):
        path = self._tmp / prompts.FILE_USER_MESSAGE
        path.write_text("моя правка", encoding="utf-8")
        created = prompts.ensure_message_files(self._tmp)
        self.assertNotIn(path, created)
        self.assertEqual(path.read_text(encoding="utf-8"), "моя правка")


if __name__ == "__main__":
    unittest.main()
