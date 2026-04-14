# Statut de vie: source de vérité

Ce document définit la sémantique officielle du statut d'une **vie** dans Singular.

## Source de vérité

La source de vérité est le champ `status` de chaque entrée dans `lives/registry.json`.

Valeurs supportées:

- `active`: la vie est considérée active dans le registre.
- `extinct`: la vie est marquée comme éteinte dans le registre.

Ce statut est porté par `LifeMetadata.status` dans `src/singular/lives.py`, persisté via `save_registry()`, et modifié via `set_life_status()`.

## Distinction des notions

Le dashboard distingue désormais:

- **Vie sélectionnée**: correspond à la clé racine `active` du registre (`registry["active"]`).
- **Vie active dans le registre**: correspond à `life.status == "active"`.
- **Run terminé**: information de run-level (ex: dernier événement `death`).
- **Extinction détectée**: information observée dans les événements de run (présence d'au moins un `event == "death"`).

## Règle d'agrégation dashboard

Le dashboard n'infère plus un statut de vie uniquement à partir des runs:

1. Il lit d'abord `status` depuis le registre (source de vérité).
2. Il calcule en parallèle des indicateurs run-level (`extinction_seen_in_runs`, `run_terminated`, `has_recent_activity`).
3. Si une extinction est détectée dans les runs pour une vie enregistrée, il synchronise le registre via `set_life_status(slug, "extinct")`.

## Horloge vitale (cycles, transitions, priorités)

L'orchestrateur suit les transitions cycliques `veille → action → introspection → sommeil`.

### Paramètres de cycle

Le fichier versionné `configs/lifecycle.yaml` définit:

- `cycle.veille_seconds`
- `cycle.sommeil_seconds`
- `cycle.introspection_frequency_ticks`
- `cycle.mutation_window_seconds`

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
