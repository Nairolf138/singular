# Tutorial — creating a Singular life

This tutorial walks through a complete local path: create a life, add a skill, run an evolutionary tick, inspect memory and the checkpoint, then read the logs. The commands use an isolated lab root so experiments do not mix with your regular lives.

## Prerequisites

Install Singular from the repository root:

```bash
pip install -e .[yaml,dashboard,viz]
```

Create a reproducible workspace:

```bash
export SINGULAR_ROOT="$PWD/.singular-tutorial"
rm -rf "$SINGULAR_ROOT"
mkdir -p "$SINGULAR_ROOT"
```

> On Windows PowerShell, use `$env:SINGULAR_ROOT = "$PWD/.singular-tutorial"` instead.

## 1. Create a life

```bash
singular --root "$SINGULAR_ROOT" lives create --name Lumen --curiosity 0.75 --patience 0.55
singular --root "$SINGULAR_ROOT" lives list
```

The command creates a life directory under `lives/`, selects it in the registry, and initializes:

- `skills/`: executable and mutable capabilities;
- `mem/`: memory artifacts (`psyche.json`, `profile.json`, `values.yaml`, JSONL journals, and more);
- `runs/`: traces for runs executed by this life.

Check the active life:

```bash
singular --root "$SINGULAR_ROOT" status --format table
```

## 2. Add a simple skill

Autonomous mutations normally write under `skills/`, but you can also add a starter skill manually. First resolve the life path:

```bash
LIFE_DIR=$(python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["SINGULAR_ROOT"])
registry = json.loads((root / "lives" / "registry.json").read_text())
active = registry["active"]
print(registry["lives"][active]["path"])
PY
)
```

Add a pure deterministic skill:

```bash
cat > "$LIFE_DIR/skills/greet.py" <<'PY'
def greet(name="friend"):
    """Return a deterministic greeting."""
    return f"Hello {name}!"

result = greet("Lumen")
PY
```

Good practices for a first skill:

- one short main function;
- no network access;
- no writes outside the organism directory;
- a `result` variable that is useful if the loop evaluates it in the sandbox.

## 3. Run an evolutionary tick

The modern loop interface is time-based: `--budget-seconds` replaces the older tick-count interface.

```bash
singular --root "$SINGULAR_ROOT" --life lumen loop --budget-seconds 5 --run-id tutorial_tick
```

During this tick, Singular may select a skill, propose a mutation, evaluate it in the sandbox, score the result, apply write governance, and journal the verdict. A rejected mutation is normal: the log explains whether the rejection came from the sandbox, score, governance, or a quota.

## 4. Inspect memory and checkpoint

The life memory lives in `mem/`:

```bash
find "$LIFE_DIR/mem" -maxdepth 1 -type f | sort
python -m json.tool "$LIFE_DIR/mem/psyche.json" | head -40
```

Useful files:

- `mem/psyche.json`: traits, mood, fatigue, and possible social signals;
- `mem/profile.json`: identity and birth metadata;
- `mem/episodic.jsonl`: lived episodes, one JSON object per line;
- `mem/procedural.jsonl`: learning and execution traces;
- `mem/generations.jsonl`: mutation attempts and verdicts;
- `mem/policy_decisions.jsonl`: blocked, forced, or review-required governance decisions.

The default `loop` checkpoint is stored at the life root:

```bash
python -m json.tool "$LIFE_DIR/life_checkpoint.json" | head -80
```

It is used to resume loop state: current iteration, best known score, metadata, and persistent run state depending on the version.

## 5. Interpret logs

Display a human-readable summary:

```bash
singular --root "$SINGULAR_ROOT" --life lumen report --id tutorial_tick --format plain
```

Then inspect raw files when needed:

```bash
find "$LIFE_DIR/runs" -maxdepth 3 -type f | sort
```

Reading hints:

- `accepted` or `improved` means a mutation was kept;
- `rejected`, `sandbox_error`, `syntax_error`, or `missing_result` means a technical rejection;
- `governance_violation` means a forbidden or unauthorized write;
- `circuit_breaker_open` means too many violations in a short window;
- `social_relation_update` appears in multi-life runs when the social graph changes.

If the report is empty, verify the `run-id`, root, and active life:

```bash
singular --root "$SINGULAR_ROOT" lives list
singular --root "$SINGULAR_ROOT" --life lumen status --verbose
```

## Reproduction tutorial — two parents and one child

Reproduction crosses two organisms from their life directories. Create two parents:

```bash
singular --root "$SINGULAR_ROOT" lives create --name Alpha --curiosity 0.80 --resilience 0.70
singular --root "$SINGULAR_ROOT" lives create --name Beta --curiosity 0.45 --resilience 0.90
```

Resolve their paths:

```bash
python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["SINGULAR_ROOT"])
registry = json.loads((root / "lives" / "registry.json").read_text())
for slug in ("alpha", "beta"):
    print(slug, registry["lives"][slug]["path"])
PY
```

Select parents with auditable criteria:

1. **Social compatibility**: a positive `SocialGraph` relation if the parents have interacted;
2. **Skill complementarity**: different capabilities increase diversity;
3. **Viability**: both parents have sufficient health;
4. **Governance**: child writes must stay in an authorized zone.

The direct command creates the child:

```bash
ALPHA_DIR=$(python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["SINGULAR_ROOT"])
registry = json.loads((root / "lives" / "registry.json").read_text())
print(registry["lives"]["alpha"]["path"])
PY
)
BETA_DIR=$(python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["SINGULAR_ROOT"])
registry = json.loads((root / "lives" / "registry.json").read_text())
print(registry["lives"]["beta"]["path"])
PY
)
singular --root "$SINGULAR_ROOT" spawn "$ALPHA_DIR" "$BETA_DIR" --out-dir "$SINGULAR_ROOT/children/alpha-beta-child"
```

What happens:

- `crossover` picks one skill from each parent, checks that function signatures match, and produces a hybrid skill;
- `inherit_psyche`, `inherit_values`, and `inherit_episodic_memory` combine non-code artifacts;
- `authorize_reproduction_write` simulates and then applies `MutationGovernancePolicy.enforce_write` before writing the child skill;
- if the output path is forbidden or unauthorized, reproduction fails before destructive modification.

Inspect the child:

```bash
find "$SINGULAR_ROOT/children/alpha-beta-child" -maxdepth 3 -type f | sort
python -m json.tool "$SINGULAR_ROOT/children/alpha-beta-child/mem/psyche.json" | head -60
```

## Multi-agent tutorial — help, response, and SocialGraph

Ecosystem mode runs multiple lives in a shared loop. Lives can ask for help when their score is low, offer a skill when confidence is high, and update their relationships.

Optionally prepare an initial relationship:

```bash
singular --root "$SINGULAR_ROOT" lives ally alpha beta
singular --root "$SINGULAR_ROOT" lives relations --name alpha
```

Run a short multi-life loop:

```bash
singular --root "$SINGULAR_ROOT" ecosystem run --life alpha --life beta --budget-seconds 5 --run-id tutorial_ecosystem
```

Inside the loop:

1. a struggling life emits a help request (`help.requested`);
2. a confident life may respond with an offer (`help.offered`) or an answer;
3. governance checks inter-life interactions, influence level, and conflicts;
4. after successful assistance, `SocialGraph.update_relation` increases affinity and trust, and lowers rivalry;
5. after a resource conflict, the relation can become more rivalrous and may trigger mediation when thresholds are exceeded.

Inspect the persistent social graph:

```bash
python -m json.tool "$SINGULAR_ROOT/mem/social_graph.json" 2>/dev/null || true
find "$SINGULAR_ROOT" -path '*social_graph.json' -print
```

Depending on the command and active `SINGULAR_HOME`, the graph can be written in root-level memory or active-life memory. Events to search for in logs include `help.requested`, `help.offered`, `help.completed`, `answer`, `social_relation_update`, `resource_conflict`, and `governance_violation`.
