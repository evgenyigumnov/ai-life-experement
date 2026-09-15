"""Тесты agent: устаревание памяти и директива последней итерации."""


import shutil
import tempfile
import unittest

from tests.agent_common import agent, make_agent_dir, _paths, _text_iter


class MemoryStalenessTests(unittest.TestCase):
    """Память отстала от работы и директива последней итерации.

    Наблюдение за живым агентом: он сохранял память рано (за 7 итераций до
    сна), дорабатывал хвост сессии через run_bash и засыпал без
    пересохранения. Поэтому: предупреждение «скоро сон» усиливается, если
    после последнего set_memory была работа, а на последней итерации вместо
    обычного тика приходит user-директива сохранить память.
    """

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-stale-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def _calls_iter(self, *names):
        """Итерация с tool-вызовами перечисленных инструментов (по порядку)."""
        calls = [{
            "id": f"call_{i}", "type": "function",
            "function": {"name": name, "arguments": "{}"},
        } for i, name in enumerate(names)]
        return {
            "n": 1,
            "timestamp": "2026-09-09T00:00:00",
            "user": agent.USER_MESSAGE,
            "assistant_message": {"role": "assistant", "content": None,
                                  "tool_calls": calls},
            "tool_results": [],
        }

    def _history(self, count, tail=()):
        """История из count итераций: текстовые + tool-итерации в конце."""
        prefix = count - len(tail)
        iterations = [_text_iter(f"шаг {i}", n=i) for i in range(1, prefix + 1)]
        for i, record in enumerate(tail, start=prefix + 1):
            record["n"] = i
            iterations.append(record)
        return {"iterations": iterations}

    def test_stale_without_any_save(self):
        # в сессии не было ни одного set_memory
        self.assertTrue(agent._memory_stale(self._history(3)["iterations"]))

    def test_stale_when_run_bash_follows_save(self):
        # сохранился, потом поработал — память устарела
        data = self._history(3, tail=(self._calls_iter("set_memory"),
                                      self._calls_iter("run_bash")))
        self.assertTrue(agent._memory_stale(data["iterations"]))

    def test_fresh_when_save_is_last_action(self):
        # поработал, затем сохранился — память актуальна
        data = self._history(3, tail=(self._calls_iter("run_bash"),
                                      self._calls_iter("set_memory")))
        self.assertFalse(agent._memory_stale(data["iterations"]))

    def test_fresh_with_only_save(self):
        data = self._history(2, tail=(self._calls_iter("set_memory"),))
        self.assertFalse(agent._memory_stale(data["iterations"]))

    def test_fresh_when_memory_refreshed_after_work(self):
        # регрессия P0: сохранился → поработал → пересохранился — память
        # актуальна; ранний выход на первом run_bash «замораживал» это
        data = self._history(3, tail=(self._calls_iter("set_memory"),
                                      self._calls_iter("run_bash"),
                                      self._calls_iter("set_memory")))
        self.assertFalse(agent._memory_stale(data["iterations"]))

    def test_stale_again_when_work_follows_refresh(self):
        # после пересохранения снова была работа — снова устарела
        data = self._history(4, tail=(self._calls_iter("set_memory"),
                                      self._calls_iter("run_bash"),
                                      self._calls_iter("set_memory"),
                                      self._calls_iter("run_bash")))
        self.assertTrue(agent._memory_stale(data["iterations"]))

    def test_refresh_in_same_iteration(self):
        # повторное сохранение в той же итерации после работы — актуально
        self.assertFalse(agent._memory_stale(
            [self._calls_iter("set_memory", "run_bash", "set_memory")]))

    def test_same_iteration_order_matters(self):
        # set_memory и run_bash в одной итерации: вызов после сохранения —
        # несохранённая работа, порядок вызовов имеет значение
        self.assertTrue(agent._memory_stale([self._calls_iter("set_memory", "run_bash")]))
        self.assertFalse(agent._memory_stale([self._calls_iter("run_bash", "set_memory")]))

    def test_get_memory_after_save_keeps_fresh(self):
        # чтение памяти — не работа: устаревания нет
        data = self._history(2, tail=(self._calls_iter("set_memory"),
                                      self._calls_iter("get_memory")))
        self.assertFalse(agent._memory_stale(data["iterations"]))

    def test_broken_records_ignored(self):
        self.assertTrue(agent._memory_stale(["мусор", None, 42]))

    def test_tick_user_message_usual_and_last(self):
        self.assertEqual(agent._tick_user_message(1, self.paths), agent.USER_MESSAGE)
        self.assertEqual(
            agent._tick_user_message(agent.SESSION_ITERATIONS - 1, self.paths),
            agent.USER_MESSAGE,
        )
        self.assertEqual(
            agent._tick_user_message(agent.SESSION_ITERATIONS, self.paths),
            agent.LAST_ITERATION_MESSAGE,
        )
        self.assertIn("Сохрани в памяти итог и следующий шаг", agent.LAST_ITERATION_MESSAGE)

    def test_warning_escalated_when_memory_stale(self):
        # 19 итераций, следующая — 20-я: сохранения не было — усиленный текст
        messages = agent.build_messages(self._history(19), self.paths)
        notes = [m["content"] for m in messages
                 if m["role"] == "user" and m is not messages[-1]]
        self.assertEqual(len(notes), 1)
        self.assertIn("не отражает последние действия", notes[0])
        self.assertIn("обнови её сейчас", notes[0])

    def test_warning_calm_when_memory_fresh(self):
        # работа закрыта сохранением — обычное предупреждение без эскалации
        data = self._history(19, tail=(self._calls_iter("run_bash"),
                                       self._calls_iter("set_memory")))
        messages = agent.build_messages(data, self.paths)
        notes = [m["content"] for m in messages
                 if m["role"] == "user" and m is not messages[-1]]
        self.assertEqual(len(notes), 1)
        self.assertNotIn("не отражает последние действия", notes[0])
        self.assertIn("итог и следующий шаг", notes[0])

    def test_warning_calm_when_memory_refreshed_after_work(self):
        # регрессия P0 на уровне build_messages: хвост save→bash→save —
        # предупреждение «спокойное», без «не отражает последние действия»
        data = self._history(19, tail=(self._calls_iter("set_memory"),
                                       self._calls_iter("run_bash"),
                                       self._calls_iter("set_memory")))
        messages = agent.build_messages(data, self.paths)
        notes = [m["content"] for m in messages
                 if m["role"] == "user" and m is not messages[-1]]
        self.assertEqual(len(notes), 1)
        self.assertNotIn("не отражает последние действия", notes[0])
        self.assertIn("итог и следующий шаг", notes[0])

if __name__ == "__main__":
    unittest.main()
