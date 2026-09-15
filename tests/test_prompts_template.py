"""Тесты шаблона system-prompt и его единственного источника."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import prompts_template as prompts


class SystemPromptTemplateTests(unittest.TestCase):
    def test_prompt_facade_is_removed(self):
        facade = Path(__file__).resolve().parent.parent / "prompts.py"
        self.assertFalse(facade.exists())

    def test_template_file_is_single_source(self):
        path = Path(__file__).resolve().parent.parent / "default-prompts" / prompts.FILE_SYSTEM_PROMPT
        self.assertEqual(prompts.SYSTEM_PROMPT_TEMPLATE_FILE, path)
        self.assertEqual(prompts.read_system_prompt_template(), path.read_text(encoding="utf-8").strip())
        self.assertFalse(hasattr(prompts, "DEFAULT_SYSTEM_PROMPT"))

    def test_template_rereads_from_disk(self):
        with tempfile.TemporaryDirectory(prefix="ai-tpl-") as tmp:
            path = Path(tmp) / "system-prompt.md"
            path.write_text("шаблон v1 {name}", encoding="utf-8")
            with mock.patch.object(prompts, "SYSTEM_PROMPT_TEMPLATE_FILE", path):
                self.assertEqual(prompts.read_system_prompt_template(), "шаблон v1 {name}")
                path.write_text("шаблон v2 {name}", encoding="utf-8")
                self.assertEqual(prompts.read_system_prompt_template(), "шаблон v2 {name}")

    def test_template_placeholders_contract(self):
        self.assertEqual(prompts._placeholder_names(prompts.read_system_prompt_template()), prompts.SYSTEM_PROMPT_PLACEHOLDERS)
        self.assertEqual(prompts.SYSTEM_PROMPT_PLACEHOLDERS, {"name", "session_iterations", "sleep_warn_remaining"})

    def test_template_is_deduplicated_and_compact(self):
        template = prompts.read_system_prompt_template()
        self.assertEqual(template.count("{name}"), 2)
        self.assertEqual(template.count("{session_iterations}"), 2)
        self.assertEqual(template.count("{sleep_warn_remaining}"), 1)
        self.assertLessEqual(len(template), 3400)
        for marker in ("не ассистент", "единственное хранилище", "журналов", "незнакомые файлы", "рутинные проверки", "перезапиши память", "прочитай память", "run_bash", "get_messages", "send_message", "money_balance", "money_spend"):
            self.assertIn(marker, template)

    def test_template_describes_messaging_with_creator(self):
        template = prompts.read_system_prompt_template()
        self.assertIn("В начале итерации проверяй сообщения создателя", template)
        self.assertIn("send_message", template)
        self.assertIn("get_messages", template)
        self.assertIn("единственный канал связи", template)

    def test_template_describes_money_tools_and_schedule(self):
        template = prompts.read_system_prompt_template()
        self.assertIn("money_balance", template)
        self.assertIn("money_spend", template)
        self.assertIn("1 единица = 1 следующий цикл/тик LLM без паузы перед ним", template)
        self.assertIn("0 → 30 сек → 1 мин → 2 мин → 5 мин → 10 мин → 20 мин → 40 мин → 1 час → 2 часа → 4 часа", template)
        self.assertIn("только отменяют межцикловое ожидание", template)

    def test_render_substitutes_name_and_defaults(self):
        rendered = prompts.render_system_prompt("Олег")
        self.assertIn("Тебя зовут Олег.", rendered)
        self.assertIn("«Олег» — это ты", rendered)
        self.assertIn("сессиями по 30 итераций", rendered)
        self.assertIn("После 30-й итерации", rendered)
        self.assertIn("останется 10 итераций", rendered)
        self.assertNotIn("{", rendered)
        self.assertNotIn("}", rendered)

    def test_render_custom_loop_params(self):
        rendered = prompts.render_system_prompt("bot", session_iterations=5, sleep_warn_remaining=2)
        self.assertIn("сессиями по 5 итераций", rendered)
        self.assertIn("останется 2 итераций", rendered)
        self.assertNotIn("сессиями по 30 итераций", rendered)
        self.assertNotIn("останется 10 итераций", rendered)

    def test_render_empty_name_raises(self):
        for name in ("", "   "):
            with self.assertRaises(ValueError):
                prompts.render_system_prompt(name)

    def test_missing_template_file_raises(self):
        with mock.patch.object(prompts, "SYSTEM_PROMPT_TEMPLATE_FILE", Path("/нет/такого.md")):
            with self.assertRaises(OSError):
                prompts.render_system_prompt("Олег")

    def test_empty_template_raises(self):
        with tempfile.TemporaryDirectory(prefix="ai-empty-") as tmp:
            path = Path(tmp) / "system-prompt.md"
            path.write_text("  \n", encoding="utf-8")
            with mock.patch.object(prompts, "SYSTEM_PROMPT_TEMPLATE_FILE", path):
                with self.assertRaises(ValueError):
                    prompts.render_system_prompt("Олег")

    def test_template_with_wrong_placeholders_raises(self):
        with tempfile.TemporaryDirectory(prefix="ai-badtpl-") as tmp:
            path = Path(tmp) / "system-prompt.md"
            path.write_text("Тебя зовут {name}, цикл {нет_такого}.", encoding="utf-8")
            with mock.patch.object(prompts, "SYSTEM_PROMPT_TEMPLATE_FILE", path):
                with self.assertRaises(ValueError) as ctx:
                    prompts.render_system_prompt("Олег")
        self.assertIn("плейсхолдеры", str(ctx.exception))

    def test_system_prompt_defaults_match_cycle_constants(self):
        import agent_sleep

        self.assertEqual(
            prompts.DEFAULT_SESSION_ITERATIONS, agent_sleep.SESSION_ITERATIONS
        )
        self.assertEqual(
            prompts.DEFAULT_SLEEP_WARN_REMAINING, agent_sleep.SLEEP_WARN_REMAINING
        )

    def test_template_moves_look_around_to_wake_up(self):
        template = prompts.read_system_prompt_template()
        self.assertIn("осмотри песочницу", template)
        self.assertIn("незнакомые файлы", template)
        self.assertIn("часть пробуждения, а не каждого шага", template)
        self.assertNotIn("Периодически осматривайся", template)

    def test_resolver_does_not_use_legacy_directory(self):
        root = Path(tempfile.mkdtemp(prefix="ai-resolver-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        new = root / "default-prompts" / "system-prompt.md"
        old = root / "default-promts" / "system-prompt.md"
        old.parent.mkdir(parents=True)
        old.write_text("legacy", encoding="utf-8")
        with mock.patch.object(prompts, "SYSTEM_PROMPT_TEMPLATE_FILE", new):
            with self.assertRaises(OSError) as ctx:
                prompts.read_system_prompt_template()
        self.assertIn(str(new), str(ctx.exception))
        self.assertNotIn("default-promts", str(ctx.exception))


class EnsureSystemPromptTests(unittest.TestCase):
    def setUp(self):
        self._tmp = Path(tempfile.mkdtemp(prefix="ai-sysprompt-"))
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)

    def test_creates_prompt_with_agent_name_when_missing(self):
        created = prompts.ensure_system_prompt(self._tmp, "ghost")
        self.assertIsNotNone(created)
        self.assertEqual(created, self._tmp / prompts.FILE_SYSTEM_PROMPT)
        self.assertIn("Тебя зовут ghost.", created.read_text(encoding="utf-8"))
        self.assertIn("сессиями по 30 итераций", created.read_text(encoding="utf-8"))

    def test_existing_prompt_not_overwritten(self):
        path = self._tmp / prompts.FILE_SYSTEM_PROMPT
        path.write_text("мой кастомный промпт", encoding="utf-8")
        self.assertIsNone(prompts.ensure_system_prompt(self._tmp, "ghost"))
        self.assertEqual(path.read_text(encoding="utf-8"), "мой кастомный промпт")

    def test_creates_at_most_once(self):
        self.assertIsNotNone(prompts.ensure_system_prompt(self._tmp, "bot"))
        self.assertIsNone(prompts.ensure_system_prompt(self._tmp, "bot"))


if __name__ == "__main__":
    unittest.main()
