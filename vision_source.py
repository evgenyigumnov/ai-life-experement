"""Получение байтов изображения из URL или Docker-песочницы."""

import socket
import urllib.request
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from sandbox_scripts import exec_python
from tools_sandbox import sandbox_container_name
from vision_container import IMAGE_READER_SCRIPT
from vision_container import read_container_file as _read_container_file
from vision_http import read_response

MAX_IMAGE_BYTES = 20 * 1024 * 1024
URL_TIMEOUT = 15.0
MAX_REDIRECTS = 5
IMAGE_READ_TIMEOUT = 30.0
USER_AGENT = "ai-life-image-inspector/1.0"
_DEFAULT_URLOPEN = urllib.request.urlopen


class VisionSourceError(ValueError):
    pass


class _LimitedRedirectHandler(HTTPRedirectHandler):
    """Ограничивает число redirect и оставляет только HTTP(S)."""

    def __init__(self):
        super().__init__()
        self.count = 0

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.count += 1
        if self.count > MAX_REDIRECTS:
            raise VisionSourceError("слишком много перенаправлений")
        try:
            parts = urlsplit(newurl)
            valid = parts.scheme.lower() in {"http", "https"} and bool(parts.hostname)
        except ValueError:
            valid = False
        if not valid:
            raise VisionSourceError("перенаправление на недопустимый адрес")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def urlopen(request, timeout=URL_TIMEOUT):
    """Открыть URL с ограниченным redirect."""
    if urllib.request.urlopen is not _DEFAULT_URLOPEN:
        return urllib.request.urlopen(request, timeout=timeout)
    return build_opener(_LimitedRedirectHandler()).open(request, timeout=timeout)


def _url_is_valid(source: str) -> bool:
    try:
        parts = urlsplit(source)
        return (
            parts.scheme.lower() in {"http", "https"}
            and bool(parts.hostname)
            and (parts.port is None or 0 < parts.port <= 65535)
        )
    except ValueError:
        return False


def _read_http_response(response) -> bytes:
    return read_response(response, MAX_IMAGE_BYTES, VisionSourceError)


def download_url(source: str) -> bytes:
    if not _url_is_valid(source):
        raise VisionSourceError("нужен URL с поддерживаемой схемой http или https")
    response = None
    try:
        request = Request(source, headers={"User-Agent": USER_AGENT}, method="GET")
        response = urlopen(request, timeout=URL_TIMEOUT)
        return _read_http_response(response)
    except VisionSourceError:
        raise
    except HTTPError as exc:
        raise VisionSourceError(f"HTTP {getattr(exc, 'code', 'ошибка')}") from exc
    except (TimeoutError, socket.timeout):
        raise VisionSourceError("таймаут загрузки изображения")
    except URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise VisionSourceError("таймаут загрузки изображения")
        raise VisionSourceError("ошибка сети при загрузке изображения")
    except (OSError, ValueError):
        raise VisionSourceError("не удалось загрузить изображение")
    except Exception:
        raise VisionSourceError("не удалось загрузить изображение")
    finally:
        if response is not None:
            close = getattr(response, "close", None)
            if callable(close):
                close()


def read_container_file(source: str, paths) -> bytes:
    return _read_container_file(
        source,
        paths,
        exec_runner=exec_python,
        name_resolver=sandbox_container_name,
        error_cls=VisionSourceError,
        timeout=IMAGE_READ_TIMEOUT,
    )


def load_source(source: str, paths=None) -> bytes:
    if not isinstance(source, str) or not source.strip():
        raise VisionSourceError("источник изображения должен быть непустой строкой")
    source = source.strip()
    if _url_is_valid(source):
        return download_url(source)
    try:
        has_scheme = bool(urlsplit(source).scheme)
    except ValueError as exc:
        raise VisionSourceError("некорректный URL или путь") from exc
    if has_scheme:
        raise VisionSourceError("разрешены только URL http/https")
    if not Path(source).is_absolute():
        raise VisionSourceError("путь изображения должен быть абсолютным")
    return read_container_file(source, paths)


load_image_source = load_source
fetch_url = download_url
