"""Tool internet_search: короткий поиск через Brave Web Search API."""

import os
import re
import urllib.parse
import urllib.request

from tools_search_format import MAX_RESULT_CHARS, _truncate, format_search_results
from tools_search_http import SearchError, request_json
from tools_search_schema import INTERNET_SEARCH_TOOL

BRAVE_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
HTTP_TIMEOUT = 15
DEFAULT_COUNT = 5
MAX_COUNT = 10
MAX_OFFSET = 9
MAX_QUERY_CHARS = 400
MAX_FILTER_CHARS = 32
BRAVE_KEY_ENV = "BRAVE_KEY"
FRESHNESS_VALUES = frozenset({"pd", "pw", "pm", "py"})
_LANG_RE = r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8})*$"
_REAL_URLOPEN = urllib.request.urlopen
urlopen = _REAL_URLOPEN

def _filter(args: dict, name: str, pattern: str, label: str) -> str | None:
    value = args.get(name)
    if value is None:
        return None
    value = value.strip() if isinstance(value, str) else ""
    if not value or len(value) > MAX_FILTER_CHARS or not re.fullmatch(pattern, value):
        raise ValueError(f"'{name}' должен быть {label}")
    return value


def validate_search_args(args: dict) -> tuple[str, dict]:
    if not isinstance(args, dict):
        raise ValueError("ожидается JSON-объект аргументов")
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("ожидается непустая строка 'query'")
    query = query.strip()
    if len(query) > MAX_QUERY_CHARS:
        raise ValueError(f"'query' не должен быть длиннее {MAX_QUERY_CHARS} символов")

    count = args.get("count", DEFAULT_COUNT)
    count = DEFAULT_COUNT if count is None else count
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_COUNT:
        raise ValueError(f"'count' должен быть целым числом от 1 до {MAX_COUNT}")
    offset = args.get("offset", 0)
    offset = 0 if offset is None else offset
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= MAX_OFFSET:
        raise ValueError(f"'offset' должен быть целым числом от 0 до {MAX_OFFSET}")

    params = {
        "q": query,
        "count": count,
        "offset": offset,
        "safesearch": "moderate",
        "spellcheck": 1,
    }
    country = _filter(args, "country", r"^[A-Za-z]{2}$", "двухбуквенным кодом")
    language = _filter(args, "search_lang", _LANG_RE, "кодом языка")
    if country is not None:
        params["country"] = country
    if language is not None:
        params["search_lang"] = language.lower()
    freshness = args.get("freshness")
    if freshness is not None:
        freshness = freshness.strip() if isinstance(freshness, str) else ""
        if freshness not in FRESHNESS_VALUES:
            raise ValueError("'freshness' должен быть одним из: pd, pw, pm, py")
        params["freshness"] = freshness
    return query, params


def build_search_url(params: dict) -> str:
    return f"{BRAVE_SEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"


def request_search(params: dict, api_key: str) -> tuple[list, bool]:
    opener = urllib.request.urlopen if urlopen is _REAL_URLOPEN else urlopen
    return request_json(build_search_url(params), api_key, HTTP_TIMEOUT, opener)


def _redact(text: str, secret: str) -> str:
    return text.replace(secret, "[секрет скрыт]") if secret else text


def handle_internet_search(args: dict, paths=None) -> str:
    try:
        query, params = validate_search_args(args)
    except ValueError as exc:
        return f"Error: invalid arguments: {exc}"
    api_key = os.environ.get(BRAVE_KEY_ENV, "").strip()
    if not api_key:
        return "Error: internet_search не настроен: отсутствует BRAVE_KEY"
    try:
        results, more = request_search(params, api_key)
        answer = format_search_results(query, results, more, params["offset"])
    except SearchError as exc:
        answer = f"Error: internet_search: {exc}"
    except Exception:
        answer = "Error: internet_search: не удалось выполнить поиск"
    return _truncate(_redact(answer, api_key), MAX_RESULT_CHARS)
