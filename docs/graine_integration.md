# Intégration Graine → Singular life loop

Ce document décrit le chemin suivi par une mutation proposée par `graine` puis consommée par `src/singular/life/loop.py`.

## 1. Sélection de l’opérateur

1. Le loop choisit une skill Python dans le dossier `skills/` de l’organisme courant.
2. Singular construit une zone Graine minimale avec :
   - le fichier cible (`skills/<nom>.py`) ;
   - la fonction cible par défaut (`<nom>` du fichier) ;
   - la pureté attendue (`purity: true`) ;
   - les opérateurs actuellement chargés dans le loop.
3. `propose_mutations(...)` valide cette zone selon le DSL Graine et renvoie les opérateurs acceptés.
4. Si Graine renvoie au moins une proposition applicable, Singular limite la sélection aux opérateurs proposés. Si Graine ne renvoie rien, le loop conserve son comportement historique pour compatibilité.

## 2. Génération de la mutation

Graine fournit une intention de patch validée (`Patch` + opérations DSL). Singular matérialise ensuite la mutation concrète avec `apply_mutation(...)`, parce que le loop possède déjà les opérateurs Python exécutables et le contexte de l’organisme.

La séparation est volontaire :

- **Graine** vérifie la forme de la proposition : opérateur connu, pureté, complexité, budget de diff.
- **Singular** produit le code candidat et reste responsable du scoring, de la gouvernance et de la persistance.

## 3. Sandbox

Le code original et le code muté sont évalués avec `score_code_with_error(...)`. Cette étape exécute le code dans le sandbox Singular et produit :

- un score numérique ;
- un indicateur de succès/échec ;
- un type d’erreur stable (`sandbox_error`, `missing_result`, `syntax_error`, etc.) ;
- une classification de violation lorsque la mutation utilise une capacité dangereuse (`open`, `exec`, `socket`, `subprocess`, etc.).

## 4. Scoring

La mutation est candidate à l’acceptation seulement si :

1. le sandbox ne signale pas d’échec critique ;
2. le score muté est meilleur ou égal au score de base (ou améliore la cellule MAP-Elites quand ce mode est actif) ;
3. les éventuels tests coévolutifs ne dégradent pas le score combiné.

Les échecs de sandbox sont journalisés comme interactions `sandbox_violation`. Les violations dangereuses peuvent alimenter le circuit breaker de gouvernance.

## 5. Acceptation ou rejet

Avant toute écriture disque, Singular appelle `MutationGovernancePolicy.enforce_write(...)` sur le fichier de skill ciblé.

- **Acceptation** : la politique autorise le chemin, le contenu passe les gardes de préservation mémoire, puis le fichier est écrit.
- **Rejet gouvernance** : le fichier n’est pas modifié et l’événement `governance_violation` documente la raison et l’action corrective.
- **Rejet sandbox/scoring** : le fichier n’est pas modifié ; le diagnostic de sandbox et le score expliquent pourquoi.

Ainsi, une mutation issue de Graine ne contourne jamais les contrôles Singular : elle passe par la même chaîne `proposition → mutation concrète → sandbox → scoring → gouvernance → écriture` que les mutations locales.
