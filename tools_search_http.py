"""Один HTTP-запрос Brave Search и безопасное извлечение JSON."""

import json
import socket
import urllib.error
import urllib.request


class SearchError(Exception):
    """Ошибка поиска с сообщением, не содержащим секретов."""


def _is_timeout(reason):
    text = str(reason).lower()
    return isinstance(reason, (TimeoutError, socket.timeout)) or "timeout" in text or "timed out" in text


def _status(response):
    status = getattr(response, "status", None)
    if not isinstance(status, int):
        getcode = getattr(response, "getcode", None)
        status = getcode() if callable(getcode) else None
    return status if isinstance(status, int) else None


def _http_error(status):
    if status in (401, 403):
        return SearchError(f"неверный ключ Brave Search API (HTTP {status})")
    if status == 429:
        return SearchError("превышен лимит Brave Search API (HTTP 429)")
    if 500 <= status <= 599:
        return SearchError(f"временная ошибка Brave Search API (HTTP {status})")
    return SearchError(f"ошибка Brave Search API (HTTP {status})")


def request_json(url: str, api_key: str, timeout: int, opener=None):
    """GET без повторов; вернуть только web.results и флаг пагинации."""
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "X-Subscription-Token": api_key}
    )
    response = None
    try:
        open_url = urllib.request.urlopen if opener is None else opener
        response = open_url(request, timeout=timeout)
        status = _status(response)
        if status is not None and status >= 400:
            raise _http_error(status)
        raw = response.read()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise _http_error(exc.code) from None
    except (TimeoutError, socket.timeout):
        raise SearchError("превышено время ожидания Brave Search API") from None
    except urllib.error.URLError as exc:
        if _is_timeout(exc.reason):
            raise SearchError("превышено время ожидания Brave Search API") from None
        raise SearchError("сетевая ошибка при обращении к Brave Search API") from None
    except OSError:
        raise SearchError("сетевая ошибка при обращении к Brave Search API") from None
    except (UnicodeError, TypeError, ValueError):
        raise SearchError("Brave Search API вернул некорректный JSON") from None
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()

    if not isinstance(data, dict):
        raise SearchError("неожиданный формат ответа Brave Search API")
    web, query = data.get("web"), data.get("query")
    results = web.get("results") if isinstance(web, dict) else None
    more = query.get("more_results_available") if isinstance(query, dict) else None
    if not isinstance(results, list) or not isinstance(more, bool):
        raise SearchError("неожиданный формат ответа Brave Search API")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("title"), str)
        or not isinstance(item.get("url"), str)
        for item in results
    ):
        raise SearchError("неожиданный формат ответа Brave Search API")
    return results, more
