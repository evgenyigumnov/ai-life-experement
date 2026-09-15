"""Русская плюрализация числительных."""

import unittest

from agent_text import _plural_entries, _plural_iterations, _plural_messages


class PluralizationTests(unittest.TestCase):
    def test_all_word_forms(self):
        functions = (
            (_plural_iterations, "итерацию", "итерации", "итераций"),
            (_plural_messages, "сообщение", "сообщения", "сообщений"),
            (_plural_entries, "запись", "записи", "записей"),
        )
        for pluralize, one, few, many in functions:
            with self.subTest(function=pluralize.__name__):
                self.assertEqual(pluralize(1), f"1 {one}")
                self.assertEqual(pluralize(2), f"2 {few}")
                self.assertEqual(pluralize(5), f"5 {many}")
                self.assertEqual(pluralize(11), f"11 {many}")
                self.assertEqual(pluralize(14), f"14 {many}")
                self.assertEqual(pluralize(21), f"21 {one}")
                self.assertEqual(pluralize(22), f"22 {few}")


if __name__ == "__main__":
    unittest.main()
