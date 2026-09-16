"""Тесты веса контекста: context_weight.weight_note и тик-заметка."""

import json
import re
import shutil
import tempfile
import unittest

from tests.agent_common import (
    agent, append_message, SENDER_CREATOR, _paths, _text_iter, make_agent_dir,
)
from context_weight import weight_note

NOTE_RE = re.compile(r"\(контекст запроса: ~(\d+\.\d) КБ, (\d+) итераций\)")


def _note_kb(text: str) -> float:
    match = NOTE_RE.search(text)
    assert match, f"заметка о весе не найдена: {text!r}"
    return float(match.group(1))


def _note_iterations(text: str) -> int:
    return int(NOTE_RE.search(text).group(2))


def _messages_with_n_iterations(paths, n):
    iterations = [_text_iter(f"шаг {i}", n=i) for i in range(1, n + 1)]
    return agent.build_messages({"iterations": iterations}, paths)


class WeightNoteTests(unittest.TestCase):
    """Чистая функция: формат, размер, число итераций."""

    def test_format_and_iterations_count(self):
        note = weight_note([{"role": "system", "content": "промпт"}], 18)
        self.assertEqual(note, "(контекст запроса: ~0.0 КБ, 18 итераций)")
        self.assertEqual(_note_iterations(note), 18)
        self.assertIn("КБ", note)  # килобайты, не байты

    def test_kb_value_matches_json_size(self):
        messages = [
            {"role": "system", "content": "Ты — тестовый агент."},
            {"role": "user", "content": "тик " * 200},
        ]
        expected = len(json.dumps(messages, ensure_ascii=False)
                       .encode("utf-8")) / 1024
        note = weight_note(messages, 3)
        self.assertEqual(_note_kb(note), float(f"{expected:.1f}"))

    def test_size_grows_with_history(self):
        small = weight_note([{"role": "user", "content": "короткий"}], 1)
        big = weight_note([{"role": "user", "content": "длинный " * 500}], 1)
        self.assertLess(_note_kb(small), _note_kb(big))


class TickNoteTests(unittest.TestCase):
    """Интеграция: заметка в финальном user-сообщении build_messages."""

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-weight-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def test_note_in_final_user_message_before_tick_without_status(self):
        messages = _messages_with_n_iterations(self.paths, 2)
        final = messages[-1]
        self.assertEqual(final["role"], "user")
        self.assertIn("(контекст запроса: ~", final["content"])
        self.assertIn("КБ, 3 итераций)", final["content"])
        self.assertNotIn("Сейчас нет новых сообщений", final["content"])
        self.assertTrue(final["content"].endswith(agent.USER_MESSAGE))

    def test_previous_llm_duration_is_visible_to_model(self):
        iteration = _text_iter("шаг", n=1)
        iteration["llm_duration"] = 47.17
        final = agent.build_messages({"iterations": [iteration]}, self.paths)[-1]
        self.assertIn(
            "(последний ответ LLM генерировался 47.17 сек)",
            final["content"],
        )

    def test_unread_status_precedes_weight_note(self):
        append_message(self.paths.messages, SENDER_CREATOR, "письмо")
        final = agent.build_messages({"iterations": []}, self.paths)[-1]
        self.assertLess(
            final["content"].index("У тебя есть непрочитанные сообщения"),
            final["content"].index("(контекст запроса:"),
        )
        self.assertNotIn("письмо", final["content"])
        self.assertTrue(final["content"].endswith(agent.USER_MESSAGE))

    def test_note_kb_is_honest_includes_itself(self):
        # число в заметке совпадает с фактическим размером всего запроса,
        # включая финальное сообщение с самой заметкой (два прохода
        # стабилизируют значение)
        messages = _messages_with_n_iterations(self.paths, 5)
        actual_kb = len(json.dumps(messages, ensure_ascii=False)
                        .encode("utf-8")) / 1024
        self.assertEqual(_note_kb(messages[-1]["content"]),
                         float(f"{actual_kb:.1f}"))

    def test_reported_size_grows_from_5_to_15_iterations(self):
        self.assertLess(
            _note_kb(_messages_with_n_iterations(self.paths, 5)[-1]["content"]),
            _note_kb(_messages_with_n_iterations(self.paths, 15)[-1]["content"]),
        )
        self.assertEqual(
            _note_iterations(_messages_with_n_iterations(self.paths, 15)
                             [-1]["content"]), 16)

    def test_prefix_stable_across_iterations(self):
        # запрос итерации N без финального тика целиком стоит в начале
        # запроса итерации N+1 — страховка append-only префикса кеша
        iterations = [_text_iter(f"шаг {i}", n=i) for i in range(1, 5)]
        earlier = agent.build_messages(
            {"iterations": iterations[:3]}, self.paths)
        later = agent.build_messages(
            {"iterations": iterations[:4]}, self.paths)
        self.assertEqual(later[: len(earlier) - 1], earlier[:-1])


if __name__ == "__main__":
    unittest.main()
