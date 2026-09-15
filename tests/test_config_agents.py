"""Тесты поиска и создания папки агента."""

import json
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

import agent_paths as config
import prompts_messages as prompts
from config_env import Config
from tests.helpers import env, make_agent_dir


def cfg(root=None, **extra):
    values = dict(base_url="http://x/v1", model="m", api_key="k", agents_root=root)
    values.update(extra)
    return Config(**values)


class ListAgentsTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-list-"))
        self.old_cwd = Path.cwd()
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_agents_root_filters_and_sorts(self):
        agents = self.root / "agents"
        make_agent_dir(agents, "zeta")
        make_agent_dir(agents, "alpha")
        make_agent_dir(agents, ".hidden")
        (agents / "not-agent").mkdir()
        self.assertEqual(config.list_agents(cfg(str(agents))), ["alpha", "zeta"])

    def test_agents_root_lists_only_valid_agent_folders(self):
        agents = self.root / "agents"
        make_agent_dir(agents, "bot")
        (agents / "data").mkdir()
        make_agent_dir(agents, ".hidden")
        self.assertEqual(config.list_agents(cfg(str(agents))), ["bot"])

    def test_cwd_direct_and_nested_scan(self):
        os.chdir(self.root)
        make_agent_dir(self.root, "top")
        make_agent_dir(self.root / "group", "nested")
        self.assertEqual(config.list_agents(cfg()), ["nested", "top"])

    def test_cwd_scan_ignores_non_agents(self):
        os.chdir(self.root)
        (self.root / "group" / "empty").mkdir(parents=True)
        self.assertEqual(config.list_agents(cfg()), [])

    def test_empty_or_missing_root(self):
        self.assertEqual(config.list_agents(cfg(str(self.root / "missing"))), [])
        os.chdir(self.root)
        self.assertEqual(config.list_agents(cfg()), [])


class FindAgentFolderTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-agent-"))
        self.old_cwd = Path.cwd()
        self.addCleanup(self._restore)

    def _restore(self):
        os.chdir(self.old_cwd)
        shutil.rmtree(self.root, ignore_errors=True)

    def test_first_run_creates_all_state_and_preserves_it(self):
        agents = self.root / "agents"
        paths = config.find_agent_folder("bot", cfg(str(agents)))
        self.assertEqual(paths.folder, (agents / "bot").resolve())
        self.assertTrue(paths.system_prompt.is_file())
        self.assertTrue(paths.memory.is_file())
        self.assertTrue(paths.wallet.is_file())
        wallet = json.loads(paths.wallet.read_text(encoding="utf-8"))
        self.assertEqual((wallet["schema_version"], wallet["acceleration_cycles"]), (1, 0))
        messages = json.loads(paths.messages.read_text(encoding="utf-8"))
        diary = json.loads(paths.diary.read_text(encoding="utf-8"))
        self.assertEqual(messages["messages"], [])
        self.assertEqual((diary["entries"], diary["next_id"]), ([], 1))
        self.assertEqual(json.loads(paths.mind_loop.read_text(encoding="utf-8"))["iterations"], [])
        for filename in prompts.EDITABLE_MESSAGE_FILES:
            self.assertTrue((paths.folder / filename).is_file())
        self.assertFalse((paths.folder / "unread-messages.md").exists())
        custom = paths.folder / prompts.FILE_USER_MESSAGE
        custom.write_text("моя правка", encoding="utf-8")
        config.find_agent_folder("bot", cfg(str(agents)))
        self.assertEqual(custom.read_text(encoding="utf-8"), "моя правка")

    def test_first_run_uses_shared_mind_loop_factory(self):
        agents = self.root / "agents"
        mind_loop = {
            "agent": "bot",
            "created_at": "created",
            "updated_at": "updated",
            "session": 1,
            "iterations": [],
        }
        with mock.patch.object(config, "_empty_mind_loop", return_value=mind_loop) as factory:
            paths = config.find_agent_folder("bot", cfg(str(agents)))

        factory.assert_called_once_with("bot")
        self.assertEqual(
            json.loads(paths.mind_loop.read_text(encoding="utf-8")), mind_loop
        )

    def test_first_run_does_not_overwrite_edited_message_files(self):
        agents = self.root / "agents"
        paths = config.find_agent_folder("bot", cfg(str(agents)))
        custom = paths.folder / prompts.FILE_USER_MESSAGE
        custom.write_text("моя команда", encoding="utf-8")
        config.find_agent_folder("bot", cfg(str(agents)))
        self.assertEqual(custom.read_text(encoding="utf-8"), "моя команда")

    def test_session_override_reaches_new_system_prompt(self):
        paths = config.find_agent_folder("bot", cfg(
            str(self.root / "agents"), session_iterations=80, sleep_warn_remaining=7
        ))
        text = paths.system_prompt.read_text(encoding="utf-8")
        self.assertIn("сессиями по 80 итераций", text)
        self.assertIn("останется 7 итераций", text)

    def test_agents_root_missing_folder_creates_new_agent(self):
        agents = self.root / "agents"
        with redirect_stdout(StringIO()):
            paths = config.find_agent_folder("ghost", cfg(str(agents)))
        self.assertEqual(paths.folder, (agents / "ghost").resolve())
        self.assertIn("Тебя зовут ghost.", paths.system_prompt.read_text(encoding="utf-8"))
        self.assertEqual(config.list_agents(cfg(str(agents))), ["ghost"])

    def test_existing_prompt_is_not_overwritten(self):
        agents = self.root / "agents"
        folder = make_agent_dir(agents, "bot", prompt="мой промпт")
        with redirect_stdout(StringIO()):
            config.find_agent_folder("bot", cfg(str(agents), session_iterations=80))
        self.assertEqual((folder / "system-prompt.md").read_text(encoding="utf-8"), "мой промпт")

    def test_direct_and_nested_locations(self):
        os.chdir(self.root)
        direct = make_agent_dir(self.root, "bot")
        self.assertEqual(config.find_agent_folder("bot", cfg()).folder, direct.resolve())
        shutil.rmtree(direct)
        nested = make_agent_dir(self.root / "group", "bot")
        self.assertEqual(config.find_agent_folder("bot", cfg()).folder, nested.resolve())

    def test_not_found_in_cwd_creates_agent_there(self):
        os.chdir(self.root)
        with redirect_stdout(StringIO()):
            paths = config.find_agent_folder("newcomer", cfg())
        self.assertEqual(paths.folder, (self.root / "newcomer").resolve())
        self.assertEqual(config.list_agents(cfg()), ["newcomer"])

    def test_existing_folder_without_prompt_gets_one(self):
        agents = self.root / "agents"
        (agents / "bot").mkdir(parents=True)
        with redirect_stdout(StringIO()):
            paths = config.find_agent_folder("bot", cfg(str(agents)))
        self.assertTrue(paths.system_prompt.is_file())

    def test_invalid_names_create_nothing(self):
        agents = self.root / "agents"
        agents.mkdir()
        for name in ("", " ", "../evil", "a/b", "a\\b", ".hidden", ".", ".."):
            with self.subTest(name=name), redirect_stderr(StringIO()) as err:
                with self.assertRaises(SystemExit):
                    config.find_agent_folder(name, cfg(str(agents)))
                self.assertIn("недопустимое имя агента", err.getvalue())
        self.assertEqual(list(agents.iterdir()), [])

    def test_agents_root_has_precedence(self):
        os.chdir(self.root)
        cwd_agent = make_agent_dir(self.root, "bot")
        agents = self.root / "elsewhere"
        paths = config.find_agent_folder("bot", cfg(str(agents)))
        self.assertEqual(paths.folder, (agents / "bot").resolve())
        self.assertEqual((cwd_agent / "system-prompt.md").read_text(encoding="utf-8"), "Ты — тестовый агент.")

    def test_agent_paths_defaults_and_explicit_paths(self):
        folder = self.root / "bot"
        paths = config.AgentPaths(folder, folder / "system-prompt.md", folder / "mind-loop.json", folder / "memory.md")
        self.assertEqual(paths.messages, folder / "messages.json")
        self.assertEqual(paths.diary, folder / "diary.json")
        self.assertEqual(paths.wallet, folder / "wallet.json")
        explicit = config.AgentPaths(paths.folder, paths.system_prompt, paths.mind_loop, paths.memory, folder / "m.json", folder / "d.json")
        self.assertEqual((explicit.messages, explicit.diary), (folder / "m.json", folder / "d.json"))


if __name__ == "__main__":
    unittest.main()
