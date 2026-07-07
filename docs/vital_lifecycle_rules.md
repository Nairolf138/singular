# Spécification métier — cycle vital déterministe

Cette spécification formalise des règles **déterministes** (seuils fixes) et **observables** (causes explicitement remontées) pour:

- âge,
- déclin,
- extinction,
- reproduction.

## Variables observables

- `age`: nombre de mutations observées sur la vie.
- `current_health`: dernier `health.score` connu.
- `failure_rate`: part des mutations échouées (`accepted/ok == false`).
- `failure_streak`: plus longue série continue d’échecs.
- `extinction_seen`: présence d’un événement `event == "death"` dans les runs.
- `registry_status`: statut actuel du registre (`active` ou `extinct`).
- `life_score`: score pondéré calculé depuis `configs/life_definition.yaml`.
- `fundamental_signals_present`: présence des critères fondamentaux d'identité, génération, cycle, objectifs intrinsèques et narration minimale.
- `autopsy_present`: présence d'un artefact `autopsy.json`.

## Seuils (version 1)

- `decline_age = 50`
- `terminal_age = 120`
- `terminal_health = 25.0`
- `high_failure_rate = 0.60`
- `terminal_failure_streak = 5`
- `reproduction_age_window = [3, 80]`
- `fragile_minimum_score = 50`
- `alive_minimum_score = 80`

## Barème vital pondéré

Le barème de qualification vitale est défini dans `configs/life_definition.yaml` et totalise 100 points:

- identité persistante: 20 points,
- registre de générations: 15 points,
- cycle stable: 20 points,
- objectifs intrinsèques continus: 20 points,
- reproduction possible: 10 points,
- narration cohérente sur N jours: 15 points.

`N` correspond à `thresholds.minimum_narrative_trajectory_days`. Les signaux fondamentaux sont tous les critères ci-dessus sauf la reproduction possible, qui reste contributive mais non bloquante pour l'état `alive`.

## Statuts de qualification vitale

La qualification vitale produit les statuts suivants:

1. **Extinct** (`status=extinct`)
   - si `autopsy_present == true`,
   - ou `registry_status == "extinct"`,
   - ou `extinction_seen == true`.
2. **Dying** (`status=dying`)
   - si un signal terminal ou une dégradation forte est détecté,
   - et qu'aucune extinction confirmée n'est encore disponible.
3. **Alive** (`status=alive`)
   - si `life_score >= alive_minimum_score`,
   - et `fundamental_signals_present == true`,
   - et aucun signal terminal n'est présent.
4. **Fragile** (`status=fragile`)
   - si `life_score >= fragile_minimum_score`,
   - mais que la continuité est incomplète ou qu'un critère fondamental reste partiel.
5. **Not alive yet** (`status=not_alive_yet`)
   - si le score est insuffisant,
   - ou si des signaux fondamentaux sont absents.

Priorité d'évaluation: `extinct` domine `dying`, qui domine `alive`, qui domine `fragile`, qui domine `not_alive_yet`. Cette priorité évite qu'un score élevé masque une extinction ou une trajectoire terminale.

## États et transitions

Ordre de priorité des transitions:

1. **Extinction** (`state=extinct`)
   - si `extinction_seen == true` **ou** `registry_status == "extinct"`.
2. **Terminal** (`state=terminal`)
   - si `age >= terminal_age`
   - ou `current_health <= terminal_health`
   - ou `failure_streak >= terminal_failure_streak`.
3. **Déclin** (`state=declining`)
   - si `age >= decline_age`
   - ou `failure_rate >= high_failure_rate`.
4. **Mature** (`state=mature`) sinon.

## Risque et indicateurs dérivés

- `risk_level=low` pour `mature`.
- `risk_level=medium` pour `declining`.
- `risk_level=high` pour `terminal` et `extinct`.
- `terminal=true` pour `terminal` et `extinct`, sinon `false`.
- `causes`: liste des causes observées (ex: `high_failure_rate`, `critical_health_score`).

## Éligibilité reproduction

`reproduction_eligible=true` si et seulement si:

- état ∈ `{mature, declining}`,
- `age` dans `[3, 80]`,
- `failure_rate < 0.60` (si disponible),
- `current_health > 25.0` (si disponible).

Sinon `false`.

## Exceptions

- Si aucune donnée de santé n’est disponible, on n’applique pas la règle `current_health`.
- Si aucune donnée de réussite/échec n’est disponible, on n’applique pas la règle `failure_rate`.
- L’extinction observée domine toujours les autres états.

## Contrats de persistance (JSON)

Les règles déterministes de cycle vital s'appuient sur des artefacts JSON versionnés/tolérants.

Voir la spécification détaillée: [`docs/technical_memory_artifacts.md`](./technical_memory_artifacts.md).

Points à retenir:

- `autopsy.json` porte la causalité terminale technique + comportementale.
- `world_state.json` porte les contraintes écologiques/relatives influençant le risque.
- `self_narrative.json` porte la continuité identitaire et les inflexions narratives.
- la trajectoire des objectifs est calculée depuis `quests_state.json` + runs + `goals.json`.

Tout changement de seuil métier qui modifie la structure ou l'interprétation de ces artefacts doit être accompagné d'un plan de migration backward-compatible.
