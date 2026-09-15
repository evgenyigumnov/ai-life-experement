"""Пути и рабочие файлы агента."""

from dataclasses import dataclass
from pathlib import Path

from agent_state import prepare_agent_folder
from config_env import Config
from errors import die
from storage import _empty_mind_loop


@dataclass(frozen=True)
class AgentPaths:
    """Пути к данным агента."""

    folder: Path
    system_prompt: Path
    mind_loop: Path
    memory: Path
    messages: Path | None = None
    diary: Path | None = None
    name: str = ""
    wallet: Path | None = None

    def __post_init__(self) -> None:
        # Допускаем старый/новый позиционный порядок: wallet иногда
        # передаётся сразу после diary, до name.
        if isinstance(self.name, Path):
            old_wallet = self.name
            old_name = self.wallet if isinstance(self.wallet, str) else ""
            object.__setattr__(self, "wallet", old_wallet)
            object.__setattr__(self, "name", old_name)
        if self.messages is None:
            object.__setattr__(self, "messages", self.folder / "messages.json")
        if self.diary is None:
            object.__setattr__(self, "diary", self.folder / "diary.json")
        if self.wallet is None:
            object.__setattr__(self, "wallet", self.folder / "wallet.json")


def _search_candidates(name: str, cfg: Config) -> list[Path]:
    if cfg.agents_root:
        return [Path(cfg.agents_root) / name]
    direct = Path.cwd() / name
    if direct.is_dir():
        return [direct]
    return [
        child / name
        for child in sorted(Path.cwd().iterdir())
        if child.is_dir() and (child / name).is_dir()
    ]


def _is_agent_folder(folder: Path) -> bool:
    return folder.is_dir() and not folder.name.startswith(".") and (
        folder / "system-prompt.md"
    ).is_file()


def list_agents(cfg: Config) -> list[str]:
    """Найти имена агентов в тех же местах, что и find_agent_folder."""
    folders: list[Path] = []
    if cfg.agents_root:
        root = Path(cfg.agents_root)
        if root.is_dir():
            folders = [d for d in sorted(root.iterdir()) if _is_agent_folder(d)]
    else:
        for child in sorted(Path.cwd().iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            if _is_agent_folder(child):
                folders.append(child)
            folders.extend(
                d for d in sorted(child.iterdir()) if _is_agent_folder(d)
            )
    return list(dict.fromkeys(folder.name for folder in folders))


def _is_valid_agent_name(name: str) -> bool:
    return bool(
        name
        and name == name.strip()
        and not name.startswith(".")
        and name not in {".", ".."}
        and "/" not in name
        and "\\" not in name
    )


def find_agent_folder(name: str, cfg: Config) -> AgentPaths:
    """Найти или создать папку агента и её рабочие файлы."""
    if not _is_valid_agent_name(name):
        die(
            f"недопустимое имя агента '{name}': ожидается простое имя папки "
            "без разделителей пути (например, oleg), не скрытое и не пустое."
        )
    candidates = _search_candidates(name, cfg)
    folder = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if folder is None:
        folder = candidates[0] if candidates else Path.cwd() / name
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            die(f"не удалось создать папку нового агента {folder}: {exc}")
        print(
            f"Агент '{name}' не найден — создаю нового в {folder.resolve()} "
            "(system-prompt.md будет сгенерирован из шаблона)", flush=True,
        )
    return prepare_agent_folder(
        folder, name, cfg, create_prompt=True, mind_loop_factory=_empty_mind_loop
    )


def find_existing_agent_folder(name: str, cfg: Config) -> AgentPaths | None:
    """Найти только существующего полноценного агента, ничего не создавая."""
    if not _is_valid_agent_name(name):
        return None
    folder = next(
        (candidate for candidate in _search_candidates(name, cfg)
         if _is_agent_folder(candidate)),
        None,
    )
    return (prepare_agent_folder(
        folder, name, cfg, create_prompt=False, mind_loop_factory=_empty_mind_loop
    ) if folder is not None else None)
