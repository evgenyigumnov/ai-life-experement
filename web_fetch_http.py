import socket
import urllib.request
from collections import namedtuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MAX_BODY_BYTES = 2_000_000
HTTP_TIMEOUT = 15
MAX_REDIRECTS = 5
USER_AGENT = "ai-life-web-fetch/1.0"
_DEFAULT_URLOPEN = urllib.request.urlopen
urlopen = _DEFAULT_URLOPEN


class WebFetchError(ValueError):
    pass


FetchedPage = namedtuple("FetchedPage", "body content_type url")


class _LimitedRedirectHandler(HTTPRedirectHandler):
    count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > MAX_REDIRECTS:
            raise WebFetchError("слишком много перенаправлений")
        try:
            parts = urlsplit(newurl)
            valid = parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)
        except ValueError:
            valid = False
        if not valid:
            raise WebFetchError("перенаправление на недопустимый адрес")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def is_valid_url(value: str) -> bool:
    try:
        parts = urlsplit(value)
        return (
            parts.scheme.lower() in {"http", "https"}
            and bool(parts.hostname)
            and (parts.port is None or 0 < parts.port <= 65535)
        )
    except ValueError:
        return False


def _open(request):
    if urlopen is not _DEFAULT_URLOPEN:
        return urlopen(request, timeout=HTTP_TIMEOUT)
    if urllib.request.urlopen is not _DEFAULT_URLOPEN:
        return urllib.request.urlopen(request, timeout=HTTP_TIMEOUT)
    return build_opener(_LimitedRedirectHandler()).open(request, timeout=HTTP_TIMEOUT)


def _status(response):
    status = getattr(response, "status", None)
    if not isinstance(status, int):
        getcode = getattr(response, "getcode", None)
        status = getcode() if callable(getcode) else None
    return status if isinstance(status, int) else None


def _header(response, name):
    headers = getattr(response, "headers", None)
    if headers is None:
        return ""
    value = headers.get(name, headers.get(name.lower(), ""))
    return value if isinstance(value, str) else ""


def _read_body(response):
    length = _header(response, "Content-Length")
    try:
        length = int(length) if length else 0
    except ValueError:
        length = 0
    if length > MAX_BODY_BYTES:
        raise WebFetchError(f"страница слишком большая (лимит {MAX_BODY_BYTES} байт)")

    chunks, total = [], 0
    while total <= MAX_BODY_BYTES:
        size = min(64 * 1024, MAX_BODY_BYTES + 1 - total)
        try:
            chunk = response.read(size)
        except TypeError:
            chunk = response.read()
        if not chunk:
            break
        chunk = bytes(chunk)
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise WebFetchError(f"страница слишком большая (лимит {MAX_BODY_BYTES} байт)")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_url(url):
    if not is_valid_url(url):
        raise WebFetchError("нужен URL с поддерживаемой схемой http или https")
    response = None
    try:
        request = Request(
            url,
            headers={
                "Accept": "text/html, text/plain, application/xhtml+xml;q=0.9, */*;q=0.1",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        response = _open(request)
        status = _status(response)
        if status is not None and not 200 <= status < 300:
            raise WebFetchError(f"HTTP {status}")
        body = _read_body(response)
        final_url = getattr(response, "geturl", lambda: url)()
        if not isinstance(final_url, str) or not is_valid_url(final_url):
            final_url = url
        return FetchedPage(body, _header(response, "Content-Type"), final_url)
    except WebFetchError:
        raise
    except HTTPError as exc:
        raise WebFetchError(f"HTTP {getattr(exc, 'code', 'ошибка')}") from None
    except (TimeoutError, socket.timeout):
        raise WebFetchError("таймаут загрузки страницы") from None
    except URLError as exc:
        reason = str(getattr(exc, "reason", exc)).lower()
        if "timeout" in reason or "timed out" in reason:
            raise WebFetchError("таймаут загрузки страницы") from None
        raise WebFetchError("ошибка сети при загрузке страницы") from None
    except (OSError, ValueError):
        raise WebFetchError("не удалось загрузить страницу") from None
    except Exception:
        raise WebFetchError("не удалось загрузить страницу") from None
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
