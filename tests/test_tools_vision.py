"""Unit-тесты inspect_image: валидация, payload и безопасный ответ."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tool_registry as tools  # noqa: E402
import tools_vision  # noqa: E402
from agent_paths import AgentPaths  # noqa: E402
from tool_context import ToolContext  # noqa: E402


DATA_URL = "data:image/jpeg;base64,QUJD"


def _paths(root: Path) -> AgentPaths:
    return AgentPaths(
        folder=root,
        system_prompt=root / "system-prompt.md",
        mind_loop=root / "mind-loop.json",
        memory=root / "memory.md",
        name="vision-unit-agent",
    )


class VisionToolTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="ai-vision-tool-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.paths = _paths(self.root)
        self.context = ToolContext("shared", "vision-model", 0.83, "max")

    def call(self, args, paths=None, context=None):
        return tools.execute_tool("inspect_image", args, paths, context)

    def test_schema_is_registered_and_not_bash_gated(self):
        names = [tool["function"]["name"] for tool in tools.build_tools_schema(False)]
        self.assertIn("inspect_image", names)
        self.assertIs(tools._HANDLERS["inspect_image"], tools_vision.handle_inspect_image)

    def test_schema_has_exact_arguments(self):
        function = tools_vision.INSPECT_IMAGE_TOOL["function"]
        self.assertEqual(function["name"], "inspect_image")
        parameters = function["parameters"]
        self.assertEqual(set(parameters["properties"]), {"source", "question"})
        self.assertEqual(parameters["required"], ["source", "question"])
        self.assertNotIn("docker", json.dumps(function, ensure_ascii=False).lower())
        json.dumps(tools_vision.INSPECT_IMAGE_TOOL)

    def test_invalid_arguments_are_rejected_before_io(self):
        invalid = [
            {}, {"source": "https://example.org/a.jpg"},
            {"question": "что?"}, {"source": 42, "question": "что?"},
            {"source": "", "question": "что?"},
            {"source": "https://example.org/a.jpg", "question": "   "},
            {"source": "relative.jpg", "question": "что?"},
            {"source": "file:///tmp/a.jpg", "question": "что?"},
            {"source": "data:image/jpeg;base64,AAAA", "question": "что?"},
            {"source": "ftp://example.org/a.jpg", "question": "что?"},
            {"source": "https://", "question": "что?"},
            {"source": "https://example.org/a.jpg", "question": "x" * 8001},
            {"source": "/root/a.jpg", "question": "что?", "extra": 1},
        ]
        with mock.patch.object(tools_vision, "load_source") as load, \
             mock.patch.object(tools_vision, "call_llm") as call:
            for args in invalid:
                with self.subTest(args=args):
                    result = self.call(args, self.paths, self.context)
                    self.assertTrue(result.startswith("Error: invalid arguments"), result)
        load.assert_not_called()
        call.assert_not_called()

    def test_url_does_not_require_paths_or_context_for_validation(self):
        result = self.call(
            {"source": "https://example.org/a.jpg", "question": "что?"},
            None,
        )
        self.assertEqual(result, "Error: vision: отсутствует контекст вложенного LLM-вызова")

    def test_url_payload_uses_one_nested_call(self):
        args = {"source": " https://example.org/a.jpg?token=secret ", "question": " Что здесь? "}
        snapshot = copy.deepcopy(args)
        with mock.patch.object(tools_vision, "load_source", return_value=b"raw"), \
             mock.patch.object(tools_vision, "to_data_url", return_value=DATA_URL), \
             mock.patch.object(
                 tools_vision, "call_llm", return_value={"content": "красный", "reasoning": "secret"}
             ) as call:
            result = self.call(args, None, self.context)

        self.assertEqual(result, "красный")
        self.assertEqual(args, snapshot)
        call.assert_called_once()
        client, model, messages = call.call_args.args[:3]
        self.assertIs(client, self.context.client)
        self.assertEqual(model, self.context.model)
        self.assertEqual(messages[0]["role"], "user")
        content = messages[0]["content"]
        self.assertEqual([part["type"] for part in content], ["image_url", "text"])
        self.assertEqual(content[0]["image_url"]["url"], DATA_URL)
        self.assertEqual(content[1]["text"], "Что здесь?")
        self.assertIsNone(call.call_args.kwargs["tools"])
        self.assertEqual(call.call_args.kwargs["temperature"], 0.83)
        self.assertEqual(call.call_args.kwargs["reasoning_effort"], "max")
        self.assertNotIn(DATA_URL, result)
        self.assertNotIn("secret", result)

    def test_absolute_path_uses_supplied_paths(self):
        with mock.patch.object(tools_vision, "load_source", return_value=b"raw") as load, \
             mock.patch.object(tools_vision, "to_data_url", return_value=DATA_URL), \
             mock.patch.object(tools_vision, "call_llm", return_value=SimpleNamespace(content="ответ")):
            result = self.call(
                {"source": "/root/assets/photo.webp", "question": "цвет?"},
                self.paths, self.context,
            )
        self.assertEqual(result, "ответ")
        load.assert_called_once_with("/root/assets/photo.webp", self.paths)

    def test_absolute_path_without_paths_fails_before_loader(self):
        with mock.patch.object(tools_vision, "load_source") as load:
            result = self.call(
                {"source": "/root/photo.jpg", "question": "что?"},
                None, self.context,
            )
        self.assertTrue(result.startswith("Error: invalid arguments"))
        load.assert_not_called()

    def test_dict_and_sdk_answers_are_strings(self):
        for response in ({"content": "dict answer"}, SimpleNamespace(content="sdk answer")):
            with self.subTest(response=response), \
                 mock.patch.object(tools_vision, "load_source", return_value=b"raw"), \
                 mock.patch.object(tools_vision, "to_data_url", return_value=DATA_URL), \
                 mock.patch.object(tools_vision, "call_llm", return_value=response):
                result = self.call(
                    {"source": "https://example.org/a", "question": "что?"},
                    None, self.context,
                )
            self.assertIsInstance(result, str)
            self.assertNotIn("reasoning", result)

    def test_errors_are_standard_and_keyboard_interrupt_propagates(self):
        args = {"source": "https://example.org/a", "question": "что?"}
        for target, error in (
            ("load_source", ValueError("download failed")),
            ("to_data_url", ValueError("bad image")),
            ("call_llm", RuntimeError("api failed")),
        ):
            with self.subTest(target=target), mock.patch.object(
                tools_vision, target, side_effect=error
            ):
                result = self.call(args, None, self.context)
            self.assertTrue(result.startswith("Error: vision:"), result)
            self.assertNotIn("data:image", result)

        with mock.patch.object(tools_vision, "load_source", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.call(args, None, self.context)


class VisibleAnswerTests(unittest.TestCase):
    def test_reasoning_fields_and_think_blocks_are_not_visible(self):
        cases = [
            ({"content": "<think>secret</think>answer", "reasoning_content": "x"}, "answer"),
            ({"content": "before<think>secret</think>after", "reasoning": "x"}, "beforeafter"),
            ({"content": "<think>one</think><think>two</think>yes"}, "yes"),
            ({"content": "secret</think>answer"}, "answer"),
            ({"content": "answer data:image/jpeg;base64,QUJD"}, "answer"),
        ]
        for response, expected in cases:
            with self.subTest(response=response):
                self.assertEqual(tools_vision.extract_visible_answer(response), expected)

    def test_empty_reasoning_and_unclosed_think_are_errors(self):
        for content in (None, "", "  ", "<think>only reasoning</think>", "<think>unfinished"):
            with self.subTest(content=content):
                with self.assertRaises(tools_vision.VisionAnswerError):
                    tools_vision.extract_visible_answer({"content": content})

    def test_api_error_data_url_is_redacted(self):
        error = RuntimeError("bad data:image/jpeg;base64,QUJDREVGRw== payload")
        self.assertNotIn("QUJD", tools_vision.safe_error(error))


if __name__ == "__main__":
    unittest.main()
