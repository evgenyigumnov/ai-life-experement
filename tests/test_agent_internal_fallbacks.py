"""Тесты внутренних fallback-строк agent (INTERNAL_MESSAGES)."""


import shutil
import tempfile
import unittest

from tests.agent_common import agent, make_agent_dir, _paths, _tool_iter


class InternalFallbackTests(unittest.TestCase):
    """Сбойные итерации и потерянные tool-результаты — внутренние строки,

    а не файлы в папке агента: файлы tool-result-missing.md и
    iteration-failed.md агент игнорирует (см. prompts_messages.py).
    """

    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-msgfiles-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def _write(self, filename: str, text: str):
        (self.folder / filename).write_text(text, encoding="utf-8")

    def test_tool_result_missing_uses_internal_fallback(self):
        # tool-result-missing.md больше не читается циклом:
        # используется внутренняя строка из INTERNAL_MESSAGES
        record = _tool_iter(n=1)
        record["tool_results"] = []  # результат пропал
        messages = agent.build_messages({"iterations": [record]}, self.paths)
        tool_message = next(m for m in messages if m["role"] == "tool")
        self.assertIn("Error", tool_message["content"])
        from prompts_messages import INTERNAL_MESSAGES
        self.assertEqual(tool_message["content"], INTERNAL_MESSAGES["tool-result-missing.md"])

    def test_tool_result_missing_file_ignored_by_agent(self):
        # наличие файла tool-result-missing.md в папке агента не влияет
        # на агента: он использует только внутренний fallback
        self._write("tool-result-missing.md", "результат утерян")
        record = _tool_iter(n=1)
        record["tool_results"] = []
        messages = agent.build_messages({"iterations": [record]}, self.paths)
        tool_message = next(m for m in messages if m["role"] == "tool")
        from prompts_messages import INTERNAL_MESSAGES
        self.assertEqual(tool_message["content"], INTERNAL_MESSAGES["tool-result-missing.md"])

    def test_iteration_failed_uses_internal_fallback(self):
        # iteration-failed.md больше не читается циклом:
        # используется внутренняя строка из INTERNAL_MESSAGES
        messages = agent.build_messages(
            {"iterations": [{"n": 1, "user": "x", "error": "упало"}]}, self.paths
        )
        self.assertIn("[сбой итерации: упало]", messages[1]["content"])
        from prompts_messages import INTERNAL_MESSAGES
        self.assertEqual(
            messages[1]["content"],
            INTERNAL_MESSAGES["iteration-failed.md"].format(error="упало"),
        )

    def test_iteration_failed_file_ignored_by_agent(self):
        # наличие файла iteration-failed.md в папке агента не влияет на агента
        self._write("iteration-failed.md", "СБОЙ ИТЕРАЦИИ: {error}")
        messages = agent.build_messages(
            {"iterations": [{"n": 1, "user": "x", "error": "упало"}]}, self.paths
        )
        from prompts_messages import INTERNAL_MESSAGES
        self.assertEqual(
            messages[1]["content"],
            INTERNAL_MESSAGES["iteration-failed.md"].format(error="упало"),
        )

if __name__ == "__main__":
    unittest.main()
