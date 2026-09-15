"""Проверка ответа HTTP и потоковое чтение с лимитом байтов."""


def read_response(response, max_bytes: int, error_cls):
    status = getattr(response, "status", None)
    if status is None:
        getcode = getattr(response, "getcode", None)
        status = getcode() if callable(getcode) else None
    if isinstance(status, int) and not 200 <= status < 300:
        raise error_cls(f"HTTP {status}")

    headers = getattr(response, "headers", None)
    length = None
    if headers is not None:
        value = headers.get("Content-Length")
        try:
            if value is not None and int(value) >= 0:
                length = int(value)
        except (TypeError, ValueError):
            pass
    if length is not None and length > max_bytes:
        raise error_cls(f"изображение слишком большое (лимит {max_bytes} байт)")

    chunks, total = [], 0
    while total <= max_bytes:
        remaining = max_bytes + 1 - total
        chunk = response.read(min(64 * 1024, remaining))
        if not chunk:
            break
        chunk = bytes(chunk)
        total += len(chunk)
        if total > max_bytes:
            raise error_cls(f"изображение слишком большое (лимит {max_bytes} байт)")
        chunks.append(chunk)
    return b"".join(chunks)
