"""Тесты кэшируемости системного промпта в циклических LLM-вызовах."""


import contextlib
import copy
import json
import shutil
import tempfile
import unittest
from unittest import mock

from tests.agent_common import (
    agent, agent_console, agent_loop, agent_sleep, append_message, Config,
    make_agent_dir, SENDER_CREATOR, _paths,
)


class _PromptCacheBase(unittest.TestCase):
    """База тестов кеша промпта: мок LLM с трассировкой каждого запроса."""

    PROMPT_TEXT = "# Роль\nТы — тестовый агент.\nПравила:\n— действуй сам\n"

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-spcache-"),
                                     prompt=self.PROMPT_TEXT)
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)
        self.cfg = Config(base_url="http://mock/v1", model="mock-model",
                          api_key="k", agents_root=None, loop_delay=0)
        # растущая пауза «молчания создателя» не должна тормозить тесты —
        # циклы здесь гоняются десятками итераций; ожидание паузы (с
        # ежесекундной проверкой переписки) подменено заглушкой
        wait_patcher = mock.patch.object(agent_loop, "_wait_pause", return_value=False)
        self.addCleanup(wait_patcher.stop)
        wait_patcher.start()

    @staticmethod
    def _tool_response(n: int) -> dict:
        # у каждой итерации свои аргументы — серии одинаковых вызовов нет,
        # иначе сработает анти-ступор и в запрос встанет лишняя заметка
        return {
            "role": "assistant", "content": None,
            "tool_calls": [{
                "id": f"call_{n}", "type": "function",
                "function": {"name": "get_memory",
                             "arguments": json.dumps({"hint": n})},
            }],
        }

    @staticmethod
    def _text_response(n: int) -> dict:
        return {"role": "assistant", "content": f"ответ {n}"}

    def _run_loop(self, responses, *, session_iterations=None, logs=None,
                  request_trace_path=None, on_iteration=None):
        """Прогнать run_loop с моком LLM, записывая каждый ушедший запрос.

        Возвращает (copies, refs): copies — глубокие копии messages каждого
        вызова (сняты в момент отправки), refs — живые ссылки на те же
        списки. Когда скрипт ответов исчерпан, мок поднимает
        KeyboardInterrupt и run_loop аккуратно завершается.

        Если задан `request_trace_path`, каждый payload дополнительно
        сохраняется одной JSON-строкой — это отдельный текстовый след того,
        что было передано в LLM. `on_iteration(n)` вызывается перед сборкой
        n-й итерации.
        """
        copies: list[list[dict]] = []
        refs: list[list[dict]] = []
        queue = list(responses)

        def fake_call_llm(client, model, messages, tools, temperature=0.7,
                          reasoning_effort=None):
            if request_trace_path is not None:
                with request_trace_path.open("a", encoding="utf-8") as trace:
                    trace.write(json.dumps(messages, ensure_ascii=False) + "\n")
            copies.append(copy.deepcopy(messages))
            refs.append(messages)
            if queue:
                return queue.pop(0)
            raise KeyboardInterrupt

        with contextlib.ExitStack() as stack:
            stack.enter_context(
                mock.patch.object(agent_loop, "make_client", lambda cfg: object())
            )
            stack.enter_context(mock.patch.object(agent_loop, "call_llm", fake_call_llm))
            if logs is not None:
                stack.enter_context(mock.patch.object(agent_loop, "_log", logs.append))
                stack.enter_context(mock.patch.object(agent_console, "USE_COLOR", False))
            if session_iterations is not None:
                stack.enter_context(
                    mock.patch.object(agent_sleep, "SESSION_ITERATIONS", session_iterations)
                )
            if on_iteration is not None:
                real_iteration = agent._run_iteration
                iteration_number = 0

                def counting_iteration(paths, cfg, client, console_state=None):
                    nonlocal iteration_number
                    iteration_number += 1
                    on_iteration(iteration_number)
                    return real_iteration(paths, cfg, client, console_state)

                stack.enter_context(
                    mock.patch.object(agent_loop, "_run_iteration", counting_iteration)
                )
            agent.run_loop(self.paths, self.cfg)
        return copies, refs


class SystemPromptCacheStabilityTests(_PromptCacheBase):
    """Кеш префикса срабатывает только на побайтово идентичный префикс."""

    def test_system_prompt_byte_identical_across_iterations(self):
        # 6 итераций с чередованием tool/text ответов (+1 вызов, обрываемый
        # KeyboardInterrupt): system-сообщение каждого запроса побайтово
        # одно и то же и равно файлу на диске
        responses = [
            self._tool_response(1), self._text_response(2),
            self._tool_response(3), self._text_response(4),
            self._tool_response(5), self._text_response(6),
        ]
        copies, _ = self._run_loop(responses)
        self.assertEqual(len(copies), 7)
        system_messages = []
        for request in copies:
            self.assertEqual(request[0]["role"], "system")  # всегда первый
            self.assertEqual(set(request[0]), {"role", "content"})  # без лишних полей
            system_messages.append(request[0])
        # ровно один уникальный system-промпт за весь цикл
        unique = {json.dumps(m, ensure_ascii=False, sort_keys=True)
                  for m in system_messages}
        self.assertEqual(len(unique), 1)
        # побайтово равен файлу на диске — никаких strip/нормализаций,
        # иначе кеш провайдера промахнётся
        on_disk = self.paths.system_prompt.read_text(encoding="utf-8")
        self.assertEqual(system_messages[0]["content"], on_disk)
        self.assertEqual(system_messages[0],
                         {"role": "system", "content": self.PROMPT_TEXT})

    def test_requests_grow_only_by_append(self):
        # append-only префикс — условие попадания в prompt-кеш: запрос
        # итерации N без финального user-тика целиком стоит в начале
        # запроса итерации N+1 (история не переписывается задним числом)
        responses = [self._tool_response(i) for i in range(1, 5)]
        copies, _ = self._run_loop(responses)
        self.assertEqual(len(copies), 5)
        for earlier, later in zip(copies, copies[1:]):
            self.assertEqual(later[: len(earlier) - 1], earlier[:-1])

    def test_sent_messages_not_mutated_afterwards(self):
        # объекты уже отправленных запросов (включая system-сообщение)
        # не мутируются на месте: живая ссылка остаётся равна глубокой
        # копии, снятой в момент отправки
        responses = [self._tool_response(1), self._text_response(2),
                     self._tool_response(3)]
        copies, refs = self._run_loop(responses)
        self.assertEqual(len(copies), len(refs))
        for request_copy, request_ref in zip(copies, refs):
            self.assertEqual(request_copy, request_ref)

    def test_system_prompt_stable_across_sleep_and_wake_notes(self):
        # сессии по 3 итерации: в запросах появляются user-заметки сна и
        # пробуждения, но системный промпт — начало кеш-префикса — не меняется
        responses = [self._text_response(i) for i in range(1, 8)]
        copies, _ = self._run_loop(responses, session_iterations=3)
        self.assertEqual(len(copies), 8)
        self.assertEqual({c[0]["content"] for c in copies}, {self.PROMPT_TEXT})
        # заметки действительно вставлялись — иначе тест ничего не проверяет
        notes = [m for c in copies for m in c[1:-1] if m["role"] == "user"]
        self.assertTrue(notes)
        self.assertIn("проснулся", json.dumps(notes, ensure_ascii=False))

if __name__ == "__main__":
    unittest.main()
