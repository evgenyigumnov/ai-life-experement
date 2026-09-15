"""Тесты agent.build_messages: сессии, сон и пробуждение."""


import json
import shutil
import tempfile
import unittest

import prompts_messages as prompts
from tests.agent_common import agent, make_agent_dir, _paths, _text_iter


class SleepCycleTests(unittest.TestCase):
    """Циклы жизни и сон: сессии по SESSION_ITERATIONS, предупреждение, пробуждение.

    История в k итераций означает, что следующая итерация имеет номер k+1
    внутри текущей сессии (mind-loop.json хранит одну «жизнь», нумерация
    с 1). Пробуждение определяется по метке woke_up_at в свежем файле,
    который storage.archive_mind_loop создаёт после сна.
    """

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-sleep-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def _history(self, count: int) -> dict:
        return {"iterations": [_text_iter(f"шаг {i}", n=i) for i in range(1, count + 1)]}

    def _woke_file(self, session: int = 2) -> dict:
        """Свежий mind-loop.json сразу после сна: метка + пустая история."""
        return {
            "agent": "bot",
            "created_at": "2026-09-09T00:00:00",
            "updated_at": "2026-09-09T00:00:00",
            "session": session,
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

    def test_no_warning_before_20th_iteration(self):
        # следующая итерация — 19-я, до сна 12: предупреждения нет
        messages = agent.build_messages(self._history(18), self.paths)
        self.assertEqual(self._notes(messages), [])
        dumped = json.dumps(messages, ensure_ascii=False)
        self.assertNotIn("сон", dumped)

    def test_warning_at_20th_iteration_says_10_left(self):
        # следующая итерация — 20-я: «прошло 20 — осталось 10»
        messages = agent.build_messages(self._history(19), self.paths)
        notes = self._notes(messages)
        self.assertEqual(len(notes), 1)
        self.assertIn("осталось 10 итераций", notes[0])
        self.assertIn("обнови её сейчас", notes[0])

    def test_warning_countdown_decreases(self):
        # следующая итерация — 25-я: осталось 5
        messages = agent.build_messages(self._history(24), self.paths)
        self.assertIn("осталось 5 итераций", self._notes(messages)[0])

    def test_warning_singular_form(self):
        # следующая итерация — 29-я: осталось 1 итерацию
        messages = agent.build_messages(self._history(28), self.paths)
        self.assertIn("осталось 1 итерацию", self._notes(messages)[0])

    def test_last_iteration_before_sleep_note(self):
        # следующая итерация — 30-я, последняя в сессии: вместо обычного тика
        # приходит user-директива сохранить память, заметки нет
        messages = agent.build_messages(self._history(29), self.paths)
        self.assertEqual(self._notes(messages), [])
        self.assertEqual(messages[-1]["role"], "user")
        self.assertTrue(messages[-1]["content"].endswith(agent.LAST_ITERATION_MESSAGE))
        self.assertIn("Сохрани в памяти итог и следующий шаг", messages[-1]["content"])
        self.assertIn("Новую работу не начинай", messages[-1]["content"])

    def test_warning_note_placed_right_before_user_message(self):
        messages = agent.build_messages(self._history(19), self.paths)
        self.assertEqual(messages[-1]["role"], "user")
        self.assertTrue(messages[-1]["content"].endswith(agent.USER_MESSAGE))
        self.assertEqual(messages[-2]["role"], "user")
        self.assertIn("осталось 10 итераций", messages[-2]["content"])

    def test_wake_up_note_on_fresh_file_after_sleep(self):
        # сразу после сна: файл пуст, есть метка woke_up_at — заметка «проснулся»
        messages = agent.build_messages(self._woke_file(), self.paths)
        self.assertEqual([m["role"] for m in messages], ["system", "user", "user"])
        self.assertIn("проснулся", messages[1]["content"])
        self.assertEqual(
            messages[1]["content"],
            prompts.read_default_message(prompts.FILE_WAKE_UP_MESSAGE),
        )

    def test_wake_up_note_is_only_a_session_marker(self):
        # Чек-лист первого тика уже находится в system-prompt.md, а выбор
        # действия — в финальном user-message.md; после сна нужна только метка.
        messages = agent.build_messages(self._woke_file(), self.paths)
        content = messages[1]["content"]
        self.assertEqual(content, "Ты проснулся. Новая сессия началась.")
        for marker in ("Прочитай память", "get_messages", "diary_tags", "незнакомые файлы", "приоритетный шаг"):
            self.assertNotIn(marker, content)
        self.assertTrue(messages[-1]["content"].endswith(agent.USER_MESSAGE))

    def test_no_wake_up_note_after_first_iteration_recorded(self):
        # метка остаётся в файле всю сессию, но заметка только при пустой истории
        data = self._woke_file()
        data["iterations"] = [_text_iter("первое дело после сна", n=1)]
        messages = agent.build_messages(data, self.paths)
        self.assertEqual(self._notes(messages), [])
        assistant = [m["content"] for m in messages if m["role"] == "assistant"]
        self.assertEqual(assistant, ["первое дело после сна"])

    def test_no_wake_up_note_mid_session_restart(self):
        # рестарт программы посреди сессии: woke_up_at есть, но история непуста —
        # нумерация продолжается, заметки о пробуждении нет
        data = self._woke_file()
        data["iterations"] = [_text_iter(f"шаг {i}", n=i) for i in range(1, 15)]
        messages = agent.build_messages(data, self.paths)
        self.assertNotIn("проснулся", json.dumps(messages, ensure_ascii=False))
        self.assertEqual(len([m for m in messages if m["role"] == "assistant"]), 14)

    def test_first_life_has_no_wake_note(self):
        # самый первый запуск: файла-предшественника не было, метки нет
        messages = agent.build_messages({"iterations": []}, self.paths)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertNotIn("проснулся", json.dumps(messages, ensure_ascii=False))

    def test_wake_up_without_session_field(self):
        # архив без счётчика сессии — заметка всё равно показывается
        data = self._woke_file()
        data.pop("session")
        messages = agent.build_messages(data, self.paths)
        self.assertIn("проснулся", messages[1]["content"])

if __name__ == "__main__":
    unittest.main()
