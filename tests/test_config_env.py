"""Тесты загрузки .env и валидации Config."""

import json
import unittest

from tests.config_testkit import config_data, run_config

BASE = "OPENAI_BASE_URL=http://x/v1\nOPENAI_MODEL=m\n"


class LoadConfigTests(unittest.TestCase):
    def test_reads_required_from_env_file(self):
        data = config_data(run_config(BASE, {"OPENAI_BASE_URL": None, "OPENAI_MODEL": None}))
        self.assertEqual((data["base_url"], data["model"]), ("http://x/v1", "m"))
        self.assertIsNone(data["loop_pause"])

    def test_loop_pause_not_read_from_env(self):
        data = config_data(run_config(BASE + "LOOP_PAUSE=30\n", {"LOOP_PAUSE": None}))
        self.assertIsNone(data["loop_pause"])

    def test_api_key_dummy_when_absent(self):
        self.assertEqual(config_data(run_config(BASE, {"OPENAI_API_KEY": None}))["api_key"], "dummy")

    def test_api_key_from_env(self):
        data = config_data(run_config(BASE + "OPENAI_API_KEY=sk-real\n", {}))
        self.assertEqual(data["api_key"], "sk-real")

    def test_defaults(self):
        result = run_config(BASE, {
            "OPENAI_BASE_URL": None, "OPENAI_MODEL": None,
            "OPENAI_API_KEY": None, "LOOP_DELAY": None,
            "TEMPERATURE": None, "REASONING_EFFORT": None,
            "ENABLE_BASH_TOOL": None, "SESSION_ITERATIONS": None,
            "SLEEP_WARN_REMAINING": None,
        })
        data = config_data(result)
        self.assertEqual(data["api_key"], "dummy")
        self.assertEqual(data["loop_delay"], 1.0)
        self.assertEqual(data["temperature"], 0.7)
        self.assertFalse(data["enable_bash_tool"])
        self.assertEqual(data["session_iterations"], 30)
        self.assertEqual(data["sleep_warn_remaining"], 10)

    def test_required_and_optional_values(self):
        data = config_data(run_config(BASE + "OPENAI_API_KEY=sk\nLOOP_DELAY=0.5\n", {}))
        self.assertEqual((data["base_url"], data["model"], data["api_key"]), ("http://x/v1", "m", "sk"))
        self.assertEqual(data["loop_delay"], 0.5)
        self.assertIsNone(data["loop_pause"])

    def test_environment_wins_over_dotenv(self):
        data = config_data(run_config(
            BASE + "AGENTS_ROOT=from-file\nSESSION_ITERATIONS=12\n",
            {"OPENAI_BASE_URL": "http://env/v1", "OPENAI_MODEL": "env-model", "SESSION_ITERATIONS": "17"},
        ))
        self.assertEqual(data["base_url"], "http://env/v1")
        self.assertEqual(data["model"], "env-model")
        self.assertEqual(data["agents_root"], "from-file")
        self.assertEqual(data["session_iterations"], 17)

    def test_environment_overrides_env_file_for_required_values(self):
        data = config_data(run_config(BASE + "AGENTS_ROOT=from-file\n", {
            "OPENAI_BASE_URL": "http://env/v1", "OPENAI_MODEL": "env-model"
        }))
        self.assertEqual(data["base_url"], "http://env/v1")
        self.assertEqual(data["model"], "env-model")
        self.assertEqual(data["agents_root"], "from-file")

    def test_loop_delay_valid(self):
        self.assertEqual(config_data(run_config(BASE, {"LOOP_DELAY": "0.5"}))["loop_delay"], 0.5)

    def test_loop_delay_invalid_is_fatal(self):
        result = run_config(BASE, {"LOOP_DELAY": "abc"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("LOOP_DELAY", result.stderr)

    def test_temperature_default_when_absent(self):
        self.assertEqual(config_data(run_config(BASE, {"TEMPERATURE": None}))["temperature"], 0.7)

    def test_temperature_from_env_file(self):
        self.assertEqual(config_data(run_config(BASE + "TEMPERATURE=0.85\n", {}))["temperature"], 0.85)

    def test_temperature_env_overrides_env_file(self):
        data = config_data(run_config(BASE + "TEMPERATURE=0.9\n", {"TEMPERATURE": "0.2"}))
        self.assertEqual(data["temperature"], 0.2)

    def test_temperature_out_of_range_is_fatal(self):
        for value in ("-0.1", "2.5"):
            with self.subTest(value=value):
                result = run_config(BASE, {"TEMPERATURE": value})
                self.assertEqual(result.returncode, 1)
                self.assertIn("TEMPERATURE", result.stderr)

    def test_reasoning_effort_default_when_absent(self):
        self.assertIsNone(config_data(run_config(BASE, {"REASONING_EFFORT": None}))["reasoning_effort"])

    def test_reasoning_effort_max_from_env_file(self):
        data = config_data(run_config(BASE + "REASONING_EFFORT=max\n", {}))
        self.assertEqual(data["reasoning_effort"], "max")

    def test_reasoning_effort_env_overrides_env_file(self):
        data = config_data(run_config(BASE + "REASONING_EFFORT=max\n", {"REASONING_EFFORT": "high"}))
        self.assertEqual(data["reasoning_effort"], "high")

    def test_reasoning_effort_normalized_to_lower(self):
        for raw, expected in (("MAX", "max"), ("High", "high")):
            with self.subTest(raw=raw):
                self.assertEqual(config_data(run_config(BASE, {"REASONING_EFFORT": raw}))["reasoning_effort"], expected)

    def test_reasoning_effort_full_scale_accepted(self):
        for value in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
            with self.subTest(value=value):
                self.assertEqual(config_data(run_config(BASE, {"REASONING_EFFORT": value}))["reasoning_effort"], value)

    def test_reasoning_effort_invalid_is_fatal(self):
        for value in ("ultra", "maximum", "0"):
            with self.subTest(value=value):
                result = run_config(BASE, {"REASONING_EFFORT": value})
                self.assertEqual(result.returncode, 1)
                self.assertIn("REASONING_EFFORT", result.stderr)

    def test_enable_bash_tool_default_off(self):
        self.assertFalse(config_data(run_config(BASE, {"ENABLE_BASH_TOOL": None}))["enable_bash_tool"])

    def test_enable_bash_tool_env_overrides_env_file(self):
        data = config_data(run_config(BASE + "ENABLE_BASH_TOOL=1\n", {"ENABLE_BASH_TOOL": "0"}))
        self.assertFalse(data["enable_bash_tool"])

    def test_parse_bool_env_helper(self):
        from config_env import parse_bool_env

        self.assertIsNone(parse_bool_env(None))
        self.assertIsNone(parse_bool_env("maybe"))
        self.assertTrue(parse_bool_env(" 1 "))
        self.assertTrue(parse_bool_env("True"))
        self.assertFalse(parse_bool_env("0"))
        self.assertFalse(parse_bool_env(""))

    def test_missing_required_value_is_fatal(self):
        for env_values, expected in (
            ({"OPENAI_BASE_URL": None, "OPENAI_MODEL": "m"}, "OPENAI_BASE_URL"),
            ({"OPENAI_BASE_URL": "http://x/v1", "OPENAI_MODEL": None}, "OPENAI_MODEL"),
        ):
            with self.subTest(name=expected):
                result = run_config(None, env_values)
                self.assertEqual(result.returncode, 1)
                self.assertIn(expected, result.stderr)

    def test_loop_and_temperature_validation(self):
        valid = config_data(run_config(BASE + "TEMPERATURE=0\n", {"LOOP_DELAY": "1.5"}))
        self.assertEqual(valid["temperature"], 0.0)
        self.assertEqual(valid["loop_delay"], 1.5)
        for name, value in (("LOOP_DELAY", "abc"), ("TEMPERATURE", "hot"), ("TEMPERATURE", "2.1")):
            with self.subTest(name=name, value=value):
                result = run_config(BASE, {name: value})
                self.assertEqual(result.returncode, 1)
                self.assertIn(name, result.stderr)

    def test_reasoning_effort(self):
        for value in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
            with self.subTest(value=value):
                data = config_data(run_config(BASE, {"REASONING_EFFORT": value}))
                self.assertEqual(data["reasoning_effort"], value)
        result = run_config(BASE, {"REASONING_EFFORT": "ultra"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("REASONING_EFFORT", result.stderr)

    def test_bash_flag_values(self):
        for raw, expected in (("1", True), ("true", True), ("yes", True), ("0", False), ("off", False)):
            with self.subTest(raw=raw):
                data = config_data(run_config(BASE, {"ENABLE_BASH_TOOL": raw}))
                self.assertEqual(data["enable_bash_tool"], expected)
        result = run_config(BASE, {"ENABLE_BASH_TOOL": "maybe"})
        self.assertEqual(result.returncode, 1)
        self.assertIn("ENABLE_BASH_TOOL", result.stderr)

    def test_session_values_from_file_and_environment(self):
        data = config_data(run_config(BASE + "SESSION_ITERATIONS=80\nSLEEP_WARN_REMAINING=7\n", {}))
        self.assertEqual((data["session_iterations"], data["sleep_warn_remaining"]), (80, 7))
        data = config_data(run_config(BASE + "SESSION_ITERATIONS=80\nSLEEP_WARN_REMAINING=7\n", {
            "SESSION_ITERATIONS": "12", "SLEEP_WARN_REMAINING": "3"
        }))
        self.assertEqual((data["session_iterations"], data["sleep_warn_remaining"]), (12, 3))

    def test_session_invalid_values_are_fatal(self):
        cases = (
            ("SESSION_ITERATIONS", "abc"),
            ("SESSION_ITERATIONS", "0"),
            ("SESSION_ITERATIONS", "-1"),
            ("SESSION_ITERATIONS", "10001"),
            ("SLEEP_WARN_REMAINING", "abc"),
            ("SLEEP_WARN_REMAINING", "-1"),
            ("SLEEP_WARN_REMAINING", "30"),
        )
        for name, value in cases:
            with self.subTest(name=name, value=value):
                result = run_config(BASE, {name: value})
                self.assertEqual(result.returncode, 1)
                self.assertIn(name, result.stderr)


if __name__ == "__main__":
    unittest.main()
