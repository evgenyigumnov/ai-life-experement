"""Проверки совместимости профилей моделей DeepInfra."""

import unittest

from model_support import (
    DEEPSEEK_V41_FLASH_MODEL,
    GLM_53_FLASH_MODEL,
    SUPPORTED_MODELS,
    is_supported_model,
    normalize_reasoning_effort,
)


class ModelSupportTests(unittest.TestCase):
    def test_both_requested_models_are_known(self):
        self.assertEqual(
            SUPPORTED_MODELS,
            {GLM_53_FLASH_MODEL, DEEPSEEK_V41_FLASH_MODEL},
        )
        self.assertTrue(is_supported_model(GLM_53_FLASH_MODEL))
        self.assertTrue(is_supported_model(DEEPSEEK_V41_FLASH_MODEL))

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

    def test_deepseek_keeps_deepinfra_effort_enum(self):
        for effort in ("none", "minimal", "low", "medium", "high", "xhigh", "max"):
            with self.subTest(effort=effort):
                self.assertEqual(
                    normalize_reasoning_effort(DEEPSEEK_V41_FLASH_MODEL, effort),
                    effort,
                )

    def test_unknown_models_keep_their_value(self):
        self.assertEqual(
            normalize_reasoning_effort("local/model", "high"), "high"
        )
        self.assertIsNone(normalize_reasoning_effort("local/model", None))


if __name__ == "__main__":
    unittest.main()
