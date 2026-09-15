"""Тесты agent.build_messages: тексты сообщений из файлов папки агента."""


import shutil
import tempfile
import unittest

from tests.agent_common import (
    agent, make_agent_dir, _paths, _text_iter, _tool_iter,
)


class MessageFilesTests(unittest.TestCase):
    """Тексты сообщений — из файлов рядом с system-prompt.md (см. prompts_messages.py)."""

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-msgfiles-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def _write(self, filename: str, text: str):
        (self.folder / filename).write_text(text, encoding="utf-8")

    def _history(self, count: int) -> dict:
        return {"iterations": [_text_iter(f"шаг {i}", n=i) for i in range(1, count + 1)]}

    def _woke_file(self) -> dict:
        return {
            "agent": "bot",
            "session": 2,
            "woke_up_at": "2026-09-09T00:00:00",
            "iterations": [],
        }

    def _notes(self, messages) -> list[str]:
        # служебные заметки (сон/пробуждение/зацикливание) — user-сообщения
        # перед финальным тиком: role=system допустим только первым сообщением
        return [
            m["content"]
            for m in messages
            if m["role"] == "user" and m is not messages[-1]
        ]

    def test_user_message_file_overrides_tick(self):
        self._write("user-message.md", "твори дальше")
        messages = agent.build_messages(self._history(1), self.paths)
        self.assertEqual(messages[-1]["role"], "user")
        self.assertTrue(messages[-1]["content"].endswith("твори дальше"))

    def test_last_iteration_message_file_overrides_directive(self):
        self._write("last-iteration-message.md", "спать! сохранись!")
        messages = agent.build_messages(self._history(29), self.paths)
        self.assertTrue(messages[-1]["content"].endswith("спать! сохранись!"))

    def test_wake_up_message_file_overrides_note(self):
        self._write("wake-up-message.md", "hello, ты снова живой")
        messages = agent.build_messages(self._woke_file(), self.paths)
        self.assertEqual([m["role"] for m in messages], ["system", "user", "user"])
        self.assertEqual(messages[1]["content"], "hello, ты снова живой")

    def test_sleep_warning_files_fill_placeholders(self):
        self._write("sleep-warning.md", "СОН {remaining}: {memory_note}")
        # 19 итераций, следующая 20-я: осталось 10, сохранений не было → stale
        stale_messages = agent.build_messages(self._history(19), self.paths)
        self.assertEqual(
            self._notes(stale_messages),
            ["СОН 10 итераций: Память не отражает последние действия — обнови её сейчас."]
        )
        # то же, но память свежая (set_memory последним действием) → спокойный
        fresh_history = self._history(19)
        fresh_history["iterations"][-1] = {
            "n": 19,
            "user": agent.USER_MESSAGE,
            "assistant_message": {
                "role": "assistant", "content": None,
                "tool_calls": [{"id": "c1", "type": "function",
                                "function": {"name": "set_memory", "arguments": "{}"}}],
            },
            "tool_results": [],
        }
        fresh_messages = agent.build_messages(fresh_history, self.paths)
        self.assertEqual(
            self._notes(fresh_messages),
            ["СОН 10 итераций: Проверь, что в памяти есть итог и следующий шаг."]
        )
    def test_sleep_warning_legacy_placeholders_fall_back_to_default(self):
        self._write("sleep-warning.md", "СОН {remaining}/{session_iterations}: {advice}")
        messages = agent.build_messages(self._history(19), self.paths)
        note = self._notes(messages)[0]
        self.assertIn("До сна осталось 10 итераций", note)
        self.assertIn("обнови её сейчас", note)

    def test_repeat_alert_file_fills_placeholders(self):
        self._write("repeat-alert.md", "СТОП: {streak} одно и то же: {examples}")
        data = {"iterations": [_tool_iter(n=i) for i in range(1, 4)]}
        messages = agent.build_messages(data, self.paths)
        self.assertEqual(messages[-2]["role"], "user")
        self.assertEqual(
            messages[-2]["content"],
            'СТОП: 3 итерации одно и то же: run_bash({"command": "echo hi"})',
        )

    def test_files_reread_on_every_build(self):
        self._write("user-message.md", "версия 1")
        first = agent.build_messages(self._history(1), self.paths)
        self._write("user-message.md", "версия 2")
        second = agent.build_messages(self._history(1), self.paths)
        self.assertTrue(first[-1]["content"].endswith("версия 1"))
        self.assertTrue(second[-1]["content"].endswith("версия 2"))

    def test_empty_message_file_falls_back_to_default(self):
        self._write("user-message.md", "   \n")
        messages = agent.build_messages(self._history(1), self.paths)
        self.assertTrue(messages[-1]["content"].endswith(agent.USER_MESSAGE))

if __name__ == "__main__":
    unittest.main()
