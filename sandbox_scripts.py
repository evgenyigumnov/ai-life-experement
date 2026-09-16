"""Скрипты песочницы и запуск docker exec.

RUNNER_SCRIPT запускает bash в отдельной process group, чтобы таймаут убивал
и фоновых детей. READER_SCRIPT отдаёт страницу с метаданными, не собирая весь
файл в память. exec_python — общая обвязка с проверкой Docker и таймаутом.
"""

import subprocess

from sandbox_docker import DOCKER_BIN, check_docker_available, ensure_docker_container

RUNNER_SCRIPT = """
import sys, subprocess, os, signal, json

cmd = sys.argv[1]
timeout = float(sys.argv[2])
proc = subprocess.Popen(
    ["/bin/bash", "-c", cmd],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    encoding="utf-8",
    errors="replace",
    start_new_session=True,
)
try:
    stdout, stderr = proc.communicate(timeout=timeout)
    data = {"returncode": proc.returncode, "stdout": stdout, "stderr": stderr, "timed_out": False}
except subprocess.TimeoutExpired:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except ProcessLookupError:
        pass
    proc.communicate()
    data = {"returncode": 124, "stdout": "", "stderr": "", "timed_out": True}
print(json.dumps(data))
"""

READER_SCRIPT = """
import json, os, sys

path = sys.argv[1]
offset = int(sys.argv[2])
limit = int(sys.argv[3])

if not os.path.exists(path):
    print(json.dumps({"error": "not_found"}))
    raise SystemExit
if os.path.isdir(path):
    print(json.dumps({"error": "is_dir"}))
    raise SystemExit

size = os.path.getsize(path)
with open(path, "rb") as binary_file:
    while chunk := binary_file.read(65536):
        if b"\\x00" in chunk:
            print(json.dumps({"error": "binary", "size": size}))
            raise SystemExit

MAX_LINE_CHARS = 2000
lines = []
line_lengths = []
total = 0
with open(path, "r", encoding="utf-8", errors="replace", newline=None) as text_file:
    for line in text_file:
        total += 1
        if offset <= total < offset + limit:
            value = line.rstrip("\\r\\n")
            line_lengths.append(len(value))
            lines.append(value[:MAX_LINE_CHARS])

if offset > total and not (total == 0 and offset == 1):
    print(json.dumps({"error": "offset_out_of_range", "total_lines": total}))
    raise SystemExit

start = offset
end = min(start + len(lines) - 1, total) if lines else 0
print(json.dumps({
    "path": path,
    "size": size,
    "total_lines": total,
    "start": start,
    "end": end,
    "lines": lines,
    "line_lengths": line_lengths,
}))
"""


def exec_python(container_name: str, script: str, script_args: list[str], timeout: float):
    """Исполнить python-скрипт внутри контейнера агента (`python3 -`).

    Скрипт передаётся на stdin, script_args — как argv. Возвращает кортеж
    (error, proc, stdout, stderr):
    - error is None — скрипт исполнен, вывод собран;
    - error == "TIMEOUT" — host-таймаут, процесс убит (proc возвращён);
    - error — прочая строка «Error: ...» для ответа tool.
    """
    docker_err = check_docker_available()
    if docker_err is not None:
        return docker_err, None, None, None

    try:
        c_name = ensure_docker_container(container_name)
    except Exception as exc:
        return f"Error: песочница docker недоступна: {exc}", None, None, None

    exec_cmd = [
        DOCKER_BIN, "exec", "-i", "-w", "/root",
        c_name, "python3", "-", *script_args,
    ]
    try:
        proc = subprocess.Popen(
            exec_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return (
            f"Error: песочница docker недоступна: "
            f"не найден бинарь docker ({DOCKER_BIN!r})",
            None, None, None,
        )
    except Exception as exc:
        return f"Error: не удалось выполнить команду: {exc!r}", None, None, None

    try:
        stdout, stderr = proc.communicate(input=script, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass
        proc.communicate()
        return "TIMEOUT", proc, None, None
    return None, proc, stdout, stderr
