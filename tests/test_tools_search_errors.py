"""Ошибки и валидация internet_search без сети."""

import unittest
import urllib.error
from unittest import mock

import tools_search
from tests.helpers import env
from tests.test_tools_search import KEY, Response


class SearchErrorTests(unittest.TestCase):
    def call(self, args, response=None, side_effect=None):
        with env(BRAVE_KEY=KEY), mock.patch.object(
            tools_search.urllib.request,
            "urlopen",
            return_value=response,
            side_effect=side_effect,
        ) as urlopen:
            return tools_search.handle_internet_search(args), urlopen

    def test_invalid_arguments_do_not_make_http_request(self):
        invalid = [
            {}, {"query": ""}, {"query": 1},
            {"query": "x", "count": 0}, {"query": "x", "count": 11},
            {"query": "x", "count": 1.5}, {"query": "x", "count": True},
            {"query": "x", "offset": -1}, {"query": "x", "offset": 10},
            {"query": "x", "offset": 1.5}, {"query": "x", "offset": False},
            {"query": "x", "country": "U"}, {"query": "x", "country": "USA"},
            {"query": "x", "country": 1}, {"query": "x", "search_lang": "x"},
            {"query": "x", "search_lang": 1}, {"query": "x", "freshness": "day"},
        ]
        with env(BRAVE_KEY=KEY), mock.patch.object(tools_search.urllib.request, "urlopen") as urlopen:
            for args in invalid:
                with self.subTest(args=args):
                    self.assertTrue(
                        tools_search.handle_internet_search(args).startswith("Error: invalid arguments")
                    )
        urlopen.assert_not_called()

    def test_missing_key(self):
        with env(BRAVE_KEY=None), mock.patch.object(tools_search.urllib.request, "urlopen") as urlopen:
            result = tools_search.handle_internet_search({"query": "x"})
        self.assertIn("BRAVE_KEY", result)
        urlopen.assert_not_called()

    def test_network_and_api_errors_are_strings_without_key(self):
        cases = [
            (TimeoutError(), "ожидания"),
            (urllib.error.URLError("offline"), "Error:"),
            (Response(b"not json"), "некорректный JSON"),
            (Response({}, 401), "401"), (Response({}, 403), "403"),
            (Response({}, 429), "429"), (Response({}, 503), "503"),
        ]
        for source, expected in cases:
            with self.subTest(source=type(source).__name__):
                kwargs = {"side_effect": source} if isinstance(source, BaseException) else {"response": source}
                result, _ = self.call({"query": "x"}, **kwargs)
                self.assertTrue(result.startswith("Error:"), result)
                self.assertIn(expected, result)
                self.assertNotIn(KEY, result)

    def test_unexpected_json_format(self):
        result, _ = self.call({"query": "x"}, Response({"web": {"results": []}}))
        self.assertTrue(result.startswith("Error:"))
        self.assertIn("формат", result)


if __name__ == "__main__":
    unittest.main()
