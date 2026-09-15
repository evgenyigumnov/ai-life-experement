"""Изолированный subprocess для тестов загрузки config_env."""

import json
import shutil
import tempfile
from pathlib import Path

from tests.helpers import PROJECT_ROOT, run_python


def run_config(dotenv_text: str | None, env_extra: dict, snippet: str | None = None):
    """Скопировать только модули конфигурации в временный проект."""
    tmp = Path(tempfile.mkdtemp(prefix="ai-cfg-"))
    try:
        for name in ("config_env.py", "errors.py", "prompts_template.py"):
            shutil.copy(PROJECT_ROOT / name, tmp / name)
        if dotenv_text is not None:
            (tmp / ".env").write_text(dotenv_text, encoding="utf-8")
        code = snippet or (
            "import json, config_env\n"
            "c = config_env.load_config()\n"
            "print(json.dumps({"
            "'base_url': c.base_url, 'model': c.model, 'api_key': c.api_key, "
            "'agents_root': c.agents_root, 'loop_delay': c.loop_delay, "
            "'loop_pause': c.loop_pause, 'temperature': c.temperature, "
            "'reasoning_effort': c.reasoning_effort, "
            "'enable_bash_tool': c.enable_bash_tool, "
            "'session_iterations': c.session_iterations, "
            "'sleep_warn_remaining': c.sleep_warn_remaining}))\n"
        )
        return run_python(code, cwd=tmp, env_extra=env_extra)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def config_data(result):
    """Проверить удобный JSON-ответ subprocess."""
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)
