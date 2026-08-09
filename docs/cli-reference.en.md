# Singular CLI reference

This reference inventories **every** parser built by `_build_parser`. It is automatically checked by `tests/test_cli_reference.py`.

## Scope and global options

Every syntax accepts, before the command: `singular [--seed INT] [--root PATH] [--home PATH] [--life NAME] [--format {table,json,plain}] [--safe-mode] …`. Defaults: seed/root/home/life `None` (root/home may come from the environment), format `plain`, safe mode `false`. `--root` selects the registry; `--home` directly selects a life directory; `--life` resolves a life in the registry. `SINGULAR_ROOT`, `SINGULAR_HOME`, `OPENAI_API_KEY`, and provider variables can therefore change context.

Paths below are relative to the root or `SINGULAR_HOME`. Always back up before deletion, reset, rollback, or real retention.

<!-- cli-command: embodiment -->
## `embodiment`

**Syntax :** `singular embodiment [-h] --config CONFIG [--mode {simulation,dry-run,hardware}] [--steps STEPS] [--audit AUDIT]`

**Arguments and defaults :** `--config` (requis/required); `--mode` (`simulation`; choix/choices: simulation, dry-run, hardware); `--steps` (`None`); `--audit` (`None`)

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular embodiment --config configs/embodiment.yaml`

**Advanced example :** `singular --root /srv/singular --life ada --format json embodiment --config configs/embodiment.yaml`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: birth -->
## `birth`

**Syntax :** `singular birth [-h] [--name NAME] [--curiosity CURIOSITY] [--patience PATIENCE] [--playfulness PLAYFULNESS] [--optimism OPTIMISM] [--resilience RESILIENCE] [--starter-profile STARTER_PROFILE] [--starter-skill STARTER_SKILL]`

**Arguments and defaults :** `--name` (`New life`); `--curiosity` (`None`); `--patience` (`None`); `--playfulness` (`None`); `--optimism` (`None`); `--resilience` (`None`); `--starter-profile` (`assistant`); `--starter-skill` (`[]`)

**Prerequisites :** Writable root; valid starter profile.

**Target root and life :** Resolved root; creates and activates a new life.

**Files read or written :** Writes `lives/registry.json` and `lives/<slug>/` (identity, psyche, skills, memory).

**Side effects :** Creates directories and sets `SINGULAR_HOME`; `birth` is deprecated.

**Minimal example :** `singular birth --name Ada`

**Advanced example :** `singular --root /srv/singular --life ada --format json birth --name Ada`

**Common errors :** Trait outside [0,1], invalid name/profile, unwritable root.

<!-- cli-command: spawn -->
## `spawn`

**Syntax :** `singular spawn [-h] [--out-dir OUT_DIR] parent_a parent_b`

**Arguments and defaults :** `parent_a` (requis/required); `parent_b` (requis/required); `--out-dir` (`None`)

**Prerequisites :** Required inputs present and writable root/life.

**Target root and life :** Active life, except `spawn`, which targets parent paths and output.

**Files read or written :** Reads parents/spec/memory; writes child, skill, memory, or restored generation depending on command.

**Side effects :** Creates/changes artifacts; `rollback` atomically replaces active state.

**Minimal example :** `singular spawn life/a life/b`

**Advanced example :** `singular --root /srv/singular --life ada --format json spawn life/a life/b`

**Common errors :** Missing/invalid input, unknown generation, existing or unwritable output.

<!-- cli-command: run -->
## `run`

**Syntax :** `singular run [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular run`

**Advanced example :** `singular --root /srv/singular --life ada --format json run`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: loop -->
## `loop`

**Syntax :** `singular loop [-h] [--skills-dir SKILLS_DIR] [--checkpoint CHECKPOINT] [--budget-seconds BUDGET_SECONDS] [--ticks TICKS] [--run-id RUN_ID]`

**Arguments and defaults :** `--skills-dir` (`None`); `--checkpoint` (`None`); `--budget-seconds` (`None`); `--ticks` (`None`); `--run-id` (`loop`)

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular loop --budget-seconds 10`

**Advanced example :** `singular --root /srv/singular --life ada --format json loop --budget-seconds 10`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: status -->
## `status`

**Syntax :** `singular status [-h] [--verbose] [--format {table,json,plain}]`

**Arguments and defaults :** `--verbose` (`false`); `--format` (`None`; choix/choices: table, json, plain)

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular status`

**Advanced example :** `singular --root /srv/singular --life ada --format json status`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: talk -->
## `talk`

**Syntax :** `singular talk [-h] [--provider PROVIDER] [--prompt PROMPT] [--life TALK_LIFE] [--live TALK_LIFE_LEGACY]`

**Arguments and defaults :** `--provider` (`None`); `--prompt` (`None`); `--life` (`None`); `--live` (`None`)

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular talk --prompt "Bonjour"`

**Advanced example :** `singular --root /srv/singular --life ada --format json talk --prompt "Bonjour"`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: quest -->
## `quest`

**Syntax :** `singular quest create [-h] [--example] [--schema] [--life LIFE] [spec]`

**Arguments and defaults :** `spec` (`None`); `--example` (`false`); `--schema` (`false`)

**Prerequisites :** Required inputs present and writable root/life.

**Target root and life :** Active life, except `spawn`, which targets parent paths and output.

**Files read or written :** Reads parents/spec/memory; writes child, skill, memory, or restored generation depending on command.

**Side effects :** Creates/changes artifacts; `rollback` atomically replaces active state.

**Minimal example :** `singular quest create --example`

**Advanced example :** `singular --root /srv/singular --life ada --format json quest create --example`

**Common errors :** Missing/invalid input, unknown generation, existing or unwritable output.

<!-- cli-command: skills -->
## `skills`

**Syntax :** `singular skills ACTION`

**Arguments and defaults :** `ACTION` (requis/required)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular skills list`

**Advanced example :** `singular --root /srv/singular --life ada skills list`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: skills list -->
## `skills list`

**Syntax :** `singular skills list [--life LIFE]`

**Arguments and defaults :** `--life` (`None`)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular skills list --life ada`

**Advanced example :** `singular --root /srv/singular --life ada skills list --life ada`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: quest create -->
## `quest create`

**Syntax :** `singular quest create [--example] [--schema] [--life LIFE] [spec]`

**Arguments and defaults :** `spec` (`None`); options (`false`)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular quest create --example`

**Advanced example :** `singular --root /srv/singular --life ada quest create --example`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: quest list -->
## `quest list`

**Syntax :** `singular quest list [--life LIFE]`

**Arguments and defaults :** `--life` (`None`)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular quest list --life ada`

**Advanced example :** `singular --root /srv/singular --life ada quest list --life ada`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: social -->
## `social`

**Syntax :** `singular social ACTION`

**Arguments and defaults :** `ACTION` (requis/required)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular social interact bob cooperation`

**Advanced example :** `singular --root /srv/singular --life ada social interact bob cooperation`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: social interact -->
## `social interact`

**Syntax :** `singular social interact TARGET EVENT [--life LIFE]`

**Arguments and defaults :** `TARGET`, `EVENT` (requis/required); `--life` (`None`)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular social interact bob cooperation --life ada`

**Advanced example :** `singular --root /srv/singular --life ada social interact bob cooperation --life ada`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: self-narrative -->
## `self-narrative`

**Syntax :** `singular self-narrative ACTION`

**Arguments and defaults :** `ACTION` (requis/required)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular self-narrative summarize`

**Advanced example :** `singular --root /srv/singular --life ada self-narrative summarize`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: self-narrative summarize -->
## `self-narrative summarize`

**Syntax :** `singular self-narrative summarize [--long] [--life LIFE]`

**Arguments and defaults :** `--long` (`false`); `--life` (`None`)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular self-narrative summarize --life ada`

**Advanced example :** `singular --root /srv/singular --life ada self-narrative summarize --life ada`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: cognition -->
## `cognition`

**Syntax :** `singular cognition ACTION`

**Arguments and defaults :** `ACTION` (requis/required)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular cognition self-observe`

**Advanced example :** `singular --root /srv/singular --life ada cognition self-observe`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: cognition self-observe -->
## `cognition self-observe`

**Syntax :** `singular cognition self-observe [--life LIFE]`

**Arguments and defaults :** `--life` (`None`)

**Prerequisites :** An active life for actions.

**Target root and life :** Global or local `--life`; the local option takes precedence.

**Files read or written :** Reads or writes active-life artifacts.

**Side effects :** The action may update life memory.

**Minimal example :** `singular cognition self-observe --life ada`

**Advanced example :** `singular --root /srv/singular --life ada cognition self-observe --life ada`

**Common errors :** Missing subcommand/argument or unknown life.

<!-- cli-command: synthesize -->
## `synthesize`

**Syntax :** `singular synthesize [-h] code`

**Arguments and defaults :** `code` (requis/required)

**Prerequisites :** Required inputs present and writable root/life.

**Target root and life :** Active life, except `spawn`, which targets parent paths and output.

**Files read or written :** Reads parents/spec/memory; writes child, skill, memory, or restored generation depending on command.

**Side effects :** Creates/changes artifacts; `rollback` atomically replaces active state.

**Minimal example :** `singular synthesize "result = 1"`

**Advanced example :** `singular --root /srv/singular --life ada --format json synthesize "result = 1"`

**Common errors :** Missing/invalid input, unknown generation, existing or unwritable output.

<!-- cli-command: report -->
## `report`

**Syntax :** `singular report [-h] [--id ID] [--format {table,json,plain}] [--export EXPORT]`

**Arguments and defaults :** `--id` (`None`); `--format` (`None`; choix/choices: table, json, plain); `--export` (`None`)

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular report`

**Advanced example :** `singular --root /srv/singular --life ada --format json report`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: rollback -->
## `rollback`

**Syntax :** `singular rollback [-h] --generation GENERATION`

**Arguments and defaults :** `--generation` (requis/required)

**Prerequisites :** Required inputs present and writable root/life.

**Target root and life :** Active life, except `spawn`, which targets parent paths and output.

**Files read or written :** Reads parents/spec/memory; writes child, skill, memory, or restored generation depending on command.

**Side effects :** Creates/changes artifacts; `rollback` atomically replaces active state.

**Minimal example :** `singular rollback --generation 2`

**Advanced example :** `singular --root /srv/singular --life ada --format json rollback --generation 2`

**Common errors :** Missing/invalid input, unknown generation, existing or unwritable output.

<!-- cli-command: dashboard -->
## `dashboard`

**Syntax :** `singular dashboard [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular dashboard`

**Advanced example :** `singular --root /srv/singular --life ada --format json dashboard`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: quickstart -->
## `quickstart`

**Syntax :** `singular quickstart [-h] [--name NAME]`

**Arguments and defaults :** `--name` (`None`)

**Prerequisites :** Required inputs present and writable root/life.

**Target root and life :** Active life, except `spawn`, which targets parent paths and output.

**Files read or written :** Reads parents/spec/memory; writes child, skill, memory, or restored generation depending on command.

**Side effects :** Creates/changes artifacts; `rollback` atomically replaces active state.

**Minimal example :** `singular quickstart --name Ada`

**Advanced example :** `singular --root /srv/singular --life ada --format json quickstart --name Ada`

**Common errors :** Missing/invalid input, unknown generation, existing or unwritable output.

<!-- cli-command: monitor -->
## `monitor`

**Syntax :** `singular monitor [-h] [--verbose]`

**Arguments and defaults :** `--verbose` (`false`)

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular monitor`

**Advanced example :** `singular --root /srv/singular --life ada --format json monitor`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: watch -->
## `watch`

**Syntax :** `singular watch [-h] [--interval INTERVAL] [--sources SOURCES] [--cpu-budget CPU_BUDGET] [--memory-budget MEMORY_BUDGET] [--watch-dir WATCH_DIR] [--dry-run]`

**Arguments and defaults :** `--interval` (`5.0`); `--sources` (`file,weather,runs,folder`); `--cpu-budget` (`50.0`); `--memory-budget` (`512.0`); `--watch-dir` (`None`); `--dry-run` (`false`)

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular watch --dry-run`

**Advanced example :** `singular --root /srv/singular --life ada --format json watch --dry-run`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: orchestrate -->
## `orchestrate`

**Syntax :** `singular orchestrate [-h] {run} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular orchestrate run --dry-run`

**Advanced example :** `singular --root /srv/singular --life ada --format json orchestrate run --dry-run`

**Common errors :** Missing subcommand.

<!-- cli-command: orchestrate run -->
## `orchestrate run`

**Syntax :** `singular orchestrate run [-h] [--veille-seconds VEILLE_SECONDS] [--action-seconds ACTION_SECONDS] [--introspection-seconds INTROSPECTION_SECONDS] [--sommeil-seconds SOMMEIL_SECONDS] [--poll-interval POLL_INTERVAL] [--tick-budget TICK_BUDGET] [--lifecycle-config LIFECYCLE_CONFIG] [--dry-run]`

**Arguments and defaults :** `--veille-seconds` (`None`); `--action-seconds` (`None`); `--introspection-seconds` (`None`); `--sommeil-seconds` (`None`); `--poll-interval` (`None`); `--tick-budget` (`None`); `--lifecycle-config` (`None`); `--dry-run` (`false`)

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular orchestrate run --dry-run`

**Advanced example :** `singular --root /srv/singular --life ada --format json orchestrate run --dry-run`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: daemon -->
## `daemon`

**Syntax :** `singular daemon [-h] --life LIFE [--interval INTERVAL] [--budget-seconds BUDGET_SECONDS] [--max-errors MAX_ERRORS] [--dashboard] [--dry-run]`

**Arguments and defaults :** `--life` (requis/required); `--interval` (`5.0`); `--budget-seconds` (`None`); `--max-errors` (`3`); `--dashboard` (`false`); `--dry-run` (`false`)

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular daemon --life ada --budget-seconds 30 --dry-run`

**Advanced example :** `singular --root /srv/singular --life ada --format json daemon --life ada --budget-seconds 30 --dry-run`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: diagnose -->
## `diagnose`

**Syntax :** `singular diagnose [-h] {sandbox,evolution} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular diagnose sandbox`

**Advanced example :** `singular --root /srv/singular --life ada --format json diagnose sandbox`

**Common errors :** Missing subcommand.

<!-- cli-command: diagnose sandbox -->
## `diagnose sandbox`

**Syntax :** `singular diagnose sandbox [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular diagnose sandbox`

**Advanced example :** `singular --root /srv/singular --life ada --format json diagnose sandbox`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: diagnose evolution -->
## `diagnose evolution`

**Syntax :** `singular diagnose evolution [-h] [--life LIFE]`

**Arguments and defaults :** `--life` (`None`)

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular diagnose evolution`

**Advanced example :** `singular --root /srv/singular --life ada --format json diagnose evolution`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: retention -->
## `retention`

**Syntax :** `singular retention [-h] {run,status,config} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular retention status`

**Advanced example :** `singular --root /srv/singular --life ada --format json retention status`

**Common errors :** Missing subcommand.

<!-- cli-command: retention run -->
## `retention run`

**Syntax :** `singular retention run [-h] [--dry-run]`

**Arguments and defaults :** `--dry-run` (`false`)

**Prerequisites :** Write permission; appropriate confirmation/destructive option.

**Target root and life :** Global root for config/retention/uninstall; active life for beliefs.

**Files read or written :** Writes/deletes configuration, `runs/`, `mem/`, beliefs, or `lives/` depending on command.

**Side effects :** Persistent effect; purge/reset/uninstall may be irreversible. Use dry-run when available.

**Minimal example :** `singular retention run --dry-run`

**Advanced example :** `singular --root /srv/singular --life ada --format json retention run --dry-run`

**Common errors :** Missing required option, invalid key/value, refused confirmation, repository protection, permissions.

<!-- cli-command: retention status -->
## `retention status`

**Syntax :** `singular retention status [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular retention status`

**Advanced example :** `singular --root /srv/singular --life ada --format json retention status`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: retention config -->
## `retention config`

**Syntax :** `singular retention config [-h] {show} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular retention config show`

**Advanced example :** `singular --root /srv/singular --life ada --format json retention config show`

**Common errors :** Missing subcommand.

<!-- cli-command: retention config show -->
## `retention config show`

**Syntax :** `singular retention config show [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular retention config show`

**Advanced example :** `singular --root /srv/singular --life ada --format json retention config show`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: doctor -->
## `doctor`

**Syntax :** `singular doctor [-h] [--fix]`

**Arguments and defaults :** `--fix` (`false`)

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular doctor`

**Advanced example :** `singular --root /srv/singular --life ada --format json doctor`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: config -->
## `config`

**Syntax :** `singular config [-h] {openai,providers,root} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular config root show`

**Advanced example :** `singular --root /srv/singular --life ada --format json config root show`

**Common errors :** Missing subcommand.

<!-- cli-command: config openai -->
## `config openai`

**Syntax :** `singular config openai [-h] [--api-key API_KEY] [--shell-profile SHELL_PROFILE] [--test]`

**Arguments and defaults :** `--api-key` (`None`); `--shell-profile` (`None`); `--test` (`false`)

**Prerequisites :** Write permission; appropriate confirmation/destructive option.

**Target root and life :** Global root for config/retention/uninstall; active life for beliefs.

**Files read or written :** Writes/deletes configuration, `runs/`, `mem/`, beliefs, or `lives/` depending on command.

**Side effects :** Persistent effect; purge/reset/uninstall may be irreversible. Use dry-run when available.

**Minimal example :** `singular config openai --api-key sk-example-key`

**Advanced example :** `singular --root /srv/singular --life ada --format json config openai --api-key sk-example-key`

**Common errors :** Missing required option, invalid key/value, refused confirmation, repository protection, permissions.

<!-- cli-command: config providers -->
## `config providers`

**Syntax :** `singular config providers [-h] {doctor,setup} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular config providers doctor`

**Advanced example :** `singular --root /srv/singular --life ada --format json config providers doctor`

**Common errors :** Missing subcommand.

<!-- cli-command: config providers doctor -->
## `config providers doctor`

**Syntax :** `singular config providers doctor [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular config providers doctor`

**Advanced example :** `singular --root /srv/singular --life ada --format json config providers doctor`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: config root -->
## `config root`

**Syntax :** `singular config root [-h] {set,show,install-systemd} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular config root show`

**Advanced example :** `singular --root /srv/singular --life ada --format json config root show`

**Common errors :** Missing subcommand.

<!-- cli-command: config root set -->
## `config root set`

**Syntax :** `singular config root set [-h] [--scope {global,project}] path`

**Arguments and defaults :** `path` (requis/required); `--scope` (`global`; choix/choices: global, project)

**Prerequisites :** Write permission; appropriate confirmation/destructive option.

**Target root and life :** Global root for config/retention/uninstall; active life for beliefs.

**Files read or written :** Writes/deletes configuration, `runs/`, `mem/`, beliefs, or `lives/` depending on command.

**Side effects :** Persistent effect; purge/reset/uninstall may be irreversible. Use dry-run when available.

**Minimal example :** `singular config root set /srv/singular`

**Advanced example :** `singular --root /srv/singular --life ada --format json config root set /srv/singular`

**Common errors :** Missing required option, invalid key/value, refused confirmation, repository protection, permissions.

<!-- cli-command: config root show -->
## `config root show`

**Syntax :** `singular config root show [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular config root show`

**Advanced example :** `singular --root /srv/singular --life ada --format json config root show`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: config root install-systemd -->
## `config root install-systemd`

**Syntax :** `singular [--root PATH] [--life NAME] config root install-systemd [--user USER] [--group GROUP] [--binary PATH] [--environment-file PATH] [--unit-file PATH]`

**Arguments and defaults :** `singular` user/group; `/etc/singular/singular.env` environment; `/etc/systemd/system/singular.service` unit; binary discovered from `PATH`.

**Prerequisites :** An existing active life, a `singular` binary, `mem/` and `runs/` writable by the service user, permission to write `/etc`, and systemd.

**Target root and life :** The resolved root and active life (or `--life`) are pinned as `SINGULAR_ROOT` and `SINGULAR_HOME`.

**Files read or written :** Atomically generates the non-secret environment file and rendered unit. Non-secret provider variables (`LLM_PROVIDER`, model names, and Ollama settings) are retained; API keys are excluded.

**Side effects :** Runs `systemctl daemon-reload`; activation remains explicit through `systemctl enable --now singular`.

**Minimal example :** `sudo singular --root /var/lib/singular config root install-systemd`

**Advanced example :** `sudo singular --root /srv/singular --life ada config root install-systemd --user singular --group singular --binary /srv/app/.venv/bin/singular`

**Diagnostics :** `systemctl cat singular`; `cat /etc/singular/singular.env`; `sudo -u singular test -w <life>/mem -a -w <life>/runs`; `sudo -u singular SINGULAR_ROOT=<root> singular lives list`.

**Common errors :** Missing life/directory or binary, unknown account, or incompatible permissions; the diagnostic identifies the command or path to fix and installs no file.

<!-- cli-command: lives -->
## `lives`

**Syntax :** `singular lives [-h] {list,create,use,delete,archive,memorial,clone,reproduce,relations,ally,rival,reconcile,proximity} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular lives list`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives list`

**Common errors :** Missing subcommand.

<!-- cli-command: lives list -->
## `lives list`

**Syntax :** `singular lives list [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads `lives/registry.json` and affected life directories.

**Side effects :** Display only.

**Minimal example :** `singular lives list`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives list`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives create -->
## `lives create`

**Syntax :** `singular lives create [-h] [--name NAME] [--curiosity CURIOSITY] [--patience PATIENCE] [--playfulness PLAYFULNESS] [--optimism OPTIMISM] [--resilience RESILIENCE] [--starter-profile STARTER_PROFILE] [--starter-skill STARTER_SKILL]`

**Arguments and defaults :** `--name` (`New life`); `--curiosity` (`None`); `--patience` (`None`); `--playfulness` (`None`); `--optimism` (`None`); `--resilience` (`None`); `--starter-profile` (`assistant`); `--starter-skill` (`[]`)

**Prerequisites :** Writable root; valid starter profile.

**Target root and life :** Resolved root; creates and activates a new life.

**Files read or written :** Writes `lives/registry.json` and `lives/<slug>/` (identity, psyche, skills, memory).

**Side effects :** Creates directories and sets `SINGULAR_HOME`; `birth` is deprecated.

**Minimal example :** `singular lives create --name Ada`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives create --name Ada`

**Common errors :** Trait outside [0,1], invalid name/profile, unwritable root.

<!-- cli-command: lives use -->
## `lives use`

**Syntax :** `singular lives use [-h] name`

**Arguments and defaults :** `name` (requis/required)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives use ada`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives use ada`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives delete -->
## `lives delete`

**Syntax :** `singular lives delete [-h] name`

**Arguments and defaults :** `name` (requis/required)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives delete ada`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives delete ada`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives archive -->
## `lives archive`

**Syntax :** `singular lives archive [-h] name`

**Arguments and defaults :** `name` (requis/required)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives archive ada`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives archive ada`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives memorial -->
## `lives memorial`

**Syntax :** `singular lives memorial [-h] [--message MESSAGE] name`

**Arguments and defaults :** `name` (requis/required); `--message` (`Merci pour ce cycle de vie.`)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives memorial ada`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives memorial ada`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives clone -->
## `lives clone`

**Syntax :** `singular lives clone [-h] [--new-name NEW_NAME] name`

**Arguments and defaults :** `name` (requis/required); `--new-name` (`None`)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives clone ada`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives clone ada`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives reproduce -->
## `lives reproduce`

**Syntax :** `singular lives reproduce [-h] [--new-name NEW_NAME] parent_a parent_b`

**Arguments and defaults :** `parent_a` (requis/required); `parent_b` (requis/required); `--new-name` (`None`)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives reproduce ada bob`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives reproduce ada bob`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives relations -->
## `lives relations`

**Syntax :** `singular lives relations [-h] [--name NAME]`

**Arguments and defaults :** `--name` (`None`)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads `lives/registry.json` and affected life directories.

**Side effects :** Display only.

**Minimal example :** `singular lives relations`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives relations`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives ally -->
## `lives ally`

**Syntax :** `singular lives ally [-h] name other`

**Arguments and defaults :** `name` (requis/required); `other` (requis/required)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives ally ada bob`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives ally ada bob`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives rival -->
## `lives rival`

**Syntax :** `singular lives rival [-h] name other`

**Arguments and defaults :** `name` (requis/required); `other` (requis/required)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives rival ada bob`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives rival ada bob`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives reconcile -->
## `lives reconcile`

**Syntax :** `singular lives reconcile [-h] name other`

**Arguments and defaults :** `name` (requis/required); `other` (requis/required)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives reconcile ada bob`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives reconcile ada bob`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: lives proximity -->
## `lives proximity`

**Syntax :** `singular lives proximity [-h] --score SCORE name`

**Arguments and defaults :** `name` (requis/required); `--score` (requis/required)

**Prerequisites :** Existing registry; named lives must exist.

**Target root and life :** Resolved root; named life/lives, or active life for `relations`.

**Files read or written :** Reads/writes `lives/registry.json` and affected life directories.

**Side effects :** Changes registry and/or life data; `delete` is permanent.

**Minimal example :** `singular lives proximity ada --score 0.7`

**Advanced example :** `singular --root /srv/singular --life ada --format json lives proximity ada --score 0.7`

**Common errors :** Unknown/ambiguous life, ineligible reproduction, score outside [0,1], active deletion refused.

<!-- cli-command: values -->
## `values`

**Syntax :** `singular values [-h] {show} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular values show`

**Advanced example :** `singular --root /srv/singular --life ada --format json values show`

**Common errors :** Missing subcommand.

<!-- cli-command: values show -->
## `values show`

**Syntax :** `singular values show [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular values show`

**Advanced example :** `singular --root /srv/singular --life ada --format json values show`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: policy -->
## `policy`

**Syntax :** `singular policy [-h] {show,set} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular policy show`

**Advanced example :** `singular --root /srv/singular --life ada --format json policy show`

**Common errors :** Missing subcommand.

<!-- cli-command: policy show -->
## `policy show`

**Syntax :** `singular policy show [-h]`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular policy show`

**Advanced example :** `singular --root /srv/singular --life ada --format json policy show`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: policy set -->
## `policy set`

**Syntax :** `singular policy set [-h] --key {autonomy.auto_rollback_cost_threshold,autonomy.auto_rollback_failure_threshold,autonomy.circuit_breaker_cooldown_seconds,autonomy.circuit_breaker_threshold,autonomy.circuit_breaker_window_seconds,autonomy.mutation_quota_per_window,autonomy.mutation_quota_window_seconds,autonomy.runtime_blacklisted_capabilities,autonomy.runtime_call_quota_per_hour,autonomy.safe_mode,autonomy.safe_mode_review_required_skill_families,autonomy.skill_circuit_breaker_cooldown_seconds,autonomy.skill_circuit_breaker_cost_threshold,autonomy.skill_circuit_breaker_failure_threshold,forgetting.enabled,forgetting.max_episodic_entries,memory.preserve_threshold,permissions.forbidden_paths,permissions.force_allow_paths,permissions.modifiable_paths,permissions.review_required_paths} --value VALUE`

**Arguments and defaults :** `--key` (requis/required; choix/choices: autonomy.auto_rollback_cost_threshold, autonomy.auto_rollback_failure_threshold, autonomy.circuit_breaker_cooldown_seconds, autonomy.circuit_breaker_threshold, autonomy.circuit_breaker_window_seconds, autonomy.mutation_quota_per_window, autonomy.mutation_quota_window_seconds, autonomy.runtime_blacklisted_capabilities, autonomy.runtime_call_quota_per_hour, autonomy.safe_mode, autonomy.safe_mode_review_required_skill_families, autonomy.skill_circuit_breaker_cooldown_seconds, autonomy.skill_circuit_breaker_cost_threshold, autonomy.skill_circuit_breaker_failure_threshold, forgetting.enabled, forgetting.max_episodic_entries, memory.preserve_threshold, permissions.forbidden_paths, permissions.force_allow_paths, permissions.modifiable_paths, permissions.review_required_paths); `--value` (requis/required)

**Prerequisites :** Write permission; appropriate confirmation/destructive option.

**Target root and life :** Global root for config/retention/uninstall; active life for beliefs.

**Files read or written :** Writes/deletes configuration, `runs/`, `mem/`, beliefs, or `lives/` depending on command.

**Side effects :** Persistent effect; purge/reset/uninstall may be irreversible. Use dry-run when available.

**Minimal example :** `singular policy set --key autonomy.safe_mode --value true`

**Advanced example :** `singular --root /srv/singular --life ada --format json policy set --key autonomy.safe_mode --value true`

**Common errors :** Missing required option, invalid key/value, refused confirmation, repository protection, permissions.

<!-- cli-command: ecosystem -->
## `ecosystem`

**Syntax :** `singular ecosystem [-h] {run} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular ecosystem run --life ada --budget-seconds 10`

**Advanced example :** `singular --root /srv/singular --life ada --format json ecosystem run --life ada --budget-seconds 10`

**Common errors :** Missing subcommand.

<!-- cli-command: ecosystem run -->
## `ecosystem run`

**Syntax :** `singular ecosystem run [-h] [--life ECOSYSTEM_LIVES] [--life-group ECOSYSTEM_GROUPS] [--checkpoint CHECKPOINT] --budget-seconds BUDGET_SECONDS [--run-id RUN_ID]`

**Arguments and defaults :** `--life` (`[]`); `--life-group` (`[]`); `--checkpoint` (`None`); `--budget-seconds` (requis/required); `--run-id` (`ecosystem`)

**Prerequisites :** Active life and mode-specific config/provider; positive budget when required.

**Target root and life :** Life selected by `--home`/`--life`; `ecosystem run` targets all listed lives.

**Files read or written :** Reads config and memory; writes events, checkpoints, and runs under the life. `embodiment` reads `--config`; `dashboard` serves these data.

**Side effects :** May call an LLM/sensor, mutate skills, write logs, or start a service; `--dry-run` limits mutations.

**Minimal example :** `singular ecosystem run --life ada --budget-seconds 10`

**Advanced example :** `singular --root /srv/singular --life ada --format json ecosystem run --life ada --budget-seconds 10`

**Common errors :** Missing life/provider/config, invalid budget/interval, unavailable sensor, daemon error limit.

<!-- cli-command: beliefs -->
## `beliefs`

**Syntax :** `singular beliefs [-h] {audit,reset} ...`

**Arguments and defaults :** Aucune / None.

**Prerequisites :** None; select a subcommand.

**Target root and life :** Registry root; no life until a subcommand is selected.

**Files read or written :** No file directly.

**Side effects :** Shows help or delegates; no direct effect.

**Minimal example :** `singular beliefs audit`

**Advanced example :** `singular --root /srv/singular --life ada --format json beliefs audit`

**Common errors :** Missing subcommand.

<!-- cli-command: beliefs audit -->
## `beliefs audit`

**Syntax :** `singular beliefs audit [-h] [--limit LIMIT]`

**Arguments and defaults :** `--limit` (`25`)

**Prerequisites :** Active life for life diagnostics; relevant dependencies available.

**Target root and life :** `SINGULAR_HOME`/selected life; `doctor` and `config root show` are global.

**Files read or written :** Depending on command, reads registry, `mem/`, `runs/`, `skills/`, policy, or config; `report --export` writes the requested file.

**Side effects :** Display only, except report export and `doctor --fix` (Windows user PATH).

**Minimal example :** `singular beliefs audit`

**Advanced example :** `singular --root /srv/singular --life ada --format json beliefs audit`

**Common errors :** Missing life/run/file, invalid JSON, sandbox failure, invalid format/export.

<!-- cli-command: beliefs reset -->
## `beliefs reset`

**Syntax :** `singular beliefs reset [-h] (--hypothesis HYPOTHESIS | --prefix PREFIX | --all)`

**Arguments and defaults :** `--hypothesis` (`None`); `--prefix` (`None`); `--all` (`false`)

**Prerequisites :** Write permission; appropriate confirmation/destructive option.

**Target root and life :** Global root for config/retention/uninstall; active life for beliefs.

**Files read or written :** Writes/deletes configuration, `runs/`, `mem/`, beliefs, or `lives/` depending on command.

**Side effects :** Persistent effect; purge/reset/uninstall may be irreversible. Use dry-run when available.

**Minimal example :** `singular beliefs reset --hypothesis test`

**Advanced example :** `singular --root /srv/singular --life ada --format json beliefs reset --hypothesis test`

**Common errors :** Missing required option, invalid key/value, refused confirmation, repository protection, permissions.

<!-- cli-command: uninstall -->
## `uninstall`

**Syntax :** `singular uninstall [-h] (--keep-lives | --purge-lives) [--yes] [--force]`

**Arguments and defaults :** `--keep-lives` (`false`); `--purge-lives` (`false`); `--yes` (`false`); `--force` (`false`)

**Prerequisites :** Write permission; appropriate confirmation/destructive option.

**Target root and life :** Global root for config/retention/uninstall; active life for beliefs.

**Files read or written :** Writes/deletes configuration, `runs/`, `mem/`, beliefs, or `lives/` depending on command.

**Side effects :** Persistent effect; purge/reset/uninstall may be irreversible. Use dry-run when available.

**Minimal example :** `singular uninstall --keep-lives --yes`

**Advanced example :** `singular --root /srv/singular --life ada --format json uninstall --keep-lives --yes`

**Common errors :** Missing required option, invalid key/value, refused confirmation, repository protection, permissions.

## Aliases and help

`veille` is an exact alias of `watch`; `talk --live` is a deprecated alias for `talk --life`; `birth` can be disabled with `SINGULAR_ENABLE_BIRTH_ALIAS=0`. `singular <command> --help` remains the executable source for metavar details.

<!-- cli-command: config providers setup -->
## `config providers setup`

**Syntax :** `singular config providers setup [-h] [--model MODEL] [--non-interactive] [--pull] [--timeout TIMEOUT] {ollama}`

**Arguments and defaults :** provider `ollama` (required); `--model` (`OLLAMA_MODEL`, then provider default); `--non-interactive` (`false`); `--pull` (`false`); `--timeout` (`120.0`).

**Prerequisites :** A reachable `ollama serve`; automated installation must explicitly combine `--non-interactive --pull`.

**Target root and life :** No root or life; only the service selected by `OLLAMA_HOST`.

**Files read or written :** No Singular file; Ollama manages downloaded model data.

**Side effects :** Lists models, optionally runs `ollama pull`, and validates a minimal generation. `talk` never downloads models.

**Minimal example :** `singular config providers setup ollama`

**Advanced example :** `singular config providers setup ollama --non-interactive --pull --model llama3.2`

**Common errors :** `service_stopped`, `command_missing`, `model_missing`, `download_incomplete`, `timeout`, or `invalid_generation`; every failure includes remediation.
