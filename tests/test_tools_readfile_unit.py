"""read_file без docker: сборка команды и форматирование ответа раннера."""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sandbox_docker  # noqa: E402
import sandbox_scripts  # noqa: E402
import tool_registry as tools  # noqa: E402
import tools_readfile  # noqa: E402
from tests.tools_testkit import _paths, bash_tool_on  # noqa: E402

class ReadFileUnitTests(unittest.TestCase):
    """read_file без docker: сборка команды и форматирование ответа раннера."""

    def setUp(self):
        from unittest.mock import patch

        self._patch = patch
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-readunit-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.paths = _paths(self.tmp / "memory.md", name="ai-read-unit")
        ctx = bash_tool_on()
        ctx.__enter__()
        self.addCleanup(ctx.__exit__, None, None, None)
        self.captured_input = None
        outer = self

        class FakeProc:
            returncode = 0

            def __init__(self, stdout="", stderr="", raise_timeout=False):
                self.stdout = stdout
                self.stderr = stderr
                self.raise_timeout = raise_timeout
                self.killed = False

            def kill(self):
                self.killed = True

            def communicate(self, input=None, timeout=None):
                if timeout is not None and self.raise_timeout:
                    raise subprocess.TimeoutExpired("docker exec", timeout)
                outer.captured_input = input
                return self.stdout, self.stderr

        self.FakeProc = FakeProc

    def _read(self, args: dict, proc=None):
        if proc is None:
            proc = self.FakeProc()
        with self._patch.object(sandbox_scripts, "check_docker_available", return_value=None), \
             self._patch.object(
                 sandbox_scripts, "ensure_docker_container", return_value="fake-container"
             ), \
             self._patch.object(sandbox_scripts.subprocess, "Popen", return_value=proc) as popen:
            result = tools.execute_tool("read_file", json.dumps(args), self.paths)
        return result, popen

    def test_exec_runs_reader_script_in_agent_container(self):
        payload = {
            "path": "/root/code.py",
            "size": 100,
            "total_lines": 3,
            "start": 1,
            "end": 3,
            "lines": ["a", "b", "c"],
        }
        result, popen = self._read(
            {"path": "/root/code.py"},
            proc=self.FakeProc(stdout=json.dumps(payload)),
        )
        cmd = popen.call_args.args[0]
        self.assertEqual(
            cmd,
            [
                sandbox_docker.DOCKER_BIN,
                "exec",
                "-i",
                "-w",
                "/root",
                "fake-container",
                "python3",
                "-",
                "/root/code.py",
                "1",
                "200",
            ],
        )
        self.assertEqual(self.captured_input, tools_readfile.READER_SCRIPT)
        self.assertIn("прочитано 3 из 3 строк", result)
        self.assertIn("(конец файла)", result)

    def test_limit_above_max_is_clamped_with_note(self):
        payload = {
            "path": "x",
            "size": 100,
            "total_lines": 10,
            "start": 1,
            "end": 10,
            "lines": ["l"] * 10,
        }
        result, popen = self._read(
            {"path": "x", "limit": 5000},
            proc=self.FakeProc(stdout=json.dumps(payload)),
        )
        # Раннеру передаётся граница, а не исходное значение.
        self.assertEqual(popen.call_args.args[0][-1], str(tools_readfile.READ_FILE_MAX_LIMIT))
        self.assertIn(
            f"limit уменьшен до {tools_readfile.READ_FILE_MAX_LIMIT}", result
        )

    def test_limit_below_min_is_clamped_with_note(self):
        payload = {
            "path": "x",
            "size": 100,
            "total_lines": 10,
            "start": 1,
            "end": 1,
            "lines": ["l"],
        }
        result, popen = self._read(
            {"path": "x", "limit": 0},
            proc=self.FakeProc(stdout=json.dumps(payload)),
        )
        self.assertEqual(popen.call_args.args[0][-1], "1")
        self.assertIn("limit увеличен до 1", result)

    def test_in_range_limit_produces_no_clamp_note(self):
        payload = {
            "path": "x",
            "size": 100,
            "total_lines": 10,
            "start": 1,
            "end": 10,
            "lines": ["l"] * 10,
        }
        result, _ = self._read(
            {"path": "x", "limit": tools_readfile.READ_FILE_MAX_LIMIT},
            proc=self.FakeProc(stdout=json.dumps(payload)),
        )
        self.assertNotIn("limit уменьшен", result)
        self.assertNotIn("limit увеличен", result)

    def test_custom_offset_and_limit_passed_to_runner(self):
        payload = {
            "path": "x",
            "size": 1,
            "total_lines": 100,
            "start": 51,
            "end": 75,
            "lines": ["l"] * 25,
        }
        _, popen = self._read(
            {"path": "x", "offset": 51, "limit": 25},
            proc=self.FakeProc(stdout=json.dumps(payload)),
        )
        self.assertEqual(popen.call_args.args[0][-3:], ["x", "51", "25"])

    def test_formats_page_with_continuation_hint(self):
        payload = {
            "path": "/root/big.py",
            "size": 45213,
            "total_lines": 1253,
            "start": 1,
            "end": 200,
            "lines": ["line-%d" % i for i in range(1, 201)],
        }
        result, _ = self._read(
            {"path": "/root/big.py"}, proc=self.FakeProc(stdout=json.dumps(payload))
        )
        self.assertIn("/root/big.py — 1253 строк, 45213 байт", result)
        self.assertIn("прочитано 200 из 1253 строк", result)
        self.assertIn("показаны строки 1–200 из 1253", result)
        self.assertIn("продолжение — read_file offset=201", result)
        self.assertIn("1 | line-1", result)
        self.assertIn("200 | line-200", result)
        self.assertNotIn("(конец файла)", result)

    def test_formats_last_page_as_end_of_file(self):
        payload = {
            "path": "x",
            "size": 1,
            "total_lines": 305,
            "start": 201,
            "end": 305,
            "lines": ["l"] * 105,
        }
        result, _ = self._read(
            {"path": "x", "offset": 201}, proc=self.FakeProc(stdout=json.dumps(payload))
        )
        self.assertIn("показаны строки 201–305 из 305", result)
        self.assertIn("(конец файла)", result)
        self.assertNotIn("продолжение", result)

    def test_overlong_line_truncated(self):
        payload = {
            "path": "x",
            "size": 9999,
            "total_lines": 1,
            "start": 1,
            "end": 1,
            "lines": ["A" * 5000],
        }
        result, _ = self._read(
            {"path": "x"}, proc=self.FakeProc(stdout=json.dumps(payload))
        )
        self.assertIn("строка обрезана, всего 5000 симв.", result)
        self.assertNotIn("A" * 3000, result)

    def test_runner_errors_translated(self):
        cases = [
            ({"error": "not_found"}, "Error: file not found: /root/x"),
            ({"error": "is_dir"}, "Error: это директория, а не файл"),
            ({"error": "binary", "size": 4096}, "Error: двоичный файл: /root/x (4096 байт)"),
            (
                {"error": "offset_out_of_range", "total_lines": 10},
                "Error: offset=999 за пределами файла (всего 10 строк)",
            ),
        ]
        for payload, expected in cases:
            with self.subTest(error=payload.get("error")):
                result, _ = self._read(
                    {"path": "/root/x", "offset": 999},
                    proc=self.FakeProc(stdout=json.dumps(payload)),
                )
                self.assertIn(expected, result)

    def test_unexpected_output_falls_back_to_raw(self):
        result, _ = self._read(
            {"path": "/root/x"}, proc=self.FakeProc(stdout="not-json", stderr="boom")
        )
        self.assertIn("$ read_file /root/x", result)
        self.assertIn("not-json", result)
        self.assertIn("boom", result)

    def test_timeout_returns_timeout_message(self):
        proc = self.FakeProc(raise_timeout=True)
        result, _ = self._read({"path": "/root/x"}, proc=proc)
        self.assertIn(f"TIMEOUT after {tools_readfile.READ_FILE_TIMEOUT}s", result)
        self.assertTrue(proc.killed)




if __name__ == "__main__":
    unittest.main()
