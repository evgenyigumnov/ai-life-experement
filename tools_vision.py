"""Tool inspect_image: ответить на вопрос по изображению."""

from pathlib import Path
from urllib.parse import urlsplit

from agent_paths import AgentPaths
from llm import call_llm
from tool_context import ToolContext
from vision_answer import VisionAnswerError, extract_visible_answer, safe_error
import vision_image
import vision_source

MAX_QUESTION_CHARS = 8_000

INSPECT_IMAGE_TOOL = {
    "type": "function",
    "function": {
        "name": "inspect_image",
        "description": "Рассмотреть изображение и ответить на вопрос по нему.",
        "parameters": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "URL изображения или абсолютный путь к нему",
                },
                "question": {
                    "type": "string",
                    "description": "Непустой вопрос по изображению",
                },
            },
            "required": ["source", "question"],
        },
    },
}


def _source_kind(source: str) -> tuple[str | None, str | None]:
    value = source.strip()
    try:
        parts = urlsplit(value)
        if parts.scheme:
            if parts.scheme.lower() not in {"http", "https"}:
                return None, "разрешены только URL http/https или абсолютный путь"
            if not parts.hostname:
                return None, "URL должен содержать имя хоста"
            if parts.port is not None and not 0 < parts.port <= 65535:
                return None, "порт URL вне диапазона"
            return "url", None
    except ValueError:
        return None, "некорректный URL"
    if not Path(value).is_absolute():
        return None, "путь изображения должен быть абсолютным"
    return "path", None


def _validate_args(args):
    if not isinstance(args, dict):
        return None, "аргументы должны быть объектом"
    unknown = [key for key in args if key not in {"source", "question"}]
    if unknown:
        return None, f"неизвестные аргументы: {', '.join(map(str, unknown))}"
    source = args.get("source")
    if not isinstance(source, str) or not source.strip():
        return None, "ожидается непустая строка 'source'"
    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        return None, "ожидается непустая строка 'question'"
    if len(question) > MAX_QUESTION_CHARS:
        return None, f"'question' не должен быть длиннее {MAX_QUESTION_CHARS} символов"
    kind, error = _source_kind(source)
    if error:
        return None, error
    return (kind, source.strip(), question.strip()), None


def load_source(source: str, paths=None) -> bytes:
    """Тонкая seam-функция: позволяет тестировать handler без I/O."""
    return vision_source.load_source(source, paths)


def to_data_url(raw: bytes) -> str:
    """Тонкая seam-функция нормализации изображения."""
    return vision_image.to_data_url(raw)


def handle_inspect_image(
    args: dict, paths: AgentPaths | None, context: ToolContext | None = None
) -> str:
    """Проверить аргументы, вызвать вложенную vision-модель и вернуть ответ."""
    validated, error = _validate_args(args)
    if error:
        return f"Error: invalid arguments: {error}"
    kind, source, question = validated
    if kind == "path" and not isinstance(paths, AgentPaths):
        return "Error: invalid arguments: для пути нужен AgentPaths контейнера"
    if context is None:
        return "Error: vision: отсутствует контекст вложенного LLM-вызова"

    try:
        raw = load_source(source, paths)
        data_url = to_data_url(raw)
        messages = [{
            "role": "user",
            "content": [
                {"type": "text", "text": question},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }]
        response = call_llm(
            context.client,
            context.model,
            messages,
            tools=None,
            temperature=context.temperature,
            reasoning_effort=context.reasoning_effort,
        )
        return extract_visible_answer(response)
    except Exception as exc:
        return f"Error: vision: {safe_error(exc)}"


_extract_visible_answer = extract_visible_answer
_safe_error = safe_error
