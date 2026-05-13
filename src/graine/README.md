# Graine

Prototype of a secure closed-loop evolutionary patching system.

This repository provides a skeleton implementation following a restricted DSL
and security-focused architecture. Many components are placeholders and require
further development.

## Objective

Graine explores how software can evolve through strictly controlled patches
while remaining verifiable and deterministic. The project aims to provide a
research platform for secure closed-loop patch generation and evaluation.

## Installation

Clone the repository and install it in editable mode:

```bash
git clone <repo-url>
cd graine
pip install -e .
```

## Usage

The package is a skeleton and exposes no runtime interface yet. You can import
the module in Python to experiment with extensions:

```python
import graine
```

Future revisions will include command-line tools for patch tournaments and
analysis.

## Limitations

- Many components are placeholders and must be implemented before production
  use.
- The environment is intentionally sandboxed: no network, subprocesses, or FFI.
- Only repository files are accessible; external resources are not supported.

## Consommation par `src/singular/life/loop.py`

`graine.evolver.generate.propose_mutations` est consommé par le loop de vie
Singular comme générateur d’intentions de mutation, pas comme écrivain direct de
fichiers. Le loop construit, pour la skill courante, une zone minimale contenant
le chemin `skills/<skill>.py`, la fonction cible implicite et la liste des
opérateurs chargés. Graine valide cette zone avec son DSL (`Patch`, opérateurs
connus, pureté, limites de complexité) et renvoie les opérateurs applicables.

Dans `src/singular/life/loop.py`, ces propositions servent à borner la sélection
d’opérateur avant l’appel à `apply_mutation`. Singular garde ensuite la
responsabilité complète de l’exécution sûre : la mutation concrète est évaluée en
sandbox, scorée, puis soumise à `MutationGovernancePolicy.enforce_write` avant
toute persistance dans `skills/`. Une proposition Graine ne peut donc pas écrire
hors sandbox ni contourner les règles de gouvernance ; elle ne fait que réduire
l’espace de recherche à des mutations DSL-valides.
