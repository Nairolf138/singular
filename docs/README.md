# Index de la documentation

La [grammaire des parcours CLI de recette](cli-visible-paths.fr.md) décrit les
groupes `skills`, `quest`, `social`, `self-narrative` et `cognition`, ainsi que
le placement cohérent de `--life` et la migration des anciennes syntaxes.

Cet index est le point d'entrée canonique de la documentation Singular. Les
documents de planification et les spécifications cibles sont volontairement
séparés des fonctions utilisables afin qu'une intention ne soit pas interprétée
comme une promesse produit.

## Taxonomie de statut

Une fonctionnalité documentée porte **un seul** des statuts suivants. Le statut
qualifie sa disponibilité dans le dépôt courant, pas son importance :

| Statut | Signification | Engagement |
| --- | --- | --- |
| `stable` | Parcours utilisable via une entrée CLI ou dashboard, couvert par un scénario d'acceptation maintenu. | Compatibilité et corrections de régression. |
| `experimental` | Implémentation exécutable, mais interface, comportement ou persistance encore susceptibles de changer. | Essais locaux ; pas de garantie de compatibilité. |
| `optional` | Intégration disponible seulement avec une dépendance, un service ou du matériel facultatif. | Support limité au prérequis annoncé. |
| `target-only` | Cible, proposition, KPI ou travail planifié ; aucune disponibilité produit n'est affirmée. | Aucun point d'entrée garanti. |
| `deprecated` | Compatibilité transitoire conservée pour migrer un ancien usage. | Ne pas adopter ; suivre le remplacement indiqué. |

`stable` n'est pas synonyme de « capacité cognitive validée » : les preuves
C/B/P/V et les campagnes longitudinales restent définies dans la
[matrice cognitive](cognitive-capabilities-matrix.md). Toute nouvelle déclaration
`stable` doit ajouter une ligne au registre ci-dessous avec entrée, prérequis et
acceptation. Une fonction conditionnée par un extra ou un système externe est
`optional`, même si ses tests sont fiables.

## Registre des capacités `stable`

Toutes les commandes partent de la racine du dépôt. Le prérequis commun est
Python 3.10+ et une installation `pip install -e .`; chaque scénario utilise un
répertoire temporaire fourni par pytest.

| Capacité stable | Point d'entrée | Prérequis spécifiques | Test ou scénario d'acceptation |
| --- | --- | --- | --- |
| Créer et sélectionner une vie | `singular lives create --name Lumen`, puis `singular lives use lumen` | Root accessible en écriture ; nom de vie unique. | `pytest -q tests/test_cli_lives.py tests/test_lives.py` |
| Initialiser le starter-pack | `singular lives create --name Lumen --starter-profile assistant` | Root accessible ; profil `assistant` distribué avec le paquet. | `pytest -q tests/test_birth_starter_profiles.py tests/test_living_starter_integration.py` |
| Consulter les vies | `singular lives list` | Root initialisé ; aucune vie n'est requise pour afficher un registre vide. | `pytest -q tests/test_cli_lives.py tests/test_multi_life_help_integration.py` |
| Consulter l'état d'une vie | `singular status --format table` | Une vie active, ou `--life <slug>`. | `pytest -q tests/test_life_status.py tests/test_cli_lives.py` |
| Produire un rapport de run | `singular report --format plain` | Une vie active ; un run existant pour un rapport non vide. | `pytest -q tests/test_report.py` |
| Conversation locale avec fallback | `singular talk --prompt "Bonjour"` | Une vie active ; le provider `dummy` assure le fallback sans service externe. | `pytest -q tests/test_end_to_end.py tests/providers/test_llm_fallback_chain.py` |
| Diagnostic d'installation | `singular doctor` | Aucun service distant requis ; les intégrations absentes sont rapportées. | `pytest -q tests/test_cli_doctor.py tests/providers/test_provider_doctor.py` |
| Politique de rétention | `singular retention status` et `singular retention run --dry-run` | Root accessible ; appliquer sans `--dry-run` exige de valider les suppressions. | `pytest -q tests/test_cli_retention.py tests/test_retention.py` |

## Guides utilisateur

- [README et démarrage rapide](../README.md)
- [Tutoriel FR — créer une vie](tutorial_create_life.fr.md)
- [Tutorial EN — create a life](tutorial_create_life.en.md)
- [Dashboard : installation et utilisation](dashboard.md)
- [Profil de démarrage `living`](living_starter_profile.md)
- [Personnaliser `policy.yaml`](policy_customization.md)
- [Bridge ROS2 optionnel](ros2_bridge.md)

## Exploitation

- [Reprise sécurisée](safe_restart.md)
- [Diagnostic gouvernance et circuit breaker](governance_circuit_breaker.md)
- [Métriques hôte](host_metrics.md)
- [Registre des générations et rollback](generations_registry.md)
- [Audit des modules runtime](runtime-package-audit.md)
- [Matrice de fiabilité fonctionnelle](functional-reliability-matrix.md)

## Référence technique

- [Référence CLI française](cli-reference.fr.md)
- [CLI reference in English](cli-reference.en.md)
- [Artefacts mémoire](technical_memory_artifacts.md)
- [Statut de vie : source de vérité](technical_life_status.md)
- [Règles du cycle vital](vital_lifecycle_rules.md)
- [Signaux de perception et objectifs intrinsèques](perception_signals_intrinsic_goals.md)
- [Intégration Graine](graine_integration.md)

## Sécurité et gouvernance

- [Personnalisation de la politique](policy_customization.md)
- [Gouvernance et circuit breaker](governance_circuit_breaker.md)
- [Reprise sécurisée](safe_restart.md)
- [Critères d'acceptation du cycle persistant](acceptance_victor_lifecycle.md)

## Spécifications cibles

Ces documents sont `target-only` sauf statut explicite d'une sous-capacité :

- [Spécification cible AGI](agi_target_spec.md)
- [Matrice des capacités cognitives](cognitive-capabilities-matrix.md)

## Documents de planification

Ces documents décrivent du travail et des portes de sortie, pas des fonctions
livrées :

- [Critères de sortie release v2](release_v2.md)
- [Plan Dashboard Recovery](dashboard-recovery-plan.md)
