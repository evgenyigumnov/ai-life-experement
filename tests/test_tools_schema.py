"""Схемы tools, аргументы, неизвестные/удалённые инструменты."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sandbox_docker  # noqa: E402
import tool_registry as tools  # noqa: E402
import tools_sandbox  # noqa: E402
from tests.helpers import env  # noqa: E402
from tests.tools_testkit import _paths  # noqa: E402

class DashboardToolsTests(unittest.TestCase):
    """Удалённые tools дашборда теперь неизвестны."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-dashtool-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.paths = _paths(self.tmp / "memory.md")

    def test_removed_dashboard_tools_are_unknown(self):
        for name in (
            "dashboard",
            "add_journal_entry",
            "get_journal",
            "garden_plant",
            "garden_update",
            "garden_list",
        ):
            self.assertEqual(
                tools.execute_tool(name, "{}", self.paths),
                f"Error: unknown tool: {name}",
                name,
            )

    def test_no_activity_log_written_on_tool_call(self):
        tools.execute_tool("set_memory", json.dumps({"content": "тест"}), self.paths)
        self.assertFalse((self.paths.folder / "activity.log").exists())


class ArgumentsAndSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-sch-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self.paths = _paths(self.tmp / "memory.md")

    def test_unknown_tool(self):
        self.assertEqual(
            tools.execute_tool("no_such_tool", "{}", self.paths),
            "Error: unknown tool: no_such_tool",
        )
        self.assertEqual(
            tools.execute_tool("diary_history", "{}", self.paths),
            "Error: unknown tool: diary_history",
        )

    def test_invalid_json_arguments(self):
        out = tools.execute_tool("run_bash", "{не json}", self.paths)
        self.assertTrue(out.startswith("Error: invalid arguments"))

    def test_non_object_arguments(self):
        out = tools.execute_tool("run_bash", "[1, 2]", self.paths)
        self.assertTrue(out.startswith("Error: invalid arguments"))

    def test_missing_or_empty_command(self):
        # валидация аргументов — до запуска песочницы, поэтому включаем run_bash
        with env(ENABLE_BASH_TOOL="1"):
            for args in ('{}', '{"command": ""}', '{"command": "   "}'):
                out = tools.execute_tool("run_bash", args, self.paths)
                self.assertTrue(out.startswith("Error: invalid arguments"), args)

    def test_dict_arguments_accepted(self):
        out = tools.execute_tool("get_memory", {}, self.paths)
        self.assertEqual(out, "(память пуста)")

    def test_truncate_helper(self):
        self.assertEqual(tools_sandbox.truncate("коротко"), "коротко")
        long = "a" * (tools_sandbox.MAX_OUTPUT_CHARS + 137)
        cut = tools_sandbox.truncate(long)
        self.assertTrue(cut.startswith("a" * tools_sandbox.MAX_OUTPUT_CHARS))
        self.assertIn("...output truncated (137 chars)...", cut)

    def test_schema_structure(self):
        self.assertEqual(len(tools.TOOLS_SCHEMA), 21)
        names = [t["function"]["name"] for t in tools.TOOLS_SCHEMA]
        self.assertEqual(
            names,
            [
                "run_bash",
                "read_file",
                "write",
                "edit",
                "grep",
                "find",
                "ls",
                "send_message",
                "get_messages",
                "get_memory",
                "set_memory",
                "sleep",
                "diary_remember",
                "diary_recall",
                "diary_edit",
                "diary_tags",
                "internet_search",
                "web_fetch",
                "inspect_image",
                "money_balance",
                "money_spend",
            ],
        )
        for tool in tools.TOOLS_SCHEMA:
            self.assertEqual(tool["type"], "function")
            params = tool["function"]["parameters"]
            self.assertEqual(params["type"], "object")
            self.assertTrue(set(params.get("required", [])) <= set(params["properties"]))
        get_messages = next(
            tool for tool in tools.TOOLS_SCHEMA
            if tool["function"]["name"] == "get_messages"
        )
        self.assertNotIn("force", get_messages["function"]["parameters"]["properties"])

    def test_file_tools_are_loaded_from_tools_catalog(self):
        from tools import discover_tools

        discovered = [definition["function"]["name"] for definition, _ in discover_tools()]
        self.assertEqual(discovered, ["write", "edit", "grep", "find", "ls"])
        for name in discovered:
            self.assertIn(name, tools._HANDLERS)

    def test_build_tools_schema_full_and_filtered(self):
        # полный список — с песочницей; выключенный — без обоих её инструментов
        with env(BRAVE_KEY="test-brave-key"):
            full = tools.build_tools_schema(True)
            self.assertEqual(
                [t["function"]["name"] for t in full],
                [t["function"]["name"] for t in tools.TOOLS_SCHEMA],
            )
            filtered = tools.build_tools_schema(False)
            self.assertEqual(
                [t["function"]["name"] for t in filtered],
                [
                    t["function"]["name"]
                    for t in tools.TOOLS_SCHEMA
                    if t["function"]["name"] not in tools.SANDBOX_TOOLS
                ],
            )
            self.assertNotIn("read_file", [t["function"]["name"] for t in filtered])

    def test_search_schema_requires_configuration(self):
        with env(BRAVE_KEY="test-brave-key"):
            names = [t["function"]["name"] for t in tools.build_tools_schema(False)]
            self.assertIn("internet_search", names)
        with env(BRAVE_KEY=None):
            names = [t["function"]["name"] for t in tools.build_tools_schema(False)]
            self.assertNotIn("internet_search", names)
            self.assertIn("web_fetch", names)
            self.assertIn("inspect_image", names)

    def test_run_bash_schema_short_description_and_timeout(self):
        function = tools.TOOLS_SCHEMA[0]["function"]
        self.assertEqual(
            function["description"],
            "Выполнить команду в изолированной среде и вернуть результат.",
        )
        self.assertIn("timeout", function["parameters"]["properties"])
        self.assertEqual(function["parameters"]["required"], ["command"])
        self.assertEqual(
            function["parameters"]["properties"]["timeout"]["type"], "number"
        )

    def test_schema_descriptions_short_without_infra_details(self):
        """Описания схем короткие и без деталей инфраструктуры (шаг 4 плана)."""
        infra_words = ("docker", "alpine", "busybox", "apk", "сеть", "хоста")
        for tool in tools.TOOLS_SCHEMA:
            function = tool["function"]
            descriptions = [function["description"]]
            descriptions.extend(
                prop.get("description", "")
                for prop in function["parameters"]["properties"].values()
            )
            for text in descriptions:
                for word in infra_words:
                    self.assertNotIn(word.lower(), text.lower())
                if function["name"] not in {"money_balance", "money_spend"}:
                    self.assertLessEqual(len(text), 120)

    def test_memory_schema_descriptions(self):
        descriptions = {
            t["function"]["name"]: t["function"]["description"]
            for t in tools.TOOLS_SCHEMA
        }
        self.assertEqual(descriptions["get_memory"], "Прочитать текущую память")
        self.assertEqual(
            descriptions["set_memory"], "Заменить память полным новым текстом"
        )
        self.assertEqual(
            descriptions["sleep"],
            "Добровольно завершить текущую сессию и начать новую",
        )
        self.assertEqual(descriptions["send_message"], "Отправить сообщение создателю")
        self.assertEqual(
            descriptions["get_messages"],
            "Показать страницу переписки; непрочитанные помечаются "
            "прочитанными с отметкой «стало прочитанным»",
        )
        sleep = next(
            tool for tool in tools.TOOLS_SCHEMA
            if tool["function"]["name"] == "sleep"
        )
        self.assertEqual(
            sleep["function"]["parameters"]["required"], ["reason"]
        )
        self.assertIn("1 единица = 1 следующий цикл/тик LLM без паузы перед ним", descriptions["money_balance"])
        self.assertIn("1 единица покупает 1 следующий цикл без паузы", descriptions["money_spend"])

    def test_schema_serializable(self):
        json.dumps(tools.TOOLS_SCHEMA)

    def test_constants(self):
        self.assertEqual(sandbox_docker.DOCKER_BIN, "docker")
        self.assertEqual(tools_sandbox.DEFAULT_BASH_TIMEOUT, 5)
        self.assertEqual(tools_sandbox.MAX_BASH_TIMEOUT, 300)
        self.assertEqual(sandbox_docker.DEFAULT_DOCKER_IMAGE, "ai-life-sandbox:latest")


if __name__ == "__main__":
    unittest.main()
