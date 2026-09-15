"""Общие фикстуры и утилиты тестовых модулей agent_*.

Выносит повторяемый каркас: конструктор AgentPaths, фабрики итераций
истории, прогон run_loop с моком LLM и базовый класс тестов полного
цикла (песочница + подменённое ожидание паузы). После разбиения agent.py
на модули патчи адресуются модулю-владельцу имени: call_llm, make_client,
execute_tool, _log, _wait_pause, _run_iteration — agent_loop; константы
сессии — agent_sleep; цвета консоли — agent_console (лимит размышлений —
agent_console_blocks). Общие тестовые сценарии используют namespace из
`tests.agent_api`, а патчи по-прежнему адресуют реальные модули-владельцы.
"""

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import PROJECT_ROOT, env, make_agent_dir  # noqa: F401 (env — реэкспорт)

sys.path.insert(0, str(PROJECT_ROOT))
import agent_console  # noqa: E402
import agent_console_blocks  # noqa: E402
import agent_history  # noqa: E402
import agent_loop  # noqa: E402
import agent_messages  # noqa: E402
import agent_paid_pause  # noqa: E402
import agent_pause  # noqa: E402
import agent_repeat  # noqa: E402
import agent_runtime  # noqa: E402
import agent_sleep  # noqa: E402
import agent_text  # noqa: E402
import agent_unread  # noqa: E402
import agent_usage  # noqa: E402
from agent_paths import AgentPaths  # noqa: E402
from config_env import Config  # noqa: E402
from storage import (  # noqa: E402
    SENDER_AGENT,
    SENDER_CREATOR,
    append_message,
    load_messages,
    mark_messages_read,
)


from tests.agent_api import agent  # noqa: E402

def _paths(folder: Path) -> AgentPaths:
    return AgentPaths(
        folder=folder,
        system_prompt=folder / "system-prompt.md",
        mind_loop=folder / "mind-loop.json",
        memory=folder / "memory.md",
    )


def _text_iter(text, n=1):
    return {
        "n": n,
        "timestamp": "2026-09-09T00:00:00",
        "user": agent.USER_MESSAGE,
        "assistant_message": {"role": "assistant", "content": text},
        "tool_results": [],
    }


def _tool_iter(call_id="call_1", result="done", n=2):
    return {
        "n": n,
        "timestamp": "2026-09-09T00:00:01",
        "user": agent.USER_MESSAGE,
        "assistant_message": {
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": call_id,
                "type": "function",
                "function": {"name": "run_bash", "arguments": '{"command": "echo hi"}'},
            }],
        },
        "tool_results": [{"tool_call_id": call_id, "tool": "run_bash",
                          "arguments": '{"command": "echo hi"}', "result": result}],
    }


def _run_loop_mocked(paths, cfg, responses, on_iteration=None, on_pause=None):
    """Прогнать run_loop с моком LLM; вернуть (логи, длительности пауз).

    Когда скрипт ответов исчерпан, мок поднимает KeyboardInterrupt и
    цикл аккуратно завершается. `on_iteration(n)` вызывается в начале
    n-й итерации (до запроса LLM) — позволяет симулировать сообщение
    создателя «во время» итерации. `on_pause(n)` вызывается в начале
    n-й паузы (только ненулевых: нулевая пауза переписку не проверяет)
    — позволяет симулировать сообщение создателя «во время» паузы:
    мок _wait_pause ведёт себя как настоящая функция — прерывается
    и возвращает True, как только создатель написал. Длительности
    пауз (как их запросил run_loop) собираются в список.
    time.perf_counter замокан нулём, чтобы длительности итераций
    не зашумляли ожидаемые значения пауз.
    """
    logs: list[str] = []
    sleeps: list[float] = []
    queue = list(responses)
    counter = {"n": 0}

    def fake_call_llm(client, model, messages, tools, temperature=0.7,
                      reasoning_effort=None):
        if queue:
            return queue.pop(0)
        raise KeyboardInterrupt

    def fake_wait_pause(seconds, paths, known_count):
        sleeps.append(seconds)
        if seconds <= 0:
            return False  # нулевая пауза не проверяет переписку
        if on_pause is not None:
            on_pause(len(sleeps))
        return agent._creator_messages_count(paths) != known_count

    real_iteration = agent._run_iteration

    def counting_iteration(paths, cfg, client, console_state=None):
        counter["n"] += 1
        if on_iteration is not None:
            on_iteration(counter["n"])
        return real_iteration(paths, cfg, client, console_state)

    with mock.patch.object(agent_loop, "make_client", lambda cfg: object()), \
         mock.patch.object(agent_loop, "call_llm", fake_call_llm), \
         mock.patch.object(agent_loop, "_run_iteration", counting_iteration), \
         mock.patch.object(agent_loop, "_wait_pause", fake_wait_pause), \
         mock.patch.object(agent_loop, "_log", logs.append), \
         mock.patch.object(agent_console, "USE_COLOR", False), \
         mock.patch("time.perf_counter", return_value=0.0):
        agent.run_loop(paths, cfg)
    return logs, sleeps


class RunLoopTestCase(unittest.TestCase):
    """База тестов полного цикла: папка агента, мок паузы и скриптованный LLM."""

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-loop-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)
        self.cfg = Config(base_url="http://mock/v1", model="mock-model",
                          api_key="k", agents_root=None, loop_delay=0)
        # пауза между итерациями растёт по расписанию (до 4 часов), когда
        # создатель молчит, и во время неё раз в секунду проверяет переписку
        # — в тестах ожидание паузы подменено (никогда не прерывается),
        # чтобы не ждать реального времени
        wait_patcher = mock.patch.object(agent_loop, "_wait_pause", return_value=False)
        self.addCleanup(wait_patcher.stop)
        wait_patcher.start()

    def _script_llm(self, responses):
        """Мок call_llm: раздаёт ответы по очереди, затем KeyboardInterrupt."""
        queue = list(responses)

        def fake_call_llm(client, model, messages, tools, temperature=0.7,
                          reasoning_effort=None):
            self.assertEqual(model, "mock-model")
            self.assertTrue(messages)
            if queue:
                return queue.pop(0)
            raise KeyboardInterrupt

        return fake_call_llm


if __name__ == "__main__":
    unittest.main()
