"""Интеграционные тесты Docker-песочницы: исполнение, изоляция, read_file."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sandbox_docker  # noqa: E402
import tool_registry as tools  # noqa: E402
from tests.tools_testkit import _bash, _paths, bash_tool_on  # noqa: E402

class DockerSandboxTests(unittest.TestCase):
    """Интеграционные тесты исполнения команд в Docker-песочнице."""

    TEST_CONTAINER = "ai-test-sandbox"

    @classmethod
    def setUpClass(cls):
        # песочница тестируется при включённом run_bash (по умолчанию он выключен)
        ctx = bash_tool_on()
        ctx.__enter__()
        cls.addClassCleanup(ctx.__exit__, None, None, None)
        cls.tmp = Path(tempfile.mkdtemp(prefix="ai-tools-"))
        cls.paths = _paths(cls.tmp / "memory.md", name=cls.TEST_CONTAINER)
        cls.paths.memory.write_text("", encoding="utf-8")
        sandbox_docker.ensure_docker_container(cls.TEST_CONTAINER)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        subprocess.run(
            [sandbox_docker.DOCKER_BIN, "rm", "-f", cls.TEST_CONTAINER],
            capture_output=True,
        )

    def test_basic_execution_inside_container(self):
        out = _bash("pwd && echo rc-ok", paths=self.paths)
        self.assertIn("returncode: 0", out)
        self.assertIn("/root", out)
        self.assertIn("rc-ok", out)

    def test_image_contains_required_tools(self):
        # busybox + python3 + pip + curl + apk + bash
        cmds = (
            "busybox --help | head -n 1 && "
            "python3 --version && "
            "pip --version && "
            "curl --version && "
            "apk --version && "
            "bash --version"
        )
        out = _bash(cmds, paths=self.paths)
        self.assertIn("returncode: 0", out)
        self.assertIn("BusyBox", out)
        self.assertIn("Python 3", out)
        self.assertIn("pip", out)
        self.assertIn("curl", out)
        self.assertIn("apk-tools", out)
        self.assertIn("GNU bash", out)

    def test_package_manager_can_install(self):
        # apk может устанавливать пакеты из сети
        out = _bash("apk add --no-cache which && which which", timeout=30, paths=self.paths)
        self.assertIn("returncode: 0", out)
        self.assertIn("which", out)

    def test_container_restart_policy_is_always(self):
        proc = subprocess.run(
            [
                sandbox_docker.DOCKER_BIN,
                "inspect",
                "--format",
                "{{.HostConfig.RestartPolicy.Name}}",
                self.TEST_CONTAINER,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "always")

    def test_host_files_not_readable(self):
        host_file = Path(tempfile.mkstemp(prefix="ai-host-probe-")[1])
        self.addCleanup(host_file.unlink)
        host_file.write_text("HOST-SECRET", encoding="utf-8")
        out = _bash(f"cat {host_file}; echo rc=$?", paths=self.paths)
        self.assertIn("No such file", out)
        self.assertNotIn("HOST-SECRET", out)
        self.assertIn("rc=1", out)

    def test_host_home_not_listed(self):
        out = _bash("ls /home", paths=self.paths)
        self.assertNotIn("evgeny-igumnov", out)

    def test_ps_processes_isolated(self):
        out = _bash("ps aux", paths=self.paths)
        self.assertIn("returncode: 0", out)
        self.assertNotIn("kthreadd", out)
        self.assertNotIn(str(os.getpid()), out)

    def test_writes_stay_in_container(self):
        out = _bash(
            "echo ai-test > /tmp/ai-test-write && cat /tmp/ai-test-write",
            paths=self.paths,
        )
        self.assertIn("returncode: 0", out)
        self.assertIn("ai-test", out)
        self.assertFalse((Path("/tmp") / "ai-test-write").exists())

    def test_network_dns_available(self):
        out = _bash("curl -s -I https://example.com | head -n 1", timeout=15, paths=self.paths)
        self.assertIn("returncode: 0", out)
        self.assertTrue("200" in out or "302" in out or "HTTP" in out)

    def test_default_timeout_is_5_seconds(self):
        started = time.monotonic()
        out = _bash("sleep 10", paths=self.paths)
        elapsed = time.monotonic() - started
        self.assertIn("TIMEOUT after 5.0s", out)
        self.assertGreaterEqual(elapsed, 4.3)
        self.assertLess(elapsed, 9.0)

    def test_explicit_timeout_allows_longer_command(self):
        out = _bash("sleep 6", timeout=10, paths=self.paths)
        self.assertIn("returncode: 0", out)
        self.assertNotIn("TIMEOUT", out)

    def test_timeout_kills_background_children(self):
        out = _bash("sleep 93 & sleep 93", timeout=2, paths=self.paths)
        self.assertIn("TIMEOUT after 2.0s", out)
        check = subprocess.run(
            [sandbox_docker.DOCKER_BIN, "exec", self.TEST_CONTAINER, "ps", "aux"],
            capture_output=True,
            text=True,
        )
        self.assertNotIn("sleep 93", check.stdout)

    def test_output_truncated_to_limit(self):
        out = _bash("head -c 60000 /dev/zero | tr '\\0' 'a'", timeout=30, paths=self.paths)
        self.assertIn("...output truncated", out)
        self.assertLess(len(out), 52_000)

    def test_nonzero_returncode_and_stderr_reported(self):
        out = _bash("ls /definitely/not/here", paths=self.paths)
        self.assertNotIn("returncode: 0", out)
        self.assertIn("No such file or directory", out)

    def _read(self, path, offset=None, limit=None) -> str:
        args = {"path": path}
        if offset is not None:
            args["offset"] = offset
        if limit is not None:
            args["limit"] = limit
        return tools.execute_tool("read_file", json.dumps(args), self.paths)

    def test_read_file_pages_through_large_file(self):
        _bash("seq 1 305 > /root/pages.txt", paths=self.paths)
        first = self._read("/root/pages.txt")
        self.assertIn("305 строк", first)
        self.assertIn("показаны строки 1–200 из 305", first)
        self.assertIn("продолжение — read_file offset=201", first)
        self.assertIn("200 | 200", first)
        self.assertNotIn("201 | 201", first)
        second = self._read("/root/pages.txt", offset=201)
        self.assertIn("показаны строки 201–305", second)
        self.assertIn("(конец файла)", second)
        self.assertIn("305 | 305", second)
        self.assertNotIn("продолжение", second)

    def test_read_file_respects_limit_and_offset(self):
        _bash("seq 1 10 > /root/ten.txt", paths=self.paths)
        out = self._read("/root/ten.txt", offset=3, limit=2)
        self.assertIn("10 строк", out)
        self.assertIn("прочитано 2 из 10 строк", out)
        self.assertIn("показаны строки 3–4 из 10", out)
        self.assertIn("3 | 3", out)
        self.assertIn("4 | 4", out)
        self.assertNotIn("5 | 5", out)

    def test_read_file_small_file_shown_fully(self):
        _bash("printf 'alpha\\nbeta\\n' > /root/small.txt", paths=self.paths)
        out = self._read("/root/small.txt")
        self.assertIn("2 строк", out)
        self.assertIn("(конец файла)", out)
        self.assertIn("1 | alpha", out)
        self.assertIn("2 | beta", out)

    def test_read_file_empty_file_is_end_of_file(self):
        _bash(": > /root/empty.txt", paths=self.paths)
        out = self._read("/root/empty.txt")
        self.assertIn("0 строк", out)
        self.assertIn("(конец файла)", out)
        self.assertNotIn("offset=", out)

    def test_read_file_output_has_common_byte_limit(self):
        _bash(
            "for i in $(seq 1 100); do head -c 2400 /dev/zero | tr '\\0' x; printf '\\n'; done > /root/large-lines.txt",
            paths=self.paths,
        )
        out = self._read("/root/large-lines.txt", limit=1000)
        self.assertLessEqual(len(out.encode("utf-8")), 52 * 1024)
        self.assertIn("truncatedBy=bytes", out)
        self.assertIn("всего 2400 симв.", out)
        self.assertIn("продолжение — read_file offset=", out)

    def test_read_file_rejects_late_binary_marker(self):
        _bash(
            "head -c 9000 /dev/zero | tr '\\0' 'a' > /root/late.bin; "
            "printf '\\0' >> /root/late.bin",
            paths=self.paths,
        )
        out = self._read("/root/late.bin")
        self.assertIn("Error: двоичный файл", out)

    def test_read_file_errors(self):
        missing = self._read("/definitely/not/here.txt")
        self.assertIn("Error: file not found: /definitely/not/here.txt", missing)
        is_dir = self._read("/root")
        self.assertIn("директория", is_dir)
        self.assertIn("run_bash ls", is_dir)
        over = self._read("/root/ten.txt", offset=400)
        self.assertIn("Error: file not found", over)  # файла нет — не создаём зависимостей между тестами
        _bash("seq 1 10 > /root/ten.txt", paths=self.paths)
        over = self._read("/root/ten.txt", offset=400)
        self.assertIn("Error: offset=400 за пределами файла", over)
        self.assertIn("всего 10 строк", over)

    def test_read_file_rejects_binary(self):
        _bash(
            "printf 'bin\\x00\\x01\\x02data' > /root/blob.bin",
            paths=self.paths,
        )
        out = self._read("/root/blob.bin")
        self.assertIn("Error: двоичный файл", out)

    def test_read_file_relative_path_from_root_workdir(self):
        _bash("echo rel > /root/rel.txt", paths=self.paths)
        out = self._read("rel.txt")
        self.assertIn("1 | rel", out)




if __name__ == "__main__":
    unittest.main()
