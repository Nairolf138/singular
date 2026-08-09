# Matrice de fiabilité fonctionnelle

Ce document sert de référence opérateur pour vérifier les capacités critiques du dashboard Singular.

## Capacités couvertes

| Capacité | Scénario nominal | Données minimales attendues | Critère de succès opérateur (UI/API) | Test automatisé associé (backend + UI si disponible) |
| --- | --- | --- | --- | --- |
| **Vies centralisées** | Le registre des vies est chargé et la vie active est reconnue. | `registry.active`, `registry.lives[*].slug`, `registry.lives[*].status`. | API `/dashboard/context` renvoie `registry_lives_count > 0` et `registry_state.active_valid = true`. UI affiche « Nombre de vies détectées ». | Backend: `tests/test_dashboard.py::test_dashboard_endpoints`, `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques`. UI: `tests/test_dashboard.py::test_dashboard_index_contains_cockpit_cards`. |
| **Comparaison inter-vies** | L’opérateur consulte le tableau comparatif pour prioriser les vies à risque. | Runs JSONL avec `life`, `score_base`, `score_new`, `accepted`/`ok`, horodatage `ts`. | API `/lives/comparison` renvoie `table` non vide, tri et filtres applicables, et contrat `life_metrics_contract`. | Backend: `tests/test_dashboard_services.py::test_lives_comparison_service_aggregates_metrics`, `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques`. UI: `tests/test_dashboard.py::test_dashboard_index_contains_cockpit_cards`. |
| **KPI cockpit** | Le cockpit synthétise état global, alertes et métriques vitales. | Run JSONL récent avec score mutation (`score_base`/`score_new`), statut (`accepted`/`ok`), bloc `health`. | API `/api/cockpit` renvoie `global_status`, `accepted_mutation_rate`, `health_score`, `vital_metrics`, `trajectory`. | Backend: `tests/test_dashboard.py::test_dashboard_cockpit_endpoint_schema`, `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques`. UI: `tests/test_dashboard.py::test_dashboard_index_contains_cockpit_cards`. |
| **Social links** | L’opérateur inspecte alliances/rivalités entre vies dans la généalogie. | `registry.lives[*].allies`, `registry.lives[*].rivals`, et optionnellement `mem/lives_relations.jsonl`. | API `/lives/genealogy` expose `social_edges`, `active_relations`, `active_conflicts`. | Backend: `tests/test_dashboard.py::test_lives_genealogy_returns_relations_contract`, `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques`. UI: `tests/test_dashboard.py::test_dashboard_index_contains_cockpit_cards`. |
| **Quêtes** | Les quêtes actives/complétées sont visibles et priorisables. | `mem/quests_state.json` avec listes `active` et `completed` (nom, statut, dates). | API `/quests` renvoie les listes attendues; `/api/dashboard/work-items` inclut des `objectives` normalisés. | Backend: `tests/test_dashboard.py::test_dashboard_quests_endpoint`, `tests/test_dashboard.py::test_dashboard_work_items_schema_contains_required_fields`, `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques`. UI: `tests/test_dashboard.py::test_dashboard_index_contains_cockpit_cards` (tableaux quêtes/objectifs). |
| **Interactions monde** | Les événements d’interaction (ex. partage/compétition) sont auditables dans une timeline de run. | Run JSONL avec `event="interaction"`, champ `interaction`, `ts`, `life`/`organism`. | API `/api/runs/{run_id}/timeline` expose au moins un item `event="interaction"` avec contexte. | Backend: `tests/test_dashboard.py::test_run_timeline_endpoint_filters_pagination_and_event_coherence`, `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques`. UI: `tests/test_dashboard.py::test_dashboard_index_contains_cockpit_cards` (section timeline). |
| **Conversation humain** | Une conversation issue de la conscience est visible comme item actionnable. | Fichier `*.consciousness.jsonl` avec `objective`/`summary`, `success`, `ts` (lié à un run). | API `/api/dashboard/work-items` renvoie `conversations.items` non vide avec `title`, `status`, `next_step`. | Backend: `tests/test_dashboard.py::test_dashboard_work_items_schema_contains_required_fields`, `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques`. UI: `tests/test_dashboard.py::test_dashboard_index_contains_cockpit_cards` (table conversation). |
| **Mode essentiel** | Le pilotage en mode essentiel expose les signaux critiques minimums. | Données cockpit minimales (run récent + éventuelles alertes critiques). | API `/api/cockpit/essential` renvoie `schema_version`, `global_status`, `critical_alerts_count`, `next_action`, `selected_life`. | Backend: `tests/test_dashboard.py::test_dashboard_cockpit_essential_projection_schema`, `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques`. UI: `tests/test_dashboard.py::test_dashboard_essential_mode_critical_blocks_and_visibility_markers`. |

## Test smoke recommandé

Le test `tests/test_dashboard_smoke_e2e.py::test_smoke_dashboard_e2e_capacites_critiques` valide en une seule exécution les capacités ci-dessus via des appels API dashboard représentatifs (contexte, comparaison, cockpit, quêtes, interactions, conversations, social links, mode essentiel).

## Protocole hors réseau multi-vies

Le protocole versionné `ada-bob-eve/1.0.0` rejoue les scénarios **Ada
1.0.0**, **Bob 1.1.0** et **Eve 2.0.0** pour chaque graine, sans réseau. La
commande CI recommandée est :

```bash
python scripts/run_offline_multi_life_eval.py \
  --seeds 11,23,37,53,71 \
  --output artifacts/evaluations/offline_multi_life_v2.json \
  --kpi-config configs/agi_kpis.yaml
```

Le code de sortie est non nul dès qu'un critère bloquant échoue. Chaque run
capture avant et après la configuration et la graine, le statut vital, la
santé, le risque, les ressources, la cognition, les beliefs, les traits, les
quêtes, la narration, les événements d'embodiment, les mutations et le circuit
breaker. L'artefact JSON `singular.offline-multi-life-evaluation/v2` contient
également, par scénario, la médiane, l'écart-type population (`dispersion`) et
l'intervalle observé (`low`–`high`) ; un run isolé n'est donc jamais présenté
comme résultat global.

### Seuils bloquants

Les seuils sont lus dans `configs/agi_kpis.yaml`, bloc `offline_multi_life` :

| Critère | Seuil |
| --- | --- |
| Extinctions évitables | `maximum_avoidable_extinctions: 0` |
| Chute d'un trait structurant | au plus `maximum_structural_trait_drop: 0.02` |
| Évolution de la santé | au moins `minimum_health_delta: 0.0` (stabilité admise) |
| Utilité d'une mutation acceptée | au moins `minimum_useful_mutation_delta: 0.01` |
| Échec observé | au moins une quête corrélée doit être déclenchée |
| Isolation des vies | tous les événements gardent le même `life_id` |

Le test `tests/test_offline_multi_life_evaluation.py` verrouille le schéma de
capture, les critères, les distributions et la reproductibilité octet pour
octet à configuration et graines identiques.
