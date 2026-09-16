"""Образ/контейнеры Docker, валидация timeout, ошибки недоступного Docker."""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sandbox_docker  # noqa: E402
from tests.helpers import run_python  # noqa: E402
from tests.tools_testkit import _bash, _paths, bash_tool_on  # noqa: E402

class DockerContainerLifecycleTests(unittest.TestCase):
    """Проверка управления образом и контейнерами агентов."""

    def test_sanitize_container_name(self):
        self.assertEqual(sandbox_docker.sanitize_container_name("bot"), "bot")
        self.assertEqual(sandbox_docker.sanitize_container_name("oleg"), "oleg")
        self.assertEqual(sandbox_docker.sanitize_container_name("my_agent-1"), "my_agent-1")
        self.assertEqual(sandbox_docker.sanitize_container_name("олег"), "oleg")
        self.assertEqual(sandbox_docker.sanitize_container_name(""), "default")
        self.assertEqual(sandbox_docker.sanitize_container_name("!!!"), "agent")

    def test_ensure_docker_image_present(self):
        sandbox_docker.ensure_docker_image()
        proc = subprocess.run(
            [sandbox_docker.DOCKER_BIN, "image", "inspect", sandbox_docker.DOCKER_IMAGE],
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0)

    def test_ensure_agent_container_creates_named_container_with_restart(self):
        agent_name = "test-unit-agent"
        self.addCleanup(
            lambda: subprocess.run([sandbox_docker.DOCKER_BIN, "rm", "-f", agent_name], capture_output=True)
        )
        c_name = sandbox_docker.ensure_docker_container(agent_name)
        self.assertEqual(c_name, agent_name)

        proc = subprocess.run(
            [
                sandbox_docker.DOCKER_BIN,
                "inspect",
                "--format",
                "{{.State.Running}}|{{.HostConfig.RestartPolicy.Name}}",
                agent_name,
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 0)
        running, restart_policy = proc.stdout.strip().split("|")
        self.assertEqual(running, "true")
        self.assertEqual(restart_policy, "always")

        # Повторный вызов не ломает контейнер
        c_name2 = sandbox_docker.ensure_docker_container(agent_name)
        self.assertEqual(c_name2, agent_name)

    def test_ensure_agent_container_restarts_stopped_container(self):
        agent_name = "test-stopped-agent"
        self.addCleanup(
            lambda: subprocess.run([sandbox_docker.DOCKER_BIN, "rm", "-f", agent_name], capture_output=True)
        )
        sandbox_docker.ensure_docker_container(agent_name)
        subprocess.run([sandbox_docker.DOCKER_BIN, "stop", agent_name], check=True, capture_output=True)

        # Проверяем, что ensure_docker_container перезапустит остановленный контейнер
        sandbox_docker.ensure_docker_container(agent_name)
        proc = subprocess.run(
            [sandbox_docker.DOCKER_BIN, "inspect", "--format", "{{.State.Running}}", agent_name],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.stdout.strip(), "true")


class TimeoutValidationTests(unittest.TestCase):
    """Валидация параметра timeout."""

    @classmethod
    def setUpClass(cls):
        ctx = bash_tool_on()
        ctx.__enter__()
        cls.addClassCleanup(ctx.__exit__, None, None, None)
        cls.tmp = Path(tempfile.mkdtemp(prefix="ai-tval-"))
        cls.paths = _paths(cls.tmp / "memory.md")
        cls.paths.memory.write_text("", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _invalid(self, timeout):
        out = _bash("ls", timeout=timeout, paths=self.paths)
        self.assertTrue(out.startswith("Error: invalid arguments"), out)
        self.assertIn("timeout", out)

    def test_invalid_string(self):
        self._invalid("abc")

    def test_invalid_bool(self):
        self._invalid(True)

    def test_invalid_zero(self):
        self._invalid(0)

    def test_invalid_fraction_below_minimum(self):
        self._invalid(0.5)

    def test_invalid_negative(self):
        self._invalid(-5)

    def test_invalid_over_max(self):
        self._invalid(301)

    def test_null_means_default(self):
        out = _bash("echo fast", timeout=None, paths=self.paths)
        self.assertIn("returncode: 0", out)

    def test_fractional_timeout_allowed(self):
        out = _bash("echo fast", timeout=1.5, paths=self.paths)
        self.assertIn("returncode: 0", out)



class DockerErrorsTests(unittest.TestCase):
    """Ошибки недоступного Docker."""

    def test_missing_docker_binary(self):
        r = run_python(
            "from agent_paths import AgentPaths; from pathlib import Path; "
            "import tempfile; "
            "d = Path(tempfile.mkdtemp(prefix='ai-err-')); "
            "import tool_registry as tools; "
            "p = AgentPaths(folder=d, system_prompt=d / 'x', "
            "mind_loop=d / 'x', memory=Path('/tmp/ai-err-mem.md')); "
            "print(tools.execute_tool('run_bash', '{\"command\": \"ls\"}', p))",
            env_extra={
                "DOCKER_BIN": "docker-definitely-missing",
                "ENABLE_BASH_TOOL": "1",  # без флага run_bash не исполняется вовсе
            },
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Error: песочница docker недоступна", r.stdout)
        self.assertIn("docker-definitely-missing", r.stdout)




if __name__ == "__main__":
    unittest.main()
