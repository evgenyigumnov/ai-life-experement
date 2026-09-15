"""Два живых inspect_image smoke-вызова: URL и путь внутри Docker."""

import os
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import llm  # noqa: E402
import sandbox_docker  # noqa: E402
import tool_registry  # noqa: E402
from agent_paths import AgentPaths  # noqa: E402
from tests.live_testkit import (  # noqa: E402
    LiveUnavailable, _check_reachable, _fail_fast_sleep, _load_live_config,
    _required, _skip_or_fail,
)
from tool_context import ToolContext  # noqa: E402


FIXTURE = Path(__file__).parent / "fixtures" / "vision_test.jpg"


class _FixtureHandler(BaseHTTPRequestHandler):
    payload = b""

    def do_GET(self):
        if self.path != "/vision_test.jpg":
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, *_args):
        pass


class VisionLiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        size = FIXTURE.stat().st_size if FIXTURE.is_file() else 0
        if not 5_120 <= size <= 10_240:
            raise AssertionError(f"vision fixture должен быть 5–10 KiB, получено {size}")
        try:
            cfg = _load_live_config()
            _check_reachable(cfg)
        except LiveUnavailable as exc:
            _skip_or_fail(exc)
        cls.cfg = cfg
        cls.payload = FIXTURE.read_bytes()
        cls.temp_root = Path(tempfile.mkdtemp(prefix="ai-vision-live-"))
        cls.addClassCleanup(lambda: shutil.rmtree(cls.temp_root, ignore_errors=True))

    def _context(self):
        return ToolContext(
            llm.make_client(self.cfg), self.cfg.model, self.cfg.temperature,
            self.cfg.reasoning_effort,
        )

    def _call(self, source, paths):
        args = {"source": source, "question": "Какого цвета большая фигура? Ответь по-русски."}
        with mock.patch.object(llm.time, "sleep", side_effect=_fail_fast_sleep):
            return tool_registry.execute_tool(
                "inspect_image", args, paths, self._context()
            )

    def _assert_answer(self, result):
        if result.startswith("Error:"):
            if _required():
                self.fail(result)
            # Только недоступность инфраструктуры/API допускает skip.
            markers = ("400", "Docker", "docker", "сети", "таймаут", "пауза", "недоступ")
            if any(marker in result for marker in markers):
                raise unittest.SkipTest(result)
            self.fail(result)
        lower = result.lower()
        self.assertTrue("красн" in lower or "red" in lower, result)
        self.assertNotIn("<think", lower)
        self.assertNotIn("reasoning_content", lower)
        self.assertNotIn("tool_calls", lower)
        self.assertNotIn("data:image", lower)

    def _serve_fixture(self):
        _FixtureHandler.payload = self.payload
        server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_port}/vision_test.jpg"

    def test_url_source(self):
        result = self._call(self._serve_fixture(), None)
        self._assert_answer(result)

    def test_docker_path_source(self):
        name = f"ai-vision-live-{os.getpid()}"
        try:
            container = sandbox_docker.ensure_docker_container(name)
            self.addCleanup(lambda: subprocess.run(
                [sandbox_docker.DOCKER_BIN, "rm", "-f", name], capture_output=True
            ))
            copied = subprocess.run(
                [sandbox_docker.DOCKER_BIN, "cp", str(FIXTURE),
                 f"{container}:/root/vision-live.jpg"],
                capture_output=True, text=True, timeout=30,
            )
            if copied.returncode != 0:
                raise LiveUnavailable(f"Docker cp не удался: {copied.stderr.strip()}")
        except Exception as exc:
            _skip_or_fail(exc)
        root = self.temp_root / "agent"
        root.mkdir(exist_ok=True)
        paths = AgentPaths(
            folder=root, system_prompt=root / "system-prompt.md",
            mind_loop=root / "mind-loop.json", memory=root / "memory.md",
            name=name,
        )
        self._assert_answer(self._call("/root/vision-live.jpg", paths))


if __name__ == "__main__":
    unittest.main()
