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

`N` correspond à `thresholds.minimum_narrative_trajectory_days`. Les signaux fondamentaux sont tous les critères ci-dessus sauf la reproduction possible, qui reste contributive mais non bloquante pour l'état `running`.

## Statuts de qualification vitale

La qualification émet exclusivement `running`, `budget_exhausted`, `degraded`,
`mutation_paused`, `terminal` et `dead`. Une extinction corroborée et durable
prime sur la terminalité, puis viennent l'épuisement du budget, la pause des
mutations, le fonctionnement établi et enfin la dégradation. `running` exige
le score minimum et tous les critères fondamentaux ; la reproduction est
contributive, sans être obligatoire.

Une autopsie seule, un registre `extinct` seul ou un événement `death` seul
reste une observation. Le verdict `dead` exige deux sources indépendantes
parmi autopsie, registre et événement de mort, et au moins trois événements
confirmés dans la trace. Ces seuils sont exposés dans
`evidence.vital_timeline.extinction_evidence`.

## États et transitions

La dynamique technique `vital_timeline.state` est distincte du verdict
`life_status`. Ses valeurs sont `stable`, `at_risk`, `critical`, `terminal`,
`dead` et `extinct`. L'extinction corroborée prime sur les autres seuils ;
`terminal` est atteint par l'âge, la santé ou une série d'échecs ; `critical`
par une santé basse ou un taux d'échec élevé ; `at_risk` par l'âge de déclin ;
`stable` décrit l'absence de ces signaux.

## Risque et indicateurs dérivés

- `risk_level=low` pour `stable`.
- `risk_level=medium` pour `at_risk`.
- `risk_level=high` pour `critical`, `terminal`, `dead` et `extinct`.
- `terminal=true` pour `terminal`, `dead` et `extinct`, sinon `false`.
- `causes`: liste des causes observées (ex: `high_failure_rate`, `critical_health_score`).

## Éligibilité reproduction

`reproduction_eligible=true` si et seulement si:

- état ∈ `{stable, at_risk}`,
- `age` dans `[3, 80]`,
- les seuils de risque vital ne classent pas l'état en `critical` ou pire.

Sinon `false`.

## Exceptions

- Si aucune donnée de santé n’est disponible, on n’applique pas la règle `current_health`.
- Si aucune donnée de réussite/échec n’est disponible, on n’applique pas la règle `failure_rate`.
- Une observation isolée d'extinction ne constitue pas un décès confirmé.

## Contrats de persistance (JSON)

Les règles déterministes de cycle vital s'appuient sur des artefacts JSON versionnés/tolérants.

Voir la spécification détaillée: [`docs/technical_memory_artifacts.md`](./technical_memory_artifacts.md).

Points à retenir:

- `autopsy.json` porte la causalité terminale technique + comportementale.
- `world_state.json` porte les contraintes écologiques/relatives influençant le risque.
- `self_narrative.json` porte la continuité identitaire et les inflexions narratives.
- la trajectoire des objectifs est calculée depuis `quests_state.json` + runs + `goals.json`.

Tout changement de seuil métier qui modifie la structure ou l'interprétation de ces artefacts doit être accompagné d'un plan de migration backward-compatible.
