"""Тесты messages.json и read-флагов переписки."""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.helpers import PROJECT_ROOT

sys.path.insert(0, str(PROJECT_ROOT))
import storage  # noqa: E402


class MessagesTests(unittest.TestCase):
    """Переписка хранится полностью, а выдача может брать хвост."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-msgs-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "bot" / "messages.json"
        self.path.parent.mkdir()

    def _tmp_leftovers(self):
        return [p.name for p in self.tmp.rglob("*.tmp")]

    def test_load_missing_file_returns_empty_structure(self):
        data = storage.load_messages(self.path)
        self.assertEqual(data["agent"], "bot")
        self.assertEqual(data["messages"], [])
        self.assertIn("created_at", data)
        self.assertFalse(self.path.exists())

    def test_ensure_messages_file_creates_once(self):
        self.assertTrue(storage.ensure_messages_file(self.path, "bot"))
        data = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(data["messages"], [])
        self.assertEqual(data["agent"], "bot")
        self.path.write_text('{"agent": "bot", "messages": []}', encoding="utf-8")
        self.assertFalse(storage.ensure_messages_file(self.path, "bot"))
        self.assertEqual(
            self.path.read_text(encoding="utf-8"), '{"agent": "bot", "messages": []}'
        )

    def test_append_message_roundtrip(self):
        storage.append_message(self.path, storage.SENDER_CREATOR, "как дела?")
        storage.append_message(self.path, storage.SENDER_AGENT, "работаю")
        data = storage.load_messages(self.path)
        self.assertEqual(
            [(m["from"], m["text"]) for m in data["messages"]],
            [("creator", "как дела?"), ("agent", "работаю")],
        )
        self.assertTrue(all(m["timestamp"] for m in data["messages"]))

    def test_append_keeps_full_history(self):
        for i in range(25):
            storage.append_message(self.path, storage.SENDER_CREATOR, f"сообщение {i}")
        data = storage.load_messages(self.path)
        self.assertEqual(len(data["messages"]), 25)
        self.assertEqual(data["messages"][0]["text"], "сообщение 0")
        self.assertEqual(data["messages"][-1]["text"], "сообщение 24")
        self.assertEqual(self._tmp_leftovers(), [])

    def test_concurrent_appends_are_not_lost(self):
        import threading
        errors = []

        def append(index):
            try:
                storage.append_message(self.path, storage.SENDER_CREATOR, f"{index}")
            except Exception as exc:  # pragma: no cover - assertion below
                errors.append(exc)

        threads = [threading.Thread(target=append, args=(i,)) for i in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        data = storage.load_messages(self.path)
        self.assertEqual(len(data["messages"]), 20)
        self.assertEqual({m["text"] for m in data["messages"]}, {str(i) for i in range(20)})

    def test_last_messages_returns_tail(self):
        for i in range(13):
            storage.append_message(self.path, storage.SENDER_AGENT, f"текст {i}")
        tail = storage.last_messages(self.path, limit=10)
        self.assertEqual([m["text"] for m in tail], [f"текст {i}" for i in range(3, 13)])
        self.assertEqual(len(storage.last_messages(self.path, limit=50)), 13)
        self.assertEqual(storage.last_messages(self.path, limit=0), [])

    def test_append_message_validates_sender_and_text(self):
        with self.assertRaises(ValueError):
            storage.append_message(self.path, "intruder", "привет")
        with self.assertRaises(ValueError):
            storage.append_message(self.path, storage.SENDER_CREATOR, "   ")
        with self.assertRaises(ValueError):
            storage.append_message(self.path, storage.SENDER_CREATOR, 42)
        self.assertFalse(self.path.exists())

    def test_corrupt_json_backed_up_and_conversation_reset(self):
        self.path.write_text("{это не json", encoding="utf-8")
        data = storage.load_messages(self.path)
        self.assertEqual(data["messages"], [])
        backups = list(self.path.parent.glob("messages.json.corrupt-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "{это не json")

    def test_wrong_structure_backed_up_too(self):
        self.path.write_text(json.dumps({"messages": {}}), encoding="utf-8")
        data = storage.load_messages(self.path)
        self.assertEqual(data["messages"], [])
        self.assertEqual(len(list(self.path.parent.glob("*.corrupt-*"))), 1)


class MessagesReadStateTests(unittest.TestCase):
    """Сообщения создателя непрочитаны до вызова get_messages."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ai-msgread-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.path = self.tmp / "bot" / "messages.json"
        self.path.parent.mkdir()

    def test_append_message_sender_dependent_read_flag(self):
        storage.append_message(self.path, storage.SENDER_AGENT, "я написал")
        storage.append_message(self.path, storage.SENDER_CREATOR, "тебе письмо")
        data = storage.load_messages(self.path)
        self.assertEqual([m["read"] for m in data["messages"]], [True, False])

    def test_unread_creator_positions_skips_agent_and_read(self):
        storage.append_message(self.path, storage.SENDER_CREATOR, "1")
        storage.append_message(self.path, storage.SENDER_AGENT, "2")
        storage.append_message(self.path, storage.SENDER_CREATOR, "3")
        storage.mark_messages_read(self.path, storage.load_messages(self.path), [0])
        data = storage.load_messages(self.path)
        self.assertEqual(storage.unread_creator_positions(data), [2])

    def test_old_messages_without_flag_count_as_read(self):
        raw = {
            "agent": "bot",
            "messages": [
                {"timestamp": "2026-09-11T00:00:00", "from": "creator", "text": "старое"},
                {"timestamp": "2026-09-11T00:01:00", "from": "agent", "text": "ответ"},
            ],
        }
        self.path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
        data = storage.load_messages(self.path)
        self.assertTrue(all(storage.is_message_read(m) for m in data["messages"]))
        self.assertEqual(storage.unread_creator_positions(data), [])

    def test_mark_messages_read_persists_and_ignores_junk(self):
        storage.append_message(self.path, storage.SENDER_CREATOR, "1")
        storage.append_message(self.path, storage.SENDER_CREATOR, "2")
        data = storage.load_messages(self.path)
        storage.mark_messages_read(self.path, data, [0, -1, 99, "x", None])
        reread = storage.load_messages(self.path)
        self.assertEqual([m.get("read") for m in reread["messages"]], [True, False])
        self.assertEqual(storage.unread_creator_positions(reread), [1])

    def test_mark_messages_read_skips_rewrite_without_changes(self):
        storage.append_message(self.path, storage.SENDER_CREATOR, "1")
        before = self.path.read_text(encoding="utf-8")
        storage.append_message(self.path, storage.SENDER_AGENT, "я")
        data = storage.load_messages(self.path)
        frozen = self.path.read_text(encoding="utf-8")
        storage.mark_messages_read(self.path, data, [1, 777])
        self.assertEqual(self.path.read_text(encoding="utf-8"), frozen)
        self.assertNotEqual(frozen, before)


if __name__ == "__main__":
    unittest.main()
