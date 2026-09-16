"""Одна итерация: запрос LLM, tools и запись mind-loop."""

import time

from agent_console import (
    _format_iteration_command, _format_iteration_header, _format_sleep_message,
    _format_unread_log, _format_wake_up_log,
)
from agent_console_blocks import (
    _format_llm_block, _format_reasoning_block,
    _format_system_prompt_block, _format_system_prompt_unchanged,
    _format_tool_call_block, _format_tool_result_block,
)
from agent_messages import build_messages
from agent_sleep import (
    _just_woke_up, _tick_user_message, is_session_end,
    iterations_remaining,
)
from agent_usage import (
    _extract_completion_tokens, _extract_prompt_tokens, _extract_reasoning,
    _extract_reasoning_tokens,
)
from agent_history import _serialize_message
from agent_paid_pause import creativity_temperature
from agent_paths import AgentPaths
from agent_unread import _unread_creator_count
from config_env import Config
from llm import call_llm
from storage import append_iteration, archive_mind_loop, load_mind_loop
from tool_context import ToolContext
from tool_registry import build_tools_schema, execute_tool
from time_utils import now_iso


def run_iteration(paths: AgentPaths, cfg: Config, client,
                  console_state: dict | None = None, *, log=print,
                  llm_call=call_llm, tool_executor=execute_tool,
                  tools_schema=build_tools_schema,
                  message_builder=build_messages, loader=load_mind_loop,
                  appender=append_iteration, archiver=archive_mind_loop,
                  serializer=_serialize_message,
                  extract_prompt=_extract_prompt_tokens,
                  extract_completion=_extract_completion_tokens,
                  extract_reasoning_tokens=_extract_reasoning_tokens,
                  extract_reasoning=_extract_reasoning) -> None:
    """Выполнить и сохранить один тик, используя переданные зависимости."""
    state = console_state if console_state is not None else {}
    data = loader(paths.mind_loop)
    number = len(data.get("iterations") or []) + 1
    log(_format_iteration_header(number))
    if _just_woke_up(data):
        log(_format_wake_up_log(data.get("session")))
    user_message = _tick_user_message(number, paths)
    unread_count = _unread_creator_count(paths)
    messages = message_builder(data, paths)
    log(_format_iteration_command(user_message, iterations_remaining(number)))
    if unread_count:
        log(_format_unread_log(unread_count))
    prompt = messages[0].get("content") or ""
    if state.get("system_prompt") != prompt:
        log(_format_system_prompt_block(number, prompt))
        state["system_prompt"] = prompt
    else:
        log(_format_system_prompt_unchanged(number))
    temperature = creativity_temperature(paths, cfg.temperature)
    started = time.perf_counter()
    response = llm_call(
        client, cfg.model, messages, tools_schema(cfg.enable_bash_tool),
        temperature=temperature, reasoning_effort=cfg.reasoning_effort,
    )
    duration = time.perf_counter() - started
    prompt_tokens = extract_prompt(response)
    completion_tokens = extract_completion(response)
    reasoning_tokens = extract_reasoning_tokens(response)
    reasoning = extract_reasoning(response)
    assistant = serializer(response)
    if reasoning:
        log(_format_reasoning_block(number, reasoning))
    if assistant is None:
        raise RuntimeError(
            "пустой ответ модели: нет content, tool_calls и reasoning"
        )
    record = {
        "n": number, "timestamp": now_iso(), "user": user_message,
        "assistant_message": assistant, "llm_duration": duration,
        "tool_results": [],
    }
    log(_format_llm_block(
        number, assistant.get("content"), duration, prompt_tokens,
        completion_tokens, reasoning_tokens,
    ))
    context = ToolContext(
        client=client, model=cfg.model, temperature=temperature,
        reasoning_effort=cfg.reasoning_effort,
    )
    for index, call in enumerate(assistant.get("tool_calls") or []):
        name = call["function"]["name"]
        arguments = call["function"]["arguments"]
        log(_format_tool_call_block(number, name, arguments))
        result = tool_executor(name, arguments, paths, context)
        record["tool_results"].append({
            "tool_call_id": call.get("id") or f"call_{index}", "tool": name,
            "arguments": arguments, "result": result,
        })
        log(_format_tool_result_block(number, name, result))
    if context.sleep_requested:
        data["sleep_reason"] = context.sleep_reason
    appender(paths.mind_loop, data, record)
    if is_session_end(number) or context.sleep_requested:
        archive = archiver(paths.mind_loop, data)
        log(_format_sleep_message(data.get("session") or 1, archive.name))
