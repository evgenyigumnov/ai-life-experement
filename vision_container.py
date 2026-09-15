"""Безопасное чтение изображения внутри контейнера агента."""

import base64
import json

MAX_IMAGE_BYTES = 20 * 1024 * 1024
IMAGE_READER_SCRIPT = """
import base64, json, os, sys

MAX_BYTES = %d
path = sys.argv[1]
if not os.path.exists(path):
    print(json.dumps({"error": "not_found"}, separators=(",", ":")))
    raise SystemExit
if os.path.isdir(path):
    print(json.dumps({"error": "is_dir"}, separators=(",", ":")))
    raise SystemExit
if not os.path.isfile(path):
    print(json.dumps({"error": "not_file"}, separators=(",", ":")))
    raise SystemExit
try:
    size = os.path.getsize(path)
    if size > MAX_BYTES:
        print(json.dumps({"error": "too_large", "size": size, "limit": MAX_BYTES}, separators=(",", ":")))
        raise SystemExit
    with open(path, "rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
except OSError:
    print(json.dumps({"error": "unreadable"}, separators=(",", ":")))
    raise SystemExit
if len(raw) > MAX_BYTES:
    print(json.dumps({"error": "too_large", "size": len(raw), "limit": MAX_BYTES}, separators=(",", ":")))
    raise SystemExit
print(json.dumps({"base64": base64.b64encode(raw).decode("ascii")}, separators=(",", ":")))
""" % MAX_IMAGE_BYTES


def read_container_file(
    source: str,
    paths,
    exec_runner=None,
    name_resolver=None,
    error_cls=ValueError,
    timeout=30.0,
):
    """Запустить reader через переданные зависимости и декодировать JSON."""
    if paths is None:
        raise error_cls("для чтения пути нужен контекст Docker-песочницы")
    if exec_runner is None:
        from sandbox_scripts import exec_python as exec_runner
    if name_resolver is None:
        from tools_sandbox import sandbox_container_name as name_resolver

    container = name_resolver(paths)
    error, proc, stdout, _stderr = exec_runner(
        container, IMAGE_READER_SCRIPT, [source], timeout
    )
    if error == "TIMEOUT":
        raise error_cls("таймаут чтения изображения в Docker")
    if error is not None:
        message = str(error)
        if message.startswith("Error:"):
            message = message[6:].strip()
        raise error_cls(message or "Docker недоступен")
    if stdout is None:
        raise error_cls("Docker не вернул данные изображения")
    try:
        data = json.loads(stdout.strip())
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise error_cls("Docker вернул некорректный ответ") from exc
    if not isinstance(data, dict):
        raise error_cls("Docker вернул некорректный ответ")

    kind = data.get("error")
    if kind == "not_found":
        raise error_cls(f"файл не найден в Docker: {source}")
    if kind == "is_dir":
        raise error_cls(f"путь в Docker является директорией: {source}")
    if kind == "too_large":
        raise error_cls(f"файл изображения слишком большой (лимит {MAX_IMAGE_BYTES} байт)")
    if kind in {"not_file", "unreadable"}:
        raise error_cls(f"файл изображения недоступен в Docker: {source}")
    if kind is not None:
        raise error_cls("Docker вернул неизвестную ошибку чтения")
    if proc is not None and getattr(proc, "returncode", 0) != 0:
        raise error_cls("Docker не смог прочитать файл изображения")

    encoded = data.get("base64", data.get("data"))
    if not isinstance(encoded, str) or not encoded:
        raise error_cls("Docker не вернул Base64 изображения")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError) as exc:
        raise error_cls("Docker вернул некорректный Base64") from exc
    if not raw or len(raw) > MAX_IMAGE_BYTES:
        raise error_cls(
            f"файл изображения слишком большой или пустой (лимит {MAX_IMAGE_BYTES} байт)"
        )
    return raw
