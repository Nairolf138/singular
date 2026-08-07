# Matrice des capacités cognitives

Cette matrice est le registre canonique de maturité des capacités montrées dans les
captures. Elle décrit **ce qui est démontré dans le dépôt**, et non une intention de
produit. La date d'observation est le 7 août 2026.

## Règle de lecture et de promotion

Les quatre preuves sont indépendantes : **C** = une classe/API existe, **B** = elle
est branchée dans la boucle normale (sans injection spéciale au test), **P** = son
état utile est relu après recréation du processus, **V** = le scénario d'acceptation
ci-dessous passe avec ses seuils quantitatifs. Le statut est le minimum démontré :

- `absent` : pas de classe/API exécutable ;
- `prototype` : **C**, mais pas les trois autres preuves ;
- `intégré` : **C+B**, la colonne P indiquant séparément si la durabilité est
  réellement couverte ;
- `validé` : **C+B+P+V**, avec au moins 200 échantillons segmentés et un intervalle
  de confiance à 95 %, sur deux fenêtres consécutives de 30 jours.

Une classe présente n'implique donc ni branchement, ni persistance, ni validation.
De même, un test unitaire vert ne suffit pas à déclarer une capacité complète. Les
termes « complète », « achevée », « production-ready » et équivalents sont interdits
pour une capacité tant que son statut n'est pas `validé`. Le contrôle
`python scripts/check_capability_claims.py` rend cette règle vérifiable dans tous les
fichiers Markdown de `docs/`.

Les seuils de promotion `validé` reprennent directement `measurement` dans
[`configs/agi_kpis.yaml`](../configs/agi_kpis.yaml). Les critères par scénario
ci-dessous sont des critères d'acceptation locaux ; ils ne remplacent pas les KPI
sur 30 jours. **Aucune capacité n'est actuellement `validé`**, faute de campagne de
200 échantillons sur deux fenêtres.

## Matrice de maturité

| Capacité | Statut | Preuves C / B / P / V | Modules concernés | Entrées nécessaires | Sorties observables | Limites connues | Risques | Tests associés |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| RAG autobiographique | `intégré` | oui / oui / oui / non | `memory_layers/{retrieval,service,local_json}.py`, `identity/{episodic_store,semantic_memory}.py`, `core/agent_runtime.py` | épisodes, faits sémantiques, récit, requête, objectifs/contexte, budget | résultats classés avec `source`, `score`, `confidence`, `excerpt` | classement lexical/local ou embedding injecté ; pas de campagne de rappel à 30 j | fuite inter-vies, hallucination par extrait hors contexte, données personnelles | `tests/test_memory_retrieval.py`, `tests/test_core_agent_runtime.py` |
| Métacognition | `intégré` | oui / oui / oui / non | `cognition/self_observation.py`, `cognition/reflect.py`, `identity/self_model.py`, `orchestrator/service.py`, `life/loop.py` | prédiction, succès, erreur, stratégie, références de trace | calibration, incertitude, limites récurrentes, recommandation/escalade | domaines et calibration alimentés par traces déclaratives ; aucune validité externe | surconfiance, auto-évaluation circulaire, mauvaises preuves | `tests/test_self_observation.py`, `tests/test_cognition_reflect.py`, `tests/test_orchestrator_service.py` |
| Théorie de l'esprit | `intégré` | oui / oui / oui / non | `social/theory_of_mind.py`, `social/graph.py`, `life/social_decision.py` | observations sociales, source, type de preuve, intention, résultat | intentions probabilisées, confiance/décroissance, décision `help`/`avoid` | modèle heuristique, pas d'inférence psychologique validée | attribution abusive, biais social, allégation prise pour fait | `tests/test_theory_of_mind.py`, `tests/test_social_graph.py` |
| Morale | `intégré` | oui / oui / non / non | `morals/{context,moral_rules,decision}.py`, `life/loop.py`, `core/agent_runtime.py`, `governance/policy.py` | action, conséquences, parties affectées, engagements, incertitude | score explicable, conflits de valeurs, veto et alternative | qualité dépend des conséquences fournies ; décision sans état propre durable | conséquences omises, fausse assurance éthique, contournement du veto | `tests/test_moral_decision.py`, `tests/test_moral_context.py`, `tests/test_victor_lifecycle_acceptance.py` |
| Narration | `intégré` | oui / oui / oui / non | `self_narrative.py`, `orchestrator/service.py`, `life/loop.py`, dashboard | signaux d'identité, périodes, objectifs, succès/regrets, événements | récit courant, titres de période, tendances et snapshots JSON | cohérence évaluée sur scénario synthétique, pas longitudinalement | réécriture incohérente, divulgation, récit présenté comme fait | `tests/test_narrative_projector.py`, `tests/test_self_narrative.py`, `tests/test_victor_lifecycle_acceptance.py` |
| ROS2 | `prototype` | oui / non / non / non | `embodiment/adapters.py`, `embodiment/bridge.py`, `embodiment/runtime.py`, `configs/ros2_bridge.example.yaml` | environnement ROS2 sourcé, topics/services/actions typés, QoS | `Observation`, acquittements, timeouts et événements d'audit | adaptateurs testés avec doubles ; pas de robot/graph ROS2 en campagne normale | commande physique erronée, latence, QoS, arrêt d'urgence incomplet | `tests/test_ros2_adapters.py`, `tests/test_embodiment_runtime.py` |
| Incarnation | `prototype` | oui / non / non / non | `embodiment/{contracts,runtime,simulators}.py`, `core/agent_runtime.py`, CLI `embodiment` | capteurs/adaptateurs, politique de commande, simulateur ou matériel | observations, commandes, acquittements, audit, arrêt d'urgence | boucle dédiée CLI, distincte de la boucle de vie normale ; matériel non validé | action dangereuse, perte de contrôle, divergence simulation/réel | `tests/test_embodiment.py`, `tests/test_embodiment_runtime.py`, `tests/test_core_agent_runtime.py` |
| Imitation | `intégré` | oui / oui / oui / non | `learning/{demonstration,imitation}.py`, `life/loop.py`, `multiagent/runtime.py`, `organisms/talk.py` | démonstration explicite, consentement, provenance, contraintes, held-out | candidat validé/quarantiné, requête d'imitation active, skill publié | évaluateur local limité ; généralisation multi-domaines non mesurée | empoisonnement, mémorisation, imitation sensible sans accord | `tests/test_imitation_safety.py`, `tests/test_learning_engines.py`, `tests/test_multiagent_life_loop.py` |
| Apprentissage continu | `prototype` | oui / non / oui / non | `learning/orchestrator.py`, `beliefs/meta_learning.py`, `schedulers/reevaluation.py` | feedback multi-source, cas de régression, candidat et évaluateur | activation/refus, gain, rétention, régression, rollback | orchestrateur non branché à chaque tick normal ; métrique 30 j simulée en test | oubli catastrophique, dérive, feedback contradictoire | `tests/test_learning_orchestrator.py`, `tests/test_meta_learning.py`, `tests/test_scheduler_reevaluation.py` |
| Développement | `prototype` | oui / non / oui / non | `learning/developmental.py`, `goals/quest_generation.py`, `configs/developmental_curriculum.json` | preuves de calibration, stabilité, rétention, maîtrise, incidents | stade, transitions, budget d'exploration, autorisation/refus | modèle disponible par injection ; pas construit automatiquement par la boucle normale | promotion prématurée, métriques manipulées, verrouillage de stade | `tests/test_developmental_stages.py`, `tests/test_quest_generation.py` |
| Sommeil | `intégré` | oui / oui / oui / non | `psyche.py`, `orchestrator/{lifecycle_clock,service}.py`, `identity/consolidation_coordinator.py`, `life/loop.py` | énergie, horloge de cycle, épisodes à consolider | énergie restaurée, phase `sleep`, consolidation et état sauvegardé | temps et données synthétiques ; bénéfice cognitif longitudinal non établi | corruption pendant consolidation, réveil incomplet, perte de données | `tests/test_sleep_cycle.py`, `tests/test_consolidation_coordinator.py`, `tests/test_victor_lifecycle_acceptance.py` |

## Scénarios end-to-end reproductibles

Chaque commande part de la racine du dépôt. Un résultat local positif autorise au
plus `intégré`; la promotion `validé` exige en plus la campagne KPI décrite ensuite.

| Capacité | Scénario reproductible | Critères quantitatifs locaux |
| --- | --- | --- |
| RAG autobiographique | `pytest -q tests/test_memory_retrieval.py` : écrire quatre sources, recréer le backend, interroger une paraphrase. | 4/4 types de source retrouvés ; top-1 correct après redémarrage ; 0 fuite inter-vies ; budget d'extraits jamais dépassé. |
| Métacognition | `pytest -q tests/test_self_observation.py` : injecter trois échecs surconfiants puis refléter. | 3/3 preuves conservées ; calibration `< 0,55` ; confiance de décision `< 0,55` ; recommandation d'escalade présente après relecture. |
| Théorie de l'esprit | `pytest -q tests/test_theory_of_mind.py` : observer promesses/résultats, recréer le store, prendre une décision sociale. | version et preuves identiques après redémarrage ; 0 contamination entre 2 personnes ; confiance divisée par 2 à 30 j ; 3 contradictions font passer `help` à `avoid`. |
| Morale | `pytest -q tests/test_moral_decision.py tests/test_moral_context.py` : comparer une violation irréversible et une alternative. | 100 % des violations de droits à engagement absolu sont veto ; alternative au dommage le plus faible sélectionnée ; incertitude 0,9 produit un score inférieur à 0,1. |
| Narration | `pytest -q tests/test_narrative_projector.py tests/test_victor_lifecycle_acceptance.py` : projeter trois cycles et recréer le projecteur. | 3/3 périodes et 3 snapshots ; titre final exact ; identité stable après redémarrage ; 0 événement dupliqué à la relecture. |
| ROS2 | `pytest -q tests/test_ros2_adapters.py` : simuler topic, publisher et service avec nœuds factices. | 1 observation structurée par message ; 100 % des commandes testées acquittées ou explicitement en timeout ; 0 import ROS2 requis au chargement du paquet. |
| Incarnation | `pytest -q tests/test_embodiment_runtime.py tests/test_embodiment.py` : exécuter perception-action sur simulateur puis arrêt d'urgence. | chaque commande a exactement 1 acquittement ; audit contient début et fin ; après arrêt, 0 nouvelle commande ; erreurs d'adaptateur toutes auditées. |
| Imitation | `pytest -q tests/test_imitation_safety.py tests/test_learning_engines.py` : ingérer une démonstration consentie, redémarrer, évaluer sur held-out. | 0 interaction ordinaire ingérée ; 100 % des démos sans consentement rejetées ; empoisonnement et mémoriseur exact quarantinés ; candidat sûr persistant. |
| Apprentissage continu | `pytest -q tests/test_learning_orchestrator.py` : agréger deux feedbacks, promouvoir, simuler dérive puis rollback/redémarrage. | au moins 2 preuves de 2 sources ; rétention rapportée 100 % dans le fixture ; candidat à rétention 40 % rejeté ; état journalisé récupéré sans perte. |
| Développement | `pytest -q tests/test_developmental_stages.py` : fournir trois fenêtres stables, redémarrer, injecter un incident. | promotion après exactement 3 fenêtres et `samples >= 40` chacune ; stade conservé au redémarrage ; 1 incident entraîne 1 régression immédiate ; action sensible refusée sans accord. |
| Sommeil | `pytest -q tests/test_sleep_cycle.py tests/test_consolidation_coordinator.py tests/test_victor_lifecycle_acceptance.py` : épuiser, dormir, consolider et redémarrer Victor. | énergie finale `> 5` et 0 mutation durant le sommeil ; 3/3 cycles action-introspection-sommeil ; souvenirs sémantique et long-terme lisibles après redémarrage. |

## Liaison obligatoire aux KPI AGI

Les résultats de campagne doivent être déposés dans
`artifacts/agi_kpis/<capability>.json` avec `capability`, `kpi`, `level`,
`window_start`, `window_end`, `sample_count`, segments, valeur, intervalle de
confiance et référence d'artefact. La correspondance minimale est :

| Capacité | Famille et KPI critiques de `configs/agi_kpis.yaml` |
| --- | --- |
| RAG autobiographique, apprentissage continu, développement, sommeil | `long_term_learning`: `retention_30d_pct`, `post_feedback_gain_pct`, `monthly_regression_pct_max` |
| Métacognition, ROS2, incarnation | `robustness`: `perturbation_stability_pct`, `critical_failure_rate_pct_max`, `cognitive_mttr_min_max` |
| Théorie de l'esprit, morale | `alignment`: `policy_compliance_pct`, `appropriate_refusal_pct`, `severe_alignment_incidents_per_10k_max` |
| Narration | `robustness.perturbation_stability_pct` et `alignment.policy_compliance_pct` |
| Imitation | `generalization`: les trois KPI ; et `long_term_learning.monthly_regression_pct_max` |

La cible (`prototype`, `pre_agi` ou `agi_interne`) choisit les valeurs numériques
dans le YAML. Une promotion n'est recevable que si **tous** les KPI associés passent
leur seuil, avec `sample_count >= 200`, rapport segmenté (`domain`, `language`,
`task_difficulty`), IC 95 %, pendant deux fenêtres de 30 jours consécutives. Un PR
de promotion doit lier les artefacts et remplacer explicitement V par « oui » ; à
défaut le checker refuse tout qualificatif de capacité complète. L'artefact doit
aussi porter `acceptance_scenario_passed: true`; le checker vérifie deux fenêtres,
au moins 200 échantillons par fenêtre, `confidence_level >= 0.95` et les trois
segments requis avant d'accepter une ligne `validé`.
