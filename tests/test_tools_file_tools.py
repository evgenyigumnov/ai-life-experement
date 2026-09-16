"""Интеграционные проверки write/edit/grep/find/ls в песочнице."""

import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sandbox_docker  # noqa: E402
import tool_registry  # noqa: E402
from tests.tools_testkit import _paths, bash_tool_on  # noqa: E402


class FileToolsTests(unittest.TestCase):
    container = "ai-file-tools-test"

    @classmethod
    def setUpClass(cls):
        context = bash_tool_on()
        context.__enter__()
        cls.addClassCleanup(context.__exit__, None, None, None)
        cls.tmp = Path(tempfile.mkdtemp(prefix="ai-file-tools-"))
        cls.paths = _paths(cls.tmp / "memory.md", name=cls.container)
        sandbox_docker.ensure_docker_container(cls.container)
        cls.root = "/root/file-tools-check"

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        subprocess.run([sandbox_docker.DOCKER_BIN, "rm", "-f", cls.container], capture_output=True)

    def call(self, name, **args):
        return tool_registry.execute_tool(name, json.dumps(args), self.paths)

    def test_write_and_edit_return_structured_results(self):
        written = json.loads(self.call(
            "write", path=f"{self.root}/nested/a.txt", content="alpha\nβeta\n"
        ))
        self.assertEqual(written, {
            "ok": True, "path": f"{self.root}/nested/a.txt",
            "bytes": len("alpha\nβeta\n".encode("utf-8")),
        })
        edited = json.loads(self.call(
            "edit", path=f"{self.root}/nested/a.txt", old="βeta", new="BETA"
        ))
        self.assertEqual(edited, {"ok": True, "replacements": 1})
        self.assertIn("BETA", self.call("run_bash", command=f"cat {self.root}/nested/a.txt"))

    def test_edit_rejects_zero_and_duplicate_matches(self):
        self.call("write", path=f"{self.root}/duplicates.txt", content="same\nsame\n")
        duplicate = self.call("edit", path=f"{self.root}/duplicates.txt", old="same", new="x")
        missing = self.call("edit", path=f"{self.root}/duplicates.txt", old="absent", new="x")
        self.assertIn("found 2 occurrences", duplicate)
        self.assertIn("found 0 occurrences", missing)
        self.assertIn("same\nsame", self.call("run_bash", command=f"cat {self.root}/duplicates.txt"))

    def test_parallel_edits_preserve_both_changes(self):
        path = f"{self.root}/parallel.txt"
        self.call("write", path=path, content="alpha\nbeta\n")
        calls = [("alpha", "ALPHA"), ("beta", "BETA")]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(
                lambda pair: self.call("edit", path=path, old=pair[0], new=pair[1]),
                calls,
            ))
        self.assertEqual([json.loads(result)["replacements"] for result in results], [1, 1])
        content = self.call("run_bash", command=f"cat {path}")
        self.assertIn("ALPHA", content)
        self.assertIn("BETA", content)

    def test_grep_include_and_line_limit(self):
        long_line = "needle" + "x" * 700
        self.call("write", path=f"{self.root}/match.py", content=long_line + "\nother\n")
        self.call("write", path=f"{self.root}/skip.txt", content="needle in text\n")
        result = json.loads(self.call(
            "grep", pattern="needle", path=self.root, include="*.py"
        ))
        self.assertTrue(result["ok"])
        self.assertIn("match.py:1:", result["matches"])
        self.assertNotIn("skip.txt", result["matches"])
        self.assertLessEqual(len(result["matches"].split(": ", 1)[1]), 500)
        self.assertIsNone(result["truncatedBy"])

    def test_find_and_ls_return_paths_and_entries(self):
        self.call("write", path=f"{self.root}/nested/seed.txt", content="seed")
        self.call("write", path=f"{self.root}/one.py", content="one")
        files = json.loads(self.call("find", pattern="*.py", path=self.root))
        listing = json.loads(self.call("ls", path=self.root))
        self.assertIn("one.py", files["files"])
        self.assertIn("nested/", listing["entries"])
        self.assertIn("one.py", listing["entries"])
        self.assertEqual(files["truncatedBy"], None)
        self.assertEqual(listing["truncatedBy"], None)

    def test_missing_and_invalid_arguments_are_safe(self):
        self.assertIn("file not found", self.call("find", pattern="*", path="/no/such/path"))
        self.assertIn("invalid arguments", self.call("write", path="", content="x"))
        self.assertIn("invalid pattern", self.call("grep", pattern="[", path=self.root))


if __name__ == "__main__":
    unittest.main()
