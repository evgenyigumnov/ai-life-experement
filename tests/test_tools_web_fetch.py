"""Тесты web_fetch без Brave и настоящей сети."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tool_registry  # noqa: E402
import tools_web_fetch  # noqa: E402
import web_fetch_http  # noqa: E402


class Response:
    def __init__(self, payload, content_type="text/html; charset=utf-8", status=200):
        self.payload = payload if isinstance(payload, bytes) else payload.encode()
        self.status = status
        self.headers = {"Content-Type": content_type}
        self.closed = False

    def read(self, size=-1):
        chunk, self.payload = self.payload[:size], self.payload[size:]
        return chunk

    def geturl(self):
        return "https://wiki.orc/index.html"

    def close(self):
        self.closed = True


class WebFetchTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-web-fetch-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def call(self, args, response):
        with mock.patch.object(web_fetch_http.urllib.request, "urlopen", return_value=response) as opened:
            result = tool_registry.execute_tool("web_fetch", args)
        return result, opened

    def test_schema_is_registered_and_does_not_need_brave(self):
        function = tools_web_fetch.WEB_FETCH_TOOL["function"]
        self.assertEqual(function["name"], "web_fetch")
        self.assertEqual(
            set(function["parameters"]["properties"]), {"url", "offset", "limit"}
        )
        self.assertEqual(function["parameters"]["required"], ["url"])
        self.assertIn("начиная с 1", function["parameters"]["properties"]["offset"]["description"])
        names = [tool["function"]["name"] for tool in tool_registry.build_tools_schema(False)]
        self.assertIn("web_fetch", names)
        self.assertIs(tool_registry._HANDLERS["web_fetch"], tools_web_fetch.handle_web_fetch)
        json.dumps(tools_web_fetch.WEB_FETCH_TOOL)

    def test_html_is_text_with_numbered_unique_links(self):
        response = Response(
            "<html><head><title>Wiki</title><script>secret()</script></head>"
            "<body><h1>Page</h1><p>Read <a href='/page1.html'>one</a> and "
            "<a href='https://wiki.orc/page2.html'>two</a>.</p>"
            "<p>Again <a href='/page1.html'>one</a>.</p></body></html>"
        )
        result, opened = self.call({"url": "https://wiki.orc/index.html"}, response)
        self.assertIn("Wiki\nPage\nRead one [1] and two [2].\nAgain one [1].", result)
        self.assertIn("Ссылки:\n[1] https://wiki.orc/page1.html\n[2] https://wiki.orc/page2.html", result)
        self.assertNotIn("secret", result)
        request = opened.call_args.args[0]
        self.assertIsInstance(request, Request)
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("ai-life", request.headers["User-agent"])
        self.assertNotIn("X-subscription-token", request.headers)
        self.assertTrue(response.closed)

    def test_long_page_is_read_in_character_pages(self):
        payload = "".join(f"{index:04d}" for index in range(125))
        first, _ = self.call(
            {"url": "https://example.org/start", "limit": 100},
            Response(payload, "text/plain"),
        )
        self.assertIn("web_fetch: символы 1–100 из 500", first)
        self.assertIn("продолжение — web_fetch offset=101", first)
        self.assertIn(payload[:100], first)
        self.assertNotIn(payload[100:200], first)

        second, _ = self.call(
            {"url": "https://example.org/start", "offset": 101, "limit": 100},
            Response(payload, "text/plain"),
        )
        self.assertIn("web_fetch: символы 101–200 из 500", second)
        self.assertIn(payload[100:200], second)
        self.assertNotIn(payload[:100], second)

    def test_page_result_never_exceeds_safe_output_limit(self):
        payload = "x" * (tools_web_fetch.MAX_RESULT_CHARS * 2)
        result, _ = self.call(
            {"url": "https://example.org/start"}, Response(payload, "text/plain")
        )
        self.assertLessEqual(len(result), tools_web_fetch.MAX_RESULT_CHARS)
        self.assertIn("продолжение — web_fetch offset=", result)

    def test_limit_is_clamped_with_a_note(self):
        result, _ = self.call(
            {"url": "https://example.org/start", "limit": 99999},
            Response("short", "text/plain"),
        )
        self.assertIn(
            f"limit уменьшен до {tools_web_fetch.WEB_FETCH_MAX_LIMIT}", result
        )

    def test_offset_past_page_is_reported(self):
        result, _ = self.call(
            {"url": "https://example.org/start", "offset": 5},
            Response("abc", "text/plain"),
        )
        self.assertEqual(
            result,
            "Error: web_fetch: offset=5 за пределами страницы (всего 3 символов)",
        )

    def test_raw_argument_is_rejected_after_interface_removal(self):
        with mock.patch.object(web_fetch_http.urllib.request, "urlopen") as opened:
            result = tool_registry.execute_tool(
                "web_fetch", {"url": "https://wiki.orc/index.html", "raw": True}
            )
        self.assertTrue(result.startswith("Error: invalid arguments"))
        opened.assert_not_called()

    def test_plain_text_urls_are_cited(self):
        response = Response("See https://example.org/page.\nSee it again: https://example.org/page", "text/plain")
        result, _ = self.call({"url": "https://example.org/start"}, response)
        self.assertIn("https://example.org/page [1].", result)
        self.assertEqual(result.count("[1] https://example.org/page"), 1)

    def test_invalid_args_do_not_open_network(self):
        invalid = [
            {}, {"url": ""}, {"url": "ftp://example.org"},
            {"url": "https://"}, {"url": "https://example.org", "raw": "yes"},
            {"url": "https://example.org", "extra": 1},
            {"url": "https://example.org", "offset": 0},
            {"url": "https://example.org", "offset": "1"},
            {"url": "https://example.org", "limit": 2.5},
            {"url": "https://example.org", "limit": True},
        ]
        with mock.patch.object(web_fetch_http.urllib.request, "urlopen") as opened:
            for args in invalid:
                with self.subTest(args=args):
                    self.assertTrue(tool_registry.execute_tool("web_fetch", args).startswith("Error: invalid arguments"))
        opened.assert_not_called()

    def test_http_errors_are_safe(self):
        request = Request("https://example.org/private?token=secret")
        error = HTTPError(request.full_url, 404, "secret", {}, None)
        with mock.patch.object(web_fetch_http.urllib.request, "urlopen", side_effect=error):
            result = tool_registry.execute_tool("web_fetch", {"url": request.full_url})
        self.assertEqual(result, "Error: web_fetch: HTTP 404")
        self.assertNotIn("secret", result)


if __name__ == "__main__":
    unittest.main()
