"""URL- и Docker-ветки vision_source без настоящей сети."""

import base64
import json
import shutil
import socket
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vision_source  # noqa: E402
from agent_paths import AgentPaths  # noqa: E402


class Response:
    def __init__(self, payload=b"bytes", status=200, headers=None):
        self.payload = payload
        self.status = status
        self.headers = headers or {}
        self.read_sizes = []
        self.closed = False

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size < 0:
            chunk, self.payload = self.payload, b""
            return chunk
        chunk, self.payload = self.payload[:size], self.payload[size:]
        return chunk

    def close(self):
        self.closed = True


def paths(root: Path) -> AgentPaths:
    return AgentPaths(
        folder=root, system_prompt=root / "system-prompt.md",
        mind_loop=root / "mind-loop.json", memory=root / "memory.md",
        name="source-agent",
    )


class UrlSourceTests(unittest.TestCase):
    def response(self, payload=b"image", **kwargs):
        response = Response(payload, **kwargs)
        patcher = mock.patch.object(vision_source, "urlopen", return_value=response)
        return response, patcher

    def test_get_has_safe_user_agent_and_reads_stream(self):
        response, patcher = self.response(b"image bytes")
        with patcher as urlopen:
            result = vision_source.download_url("https://example.org/photo.png")
        request = urlopen.call_args.args[0]
        self.assertIsInstance(request, Request)
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("ai-life", request.headers["User-agent"])
        self.assertEqual(result, b"image bytes")
        self.assertTrue(response.closed)

    def test_http_status_is_error_without_body(self):
        response, patcher = self.response(b"secret body", status=404)
        with patcher:
            with self.assertRaisesRegex(vision_source.VisionSourceError, "HTTP 404"):
                vision_source.download_url("https://example.org/not-found")
        self.assertEqual(response.read_sizes, [])

    def test_http_error_status_is_redacted(self):
        request = Request("https://example.org/photo?token=secret")
        error = HTTPError(request.full_url, 403, "secret", {}, None)
        with mock.patch.object(vision_source, "urlopen", side_effect=error):
            with self.assertRaisesRegex(vision_source.VisionSourceError, "HTTP 403"):
                vision_source.download_url(request.full_url)

    def test_content_length_limit_and_actual_stream_limit(self):
        with mock.patch.object(vision_source, "MAX_IMAGE_BYTES", 10):
            response, patcher = self.response(b"01234567890")
            with patcher:
                with self.assertRaises(vision_source.VisionSourceError):
                    vision_source.download_url("https://example.org/large")
            self.assertTrue(all(size <= 11 for size in response.read_sizes))

            response, patcher = self.response(
                b"0123456789", headers={"Content-Length": "not-a-number"}
            )
            with patcher:
                self.assertEqual(
                    vision_source.download_url("https://example.org/exact"),
                    b"0123456789",
                )
            self.assertEqual(response.read_sizes[-1], 1)

    def test_false_or_missing_content_length_does_not_skip_read(self):
        for headers in ({}, {"Content-Length": "-1"}, {"Content-Length": "0"}):
            with self.subTest(headers=headers):
                response, patcher = self.response(b"ok", headers=headers)
                with patcher:
                    self.assertEqual(
                        vision_source.download_url("https://example.org/a"), b"ok"
                    )
                self.assertTrue(response.read_sizes)

    def test_invalid_url_never_opens_network(self):
        with mock.patch.object(vision_source, "urlopen") as urlopen:
            for source in (
                "file:///tmp/photo.jpg", "data:image/jpeg;base64,AAAA",
                "ftp://example.org/a", "https://", "relative.jpg",
            ):
                with self.subTest(source=source):
                    with self.assertRaises(vision_source.VisionSourceError):
                        vision_source.download_url(source)
        urlopen.assert_not_called()

    def test_timeout_and_network_error_are_safe(self):
        for error, expected in (
            (TimeoutError(), "таймаут"),
            (URLError(socket.timeout()), "таймаут"),
            (URLError("offline"), "сети"),
        ):
            with self.subTest(error=error):
                with mock.patch.object(vision_source, "urlopen", side_effect=error):
                    with self.assertRaisesRegex(vision_source.VisionSourceError, expected):
                        vision_source.download_url("https://example.org/a")

    def test_redirect_policy_rejects_non_http_and_too_many(self):
        handler = vision_source._LimitedRedirectHandler()
        with self.assertRaises(vision_source.VisionSourceError):
            handler.redirect_request(
                Request("https://example.org"), object(), 302, "", {},
                "file:///tmp/photo.jpg",
            )
        handler.count = vision_source.MAX_REDIRECTS
        with self.assertRaisesRegex(vision_source.VisionSourceError, "перенаправлений"):
            handler.redirect_request(
                Request("https://example.org"), object(), 302, "", {},
                "https://example.org/next",
            )


class ContainerSourceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-vision-source-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.agent_paths = paths(self.root)

    def run_reader(self, payload, proc=None, error=None):
        if proc is None:
            proc = mock.Mock(returncode=0)
        with mock.patch.object(vision_source, "sandbox_container_name", return_value="current"), \
             mock.patch.object(vision_source, "exec_python", return_value=(error, proc, payload, "")) as run:
            try:
                result = vision_source.read_container_file("/root/photo.webp", self.agent_paths)
            except Exception as exc:
                result = exc
        return result, run

    def test_reader_uses_container_and_separate_argv(self):
        encoded = base64.b64encode(b"image").decode("ascii")
        result, run = self.run_reader(json.dumps({"base64": encoded}))
        self.assertEqual(result, b"image")
        args = run.call_args.args
        self.assertEqual(args[0], "current")
        self.assertIs(args[1], vision_source.IMAGE_READER_SCRIPT)
        self.assertEqual(args[2], ["/root/photo.webp"])
        self.assertEqual(args[3], vision_source.IMAGE_READ_TIMEOUT)

    def test_reader_errors_are_distinguished(self):
        for payload, expected in (
            ({"error": "not_found"}, "не найден"),
            ({"error": "is_dir"}, "директорией"),
            ({"error": "too_large"}, "слишком большой"),
        ):
            with self.subTest(payload=payload):
                result, _ = self.run_reader(json.dumps(payload))
                self.assertIsInstance(result, vision_source.VisionSourceError)
                self.assertIn(expected, str(result))

    def test_reader_rejects_docker_failures_and_bad_output(self):
        for payload, error, expected in (
            ("not-json", None, "некорректный ответ"),
            (json.dumps({"base64": "!"}), None, "некорректный Base64"),
            (None, "TIMEOUT", "таймаут"),
            (None, "Error: docker offline", None),
        ):
            with self.subTest(expected=expected):
                result, _ = self.run_reader(payload, error=error)
                self.assertIsInstance(result, vision_source.VisionSourceError)
                if expected:
                    self.assertIn(expected, str(result))

    def test_none_paths_never_calls_docker(self):
        with mock.patch.object(vision_source, "exec_python") as run:
            with self.assertRaises(vision_source.VisionSourceError):
                vision_source.read_container_file("/root/photo.jpg", None)
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
