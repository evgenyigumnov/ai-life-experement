# Тесты ai-life

Юнит- и интеграционные тесты (stdlib `unittest`, без внешних зависимостей;
совместимы и с pytest, если он появится).

## Запуск

Из корня проекта:

```bash
.venv/bin/python -m unittest discover -s tests -v          # всё
.venv/bin/python -m unittest tests.test_storage -v         # один модуль
.venv/bin/python -m unittest tests.test_storage.StorageTests.test_append -v  # один тест
```

## Что покрывают модули

Общие фикстуры тестов agent-модулей вынесены в `tests/agent_common.py`
(конструктор AgentPaths, фабрики итераций истории, прогон run_loop с
моком LLM и базовый класс тестов полного цикла).

| Модуль | Что проверяет |
|--------|-----------------------------------------------------------------------|
| `test_config_env` / `test_config_agents` | `config_env.load_config()` (.env, обязательные переменные, типы и диапазоны, параметры сессии), `find_agent_folder()` и `list_agents()` (поиск, ошибки, первый запуск, override параметров промпта) |
| `test_session_env` | применение SESSION_ITERATIONS/SLEEP_WARN_REMAINING к предикатам сна, баннеру, последнему тику и точке запуска main.py; синхронность дефолтов |
| `test_prompts_messages` / `test_prompts_template` | модули prompts_messages.py и prompts_template.py: дефолты из файлов default-prompts, контракт плейсхолдеров, fallback/перечитывание файлов, резолвер default-prompts |
| `test_storage` / `test_storage_messages` | mind-loop.json: загрузка/сохранение/добавление итераций, архивы и бэкапы; memory.md; системный промпт; messages.json, read-флаги и конкурентная запись переписки |
| `test_wallet` | wallet.json: ledger credit/spend, баланс, оплаченные циклы, потребление без boost_consume, повреждение, атомарность и конкурентная запись |
| `test_diary` / `test_diary_pagination` / `test_diary_edit` | diary.json: загрузка/бэкапы, remember/recall с фильтрами и курсорами, точечная правка и валидация |
| `test_diary_index` / `test_diary_search` / `test_diary_vec` | автоиндексация, FTS5, sqlite-vec, fallback и свежесть индексов |
| `test_message_format` / `test_time_utils` | общие форматирование сообщений и ISO-время |
| `test_llm` / `test_llm_support` / `test_model_support` | ретраи call_llm (429/сеть/5xx, backoff 2-4-8-16, пауза 60 и новый цикл), постоянные ошибки (400), пустой ответ, Ctrl+C во время паузы, usage без мутации SDK-сообщения (регрессия MockValSer), make_client; профили GLM-5.3-Flash, DeepInfra и официального DeepSeek API |
| `test_llm_live` | живой smoke-тест: минимальный запрос на сервер из .env (load_config → make_client → call_llm → сериализация для истории → prompt_tokens); при недоступном сервере skip, `AI_LIVE_REQUIRED=1` — обязательность провалом |
| `test_agent_build_messages` | `build_messages`: воспроизведение истории (текст, tool-calls по id и по порядку, итерации-ошибки, нормализация SDK-словарей, пробельные/пустые content, отсутствие урезания истории, перечитывание system-prompt.md) |
| `test_agent_message_files` | тексты сообщений из файлов папки агента: переопределения user/last-iteration/wake-up, sleep-warning с `{remaining}`+`{memory_note}`, repeat-alert, перечитывание при каждой сборке, пустой файл → дефолт |
| `test_agent_internal_fallbacks` | внутренние fallback-строки (INTERNAL_MESSAGES) для потерянного tool-результата и сбойной итерации; файлы tool-result-missing.md / iteration-failed.md агентом игнорируются |
| `test_agent_prompt_notes` | роль system — только у первого сообщения (заметки — user); анти-зацикливание: серия одинаковых tool-вызовов, пороги, обрыв серии, обрезка длинных аргументов |
| `test_agent_unread` | непрочитанные сообщения создателя: короткий статус по read-флагам без вставки текста, игнорирование старого счётчика, битый messages.json |
| `test_agent_sleep_cycle` | сессии по SESSION_ITERATIONS: предупреждение со обратным отсчётом, директива последней итерации, пробуждение по woke_up_at (только при пустой истории) |
| `test_agent_memory_staleness` | устаревание памяти (set_memory vs работа после него, порядок вызовов), усиленное предупреждение «скоро сон», `_tick_user_message` |
| `test_agent_run_loop` | полный цикл `run_loop` с моком LLM: запись итераций, tool-результаты из песочницы, round-trip, пустые ответы как ошибки, продолжение нумерации после рестарта |
| `test_agent_run_loop_delivery` | цикл сообщает о непрочитанных сообщениях без вставки текста, read-флаг меняется только через get_messages, миграция старого счётчика |
| `test_agent_run_loop_config` | параметры из Config: TEMPERATURE, REASONING_EFFORT, схема tools по флагу ENABLE_BASH_TOOL, полный блок промпта в консоли — один раз |
| `test_agent_run_loop_sleep` | сон и архив: сессии по 2 итерации — предупреждение, директива, архив прошлой сессии, пробуждение, нумерация с 1, без остаточных tmp |
| `test_agent_backoff_schedule` | расписание IDLE_BACKOFF_SCHEDULE, `_backoff_delay` (кап 4 часа), `_pause_seconds` (вычет длительности итерации), формат строк паузы |
| `test_agent_backoff_loop` | адаптивная пауза в живом цикле: рост при молчании создателя, сброс его сообщением (сообщения агента не считаются), LOOP_DELAY как минимум, счётчик `_creator_messages_count`, пробуждение во время паузы |
| `test_agent_fixed_pause` | фиксированная пауза --loop-pause=N: константна при молчании и после сообщений, LOOP_DELAY не применяется, сообщение во время паузы всё равно будит |
| `test_agent_paid_pause` | платные циклы отменяют адаптивное ожидание по одной единице, переживают рестарт, не действуют в --loop-pause и безопасно обходят битый кошелёк |
| `test_agent_wait_pause` | `_wait_pause`: куски сна не длиннее PAUSE_POLL_INTERVAL, немедленное пробуждение сообщением создателя, сообщения агента не будят, Ctrl+C пробрасывается |
| `test_agent_prompt_cache` | кэшируемость системного промпта: system побайтово идентичен файлу и неизменен между итерациями, append-only префикс, отправленные сообщения не мутируются, заметки сна/пробуждения не трогают префикс |
| `test_agent_prompt_cache_restart` | кеш промпта: холодный перезапуск процесса воспроизводит следующий запрос побайтово; кеш показа промпта в консоли (console_state) |
| `test_agent_iteration_logging` | консоль итерации: заголовок, команда LLM с обратным отсчётом до сна, блок system prompt (полный / «без изменений» / перечитывание с диска) |
| `test_agent_llm_blocks` | блоки консоли: LLM (тайминг, токены послано/сгенерировано/reasoning), Reasoning и сохранение reasoning-only ответов |
| `test_agent_tool_blocks` | блоки вызова/результата tool без обрезки и ANSI-кодов |
| `test_agent_reasoning_history` | путь reasoning: ответ → mind-loop.json → следующий payload, оба имени поля и SDK-атрибут |
| `test_agent_usage_extract` | извлечение usage из SDK-объектов и dict: prompt/completion/reasoning токены; `_extract_reasoning` (reasoning_content/reasoning, обёртка _MessageWithUsage, пустые) |
| `test_agent_console_format` | цвета (USE_COLOR/NO_COLOR/TERM/tty) и форматирование: tool-args, блоки reasoning/system-prompt/«без изменений» |
| `tools_testkit` | общие фикстуры модулей test_tools_* (не тесты): хелперы `_paths`/`_bash`, контекст `bash_tool_on` |
| `test_tools_bash_gate` | флаг ENABLE_BASH_TOOL: гейтинг песочницы — схема без run_bash/read_file при выключенном флаге, исполнение возвращает ошибку, остальные tools работают |
| `test_tools_chat` / `test_tools_chat_pages` | send_message/get_messages: базовое поведение (отправка, read-статусы, хранение всей переписки) и пагинация (limit/cursor/подсказки, валидация аргументов, миграция старого файла без флага read) |
| `test_tools_sandbox` | песочница Docker: исполнение, единый образ (busybox, python3, pip, curl, apk, bash), изоляция от хоста, сеть, таймауты, завершение дочерних фоновых процессов, обрезка вывода, интеграционное read_file в контейнере |
| `test_tools_docker` | управление образом/контейнерами (restart=always, перезапуск остановленного), валидация timeout, ошибки недоступного Docker |
| `test_tools_readfile_args` / `test_tools_readfile_unit` | read_file: валидация аргументов до песочницы; без docker — сборка команды раннера, клампинг limit с пометкой, форматирование страниц |
| `test_tools_memory` | get/set_memory: пустая память, roundtrip, валидация |
| `test_tools_sleep` | sleep: обязательная причина, сигнал раннего сна и результат tool |
| `test_tools_money` | money_balance/money_spend: схемы, расписание, purpose, успешные операции и безопасные ошибки |
| `test_tools_diary` / `test_tools_diary_edit` | tools дневника: remember/recall (фильтры, пагинация курсором) и точечная edit, границы имён |
| `test_diary_tags` | diary_tags: частоты тегов записей (оглавление тем) — подсчёт/сортировка/лимиты, формат ответа и плюрализация, read-only, схема и регистрация |
| `test_tools_search` / `test_tools_search_errors` | internet_search: схема, валидация, один HTTP-запрос, ошибки и форматирование результатов Brave |
| `test_tools_web_fetch` | web_fetch: прямая загрузка без Brave, HTML-текст, ссылки и постраничное чтение |
| `test_tools_vision` / `test_vision_source` / `test_vision_image` | inspect_image: валидация, Docker/URL-источник, JPEG-нормализация и очистка reasoning |
| `test_vision_live` | два smoke-вызова inspect_image (URL и Docker path) через реальный LLM/API; skip без доступной инфраструктуры |
| `test_tools_schema` / `test_tools_file_common` / `test_tools_file_tools` | схемы 21 инструмента, автоматическая регистрация файловых tools, гейтинг песочницы, общие лимиты, очередь мутаций и интеграционные write/edit/grep/find/ls |
| `test_main` / `test_main_money` | точка входа: обычные аргументы, баннер, Docker и run_loop; pay/balance/history с обязательным существующим агентом без LLM-конфигурации, unread-сообщение и история трат |
| `test_dockerfile` | Dockerfile песочницы: установлен vim, vi — симлинк на vim, задана UTF-8 локаль |

Живые smoke-тесты vision и эмбеддингов запускаются отдельно:

```bash
.venv/bin/python -m unittest tests.test_vision_live -v
AI_LIVE_REQUIRED=1 .venv/bin/python -m unittest tests.test_vision_live -v
DIARY_EMBED_TOKEN=... DIARY_VEC_SO=/tmp/vec0.so \
  .venv/bin/python -m unittest tests.test_diary_live -v
```

## Время выполнения

Полный прогон ~20–30 секунд: `test_tools_sandbox`/`test_tools_docker`
запускают реальные команды в Docker-контейнере (включая таймаут-тесты
на 2–6 сек). `test_llm_live`
ходит по сети на сервер из .env (если недоступен — пропускается),
остальные модули быстрые и наружу не ходят (LLM замокан).
