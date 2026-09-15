"""Тесты internet_search без обращения к реальному Brave API."""

import json
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tools_search  # noqa: E402
from tests.helpers import env  # noqa: E402


KEY = "test-brave-secret"


class Response:
    def __init__(self, payload, status=200):
        self.status = status
        self.payload = payload
        self.closed = False

    def read(self):
        return self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()

    def close(self):
        self.closed = True


def brave_payload(results=None, more=False):
    return {
        "query": {"more_results_available": more},
        "web": {"results": results or []},
    }


class SearchTests(unittest.TestCase):
    def call(self, args, response=None, side_effect=None):
        with env(BRAVE_KEY=KEY), mock.patch.object(
            tools_search.urllib.request,
            "urlopen",
            return_value=response,
            side_effect=side_effect,
        ) as urlopen:
            result = tools_search.handle_internet_search(args)
        return result, urlopen

    def test_schema_and_json(self):
        function = tools_search.INTERNET_SEARCH_TOOL["function"]
        self.assertEqual(function["name"], "internet_search")
        self.assertEqual(function["parameters"]["required"], ["query"])
        self.assertNotIn("safesearch", function["parameters"]["properties"])
        json.dumps(tools_search.INTERNET_SEARCH_TOOL)

    def test_valid_request_and_format(self):
        payload = brave_payload([
            {"title": "Python", "url": "https://python.org", "description": "A language"}
        ], more=True)
        result, urlopen = self.call(
            {"query": " Python docs ", "count": 3, "offset": 2,
             "country": "US", "search_lang": "EN", "freshness": "pw"},
            Response(payload),
        )
        request = urlopen.call_args.args[0]
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertEqual(params["q"], ["Python docs"])
        self.assertEqual(params["count"], ["3"])
        self.assertEqual(params["offset"], ["2"])
        self.assertEqual(params["country"], ["US"])
        self.assertEqual(params["search_lang"], ["en"])
        self.assertEqual(params["freshness"], ["pw"])
        self.assertEqual(params["safesearch"], ["moderate"])
        self.assertEqual(params["spellcheck"], ["1"])
        self.assertEqual(request.headers["X-subscription-token"], KEY)
        self.assertEqual(request.headers["Accept"], "application/json")
        self.assertIn("1. Python\n   https://python.org\n   A language", result)
        self.assertIn("следующий offset=3", result)
        self.assertNotIn(KEY, result)

    def test_format_html_pagination_and_limit(self):
        result = tools_search.format_search_results(
            "query", [{"title": "<b>Title</b>", "url": "https://x",
                       "description": "<em>A</em> &amp; B<br> C"}], True, 4
        )
        self.assertEqual(
            result,
            "Результаты поиска: query\n1. Title\n   https://x\n   A & B C\n"
            "Есть ещё результаты: следующий offset=5",
        )
        huge = tools_search.format_search_results(
            "q", [{"title": "t", "url": "https://x", "description": "x" * 20_000}]
        )
        self.assertLessEqual(len(huge), tools_search.MAX_RESULT_CHARS)
        self.assertIn("обрезаны", huge)

    def test_empty_results(self):
        result, _ = self.call({"query": "nothing"}, Response(brave_payload()))
        self.assertEqual(result, "Результаты поиска: nothing\n(нет результатов: ничего не найдено)")


if __name__ == "__main__":
    unittest.main()
