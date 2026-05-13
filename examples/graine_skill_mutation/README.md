# Exemple minimal : mutation de skill via Graine

Cet exemple montre le plus petit dossier `skills/` utilisable par le loop de vie
pour consommer une proposition Graine.

```text
examples/graine_skill_mutation/
└── skills/
    └── minimal.py
```

`minimal.py` expose simplement un `result` numérique. Le loop sélectionne la
skill, demande à Graine quels opérateurs DSL sont applicables, matérialise la
mutation avec l’opérateur Python correspondant, puis applique sandbox, scoring et
gouvernance avant d’écrire.

Commande reproductible depuis la racine du dépôt :

```bash
PYTHONPATH=src python - <<'PY'
import ast
import random
from pathlib import Path

from singular.governance.policy import MutationGovernancePolicy
from singular.life.loop import run


def decrement_first_int(tree: ast.AST, rng=None) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            node.value -= 1
            break
    return tree

root = Path("examples/graine_skill_mutation")
skill = root / "skills" / "minimal.py"
skill.write_text("result = 3\n", encoding="utf-8")

run(
    root / "skills",
    root / "checkpoint.json",
    budget_seconds=0.1,
    max_iterations=1,
    rng=random.Random(0),
    # Le nom correspond à un opérateur connu du DSL Graine.
    operators={"CONST_TUNE": decrement_first_int},
    governance_policy=MutationGovernancePolicy(modifiable_paths=("skills",)),
)

print(skill.read_text(encoding="utf-8"))
PY
```

Résultat attendu : `minimal.py` reste dans le dossier autorisé `skills/` et sa
valeur `result` diminue si le sandbox et le score acceptent la mutation.
