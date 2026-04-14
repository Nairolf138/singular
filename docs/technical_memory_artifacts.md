# Spécification technique des artefacts mémoire

Ce document formalise les contrats JSON de quatre artefacts de cycle de vie:

- `mem/self_narrative.json`
- `mem/world_state.json`
- `mem/autopsy.json`
- trajectoire des objectifs (agrégation `mem/goals.json` + `mem/quests_state.json` + runs `*.jsonl`)

Objectifs:

1. expliciter les champs obligatoires,
2. fournir des exemples JSON minimaux,
3. garantir la compatibilité backward,
4. définir une stratégie de migration opérable.

---

## 1) `self_narrative.json`

### Rôle
Mémoire narrative persistante de l'identité et des inflexions de trajectoire de la vie.

### Schéma courant
- Version logique: `schema_version = 1`
- Fichier: `mem/self_narrative.json`

### Champs obligatoires
- `schema_version` (`int`)
- `identity` (`object`)
  - `name` (`string`)
  - `born_at` (`string`, ISO8601 ou vide)
  - `logical_age` (`int`, recalculé au chargement/sauvegarde)
- `life_periods` (`array<object>`)
- `trait_trends` (`object`) avec les 5 clés:
  - `curiosity`, `patience`, `playfulness`, `optimism`, `resilience`
  - chacune avec:
    - `value` (`float` borné `[0,1]`)
    - `trend` (`"up"|"down"|"stable"`)
- `regrets_and_pride` (`object`)
  - `significant_successes` (`array<string>`)
  - `significant_failures` (`array<string>`)
  - `abandoned_skills` (`array<string>`)
  - `costly_incidents` (`array<string>`)
- `current_heading` (`string`)

### Exemple JSON (minimal valide)
```json
{
  "schema_version": 1,
  "identity": {
    "name": "Singular",
    "born_at": "2026-04-14T00:00:00+00:00",
    "logical_age": 0
  },
  "life_periods": [],
  "trait_trends": {
    "curiosity": {"value": 0.5, "trend": "stable"},
    "patience": {"value": 0.5, "trend": "stable"},
    "playfulness": {"value": 0.5, "trend": "stable"},
    "optimism": {"value": 0.5, "trend": "stable"},
    "resilience": {"value": 0.5, "trend": "stable"}
  },
  "regrets_and_pride": {
    "significant_successes": [],
    "significant_failures": [],
    "abandoned_skills": [],
    "costly_incidents": []
  },
  "current_heading": "Clarifier ma prochaine étape utile."
}
```

### Compatibilité backward
- Lecture tolérante:
  - champs absents complétés par défaut,
  - valeurs invalides coercées (`trend` invalide → `stable`, `value` hors plage bornée),
  - payload non-objet ou corrompu → restauration d'un document par défaut.
- Migration soft au chargement:
  - `schema_version` aligné au minimum sur la version courante,
  - recalcul de `identity.logical_age` depuis `identity.born_at`.

### Stratégie de migration
1. **Read-old / write-new**: toujours accepter versions partielles/anciennes en entrée.
2. **Canonicalisation immédiate**: réécrire le fichier au format courant après `load()`.
3. **Sécurité corruption**: renommer le fichier invalide en `self_narrative.json.corrupt-<timestamp>` avant régénération.
4. **Règle d'évolution**: toute future version incrémente `schema_version` et maintient un migrateur `N -> N+1` pur et idempotent.

---

## 2) `world_state.json`

### Rôle
État simulé du monde externe qui influence perception, ressources et santé globale.

### Schéma courant
- Version implicite: pas de `schema_version` dédié dans l'état courant.
- Fichier: `mem/world_state.json`

### Champs obligatoires
- `world_clock` (`int`)
- `map` (`object`)
  - `spaces` (`array<object>`)
  - `niches` (`array<object>`)
- `resources` (`object`)
  - `renewable` (`object`) avec ressources `{amount, regen_rate, capacity}`
  - `non_renewable` (`object`) avec ressources `{amount}`
- `external` (`object`)
  - `entities` (`array<object>`)
  - `artifacts` (`array<object>`)
- `global_health` (`object`)
  - `score` (`float`), `trend` (`string`), `signals` (`object`)
- `dynamics` (`object`)
  - `ecological_debt` (`float`)
  - `relational_debt` (`float`)
  - `delayed_events` (`array<object>`)

### Exemple JSON (minimal valide)
```json
{
  "world_clock": 0,
  "map": {"spaces": [], "niches": []},
  "resources": {
    "renewable": {
      "solar": {"amount": 70.0, "regen_rate": 5.0, "capacity": 100.0}
    },
    "non_renewable": {
      "ore": {"amount": 80.0}
    }
  },
  "external": {"entities": [], "artifacts": []},
  "global_health": {
    "score": 82.0,
    "trend": "stable",
    "signals": {
      "resource_pressure": 0.2,
      "cohesion": 0.85,
      "ecological_debt": 0.0,
      "relational_debt": 0.0,
      "delayed_risk": 0.0
    }
  },
  "dynamics": {
    "ecological_debt": 0.0,
    "relational_debt": 0.0,
    "delayed_events": []
  }
}
```

### Compatibilité backward
- Si le fichier est absent: initialisation automatique avec état par défaut.
- Les apply/update runtime utilisent `setdefault`, ce qui tolère des payloads incomplets.
- Certaines valeurs sont bornées (`health.score`, dettes) pour éviter la dérive hors domaine.

### Stratégie de migration
1. Introduire `schema_version` à la prochaine rupture structurante (recommandé: v2).
2. Ajouter un migrateur explicite `world_state v1? -> v2` au chargement.
3. Conserver une politique `missing keys -> defaults` durant une fenêtre de transition.
4. Journaliser le nombre de migrations effectuées pour observabilité.

---

## 3) `autopsy.json`

### Rôle
Rapport de post-mortem technique/comportemental lors d'une extinction.

### Schéma courant
- `schema_version = 1`
- Fichier: `mem/autopsy.json`

### Champs obligatoires
- `schema_version` (`int`)
- `generated_at` (`string` ISO8601)
- `iteration` (`int`)
- `technical_causes` (`array<string>`)
- `behavioral_causes` (`array<string>`)

### Exemple JSON (minimal valide)
```json
{
  "schema_version": 1,
  "generated_at": "2026-04-14T00:00:00+00:00",
  "iteration": 120,
  "technical_causes": [
    "monitor:health_below_threshold",
    "health_score=24.500"
  ],
  "behavioral_causes": [
    "decision_reason:risk_budget_exhausted",
    "mutation_policy:balanced"
  ]
}
```

### Compatibilité backward
- Le format est append-only dans la pratique: les causes sont des listes de chaînes.
- Les consommateurs doivent ignorer les champs additionnels inconnus.
- En l'absence de `autopsy.json`, le système doit considérer qu'aucune autopsie n'est disponible (pas d'erreur bloquante).

### Stratégie de migration
1. Maintenir les clés existantes inchangées (`technical_causes`, `behavioral_causes`).
2. Ajouter les nouveaux diagnostics dans des champs optionnels (`sections`, `metrics`, etc.).
3. N'incrémenter `schema_version` qu'en cas de changement non rétrocompatible.
4. Prévoir un convertisseur hors-ligne pour historiser les anciennes autopsies si une rupture devient nécessaire.

---

## 4) Trajectoire des objectifs

### Rôle
Vue consolidée des objectifs actifs/abandonnés/complétés et des variations de priorité.

> Note: il ne s'agit pas d'un fichier unique aujourd'hui; la trajectoire est calculée à la volée.

### Sources de données
- `mem/quests_state.json`
  - alimente les listes `active`, `paused`, `completed`.
- runs `*.jsonl`
  - alimentent les changements de priorité (`objective_priorities`, `objective_weights`, `objectives`)
  - alimentent les liens narratifs (`event`, `objective`, `self_narrative_event`).
- `mem/goals.json`
  - historique des poids intrinsèques (`history[*].weights`) utile pour diagnostiquer les réallocations d'axes.

### Structure retournée par le dashboard
- `trajectory.objectives.counts`
  - `in_progress`, `abandoned`, `completed` (`int`)
- `trajectory.objectives.{in_progress,abandoned,completed}` (`array<string>`)
- `trajectory.priority_changes` (`array<object>`)
  - `objective`, `at`, `from`, `to`, `delta`
- `trajectory.objective_narrative_links` (`array<object>`)
  - `objective`, `event`, `at`, `run`

### Exemple JSON (payload d'API)
```json
{
  "trajectory": {
    "objectives": {
      "counts": {"in_progress": 1, "abandoned": 0, "completed": 2},
      "in_progress": ["stabiliser-boucle-action"],
      "abandoned": [],
      "completed": ["audit-sante", "reduction-dette-eco"]
    },
    "priority_changes": [
      {
        "objective": "coherence",
        "at": "2026-04-14T00:01:22+00:00",
        "from": 0.4,
        "to": 0.72,
        "delta": 0.32
      }
    ],
    "objective_narrative_links": [
      {
        "objective": "coherence",
        "event": "self_narrative.updated",
        "at": "2026-04-14T00:01:22+00:00",
        "run": "run-20260414-0001"
      }
    ]
  }
}
```

### Compatibilité backward
- Extraction tolérante des priorités: support de 3 formats (`objective_priorities`, `objective_weights`, `objectives`).
- Champs non numériques ignorés lors de la normalisation des priorités.
- En absence de sources (`quests_state`/runs), renvoyer des collections vides plutôt qu'une erreur.

### Stratégie de migration
1. **Court terme**: conserver l'agrégation tolérante multi-sources.
2. **Moyen terme**: introduire un snapshot versionné dédié (`mem/objective_trajectory.json`) alimenté de façon incrémentale.
3. **Transition**:
   - produire le snapshot *et* continuer l'agrégation historique,
   - comparer les deux en shadow mode,
   - basculer la lecture dashboard vers le snapshot une fois la parité validée.
4. **Long terme**: documenter un contrat d'événements unique pour éviter les variantes `objective_*`.

---

## Politique générale de compatibilité

- Principe: **reader permissif, writer canonique**.
- Tout payload JSON lu depuis le disque doit être:
  1) validé/coercé, 2) migré, 3) réécrit dans la forme courante.
- Les ajouts de champs doivent être backward-compatible par défaut.
- Les suppressions/renommages imposent:
  - montée de version,
  - migrateur explicite,
  - note de migration opérateur.
