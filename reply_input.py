"""Редактор сообщений для интерактивного режима переписки."""

from contextlib import contextmanager

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.patch_stdout import patch_stdout
except ImportError:  # удобный fallback для минимальной установки проекта
    PromptSession = None
    KeyBindings = None
    patch_stdout = None

REPLY_PROMPT = (
    "\n✍️ Ваш ответ (Enter — отправить; Shift+Enter/Ctrl+Enter — "
    "новая строка, если терминал различает; иначе Ctrl+J; Ctrl+D — выйти): "
)


def _insert_newline(event) -> None:
    event.current_buffer.insert_text("\n")


def build_key_bindings():
    """Enter отправляет, а отдельные terminal-коды вставляют перенос строки."""
    if KeyBindings is None:
        return None
    bindings = KeyBindings()

    @bindings.add("enter")
    def accept(event):
        event.current_buffer.validate_and_handle()

    bindings.add("c-j")(_insert_newline)  # запасной код Ctrl+Enter в терминалах
    bindings.add("escape", "c-m")(_insert_newline)  # Alt+Enter
    bindings.add("escape", "[", "1", "3", "u")(
        lambda event: event.current_buffer.validate_and_handle()
    )
    for modifier in ("2", "5", "6"):  # Shift/Ctrl в kitty CSI-u protocol
        bindings.add(
            "escape", "[", "1", "3", ";", modifier, "u"
        )(_insert_newline)
    return bindings


def create_reply_session():
    """Создать многострочную сессию с обычной навигацией курсором."""
    if PromptSession is None:
        return None
    return PromptSession(multiline=True, key_bindings=build_key_bindings())


def read_reply(session, prompt: str) -> str | None:
    """Прочитать сообщение; Ctrl+D возвращается как ``None``."""
    try:
        text = input(prompt) if session is None else session.prompt(prompt)
    except EOFError:
        return None
    return text


@contextmanager
def reply_output(enabled: bool):
    """Безопасно печатать ответы агента поверх активного редактора."""
    if enabled and patch_stdout is not None:
        with patch_stdout():
            yield
    else:
        yield
