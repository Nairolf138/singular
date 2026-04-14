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

## Seuils (version 1)

- `decline_age = 50`
- `terminal_age = 120`
- `terminal_health = 25.0`
- `high_failure_rate = 0.60`
- `terminal_failure_streak = 5`
- `reproduction_age_window = [3, 80]`

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
