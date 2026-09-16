"""Общие ограничения вывода и очередь файловых мутаций."""

import threading
import time
import tempfile
import unittest
from pathlib import Path

from file_mutation_queue import mutation_queue_key, with_file_mutation_queue
from tools_bash_output import format_bash_result
from tools_truncate import DEFAULT_MAX_BYTES, DEFAULT_MAX_LINES, truncate_head, truncate_tail


class TruncateTests(unittest.TestCase):
    def test_head_uses_first_limit_and_returns_metadata(self):
        result = truncate_head("a\nb\nc\n", max_lines=2, max_bytes=100)
        self.assertEqual(result["content"], "a\nb")
        self.assertEqual(result["truncatedBy"], "lines")
        self.assertEqual(result["totalLines"], 3)
        self.assertEqual(result["totalBytes"], 6)

    def test_byte_limit_never_returns_a_partial_line(self):
        result = truncate_head("one\ntwo\nthree", max_lines=10, max_bytes=6)
        self.assertEqual(result["content"], "one")
        self.assertEqual(result["truncatedBy"], "bytes")
        self.assertNotIn("tw", result["content"])

    def test_tail_keeps_complete_last_lines(self):
        result = truncate_tail("1\n2\n3\n4", max_lines=2, max_bytes=100)
        self.assertEqual(result["content"], "3\n4")
        self.assertEqual(result["truncatedBy"], "lines")

    def test_dropped_final_newline_counts_as_byte_truncation(self):
        result = truncate_head("line\n", max_lines=10, max_bytes=4)
        self.assertEqual(result["content"], "line")
        self.assertEqual(result["truncatedBy"], "bytes")

    def test_default_limits_are_independent(self):
        result = truncate_head("x\n" * (DEFAULT_MAX_LINES + 1))
        self.assertEqual(result["truncatedBy"], "lines")
        self.assertEqual(result["totalLines"], DEFAULT_MAX_LINES + 1)
        self.assertLessEqual(result["outputBytes"], DEFAULT_MAX_BYTES)

    def test_run_bash_keeps_status_and_reports_common_metadata(self):
        output = format_bash_result("seq", 0, "x\n" * 2501, "")
        self.assertIn("returncode: 0", output)
        self.assertIn("truncatedBy=lines", output)
        self.assertIn("totalLines=2504", output)
        self.assertLessEqual(len(output.splitlines()), DEFAULT_MAX_LINES + 4)


class MutationQueueTests(unittest.TestCase):
    def test_same_realpath_is_serialized(self):
        order = []
        first_started = threading.Event()

        def first():
            order.append("first:start")
            first_started.set()
            time.sleep(0.02)
            order.append("first:end")

        def second():
            order.append("second:start")
            order.append("second:end")

        first_thread = threading.Thread(
            target=lambda: with_file_mutation_queue("/tmp/q", first)
        )
        second_thread = threading.Thread(
            target=lambda: with_file_mutation_queue("/tmp/q", second)
        )
        first_thread.start()
        self.assertTrue(first_started.wait(1))
        second_thread.start()
        first_thread.join()
        second_thread.join()
        self.assertEqual(order, ["first:start", "first:end", "second:start", "second:end"])

    def test_symlink_uses_target_realpath(self):
        with tempfile.TemporaryDirectory(prefix="ai-queue-") as directory:
            root = Path(directory)
            target = root / "target"
            alias = root / "alias"
            target.write_text("x", encoding="utf-8")
            alias.symlink_to(target)
            self.assertEqual(mutation_queue_key(target), mutation_queue_key(alias))


if __name__ == "__main__":
    unittest.main()
