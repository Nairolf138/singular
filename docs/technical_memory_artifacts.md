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

### Contribution au verdict de vie
`compute_life_status()` utilise cet artefact comme preuve d’identité persistante, de continuité narrative et de trajectoire sur plus de N jours. Les champs lus sont:

- `identity.name`: requis pour établir `signals.persistent_identity`. Absent, vide ou non lisible, le signal d’identité est incomplet.
- `identity.born_at`: sert de date de première apparition et contribue à l’âge narratif; il peut être remplacé par `registry.created_at` si l’entrée registre existe. Absent sans substitut registre, l’identité doit au moins fournir `identity.slug` via narration ou registre pour rester persistante.
- `identity.slug`: substitut accepté pour compléter l’identité persistante quand `born_at` manque; il peut aussi venir du registre.
- `life_periods[*].start_at` / `life_periods[*].end_at`: dates prises en compte pour calculer la première apparition et donc `signals.narrative_age_days`; les entrées non objets ou dates invalides sont ignorées.
- `life_periods`: son nombre alimente `periods_count` et sa présence constitue du contenu narratif. Absent ou non liste, il est traité comme une liste vide.
- `current_heading`: constitue du contenu narratif même sans période. Absent ou vide, la continuité narrative exige au moins des `life_periods`.

Comportement en cas d’absence: si `mem/self_narrative.json` manque, `self_narrative` apparaît dans `missing_signals`, la narration est lue comme `{}` et les valeurs de registre peuvent encore rétablir partiellement l’identité (`name`, `born_at`, `slug`). En revanche, sans `current_heading` ni `life_periods`, `narrative_continuity` reste faux; sans date valide assez ancienne pour atteindre `minimum_narrative_trajectory_days`, la trajectoire > N jours reste insuffisante.

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

### Contribution au verdict de vie
`compute_life_status()` utilise cet artefact comme indicateur de santé du monde, ressources et dette écologique/relationnelle via la métrique de santé injectée dans la timeline vitale. Les champs directement lus sont:

- `health.score`: score de santé accepté si présent à la racine; absent dans le schéma courant, donc généralement non utilisé pour ce fichier.
- `global_health.score`: score de santé global ajouté à la série `health_scores` après les scores trouvés dans les runs; s’il existe, il peut devenir `current_health` de `compute_vital_timeline()` et influencer les états `terminal`/`extinct`, le risque vital et l’éligibilité reproductive.

Les champs suivants ne sont pas lus directement par `compute_life_status()` aujourd’hui, mais documentent la causalité interprétable derrière `global_health.score` et les décisions opérateur: `resources.renewable`, `resources.non_renewable`, `global_health.trend`, `global_health.signals.resource_pressure`, `global_health.signals.cohesion`, `global_health.signals.ecological_debt`, `global_health.signals.relational_debt`, `global_health.signals.delayed_risk`, `dynamics.ecological_debt`, `dynamics.relational_debt` et `dynamics.delayed_events`.

Comportement en cas d’absence: si `mem/world_state.json` manque, `world_state` apparaît dans `missing_signals`, l’état monde est lu comme `{}` et aucun score monde n’est ajouté à `health_scores`. Le verdict continue alors avec les scores de santé éventuellement présents dans les runs; si aucun score n’existe, la timeline vitale reçoit `current_health=None`. Les dettes écologiques/relationnelles absentes n’ajoutent pas de cause directe au verdict, mais privent l’explication d’un contexte causal.

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

### Contribution au verdict de vie
`compute_life_status()` utilise cet artefact comme preuve terminale: la simple présence d’un objet JSON lisible dans `mem/autopsy.json` suffit à établir `signals.structured.extinction.evidence.autopsy_present=true`. Les champs documentaires lus indirectement ou conservés pour diagnostic sont:

- présence du fichier avec racine JSON objet: confirme une extinction, indépendamment du détail des causes.
- `technical_causes`: causes techniques terminales exploitées par les opérateurs et rapports, mais non parsées par `compute_life_status()` pour pondérer le score.
- `behavioral_causes`: causes comportementales terminales exploitées par les opérateurs et rapports, mais non parsées par `compute_life_status()` pour pondérer le score.
- `iteration` et `generated_at`: contexte temporel/post-mortem, non utilisé directement par le calcul du statut.

Comportement en cas d’absence: si `mem/autopsy.json` manque, `autopsy` apparaît dans `missing_signals`, `autopsy_present=false` et l’extinction peut encore être confirmée par `registry.status == "extinct"` ou par des événements de run contenant `extinct` ou `death`. Si le fichier existe mais est corrompu, non JSON ou non objet, il est lu comme `{}` et ne confirme pas l’extinction.

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

### Contribution au verdict de vie
`compute_life_status()` utilise `mem/goals.json` et `mem/quests_state.json` pour établir la présence d’objectifs intrinsèques ou d’une trajectoire d’objectifs. Les champs lus sont:

- `goals.weights`: objet de pondérations; chaque valeur numérique strictement positive compte dans `active_goal_count`. Absent ou non objet, il équivaut à zéro objectif actif.
- `goals.history`: sa simple présence non vide établit une trajectoire d’objectifs même si aucun poids actif n’est lisible. Absent, vide ou non liste, `history_count` vaut 0.
- `quests_state.active`: liste de quêtes actives; seules les entrées objets avec `origin == "intrinsic"` comptent comme quêtes intrinsèques. Absent ou non liste, elle est traitée comme vide.
- `quests_state.paused`: liste de quêtes suspendues; mêmes règles que `active` pour `origin == "intrinsic"`. Absent ou non liste, elle est traitée comme vide.
- runs JSONL associés: les événements dont le texte contient `goal`, `quest` ou `objective` alimentent `run_goal_events_count`, mais ne suffisent pas seuls à établir `intrinsic_goals` dans l’implémentation actuelle.

Comportement en cas d’absence: `goals.json` est optionnel pour `missing_signals`; s’il manque, les objectifs peuvent encore être établis par des quêtes intrinsèques dans `quests_state.json`. `quests_state.json` est requis: s’il manque, `quests_state` apparaît dans `missing_signals`, mais `goals.weights` ou `goals.history` peuvent encore établir `intrinsic_goals`. Si les deux sources ne fournissent ni poids positif, ni historique, ni quête intrinsèque, le signal `intrinsic_goals` reste faux.

### Contribution des runs JSONL au verdict de vie
Les runs `*.jsonl`, `*.jsonl.tmp` et `*/events.jsonl` ne sont pas un artefact mémoire unique, mais ils contribuent directement au verdict comme observation dynamique des cycles, mutations, générations, extinctions et reproductions. `compute_life_status()` lit notamment:

- `event`, `phase`, `stage`, `type`, `state`, `status`: concaténés en texte d’événement. Les séquences contenant successivement `veille`, `action`, `introspection`, `sommeil` incrémentent `observed_cycles`; atteindre `minimum_observed_cycles` établit `stable_cycle`.
- texte contenant `mutation` ou `generation`: contribue au signal de registre générationnel avec `run_generation_events_count`.
- présence de `score_new`: marque une mutation mesurable, incrémente l’âge technique passé à la timeline vitale et fait entrer l’enregistrement dans le calcul de réussite/échec.
- `accepted` ou, à défaut, `ok`: booléens utilisés pour calculer taux d’échec et plus longue série d’échecs; absents ou non booléens, ils sont ignorés.
- `health.score` ou `global_health.score`: ajoutés à la série de santé; le dernier score disponible devient la santé courante de la timeline vitale.
- texte contenant `extinct`, `death` ou `terminal`: alimente les événements d’extinction; `extinct` ou `death` confirment l’extinction.
- texte contenant `birth`, `reproduction`, `child` ou `offspring`: établit `reproduction_done` et contribue à `reproduction_capability`.
- `ts`, `time` ou `timestamp`: dates ajoutées au calcul de première apparition et donc à la trajectoire > N jours; dates absentes ou invalides ignorées.

Comportement en cas d’absence: si le répertoire `runs/` manque et que les runs ne sont pas injectés par l’appelant, `runs` apparaît dans `missing_signals` et la liste est vide. Le statut peut devenir `not_alive_yet` si aucune identité persistante n’est établie. Sans runs, `observed_cycles=0`, aucun événement de mutation/génération/death/reproduction n’est détecté, et le calcul dépend alors des artefacts mémoire, du registre et de `mem/generations.jsonl`.

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
