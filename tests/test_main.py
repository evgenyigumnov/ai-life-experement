"""Тесты main.py — точки входа (шаг 8): аргументы, баннер, запуск цикла.

run_loop подменён моком (в реальный API не ходим).
"""

import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from tests.helpers import PROJECT_ROOT, env, make_agent_dir, run_python

sys.path.insert(0, str(PROJECT_ROOT))
import main as main_mod  # noqa: E402


class CliErrorTests(unittest.TestCase):
    def test_no_arguments_no_agents_hints_agent_creation(self):
        empty_root = Path(tempfile.mkdtemp(prefix="ai-main-empty-"))
        self.addCleanup(shutil.rmtree, empty_root, ignore_errors=True)
        r = run_python(
            "import sys; sys.argv=['main.py']; import main; main.main()",
            env_extra={"AGENTS_ROOT": str(empty_root)},
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("Агенты не найдены", r.stderr)
        self.assertIn("Использование", r.stderr)
        # подсказка: с именем будет создан новый агент из шаблона
        self.assertIn("новый агент", r.stderr)

    def test_no_arguments_multiple_agents_lists_all(self):
        root = Path(tempfile.mkdtemp(prefix="ai-main-many-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        make_agent_dir(root, "alpha")
        make_agent_dir(root, "beta")
        r = run_python(
            "import sys; sys.argv=['main.py']; import main; main.main()",
            env_extra={"AGENTS_ROOT": str(root)},
        )
        self.assertEqual(r.returncode, 1)
        self.assertIn("несколько", r.stderr)
        self.assertIn("python main.py alpha", r.stderr)
        self.assertIn("python main.py beta", r.stderr)

    def test_unknown_agent_created_from_template(self):
        # агента ещё нет — main.py создаёт его на основе шаблона:
        # папка + system-prompt.md с подставленным именем (docker и цикл
        # подменены заглушками, в реальный API не ходим)
        root = Path(tempfile.mkdtemp(prefix="ai-main-new-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        r = run_python(
            "import sys; sys.argv=['main.py', 'ghost']; "
            "import main; "
            "main.ensure_docker_container = lambda name: None; "
            "main.run_loop = lambda paths, cfg: None; "
            "main.main()",
            env_extra={"AGENTS_ROOT": str(root)},
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("создаю нового", r.stdout)
        self.assertIn("агент «ghost»", r.stdout)  # баннер нового агента
        folder = root / "ghost"
        prompt = (folder / "system-prompt.md").read_text(encoding="utf-8")
        self.assertIn("Тебя зовут ghost.", prompt)
        self.assertTrue((folder / "mind-loop.json").is_file())
        self.assertTrue((folder / "memory.md").is_file())


class BannerTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-main-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.folder = make_agent_dir(self.root, "bot")
        self.calls = {}

        def fake_run_loop(paths, cfg):
            self.calls["paths"], self.calls["cfg"] = paths, cfg

        self.fake_run_loop = fake_run_loop

    def _run_main(self, argv=None, session_iterations=None):
        environment = {
            "AGENTS_ROOT": str(self.root),
            "OPENAI_BASE_URL": "http://mock.local/v1",
            "OPENAI_MODEL": "mock-model",
            "OPENAI_API_KEY": "mock-key",
        }
        if session_iterations is not None:
            environment.update(
                SESSION_ITERATIONS=str(session_iterations),
                SLEEP_WARN_REMAINING="1",
            )
        with mock.patch.object(main_mod, "run_loop", self.fake_run_loop), \
             mock.patch.object(sys, "argv", argv or ["main.py", "bot"]), \
             env(**environment), \
             redirect_stdout(StringIO()) as out:
            main_mod.main()
        return out.getvalue()

    def test_banner_fields_and_loop_started(self):
        output = self._run_main()
        for expected in ("bot", "mock-model", "http://mock.local/v1", "0 итераций"):
            self.assertIn(expected, output)
        self.assertIn(str(self.folder.resolve()), output)
        self.assertIn("Ctrl+C", output)
        # run_loop запущен с путями и конфигом
        self.assertEqual(self.calls["paths"].folder, self.folder.resolve())
        self.assertEqual(self.calls["cfg"].model, "mock-model")
        self.assertTrue((self.folder / "mind-loop.json").is_file())
        self.assertTrue((self.folder / "memory.md").is_file())

    def test_banner_shows_existing_iteration_count(self):
        data = {"agent": "bot", "created_at": "t", "updated_at": "t", "iterations": [
            {"n": 1, "assistant_message": {"role": "assistant", "content": "а"}},
            {"n": 2, "assistant_message": {"role": "assistant", "content": "б"}},
        ]}
        (self.folder / "mind-loop.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
        output = self._run_main()
        self.assertIn("2 итераций", output)

    def test_banner_shows_iterations_left_until_sleep(self):
        # свежая сессия (0 итераций) — до сна все SESSION_ITERATIONS
        output = self._run_main(session_iterations=5)
        self.assertIn("До сна:", output)
        self.assertIn("осталось 5 итераций", output)
        self.assertIn("сессия из 5", output)

    def test_banner_counts_down_after_work_done(self):
        # 2 итерации из 5 сделаны — до сна осталось 3
        data = {"agent": "bot", "created_at": "t", "updated_at": "t", "iterations": [
            {"n": 1, "assistant_message": {"role": "assistant", "content": "а"}},
            {"n": 2, "assistant_message": {"role": "assistant", "content": "б"}},
        ]}
        (self.folder / "mind-loop.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
        output = self._run_main(session_iterations=5)
        self.assertIn("осталось 3 итерации", output)

    def test_banner_sleep_countdown_never_negative(self):
        # защита от рассинхрона файла и константы: сделано не меньше длины сессии
        data = {"agent": "bot", "created_at": "t", "updated_at": "t", "iterations": [
            {"n": i, "assistant_message": {"role": "assistant", "content": "x"}}
            for i in range(1, 6)
        ]}
        (self.folder / "mind-loop.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
        output = self._run_main(session_iterations=5)
        self.assertIn("осталось 0 итераций", output)
        self.assertNotIn("осталось -", output)

    def test_banner_shows_session_number_after_sleep(self):
        # после сна mind-loop.json свежий: сессия 5, история пуста, отсчёт с 0
        data = {"agent": "bot", "created_at": "t", "updated_at": "t",
                "session": 5, "woke_up_at": "t", "iterations": []}
        (self.folder / "mind-loop.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
        output = self._run_main()
        self.assertIn("Сессия:   5", output)
        self.assertIn("0 итераций", output)

    def test_banner_session_defaults_to_one(self):
        # старый файл без поля session — первая жизнь
        data = {"agent": "bot", "created_at": "t", "updated_at": "t", "iterations": [
            {"n": 1, "assistant_message": {"role": "assistant", "content": "а"}},
        ]}
        (self.folder / "mind-loop.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
        output = self._run_main()
        self.assertIn("Сессия:   1", output)
        self.assertIn("1 итераций", output)

    def test_banner_is_boxed(self):
        output = self._run_main()
        # двойная рамка вокруг баннера и заголовок по центру
        self.assertIn("╔" + "═" * 60 + "╗", output)
        self.assertIn("╚" + "═" * 60 + "╝", output)
        self.assertIn("║", output)
        self.assertIn("AI Life — агент «bot»", output)
        self.assertIn("║ Модель:", output)

    def test_banner_no_ansi_when_not_tty(self):
        # stdout подменён StringIO (не терминал) — без ANSI-кодов
        output = self._run_main()
        self.assertNotIn("\x1b[", output)

    def test_keyboard_interrupt_from_loop_propagates(self):
        def interrupting_run_loop(paths, cfg):
            raise KeyboardInterrupt

        with mock.patch.object(main_mod, "run_loop", interrupting_run_loop), \
             mock.patch.object(sys, "argv", ["main.py", "bot"]), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key"), \
             redirect_stdout(StringIO()):
            with self.assertRaises(KeyboardInterrupt):
                main_mod.main()

    def test_main_ensures_docker_container_called_when_bash_enabled(self):
        # песочница создаётся только при включённом run_bash (ENABLE_BASH_TOOL)
        with mock.patch.object(main_mod, "run_loop", self.fake_run_loop), \
             mock.patch.object(main_mod, "ensure_docker_container") as mock_ensure, \
             mock.patch.object(sys, "argv", ["main.py", "bot"]), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key",
                 ENABLE_BASH_TOOL="1"), \
             redirect_stdout(StringIO()):
            main_mod.main()
            mock_ensure.assert_called_once_with("bot")

    def test_main_skips_docker_when_bash_disabled(self):
        # run_bash выключен — Docker-контейнер не нужен вовсе
        with mock.patch.object(main_mod, "run_loop", self.fake_run_loop), \
             mock.patch.object(main_mod, "ensure_docker_container") as mock_ensure, \
             mock.patch.object(sys, "argv", ["main.py", "bot"]), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key",
                 ENABLE_BASH_TOOL="0"), \
             redirect_stdout(StringIO()):
            main_mod.main()
            mock_ensure.assert_not_called()

    def test_main_docker_error_exits_with_code_1(self):
        with mock.patch.object(main_mod, "ensure_docker_container", side_effect=RuntimeError("docker fail")), \
             mock.patch.object(sys, "argv", ["main.py", "bot"]), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key",
                 ENABLE_BASH_TOOL="1"), \
             unittest.mock.patch("sys.stderr", new_callable=StringIO) as mock_stderr:
            with self.assertRaises(SystemExit) as cm:
                main_mod.main()
            self.assertEqual(cm.exception.code, 1)
            self.assertIn("docker fail", mock_stderr.getvalue())


class LoopPauseArgTests(unittest.TestCase):
    """Флаг --loop-pause=N: фиксированная пауза вместо адаптивного расписания."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-loop-pause-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.folder = make_agent_dir(self.root, "bot")
        self.calls = {}

    def _run_main(self, argv):
        def fake_run_loop(paths, cfg):
            self.calls["cfg"] = cfg

        with mock.patch.object(main_mod, "run_loop", fake_run_loop), \
             mock.patch.object(sys, "argv", argv), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key"), \
             redirect_stdout(StringIO()) as out:
            main_mod.main()
        return out.getvalue()

    def test_flag_after_name_sets_loop_pause(self):
        output = self._run_main(["main.py", "bot", "--loop-pause=30"])
        self.assertEqual(self.calls["cfg"].loop_pause, 30.0)
        # баннер сообщает о фиксированном режиме
        self.assertIn("Пауза:    фиксированная 30 сек", output)

    def test_flag_before_name_sets_loop_pause(self):
        # флаг в любой позиции — и до имени агента
        self._run_main(["main.py", "--loop-pause=30", "bot"])
        self.assertEqual(self.calls["cfg"].loop_pause, 30.0)

    def test_flag_space_form_sets_loop_pause(self):
        # --loop-pause N (без «=») тоже принимается
        self._run_main(["main.py", "bot", "--loop-pause", "30"])
        self.assertEqual(self.calls["cfg"].loop_pause, 30.0)

    def test_flag_accepts_fractional_seconds(self):
        output = self._run_main(["main.py", "bot", "--loop-pause=1.5"])
        self.assertEqual(self.calls["cfg"].loop_pause, 1.5)
        self.assertIn("фиксированная 1.5 сек", output)

    def test_without_flag_loop_pause_is_none(self):
        output = self._run_main(["main.py", "bot"])
        self.assertIsNone(self.calls["cfg"].loop_pause)  # адаптивное расписание
        self.assertNotIn("Пауза:", output)  # без строки в баннере

    def _expect_usage_exit(self, argv):
        with mock.patch.object(main_mod, "run_loop"), \
             mock.patch.object(sys, "argv", argv), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key"), \
             redirect_stderr(StringIO()) as err, redirect_stdout(StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main_mod.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("--loop-pause", err.getvalue())

    def test_non_numeric_value_is_usage_error(self):
        self._expect_usage_exit(["main.py", "bot", "--loop-pause=abc"])

    def test_negative_value_is_usage_error(self):
        self._expect_usage_exit(["main.py", "bot", "--loop-pause=-5"])

    def test_nan_value_is_usage_error(self):
        self._expect_usage_exit(["main.py", "bot", "--loop-pause=nan"])

    def test_missing_value_is_usage_error(self):
        self._expect_usage_exit(["main.py", "bot", "--loop-pause"])

    def test_usage_error_mentions_flag(self):
        # строка использования подсказывает и флаг
        self._expect_usage_exit(["main.py", "bot", "extra"])


class NoArgumentAgentPickTests(unittest.TestCase):
    """`python main.py` без имени: автоподбор единственного агента."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-main-auto-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.folder = make_agent_dir(self.root, "bot")
        self.calls = {}

    def test_single_agent_autoselected_and_started(self):
        def fake_run_loop(paths, cfg):
            self.calls["paths"], self.calls["cfg"] = paths, cfg

        with mock.patch.object(main_mod, "run_loop", fake_run_loop), \
             mock.patch.object(sys, "argv", ["main.py"]), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key"), \
             redirect_stdout(StringIO()) as out:
            main_mod.main()

        output = out.getvalue()
        self.assertIn("единственного найденного: «bot»", output)
        self.assertIn("AI Life — агент «bot»", output)  # баннер с автоподобранным именем
        self.assertEqual(self.calls["paths"].folder, self.folder.resolve())
        self.assertTrue((self.folder / "mind-loop.json").is_file())

    def test_explicit_name_still_supported(self):
        # прямое указание имени работает как раньше, подсказка не печатается
        make_agent_dir(self.root, "second")
        captured = {}

        def fake_run_loop(paths, cfg):
            captured["folder"] = paths.folder

        with mock.patch.object(main_mod, "run_loop", fake_run_loop), \
             mock.patch.object(sys, "argv", ["main.py", "bot"]), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key"), \
             redirect_stdout(StringIO()) as out:
            main_mod.main()

        self.assertNotIn("единственного найденного", out.getvalue())
        self.assertEqual(captured["folder"], self.folder.resolve())

    def test_multiple_agents_exit_with_listing(self):
        make_agent_dir(self.root, "second")
        with mock.patch.object(main_mod, "run_loop", lambda paths, cfg: None), \
             mock.patch.object(sys, "argv", ["main.py"]), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL="http://mock.local/v1",
                 OPENAI_MODEL="mock-model",
                 OPENAI_API_KEY="mock-key"), \
             redirect_stderr(StringIO()) as err, redirect_stdout(StringIO()):
            with self.assertRaises(SystemExit) as cm:
                main_mod.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("python main.py bot", err.getvalue())
        self.assertIn("python main.py second", err.getvalue())


class ReplyModeTests(unittest.TestCase):
    """`python main.py <имя> reply`: переписка создателя с агентом."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-reply-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.folder = make_agent_dir(self.root, "bot")

    def _run_reply(self, typed_text, argv=("main.py", "bot", "reply")):
        with mock.patch.object(sys, "argv", list(argv)), \
             mock.patch("builtins.input", return_value=typed_text), \
             mock.patch.object(main_mod, "run_loop") as mock_run_loop, \
             mock.patch.object(main_mod, "ensure_docker_container") as mock_ensure, \
             env(AGENTS_ROOT=str(self.root), ENABLE_BASH_TOOL="1"), \
             redirect_stdout(StringIO()) as out:
            main_mod.main()
        return out.getvalue(), mock_run_loop, mock_ensure

    def _write_messages(self, count):
        messages = [
            {"timestamp": f"2026-09-10T10:0{i}:00",
             "from": "creator" if i % 2 else "agent",
             "text": f"сообщение {i}"}
            for i in range(count)
        ]
        (self.folder / "messages.json").write_text(
            json.dumps({"agent": "bot", "messages": messages}, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_shows_entire_history_and_sends_reply(self):
        self._write_messages(12)  # вся переписка печатается целиком
        output, mock_run_loop, mock_ensure = self._run_reply("мой ответ")
        self.assertIn("Переписка с «bot»", output)
        self.assertIn("всего сообщений: 12", output)
        for index in range(12):
            self.assertIn(f"сообщение {index}", output)
        self.assertNotIn("последние 10", output)
        # подписи отправителей
        self.assertIn("Создатель: сообщение 3", output)
        self.assertIn("bot: сообщение 2", output)
        # ответ дописан от имени создателя, LLM и Docker не тронуты
        data = json.loads((self.folder / "messages.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["messages"]), 13)
        last = data["messages"][-1]
        self.assertEqual((last["from"], last["text"]), ("creator", "мой ответ"))
        self.assertFalse(last["read"])
        mock_run_loop.assert_not_called()
        mock_ensure.assert_not_called()
        self.assertIn("Сообщение отправлено агенту", output)

    def test_reply_display_does_not_mark_messages_read(self):
        messages = [
            {
                "timestamp": "2026-09-10T10:00:00",
                "from": "creator",
                "text": "непрочитанное письмо",
                "read": False,
            },
            {
                "timestamp": "2026-09-10T10:01:00",
                "from": "agent",
                "text": "ответ агента",
                "read": True,
            },
        ]
        self.folder.joinpath("messages.json").write_text(
            json.dumps({"agent": "bot", "messages": messages}, ensure_ascii=False),
            encoding="utf-8",
        )
        before = self.folder.joinpath("messages.json").read_text(encoding="utf-8")

        output, _, _ = self._run_reply("   ")

        self.assertIn("непрочитанное письмо (не прочитано)", output)
        self.assertIn("ответ агента (прочитано)", output)
        self.assertEqual(
            self.folder.joinpath("messages.json").read_text(encoding="utf-8"),
            before,
        )

    def test_empty_input_sends_nothing(self):
        self._write_messages(2)
        output, _, _ = self._run_reply("   ")
        data = json.loads((self.folder / "messages.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["messages"]), 2)
        self.assertIn("не отправлено", output)

    def test_first_message_creates_conversation(self):
        # переписки ещё нет — печатается подсказка, сообщение становится первым
        output, _, _ = self._run_reply("первое письмо")
        self.assertIn("переписки ещё нет", output)
        data = json.loads((self.folder / "messages.json").read_text(encoding="utf-8"))
        self.assertEqual(len(data["messages"]), 1)
        self.assertEqual(data["messages"][0]["text"], "первое письмо")

    def test_no_llm_config_required(self):
        # reply-режим работает без OPENAI_BASE_URL/OPENAI_MODEL — LLM не вызывается
        with mock.patch.object(sys, "argv", ["main.py", "bot", "reply"]), \
             mock.patch("builtins.input", return_value="привет"), \
             env(AGENTS_ROOT=str(self.root),
                 OPENAI_BASE_URL=None, OPENAI_MODEL=None, OPENAI_API_KEY=None), \
             redirect_stdout(StringIO()):
            main_mod.main()  # не падает и не зовёт load_config
        data = json.loads((self.folder / "messages.json").read_text(encoding="utf-8"))
        self.assertEqual(data["messages"][-1]["text"], "привет")

    def test_reply_without_agent_name_is_usage_error(self):
        with mock.patch.object(sys, "argv", ["main.py", "reply"]), \
             env(AGENTS_ROOT=str(self.root)), \
             redirect_stderr(StringIO()) as err:
            with self.assertRaises(SystemExit) as cm:
                main_mod.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Укажите имя агента", err.getvalue())

    def test_unknown_extra_argument_is_usage_error(self):
        with mock.patch.object(sys, "argv", ["main.py", "bot", "extra"]), \
             env(AGENTS_ROOT=str(self.root)), \
             redirect_stderr(StringIO()) as err:
            with self.assertRaises(SystemExit) as cm:
                main_mod.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Использование", err.getvalue())

    def test_creates_unknown_agent_from_template(self):
        # ответ несуществующему агенту создаёт его папку с файлами первого запуска
        output, _, _ = self._run_reply("hi", argv=("main.py", "ghost", "reply"))
        folder = self.root / "ghost"
        self.assertTrue((folder / "system-prompt.md").is_file())
        self.assertTrue((folder / "messages.json").is_file())

    def test_loop_pause_flag_ignored_in_reply_mode(self):
        # флаг фиксированной паузы относится к циклу жизни: в reply-режиме
        # цикл не запускается — флаг игнорируется, переписка работает
        output, mock_run_loop, _ = self._run_reply(
            "привет", argv=("main.py", "bot", "reply", "--loop-pause=5"))
        mock_run_loop.assert_not_called()
        data = json.loads((self.folder / "messages.json").read_text(encoding="utf-8"))
        self.assertEqual(data["messages"][-1]["text"], "привет")
        self.assertIn("Сообщение отправлено агенту", output)


if __name__ == "__main__":
    unittest.main()
