"""Небольшие адаптеры различий поддерживаемых моделей DeepInfra."""

GLM_53_FLASH_MODEL = "zai-org/GLM-5.3-Flash"
DEEPSEEK_V41_FLASH_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"
SUPPORTED_MODELS = frozenset({GLM_53_FLASH_MODEL, DEEPSEEK_V41_FLASH_MODEL})
_MODEL_KEYS = frozenset(model.casefold() for model in SUPPORTED_MODELS)

# GLM-5.3-Flash принимает только low/high/max. DeepInfra принимает общий
# reasoning_effort, поэтому приводим общие алиасы к значениям GLM до отправки.
_GLM_REASONING_ALIASES = {
    "none": "low",
    "minimal": "low",
    "medium": "high",
    "xhigh": "max",
}


def _model_key(model: str) -> str:
    return model.strip().casefold()


def is_supported_model(model: str) -> bool:
    """Известна ли модель в этом проекте как основная модель DeepInfra."""
    return _model_key(model) in _MODEL_KEYS


def normalize_reasoning_effort(model: str, effort: str | None) -> str | None:
    """Подготовить reasoning_effort к API конкретной модели.

    DeepSeek-V4.1-Flash использует полный enum DeepInfra без преобразований.
    Для GLM-5.3-Flash недоступные уровни заменяются ближайшими поддержанными,
    чтобы переключение модели не превращало запрос в HTTP 4xx.
    """
    if not isinstance(effort, str):
        return effort
    if _model_key(model) != _model_key(GLM_53_FLASH_MODEL):
        return effort
    return _GLM_REASONING_ALIASES.get(effort.casefold(), effort)
