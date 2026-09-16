"""Адаптеры различий моделей DeepInfra и официального DeepSeek API."""

GLM_53_FLASH_MODEL = "zai-org/GLM-5.3-Flash"
# Старый идентификатор DeepInfra оставлен для совместимости существующих .env.
DEEPSEEK_V41_FLASH_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"
# Официальный DeepSeek API вызывает V4.1-Flash именем deepseek-flash.
DEEPSEEK_FLASH_MODEL = "deepseek-flash"
DEEPSEEK_API_MODEL = DEEPSEEK_FLASH_MODEL
DEEPSEEK_API_BASE_URL = "https://api.deepseek.com"

SUPPORTED_MODELS = frozenset(
    {GLM_53_FLASH_MODEL, DEEPSEEK_V41_FLASH_MODEL, DEEPSEEK_FLASH_MODEL}
)
_MODEL_KEYS = frozenset(model.casefold() for model in SUPPORTED_MODELS)
_DEEPSEEK_API_MODEL_KEYS = frozenset(
    {
        DEEPSEEK_FLASH_MODEL.casefold(),
        "deepseek-v4-flash",
        "deepseek-v4-flash-vision-exp",
        "deepseek-v4.1-flash",
    }
)

_GLM_REASONING_ALIASES = {
    "none": "low",
    "minimal": "low",
    "medium": "high",
    "xhigh": "max",
}
_DEEPSEEK_REASONING_ALIASES = {
    "minimal": "low",
    "medium": "high",
    "xhigh": "high",
}


def _model_key(model: str) -> str:
    return model.strip().casefold()


def is_deepseek_api_model(model: str) -> bool:
    """Определить официальное имя или совместимый алиас DeepSeek API."""
    return _model_key(model) in _DEEPSEEK_API_MODEL_KEYS


def normalize_model_name(model: str) -> str:
    """Привести имя V4.1-Flash к официальному имени API, если нужно."""
    return DEEPSEEK_FLASH_MODEL if is_deepseek_api_model(model) else model


def is_supported_model(model: str) -> bool:
    """Известна ли модель одному из поддерживаемых OpenAI-compatible API."""
    return _model_key(model) in _MODEL_KEYS or is_deepseek_api_model(model)


def normalize_reasoning_effort(model: str, effort: str | None) -> str | None:
    """Подготовить reasoning_effort к enum конкретного провайдера."""
    if not isinstance(effort, str):
        return effort
    key = _model_key(model)
    if key == _model_key(GLM_53_FLASH_MODEL):
        return _GLM_REASONING_ALIASES.get(effort.casefold(), effort)
    if is_deepseek_api_model(model):
        if effort.casefold() == "none":
            return None
        return _DEEPSEEK_REASONING_ALIASES.get(effort.casefold(), effort)
    return effort


def request_options(model: str, effort: str | None) -> dict:
    """Собрать provider-specific параметры запроса chat.completions."""
    normalized = normalize_reasoning_effort(model, effort)
    if is_deepseek_api_model(model):
        disabled = isinstance(effort, str) and effort.casefold() == "none"
        options = {"extra_body": {"thinking": {
            "type": "disabled" if disabled else "enabled"
        }}}
        if normalized:
            options["reasoning_effort"] = normalized
        return options
    return {"reasoning_effort": normalized} if normalized else {}
