"""Тесты agent.build_messages: воспроизведение истории итераций."""


import json
import shutil
import tempfile
import unittest

from tests.agent_common import (
    agent, make_agent_dir, _paths, _text_iter, _tool_iter,
)


class BuildMessagesTests(unittest.TestCase):
    def setUp(self):
        self.folder = make_agent_dir(tempfile.mkdtemp(prefix="ai-agent-"))
        self.addCleanup(shutil.rmtree, self.folder.parent, ignore_errors=True)
        self.paths = _paths(self.folder)

    def test_empty_history_is_system_plus_user(self):
        messages = agent.build_messages({"iterations": []}, self.paths)
        self.assertEqual([m["role"] for m in messages], ["system", "user"])
        self.assertEqual(messages[0]["content"], "Ты — тестовый агент.")
        self.assertNotIn("Сейчас нет новых сообщений от создателя", messages[1]["content"])
        self.assertTrue(messages[1]["content"].endswith(agent.USER_MESSAGE))

    def test_text_iteration_replayed(self):
        messages = agent.build_messages(
            {"iterations": [_text_iter("шаг один")]}, self.paths
        )
        self.assertEqual([m["role"] for m in messages], ["system", "assistant", "user"])
        self.assertEqual(messages[1]["content"], "шаг один")

    def test_tool_iteration_replayed_with_result_by_id(self):
        messages = agent.build_messages(
            {"iterations": [_tool_iter(call_id="call_7", result="вывод команды")]}, self.paths
        )
        self.assertEqual([m["role"] for m in messages], ["system", "assistant", "tool", "user"])
        tool_call = messages[1]["tool_calls"][0]
        self.assertEqual(tool_call["id"], "call_7")
        self.assertEqual(messages[2], {"role": "tool", "tool_call_id": "call_7",
                                       "content": "вывод команды"})

    def test_results_matched_by_order_when_no_ids(self):
        record = _tool_iter(n=1)
        for tc in record["assistant_message"]["tool_calls"]:
            tc.pop("id")
        record["assistant_message"]["tool_calls"].append(dict(record["assistant_message"]["tool_calls"][0]))
        record["tool_results"] = [
            {"tool": "run_bash", "arguments": "", "result": "первый"},
            {"tool": "run_bash", "arguments": "", "result": "второй"},
        ]
        messages = agent.build_messages({"iterations": [record]}, self.paths)
        tool_messages = [m for m in messages if m["role"] == "tool"]
        self.assertEqual([m["content"] for m in tool_messages], ["первый", "второй"])

    def test_missing_result_replaced_by_error_text(self):
        record = _tool_iter(n=1)
        record["tool_results"] = []  # результат пропал
        messages = agent.build_messages({"iterations": [record]}, self.paths)
        tool_message = next(m for m in messages if m["role"] == "tool")
        self.assertIn("Error", tool_message["content"])

    def test_error_iteration_replayed_as_note(self):
        messages = agent.build_messages(
            {"iterations": [{"n": 1, "user": "x", "error": "RuntimeError: что-то сломалось"}]},
            self.paths,
        )
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertIn("[сбой итерации: RuntimeError: что-то сломалось]", messages[1]["content"])

    def test_raw_sdk_dict_normalized(self):
        record = {
            "n": 1,
            "assistant_message": {
                "role": "assistant", "content": "текст", "tool_calls": None,
                "refusal": None, "function_call": None,
            },
            "tool_results": [],
        }
        messages = agent.build_messages({"iterations": [record]}, self.paths)
        self.assertEqual(set(messages[1]), {"role", "content"})
        self.assertEqual(messages[1]["content"], "текст")

    def test_dict_arguments_stringified_back(self):
        record = _tool_iter(n=1)
        record["assistant_message"]["tool_calls"][0]["function"]["arguments"] = {"command": "ls"}
        messages = agent.build_messages({"iterations": [record]}, self.paths)
        self.assertEqual(
            messages[1]["tool_calls"][0]["function"]["arguments"], '{"command": "ls"}'
        )

    def test_broken_records_skipped(self):
        data = {"iterations": ["просто строка", None, {}, _text_iter("валидная")]}
        messages = agent.build_messages(data, self.paths)
        assistant = [m for m in messages if m["role"] == "assistant"]
        self.assertEqual([m["content"] for m in assistant], ["валидная"])

    def test_empty_string_content_record_skipped(self):
        # историческая итерация с content="" (только reasoning) не воспроизводится
        record = {
            "n": 1,
            "assistant_message": {"role": "assistant", "content": ""},
            "tool_results": [],
        }
        messages = agent.build_messages({"iterations": [record, _text_iter("дело")]}, self.paths)
        assistant = [m for m in messages if m["role"] == "assistant"]
        self.assertEqual([m["content"] for m in assistant], ["дело"])

    def test_whitespace_only_content_normalized_to_none(self):
        self.assertIsNone(
            agent._normalize_assistant_message({"role": "assistant", "content": "   \n"})
        )
        self.assertIsNone(
            agent._normalize_assistant_message({"role": "assistant", "content": ""})
        )
        # но пробельный текст при наличии tool_calls не мешает вызовам
        normalized = agent._normalize_assistant_message(
            {"role": "assistant", "content": "  ", "tool_calls": _tool_iter()["assistant_message"]["tool_calls"]}
        )
        self.assertIsNone(normalized["content"])
        self.assertEqual(len(normalized["tool_calls"]), 1)

    def test_full_session_history_included_without_trimming(self):
        # история не урезается: сессия ограничена сном (SESSION_ITERATIONS),
        # после которого контекст LLM начинается заново, — в запрос попадает
        # вся текущая история без заметки «укорочена»
        iterations = [_text_iter(f"шаг {i}", n=i)
                      for i in range(1, agent.SESSION_ITERATIONS + 1)]
        messages = agent.build_messages({"iterations": iterations}, self.paths)
        assistant = [m for m in messages if m["role"] == "assistant"]
        self.assertEqual(len(assistant), agent.SESSION_ITERATIONS)
        self.assertEqual(assistant[0]["content"], "шаг 1")  # ничего не отброшено
        self.assertEqual(assistant[-1]["content"],
                         f"шаг {agent.SESSION_ITERATIONS}")
        self.assertNotIn("укорочена", json.dumps(messages, ensure_ascii=False))

    def test_system_prompt_reread_from_disk(self):
        data = {"iterations": []}
        self.assertEqual(agent.build_messages(data, self.paths)[0]["content"],
                         "Ты — тестовый агент.")
        (self.folder / "system-prompt.md").write_text("Новый промпт.", encoding="utf-8")
        self.assertEqual(agent.build_messages(data, self.paths)[0]["content"],
                         "Новый промпт.")

    def test_messages_json_serializable(self):
        data = {"iterations": [_text_iter("а"), _tool_iter()]}
        messages = agent.build_messages(data, self.paths)
        json.dumps(messages, ensure_ascii=False)  # не должно падать

if __name__ == "__main__":
    unittest.main()
