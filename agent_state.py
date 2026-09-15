"""Инициализация файлов состояния агента."""

import json
from pathlib import Path

from config_env import Config
from diary import ensure_diary_file
from errors import die
from prompts_messages import ensure_message_files
from prompts_template import ensure_system_prompt
from storage import _empty_mind_loop, ensure_messages_file
from wallet_reconcile import reconcile_payment_messages
from wallet_storage import WalletError, ensure_wallet_file


def prepare_agent_folder(folder: Path, name: str, cfg: Config,
                         create_prompt: bool = True,
                         mind_loop_factory=_empty_mind_loop):
    """Создать отсутствующие рабочие файлы и вернуть AgentPaths."""
    folder = Path(folder).resolve()
    system_prompt = folder / "system-prompt.md"
    if create_prompt:
        try:
            created = ensure_system_prompt(
                folder, name, session_iterations=cfg.session_iterations,
                sleep_warn_remaining=cfg.sleep_warn_remaining,
            )
        except (OSError, ValueError) as exc:
            die(f"не удалось создать system-prompt.md в {folder}: {exc}")
        if created is not None:
            print(f"Создан {created} из шаблона default-prompts/system-prompt.md",
                  flush=True)

    mind_loop = folder / "mind-loop.json"
    if not mind_loop.exists():
        mind_loop.write_text(
            json.dumps(mind_loop_factory(name), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    memory = folder / "memory.md"
    if not memory.exists():
        memory.write_text("", encoding="utf-8")
    messages = folder / "messages.json"
    ensure_messages_file(messages, name)
    diary_path = folder / "diary.json"
    ensure_diary_file(diary_path, name)
    ensure_message_files(folder)
    wallet = folder / "wallet.json"
    try:
        ensure_wallet_file(wallet, name)
        reconcile_payment_messages(wallet, messages, name)
    except (WalletError, OSError, ValueError):
        # Повреждённый кошелёк оставляем на месте: цикл продолжится обычной
        # паузой, а CLI/tools сообщат о проблеме без потери денег.
        pass

    from agent_paths import AgentPaths
    return AgentPaths(folder, system_prompt, mind_loop, memory,
                      messages, diary_path, name, wallet)
