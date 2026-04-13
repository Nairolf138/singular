# Critères de sortie — Release v2

Ce document définit les garde-fous de sortie pour publier **v2** en réduisant les régressions produit et les risques de sécurité.

## 1) Qualité automatique (CI)

- **Pipeline vert obligatoire** sur la matrice Python `3.10 / 3.11 / 3.12`.
- Jobs séparés:
  - `lint` (Ruff + Black)
  - `typecheck` (mypy)
  - `tests` (pytest)
- Aucun merge si un job échoue.

## 2) Couverture de tests

- **Seuil global minimal**: `>= 85%` sur `src/singular`.
- **Seuil minimal fichiers critiques CLI** (`src/singular/cli.py`, `src/singular/lives.py`): `>= 90%`.
- Toute baisse de couverture sur un module critique doit être explicitement justifiée dans la PR.

## 3) Scénarios CLI critiques à valider

Les parcours suivants sont bloquants avant release:

1. **birth**
   - création d'une vie valide,
   - initialisation des dossiers et registres attendus.
2. **talk**
   - conversation simple (`--prompt`) avec persistance mémoire,
   - fallback robuste si provider indisponible.
3. **loop**
   - exécution avec `--budget-seconds`,
   - écriture checkpoint + traces d'exécution.
4. **lives**
   - create / list / use / delete,
   - activation cohérente de la vie courante.
5. **uninstall**
   - mode `--keep-lives` (préserve `lives/`),
   - mode `--purge-lives` (purge complète) avec confirmations de sécurité.

## 4) Checklist sécurité sandbox

Avant release, vérifier systématiquement:

- [ ] Exécution de code utilisateur dans un environnement sandboxé (pas d'exécution arbitraire hors cadre).
- [ ] Restrictions réseau appliquées côté sandbox quand requis.
- [ ] Limites CPU / temps d'exécution configurées pour éviter les boucles non bornées.
- [ ] Écritures disque bornées aux répertoires autorisés.
- [ ] Aucune clé/API secret en clair dans logs, erreurs, ou artefacts de test.
- [ ] Messages d'erreur explicites en cas de violation sandbox (pas de stacktrace sensible exposée).

## 5) Critères de validation manuelle

- Smoke test local sur Linux/macOS/Windows (au moins un mainteneur par plateforme).
- Vérification de la documentation utilisateur sur les commandes critiques.
- Validation d'un scénario de rollback (retour version précédente + intégrité des données utilisateurs).

## 6) Plan de découpage en 4 phases (aligné qualité/coverage/sécurité)

Le delivery v2 est découpé en 4 phases incrémentales. Chaque phase est **bloquante** sur les critères des sections 1, 2 et 4:

- pipeline CI vert (`lint`, `typecheck`, `tests`),
- couverture globale `>= 85%` sur `src/singular`,
- couverture fichiers critiques CLI `>= 90%`,
- checklist sécurité sandbox validée.

### Phase 1 — Fondations (bus événements + mémoire couches + journal conscience)

**Objectif**
- Stabiliser les primitives système: publication/souscription d'événements, service mémoire multi-couches, journal de conscience traçable.

**Critères d'acceptation**
- Le bus événements garantit la livraison locale des événements attendus et la non-régression des handlers existants.
- La mémoire couches préserve la compatibilité lecture/écriture avec les stores JSON et adaptateurs vectoriels.
- Le journal conscience produit des entrées horodatées, structurées et auditables (sans secrets en clair).

**Tests ciblés (`tests/`)**
- Unitaires:
  - `tests/test_memory_layers.py`
  - `tests/test_memory.py`
  - `tests/test_runs_logger.py`
- Intégration:
  - `tests/test_loop.py`
  - `tests/test_end_to_end.py`

**Migration de données (si schémas changent)**
- Versionner le schéma de journal/mémoire (`schema_version`) et fournir un migrateur idempotent (N -> N+1).
- Conserver un mode lecture rétro-compatible pour au moins la version N-1.

**Rollback**
- Snapshot préalable des fichiers mémoire/journal.
- Script de downgrade qui restaure snapshot + convertit les enregistrements N+1 vers N si possible.
- Si conversion impossible: rollback binaire + restauration snapshot complète.

### Phase 2 — Proactivité (watch mode + objectifs intrinsèques)

**Objectif**
- Activer une boucle proactive pilotée par `watch` et les objectifs intrinsèques, sans dérive des coûts/ressources.

**Critères d'acceptation**
- `watch mode` détecte les changements pertinents et déclenche des actions déterministes (logs explicites).
- Les objectifs intrinsèques influencent les priorités d'action de façon mesurable (métriques d'autonomie stables).
- Aucun dépassement de budget temps/CPU sur les scénarios de référence.

**Tests ciblés (`tests/`)**
- Unitaires:
  - `tests/test_watch_daemon.py`
  - `tests/test_cli_watch.py`
  - `tests/test_objectives.py`
  - `tests/test_agent_motivation.py`
- Intégration:
  - `tests/test_autonomy_metrics.py`
  - `tests/test_status.py`

**Migration de données (si schémas changent)**
- Ajouter les nouveaux champs d'objectifs avec valeurs par défaut sûres.
- Migration backward-compatible pour historiser les anciens runs sans recalcul destructif.

**Rollback**
- Feature flag pour désactiver la proactivité et revenir au mode réactif.
- Rejouer les runs en mode compatibilité pour valider l'absence d'écarts critiques.

### Phase 3 — Cognition avancée (réflexion hypothèses + croyances)

**Objectif**
- Introduire la réflexion sur hypothèses d'action et la persistance de croyances pour améliorer la cohérence décisionnelle.

**Critères d'acceptation**
- Chaque hypothèse évaluée produit une trace justifiée (contexte, score, décision).
- Le store de croyances applique des règles de cohérence (upsert, conflit, confiance) sans corruption.
- Les chemins CLI/talk/loop restent fonctionnels avec fallback robuste si module cognitif indisponible.

**Tests ciblés (`tests/`)**
- Unitaires:
  - `tests/test_psyche.py`
  - `tests/test_beliefs_store.py`
  - `tests/test_talk.py`
- Intégration:
  - `tests/test_loop.py`
  - `tests/test_cli_beliefs.py`
  - `tests/providers/test_llm_fallback_chain.py`

**Migration de données (si schémas changent)**
- Introduire un schéma versionné pour croyances/hypothèses (identifiants stables, timestamps ISO-8601).
- Migrateur validé par tests de round-trip (avant/après migration).

**Rollback**
- Basculer vers un store de croyances en lecture seule (mode safe) puis restaurer snapshot antérieur.
- Désactiver les écritures cognitives via config pour limiter l'impact en production.

### Phase 4 — Écosystème (multi-agent + gouvernance renforcée)

**Objectif**
- Généraliser l'exécution en mode écosystème multi-agent avec contraintes de gouvernance explicites.

**Critères d'acceptation**
- Les interactions multi-agent respectent le protocole, sont traçables et rejouables.
- Les politiques de gouvernance (règles, permissions, garde-fous) sont appliquées avant action critique.
- Les commandes `ecosystem run` restent conformes aux critères de sécurité sandbox et de rollback.

**Tests ciblés (`tests/`)**
- Unitaires:
  - `tests/test_multiagent_protocol.py`
  - `tests/test_cli_lives.py`
  - `tests/test_health.py`
- Intégration:
  - `tests/test_multi_organisms.py`
  - `tests/test_environment.py`
  - `tests/test_end_to_end.py`

**Migration de données (si schémas changent)**
- Ajouter une couche de migration pour états partagés (checkpoint écosystème, réputation, interactions).
- Garantir l'isolation des données par vie/organisme lors des migrations.

**Rollback**
- Rollback atomique par checkpoint (écosystème + états individuels).
- Procédure de retour mono-agent (désactivation orchestration multi-agent) sans perte des données vitales.

## 7) Définition de prêt-à-livrer par phase

Une phase est considérée *Done* uniquement si:

1. Les critères d'acceptation de la phase sont validés.
2. Les tests unitaires/intégration ciblés sont verts.
3. Les migrations (si présentes) sont testées et documentées.
4. La stratégie de rollback est testée sur données représentatives.
5. Les exigences qualité/couverture/sécurité de cette release restent conformes.
