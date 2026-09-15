"""Общий формат времени используется всеми хранилищами."""

import re
import unittest

import time_utils


class TimeUtilsTests(unittest.TestCase):
    def test_now_iso_has_seconds_precision(self):
        self.assertRegex(time_utils.now_iso(), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")


if __name__ == "__main__":
    unittest.main()
