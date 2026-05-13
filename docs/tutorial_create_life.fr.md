# Tutoriel — créer une vie Singular

Ce tutoriel montre un parcours local complet : créer une vie, ajouter une compétence, lancer un tick d'évolution, inspecter la mémoire et le checkpoint, puis interpréter les logs. Les commandes utilisent un root de laboratoire isolé pour éviter de mélanger vos essais avec vos vies habituelles.

## Pré-requis

Installez Singular depuis la racine du dépôt :

```bash
pip install -e .[yaml,dashboard,viz]
```

Créez un espace de travail reproductible :

```bash
export SINGULAR_ROOT="$PWD/.singular-tutorial"
rm -rf "$SINGULAR_ROOT"
mkdir -p "$SINGULAR_ROOT"
```

> Sous Windows PowerShell, utilisez plutôt `$env:SINGULAR_ROOT = "$PWD/.singular-tutorial"`.

## 1. Créer une vie

```bash
singular --root "$SINGULAR_ROOT" lives create --name Lumen --curiosity 0.75 --patience 0.55
singular --root "$SINGULAR_ROOT" lives list
```

La commande crée un dossier de vie sous `lives/`, sélectionne cette vie dans le registre et initialise :

- `skills/` : les compétences exécutables et mutables ;
- `mem/` : les artefacts de mémoire (`psyche.json`, `profile.json`, `values.yaml`, journaux JSONL, etc.) ;
- `runs/` : les traces des runs exécutés pour cette vie.

Vérifiez la vie active :

```bash
singular --root "$SINGULAR_ROOT" status --format table
```

## 2. Ajouter une compétence simple

Les mutations autonomes écrivent normalement dans `skills/`, mais vous pouvez aussi ajouter manuellement une compétence de départ. Identifiez d'abord le chemin de la vie :

```bash
LIFE_DIR=$(python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["SINGULAR_ROOT"])
registry = json.loads((root / "lives" / "registry.json").read_text())
active = registry["active"]
print(registry["lives"][active]["path"])
PY
)
```

Ajoutez une skill pure et déterministe :

```bash
cat > "$LIFE_DIR/skills/greet.py" <<'PY'
def greet(name="ami"):
    """Return a deterministic greeting."""
    return f"Bonjour {name}!"

result = greet("Lumen")
PY
```

Bonnes pratiques pour une skill débutante :

- une fonction principale courte ;
- pas d'accès réseau ;
- pas d'écriture hors du dossier de l'organisme ;
- une variable `result` utile aux tests/sandbox si la boucle l'évalue.

## 3. Lancer un tick d'évolution

L'interface moderne de la boucle est temporelle : `--budget-seconds` remplace l'ancien pilotage par nombre de ticks.

```bash
singular --root "$SINGULAR_ROOT" --life lumen loop --budget-seconds 5 --run-id tutorial_tick
```

Pendant ce tick, Singular peut sélectionner une skill, proposer une mutation, l'évaluer en sandbox, scorer le résultat, appliquer la gouvernance d'écriture, puis journaliser le verdict. Une mutation rejetée est normale : le journal explique si le rejet vient du sandbox, du score, de la gouvernance ou d'un quota.

## 4. Inspecter mémoire et checkpoint

La mémoire de la vie est située dans `mem/` :

```bash
find "$LIFE_DIR/mem" -maxdepth 1 -type f | sort
python -m json.tool "$LIFE_DIR/mem/psyche.json" | head -40
```

Points à regarder :

- `mem/psyche.json` : traits, humeur, fatigue, signaux sociaux éventuels ;
- `mem/profile.json` : identité et métadonnées de naissance ;
- `mem/episodic.jsonl` : épisodes vécus, une entrée JSON par ligne ;
- `mem/procedural.jsonl` : apprentissages et traces d'exécution ;
- `mem/generations.jsonl` : tentatives de mutation et verdicts ;
- `mem/policy_decisions.jsonl` : décisions de gouvernance bloquées, forcées ou en revue.

Le checkpoint par défaut de `loop` est placé à la racine de la vie :

```bash
python -m json.tool "$LIFE_DIR/life_checkpoint.json" | head -80
```

Il sert à reprendre l'état de boucle : itération courante, meilleur score connu, méta-informations et état persistant du run selon la version.

## 5. Interpréter les logs

Affichez un résumé humain :

```bash
singular --root "$SINGULAR_ROOT" --life lumen report --id tutorial_tick --format plain
```

Puis inspectez les fichiers bruts si nécessaire :

```bash
find "$LIFE_DIR/runs" -maxdepth 3 -type f | sort
```

Repères de lecture :

- `accepted` ou `improved` indique une mutation conservée ;
- `rejected`, `sandbox_error`, `syntax_error` ou `missing_result` indiquent un rejet technique ;
- `governance_violation` indique une écriture interdite ou une zone non autorisée ;
- `circuit_breaker_open` signale trop de violations dans une fenêtre courte ;
- `social_relation_update` apparaît dans les runs multi-vies quand le graphe social change.

Si le rapport est vide, vérifiez le `run-id`, le root et la vie active :

```bash
singular --root "$SINGULAR_ROOT" lives list
singular --root "$SINGULAR_ROOT" --life lumen status --verbose
```

## Tutoriel reproduction — deux parents et un enfant

La reproduction croise deux organismes à partir de leurs dossiers de vie. Créez deux parents :

```bash
singular --root "$SINGULAR_ROOT" lives create --name Alpha --curiosity 0.80 --resilience 0.70
singular --root "$SINGULAR_ROOT" lives create --name Beta --curiosity 0.45 --resilience 0.90
```

Récupérez leurs chemins :

```bash
python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["SINGULAR_ROOT"])
registry = json.loads((root / "lives" / "registry.json").read_text())
for slug in ("alpha", "beta"):
    print(slug, registry["lives"][slug]["path"])
PY
```

Sélectionnez les parents en fonction de critères auditables :

1. **Compatibilité sociale** : relation positive dans `SocialGraph` si les parents ont déjà interagi ;
2. **Complémentarité des skills** : des compétences différentes augmentent la diversité ;
3. **Viabilité** : santé suffisante des deux parents ;
4. **Gouvernance** : l'écriture de l'enfant doit rester dans une zone autorisée.

La commande directe crée l'enfant :

```bash
ALPHA_DIR=$(python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["SINGULAR_ROOT"])
registry = json.loads((root / "lives" / "registry.json").read_text())
print(registry["lives"]["alpha"]["path"])
PY
)
BETA_DIR=$(python - <<'PY'
import json, os, pathlib
root = pathlib.Path(os.environ["SINGULAR_ROOT"])
registry = json.loads((root / "lives" / "registry.json").read_text())
print(registry["lives"]["beta"]["path"])
PY
)
singular --root "$SINGULAR_ROOT" spawn "$ALPHA_DIR" "$BETA_DIR" --out-dir "$SINGULAR_ROOT/children/alpha-beta-child"
```

Ce qui se passe :

- `crossover` choisit une skill de chaque parent, vérifie que les signatures de fonctions correspondent et produit une skill hybride ;
- `inherit_psyche`, `inherit_values` et `inherit_episodic_memory` combinent une partie des artefacts non-code ;
- `authorize_reproduction_write` simule puis applique `MutationGovernancePolicy.enforce_write` avant d'écrire la skill enfant ;
- si le chemin de sortie est interdit ou non autorisé, la reproduction échoue avant modification destructrice.

Inspectez l'enfant :

```bash
find "$SINGULAR_ROOT/children/alpha-beta-child" -maxdepth 3 -type f | sort
python -m json.tool "$SINGULAR_ROOT/children/alpha-beta-child/mem/psyche.json" | head -60
```

## Tutoriel multi-agent — aide, réponse et SocialGraph

Le mode écosystème fait tourner plusieurs vies dans une boucle partagée. Les vies peuvent demander de l'aide si leur score est bas, offrir une compétence si leur confiance est haute, puis mettre à jour leurs relations.

Préparez une relation initiale facultative :

```bash
singular --root "$SINGULAR_ROOT" lives ally alpha beta
singular --root "$SINGULAR_ROOT" lives relations --name alpha
```

Lancez une courte boucle multi-vies :

```bash
singular --root "$SINGULAR_ROOT" ecosystem run --life alpha --life beta --budget-seconds 5 --run-id tutorial_ecosystem
```

Dans la boucle :

1. une vie en difficulté émet une demande d'aide (`help.requested`) ;
2. une vie confiante peut répondre par une offre (`help.offered`) ou une réponse ;
3. la gouvernance vérifie les interactions inter-vies, le niveau d'influence et les conflits ;
4. en cas d'entraide réussie, `SocialGraph.update_relation` augmente l'affinité et la confiance, et baisse la rivalité ;
5. en cas de conflit de ressources, la relation peut devenir plus rivale et déclencher une médiation si les seuils sont dépassés.

Inspectez le graphe social persistant :

```bash
python -m json.tool "$SINGULAR_ROOT/mem/social_graph.json" 2>/dev/null || true
find "$SINGULAR_ROOT" -path '*social_graph.json' -print
```

Selon la commande et le `SINGULAR_HOME` actif, le graphe peut être écrit dans la mémoire globale du root ou dans la mémoire de la vie active. Les événements à chercher dans les logs sont `help.requested`, `help.offered`, `help.completed`, `answer`, `social_relation_update`, `resource_conflict` et `governance_violation`.
