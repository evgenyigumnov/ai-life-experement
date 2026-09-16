"""Проверки совместимости профилей моделей и DeepSeek API."""

import unittest

from model_support import (
    DEEPSEEK_FLASH_MODEL,
    DEEPSEEK_V41_FLASH_MODEL,
    GLM_53_FLASH_MODEL,
    SUPPORTED_MODELS,
    is_supported_model,
    normalize_model_name,
    normalize_reasoning_effort,
    request_options,
)


class ModelSupportTests(unittest.TestCase):
    def test_supported_model_ids(self):
        self.assertEqual(
            SUPPORTED_MODELS,
            {GLM_53_FLASH_MODEL, DEEPSEEK_V41_FLASH_MODEL, DEEPSEEK_FLASH_MODEL},
        )
        for model in (
            GLM_53_FLASH_MODEL,
            DEEPSEEK_V41_FLASH_MODEL,
            DEEPSEEK_FLASH_MODEL,
            "DeepSeek-V4.1-Flash",
        ):
            with self.subTest(model=model):
                self.assertTrue(is_supported_model(model))

    def test_glm_aliases_are_reduced_to_supported_levels(self):
        for configured, expected in (
            ("none", "low"),
            ("minimal", "low"),
            ("medium", "high"),
            ("xhigh", "max"),
            ("max", "max"),
        ):
            with self.subTest(configured=configured):
                self.assertEqual(
                    normalize_reasoning_effort(GLM_53_FLASH_MODEL, configured),
                    expected,
                )

    def test_deepinfra_deepseek_keeps_its_effort_enum(self):
        for effort in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                self.assertEqual(
                    normalize_reasoning_effort(DEEPSEEK_V41_FLASH_MODEL, effort),
                    effort,
                )

    def test_official_deepseek_api_maps_effort_and_disables_thinking(self):
        self.assertEqual(
            normalize_reasoning_effort(DEEPSEEK_FLASH_MODEL, "xhigh"), "high"
        )
        self.assertEqual(
            request_options(DEEPSEEK_FLASH_MODEL, "max"),
            {
                "reasoning_effort": "max",
                "extra_body": {"thinking": {"type": "enabled"}},
            },
        )
        self.assertEqual(
            request_options(DEEPSEEK_FLASH_MODEL, "none"),
            {"extra_body": {"thinking": {"type": "disabled"}},},
        )

    def test_v41_display_name_is_sent_as_official_api_alias(self):
        self.assertEqual(normalize_model_name("DeepSeek-V4.1-Flash"), DEEPSEEK_FLASH_MODEL)
        self.assertEqual(normalize_model_name(DEEPSEEK_V41_FLASH_MODEL), DEEPSEEK_V41_FLASH_MODEL)

    def test_unknown_models_keep_their_value(self):
        self.assertEqual(
            normalize_reasoning_effort("local/model", "high"), "high"
        )
        self.assertEqual(request_options("local/model", None), {})
        self.assertIsNone(normalize_reasoning_effort("local/model", None))


if __name__ == "__main__":
    unittest.main()
