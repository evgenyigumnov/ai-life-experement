"""Обёртка assistant-сообщения, сохраняющая usage отдельно от SDK."""


class MessageWithUsage:
    """Делегировать сообщение SDK и добавить к нему статистику usage.

    Мутировать ChatCompletionMessage нельзя: это ломает сериализацию некоторых
    версий pydantic/OpenAI SDK. Исходный объект остаётся неизменным.
    """

    __slots__ = ("_message", "usage")

    def __init__(self, message, usage):
        self._message = message
        self.usage = usage

    def __getattr__(self, name):
        return getattr(self._message, name)

    def model_dump(self):
        """Сериализовать исходное сообщение без искусственного поля usage."""
        dump = getattr(self._message, "model_dump", None)
        if callable(dump):
            return dump()
        return {
            "role": "assistant",
            "content": getattr(self._message, "content", None),
            "tool_calls": getattr(self._message, "tool_calls", None),
        }
