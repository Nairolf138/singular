# Statut de vie: source de vérité

Ce document définit la sémantique officielle du statut d'une **vie** dans Singular.

## Vocabulaire canonique et champs indépendants

Deux sources de vérité indépendantes sont exposées; un endpoint ne change jamais
la signification d'un champ:

- `registry_status` est l'état administratif du registre: `active`, `archived`,
  `extinct`, `stopped` ou `unknown`;
- `life_status` est le verdict biologique: `running`, `budget_exhausted`,
  `degraded`, `mutation_paused`, `terminal`, `dead`, ou `null` lorsqu'aucun
  verdict biologique n'a été calculé.

La table de lecture des anciennes valeurs est explicite:

| ancienne valeur | `registry_status` | `life_status` |
|---|---|---|
| `degraded` | `active` | `degraded` |
| `dead` | `extinct` | `dead` |
| `archived` | `archived` | `null` |
| `stopped` | `stopped` | `null` |

`archived` et `stopped` ne constituent donc jamais une preuve de mort. Le code
canonique et cette table résident dans `singular.life.life_status`.

Chaque ligne de comparaison expose également `operator_actions`, une table de
booléens calculée côté serveur. Pour un registre `active`, `archive`, `talk` et
`emergency_stop` sont permis. Ils sont interdits pour tout autre état; les
actions non exécutantes `lives_use`, `memorial` et `clone` restent permises. Le
JavaScript consomme cette capacité et ne reconstruit pas ces règles depuis les
libellés de statut.

Ce statut est porté par `LifeMetadata.status` dans `src/singular/lives.py`, persisté via `save_registry()`, et modifié via `set_life_status()`.

## Barème pondéré de qualification vitale

Le fichier versionné `configs/life_definition.yaml` définit un score vital sur **100 points**. Ce score ne remplace pas la source de vérité du registre pour l'extinction, mais il qualifie l'état fonctionnel observé d'une vie.

Barème:

- **Identité persistante**: 20 points.
- **Registre de générations**: 15 points.
- **Cycle stable**: 20 points.
- **Objectifs intrinsèques continus**: 20 points.
- **Reproduction possible**: 10 points.
- **Narration cohérente sur N jours**: 15 points, avec `N = thresholds.minimum_narrative_trajectory_days`.

Les critères fondamentaux pour atteindre `running` sont:

- identité persistante,
- registre de générations,
- cycle stable,
- objectifs intrinsèques continus,
- narration cohérente sur la durée minimale configurée.

La reproduction possible contribue au score, mais n'est pas un critère bloquant pour `running`.

## Statuts biologiques qualifiés

Le calcul émet exclusivement les valeurs canoniques définies ci-dessus.
L’ordre de priorité est: `dead` pour une extinction confirmée, `terminal` pour
une terminalité sans preuve de mort, `budget_exhausted` ou `mutation_paused`
pour ces suspensions explicites, `running` lorsque la checklist contractuelle
est satisfaite, et `degraded` sinon. Un score élevé ne peut jamais masquer une
preuve terminale.

La configuration distribuée `life_definition.yaml` emploie les mêmes six clés
canoniques. Les anciennes clés (`alive`, `fragile`, etc.) ne sont plus acceptées
dans une configuration explicite. Le calcul utilise cette configuration par
défaut lorsqu'aucune configuration n'est injectée.

Une autopsie isolée, un registre `extinct` isolé ou un seul événement de mort
est une **observation**, pas une confirmation irréversible. La confirmation
vitale requiert au moins deux sources indépendantes parmi autopsie, registre et
événements de mort, ainsi que trois événements confirmés dans la trace du run.
`evidence.vital_timeline.extinction_evidence` expose ces preuves et seuils.

## Distinction des notions

- `registry_status` décrit uniquement l’administration de la vie.
- `vital_timeline.state` décrit la dynamique technique observée.
- `life_status` décrit uniquement le verdict biologique contractuel.
- `extinction_seen_in_runs` et `run_terminated` restent des observations de run.

Aucun de ces champs ne prend une autre signification selon l’endpoint.

Extrait illustratif du payload `life_status` (le score est en points sur 100):

```json
{
  "status": "running",
  "score": 90.0,
  "explanation": "Statut running: 5/6 sous-signaux configurés sont établis, score 90/100.",
  "signals": {
    "persistent_identity": true,
    "generation_registry": true,
    "stable_cycle": true,
    "intrinsic_goals": true,
    "narrative_continuity": true,
    "reproduction_possible": false,
    "terminal": false,
    "extinction": false,
    "vital_state": "stable",
    "vital_risk_level": "low"
  },
  "missing_signals": [],
  "evidence": {
    "registry": {"status": "active"},
    "vital_timeline": {
      "age": 0,
      "state": "stable",
      "risk_level": "low",
      "reproduction_eligible": false,
      "extinction_evidence": {
        "signals": [],
        "duration": 0,
        "confirmed": false,
        "required_signals": 2,
        "required_duration": 3
      }
    }
  },
  "computed_at": "2026-07-07T12:30:00+00:00"
}
```

## Règle d'agrégation dashboard

Le dashboard n'infère plus un statut de vie uniquement à partir des runs:

1. Il lit d'abord `status` depuis le registre (source de vérité).
2. Il calcule en parallèle des indicateurs run-level (`extinction_seen_in_runs`, `run_terminated`, `has_recent_activity`).
3. Si une extinction est détectée dans les runs pour une vie enregistrée, il synchronise le registre via `set_life_status(slug, "extinct")`.

## Horloge vitale (cycles, transitions, priorités)

L'orchestrateur suit les transitions cycliques `veille → action → introspection → sommeil`. `compute_life_status()` analyse les runs et événements orchestrateur pour reconstruire ces phases, compter les cycles complets et exposer dans `evidence.stable_cycle.last_cycles` les derniers cycles observés.

### Paramètres de cycle

Le fichier versionné `configs/lifecycle.yaml` définit:

- `cycle.veille_seconds`
- `cycle.sommeil_seconds`
- `cycle.introspection_frequency_ticks`
- `cycle.mutation_window_seconds`
- `life_definition.thresholds.minimum_observed_cycles`: nombre minimal de cycles complets requis pour `stable_cycle`.
- `life_definition.thresholds.maximum_cycle_anomalies`: nombre maximal de phases manquantes ou écarts d'ordre tolérés avant de rendre `stable_cycle` négatif.

Les valeurs peuvent être surchargées via `singular orchestrate run --lifecycle-config`.

### Mapping phase → comportements

Chaque phase expose un mapping comportemental:

- `cpu_budget_percent`: budget CPU cible.
- `allowed_actions`: liste des actions autorisées.
- `slowdown_on_fatigue`: multiplicateur de ralentissement quand l'humeur est `fatigue`.

En phase `action`, le budget tick effectif est plafonné par la fenêtre de mutation (`mutation_window_seconds`) puis ralenti selon `slowdown_on_fatigue` si fatigue.

### Priorités d'exécution

1. Respect de la fenêtre de mutation.
2. Respect de la fréquence d'introspection.
3. Ralentissement adaptatif en fatigue.

## Artefacts techniques JSON du cycle de vie

Référence normative complémentaire: [`docs/technical_memory_artifacts.md`](./technical_memory_artifacts.md).

Ce document précise, pour `self_narrative.json`, `world_state.json`, `autopsy.json` et la trajectoire des objectifs:

- les champs obligatoires,
- des exemples JSON minimaux,
- la compatibilité backward (`read-old/write-new`),
- la stratégie de migration.

Règle opérationnelle: toute évolution de schéma impactant un de ces artefacts doit mettre à jour **les deux** documents (`technical_life_status.md` et `technical_memory_artifacts.md`) dans le même changement.
