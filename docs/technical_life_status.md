# Statut de vie: source de vérité

Ce document définit la sémantique officielle du statut d'une **vie** dans Singular.

## Source de vérité

La source de vérité est le champ `status` de chaque entrée dans `lives/registry.json`.

Valeurs supportées:

- `active`: la vie est considérée active dans le registre.
- `extinct`: la vie est marquée comme éteinte dans le registre.

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

Les critères fondamentaux pour atteindre `alive` sont:

- identité persistante,
- registre de générations,
- cycle stable,
- objectifs intrinsèques continus,
- narration cohérente sur la durée minimale configurée.

La reproduction possible contribue au score, mais n'est pas un critère bloquant pour `alive`.

## Statuts qualifiés par score

Les statuts métier exposés par `configs/life_definition.yaml` sont:

- `not_alive_yet`: score insuffisant ou au moins un signal fondamental absent.
- `fragile`: score intermédiaire mais continuité incomplète.
- `alive`: score supérieur ou égal au seuil `alive_minimum_score`, critères fondamentaux présents et aucun signal terminal.
- `dying`: signal terminal présumé ou dégradation forte, mais extinction non confirmée.
- `extinct`: autopsy présente, registre `extinct` ou événement `death` confirmé.

Ordre de priorité recommandé:

1. `extinct` si une extinction est confirmée (`autopsy.json` présent, registre `extinct`, ou événement `death` confirmé).
2. `dying` si une dégradation forte est détectée sans confirmation d'extinction.
3. `alive` si le score atteint le seuil `alive_minimum_score`, les critères fondamentaux sont présents et aucun signal terminal n'est observé.
4. `fragile` si le score atteint le seuil `fragile_minimum_score`, mais que la continuité reste incomplète.
5. `not_alive_yet` sinon.

Les signaux terminaux dominent toujours le score: un score élevé ne peut pas produire `alive` si un signal terminal confirmé existe.

## Distinction des notions

Trois champs décrivent des niveaux différents et ne doivent pas être confondus:

- **`registry.status`**: état administratif de la vie dans `lives/registry.json`. Les seules valeurs normatives du registre sont `active` et `extinct`. Ce champ indique si la vie reste administrativement active ou si son extinction a été confirmée et persistée.
- **`vital_timeline.state`**: état vital déterministe calculé à partir des signaux techniques observables. Les valeurs exposées sont `mature`, `declining`, `terminal` et `extinct`. Ce champ décrit la dynamique vitale courante, sans remplacer la décision contractuelle.
- **`life_status.status`**: verdict contractuel portable exposé aux interfaces CLI, dashboard et rapports. Les valeurs autorisées sont `not_alive_yet`, `fragile`, `alive`, `dying` et `extinct`. Ce verdict agrège le registre, la timeline vitale et la checklist contractuelle.

Le dashboard distingue également:

- **Vie sélectionnée**: correspond à la clé racine `active` du registre (`registry["active"]`).
- **Vie active dans le registre**: correspond à `life.status == "active"`.
- **Run terminé**: information de run-level (ex: dernier événement `death`).
- **Extinction détectée**: information observée dans les événements de run (présence d'au moins un `event == "death"`).

## Ordre de priorité du verdict contractuel

Le calcul de `life_status.status` applique l'ordre de priorité suivant:

1. **Extinction confirmée domine tout**: si une extinction est confirmée (`autopsy.json` présent, `registry.status == "extinct"` ou événement `death` confirmé), le verdict est `extinct`, quel que soit le score ou l'état vital intermédiaire.
2. **Terminalité vitale produit `dying`**: si `vital_timeline.state == "terminal"` ou si un signal terminal fort est observé sans extinction confirmée, le verdict est `dying`.
3. **Checklist contractuelle produit `not_alive_yet`, `fragile` ou `alive`**: en l'absence d'extinction confirmée et de terminalité vitale, les signaux contractuels configurés dans `configs/life_definition.yaml` déterminent le verdict selon les seuils et critères fondamentaux.

Exemple complet de payload `life_status`:

```json
{
  "status": "alive",
  "score": 0.91,
  "explanation": "Identité persistante, cycle stable, objectifs intrinsèques et continuité narrative observés. Vital: état mature, risque low.",
  "signals": {
    "persistent_identity": true,
    "generation_registry": true,
    "stable_cycle": true,
    "intrinsic_goals": true,
    "narrative_continuity": true,
    "reproduction_possible": false,
    "terminal_signal": false,
    "extinction": false,
    "vital_state": "mature",
    "vital_risk_level": "low"
  },
  "missing_signals": [],
  "evidence": {
    "registry_status": "active",
    "vital_timeline": {
      "age": 42,
      "state": "mature",
      "risk_level": "low",
      "causes": [],
      "reproduction_eligible": false
    },
    "score_breakdown": {
      "persistent_identity": 20,
      "generation_registry": 15,
      "stable_cycle": 20,
      "intrinsic_goals": 20,
      "reproduction_possible": 0,
      "narrative_continuity": 15
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
