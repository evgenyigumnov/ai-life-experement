"""Тесты оформления вывода итерации: заголовок, команда, блок промпта."""


import shutil
import tempfile
import unittest
from unittest import mock

from tests.agent_common import Config, _paths, agent, agent_console, agent_loop, agent_sleep, make_agent_dir


class _IterationLoggingBase(unittest.TestCase):
    """База тестов логирования: одна итерация с моком LLM, логи в список.

    USE_COLOR принудительно выключен — проверки детерминированы.
    """

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-log-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)
        self.cfg = Config(
            base_url="http://mock/v1",
            model="mock-model",
            api_key="k",
            agents_root=None,
            loop_delay=0,
        )

    def _run(self, response, tool_result=None, console_state=None):
        """Прогнать одну итерацию с моком LLM и собрать логи."""
        logs = []
        with mock.patch.object(agent_loop, "_log", logs.append), \
             mock.patch.object(agent_console, "USE_COLOR", False), \
             mock.patch.object(agent_loop, "call_llm", return_value=response):
            if tool_result is not None:
                with mock.patch.object(agent_loop, "execute_tool", return_value=tool_result):
                    agent._run_iteration(self.paths, self.cfg, client=object(),
                                         console_state=console_state)
            else:
                agent._run_iteration(self.paths, self.cfg, client=object(),
                                     console_state=console_state)
        return logs


class IterationHeaderTests(_IterationLoggingBase):
    """Заголовок итерации, команда LLM и блок system prompt в консоли."""

    def test_iteration_header_logged(self):
        logs = self._run({"role": "assistant", "content": "ок"})
        # заголовок + команда + блок system prompt + блок LLM
        self.assertEqual(len(logs), 4)
        self.assertTrue(logs[0].startswith("\n"))
        self.assertIn("═" * 10, logs[0])
        self.assertIn("[ Итерация 1 ]", logs[0])

    def test_iteration_command_logged_with_countdown(self):
        # обычный тик: видна команда LLM и обратный отсчёт до сна
        logs = self._run({"role": "assistant", "content": "ок"})
        command = logs[1]
        self.assertIn("📤 → LLM", command)
        self.assertIn(f"«{agent.USER_MESSAGE}»", command)
        self.assertIn("до сна осталось", command)
        self.assertIn(str(agent.SESSION_ITERATIONS - 1), command)

    def test_iteration_command_last_iteration_shows_sleep_directive(self):
        # последняя итерация сессии: вместо тика — директива сохранить память
        with mock.patch.object(agent_sleep, "SESSION_ITERATIONS", 1):
            logs = self._run({"role": "assistant", "content": "сохраняюсь"})
        command = logs[1]
        self.assertIn(agent.LAST_ITERATION_MESSAGE, command)
        self.assertIn("Сохрани в памяти итог и следующий шаг", command)
        self.assertNotIn("до сна осталось", command)

    def test_system_prompt_full_block_on_first_show(self):
        # первый показ промпта (итерация без состояния консоли — как первая
        # в цикле): заголовок, команда, затем фактический текст промпта в рамке
        logs = self._run({"role": "assistant", "content": "ок"})
        prompt_block = logs[2]
        self.assertTrue(prompt_block.startswith("╔══"))
        self.assertIn("[итерация 1] 📜 System prompt", prompt_block)
        self.assertIn("║ Ты — тестовый агент.", prompt_block)
        self.assertTrue(prompt_block.splitlines()[-1].startswith("╚"))

    def test_system_prompt_short_line_when_unchanged(self):
        # промпт не менялся с прошлой итерации — вместо полного блока
        # короткая строка, текст промпта не повторяется
        console_state = {}
        self._run({"role": "assistant", "content": "первая"},
                  console_state=console_state)
        logs = self._run({"role": "assistant", "content": "вторая"},
                         console_state=console_state)
        self.assertEqual(logs[2], "[итерация 2] 📜 System prompt без изменений")
        self.assertNotIn("Ты — тестовый агент.", logs[2])

    def test_system_prompt_block_reread_from_disk_each_iteration(self):
        # правка system-prompt.md на живом агенте видна в следующей же
        # итерации: полный блок печатается снова — уже с новым текстом
        console_state = {}
        self._run({"role": "assistant", "content": "первая"},
                  console_state=console_state)
        self.paths.system_prompt.write_text("Обновлённый промпт.", encoding="utf-8")
        logs = self._run({"role": "assistant", "content": "вторая"},
                         console_state=console_state)
        self.assertTrue(logs[2].startswith("╔══"))
        self.assertIn("║ Обновлённый промпт.", logs[2])
        self.assertNotIn("Ты — тестовый агент.", logs[2])
        # и снова тишина, пока файл не изменится
        logs = self._run({"role": "assistant", "content": "третья"},
                         console_state=console_state)
        self.assertEqual(logs[2], "[итерация 3] 📜 System prompt без изменений")

if __name__ == "__main__":
    unittest.main()
