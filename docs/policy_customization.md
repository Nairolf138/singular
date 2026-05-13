# Governance and `policy.yaml` customization guide

Singular uses a strict, versioned governance policy to decide what an organism may read, mutate, create, expose, or do with other lives. The default root-level file is `policy.yaml`. If the file is missing, Singular can generate a default policy from the built-in schema.

Although the repository file is named `policy.yaml`, its content may be YAML or JSON-compatible YAML. The current schema version is `1`, and unknown top-level or section keys are rejected by validation.

## Where the active policy lives

The active policy is resolved from the current registry root:

```bash
singular --root ./lab policy show --format table
```

Programmatically, the policy path is equivalent to:

```text
$SINGULAR_ROOT/policy.yaml
```

If `SINGULAR_ROOT` is unset, Singular falls back to its configured/default registry root. For repeatable experiments, pass `--root` explicitly.

## Safe editing workflow

1. Create an isolated root or a backup of the current file.
2. Inspect the active values:
   ```bash
   singular --root ./lab policy show --format plain
   ```
3. Change one setting at a time. Prefer the CLI for supported scalar edits:
   ```bash
   singular --root ./lab policy set --key autonomy.safe_mode --value true
   ```
4. Re-run validation by showing the policy again:
   ```bash
   singular --root ./lab policy show --format table
   ```
5. Run a short loop and inspect `mem/policy_decisions.jsonl` for blocked or review-required decisions.

If validation fails, Singular reports a `PolicySchemaError` and refuses to use malformed or unknown keys.

## Policy structure

### `version`

Must match the supported policy schema version. Current value:

```yaml
version: 1
```

Do not increment this manually unless the code has been upgraded to support the new schema.

### `memory`

Controls destructive rewrites:

```yaml
memory:
  preserve_threshold: 0.6
```

When memory preservation has sufficient value weight, an existing file rewrite is blocked if the new content appears to truncate too much of the previous content. Raise this for conservative preservation; lower it only when controlled compaction is expected.

### `forgetting`

Controls memory retention:

```yaml
forgetting:
  enabled: true
  max_episodic_entries: 5000
```

Use this to bound long-running organisms. Disabling forgetting may be useful for audit labs but increases storage growth.

### `sensors`

Controls host/environment signal exposure:

```yaml
sensors:
  allowed: [host_metrics, artifact_scan, virtual_environment]
  blocked: []
  max_export_granularity: standard
  anonymization:
    enabled: true
    block_sensitive_by_default: true
    allow_sensitive_metrics_opt_in: false
    redact_machine_user_info: true
    sensitive_metric_keys_blocklist:
      - hostname
      - cwd
      - username
```

Guidance:

- keep anonymization enabled for shared logs;
- add sensitive keys to the blocklist rather than post-processing logs later;
- prefer `standard` granularity unless debugging a local-only sensor issue;
- use `blocked` to deny a sensor even if it appears in `allowed`.

### `permissions`

Controls write zones:

```yaml
permissions:
  modifiable_paths: [skills]
  review_required_paths: [skills/experimental]
  forbidden_paths: [src, .git, mem, runs, tests]
  force_allow_paths: []
```

Meanings:

- `modifiable_paths`: autonomous writes may proceed after simulation;
- `review_required_paths`: writes are denied automatically and require human review;
- `forbidden_paths`: writes are blocked and counted as governance violations;
- `force_allow_paths`: emergency override that permits matching paths and journals a forced decision.

Recommended practice:

- keep autonomous writes limited to `skills/`;
- never allow `.git`, `src`, `tests`, `mem`, or `runs` for ordinary autonomous mutation;
- use `skills/experimental` for work that should be surfaced but not auto-applied;
- treat `force_allow_paths` as temporary and document why it was used.

### `autonomy`

Controls mutation, runtime execution, rollback and circuit breakers:

```yaml
autonomy:
  safe_mode: false
  mutation_quota_per_window: 25
  mutation_quota_window_seconds: 300.0
  runtime_call_quota_per_hour: 240
  runtime_blacklisted_capabilities: []
  auto_rollback_failure_threshold: 5
  auto_rollback_cost_threshold: 10.0
  safe_mode_review_required_skill_families: [network, shell, filesystem]
  circuit_breaker_threshold: 3
  circuit_breaker_window_seconds: 180.0
  circuit_breaker_cooldown_seconds: 300.0
  skill_creation_quota_per_window: 3
  skill_creation_quota_window_seconds: 900.0
  file_creation_review_required: false
  skill_circuit_breaker_failure_threshold: 3
  skill_circuit_breaker_cost_threshold: 5.0
  skill_circuit_breaker_cooldown_seconds: 600.0
```

Important knobs:

- `safe_mode`: disables autonomous mutations and makes risky skill families require review;
- `mutation_quota_per_window`: caps mutation frequency;
- `runtime_call_quota_per_hour`: caps skill execution calls;
- `runtime_blacklisted_capabilities`: blocks named runtime capabilities;
- `auto_rollback_*`: thresholds for rollback-oriented failure handling;
- `circuit_breaker_*`: opens a global cooldown after repeated governance violations;
- `skill_creation_*`: limits automatic creation of new skill files;
- `file_creation_review_required`: requires manual review for new skill files;
- `skill_circuit_breaker_*`: isolates a repeatedly failing or expensive skill.

Conservative profile for demos:

```bash
singular --root ./lab policy set --key autonomy.safe_mode --value true
```

Exploration profile for a local sandbox only:

```yaml
autonomy:
  safe_mode: false
  mutation_quota_per_window: 10
  mutation_quota_window_seconds: 300.0
  file_creation_review_required: true
```

Keep exploration roots disposable and inspect policy decisions after every run.

### `social`

Controls interactions between lives:

```yaml
social:
  max_influence_per_life: 0.35
  blocked_hostile_behaviors:
    - threat.explicit
    - harassment.explicit
    - sabotage.explicit
    - abuse.explicit
  conflict_events:
    - conflict.explicit
    - betrayal
    - resource_conflict
  conflict_mediation_threshold: 3
  conflict_window_seconds: 900.0
  mediation_cooldown_seconds: 600.0
  prudent_mode_on_mediation: true
```

These settings affect multi-agent help, competition, social updates and reproduction arbitration:

- explicit hostile behaviors are blocked;
- influence transfer above `max_influence_per_life` requires review;
- repeated conflict events pause the pair via mediation cooldown;
- `prudent_mode_on_mediation` can make the whole system more cautious after social escalation.

## Reproduction governance

Reproduction uses the same write policy as mutation. Before a child skill is written, Singular simulates and enforces the target path. This means:

- output under an authorized child `skills/` directory is allowed;
- output under `mem/`, `runs/`, `src/`, `tests/` or `.git/` is blocked;
- review-required paths do not auto-write;
- blocked attempts are journaled in `mem/policy_decisions.jsonl`.

If you customize child output paths, keep the child root structured like:

```text
child/
  skills/
  mem/
```

## Equivalent governance files

Some deployments may wrap or generate `policy.yaml` from an environment-specific governance file. The equivalent file must still produce the same runtime schema:

- root keys: `version`, `memory`, `forgetting`, `sensors`, `permissions`, `autonomy`, `social`;
- all required keys inside each section;
- no unknown keys;
- values with the expected types and minimums.

A generator should write the resolved file to `$SINGULAR_ROOT/policy.yaml` before launching Singular, then verify with:

```bash
singular --root "$SINGULAR_ROOT" policy show --format json
```

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `unexpected root keys` | Extra section or typo | Remove the unknown key or update the code/schema together |
| `missing keys` | Partial manual file | Start from `singular policy show` or the default file and edit incrementally |
| Mutations never happen | `safe_mode` true or circuit breaker open | Check `policy show`, `status --verbose`, and `mem/policy_decisions.jsonl` |
| Write blocked outside `skills/` | Path not in `modifiable_paths` | Keep autonomous writes under `skills/` or require review |
| Social help is blocked | Influence cap, hostility block, or mediation cooldown | Reduce influence, reconcile lives, or wait for cooldown |
| Child reproduction fails | Output path violates write policy or parent skills are incompatible | Use a child root with `skills/`; ensure parent skill signatures match |

## Audit checklist before sharing a policy

- [ ] `singular --root <root> policy show --format table` succeeds.
- [ ] `permissions.forbidden_paths` still protects source, tests, memory, runs and VCS data.
- [ ] Sensor anonymization is enabled unless logs are strictly local.
- [ ] `safe_mode` can be switched on quickly for incident response.
- [ ] Social conflict and mediation thresholds are documented.
- [ ] Any `force_allow_paths` entry has an owner, reason and removal date.
