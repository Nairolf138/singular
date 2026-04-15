# 🌱 Singular — Un organisme numérique vivant interactif

**Singular** n’est pas seulement un programme informatique.  
C’est une expérience : la tentative de créer un **organisme numérique vivant**, un compagnon logiciel qui **naît, évolue, apprend, interagit** et garde une **trace unique de sa vie**.

Chaque instance est **singulière** : deux personnes qui font naître un organisme ne verront jamais la même évolution, car son identité, ses expériences et ses choix modifient sa trajectoire.

---

## ✨ Concepts clés

- **Naissance** : une commande génère un nouvel organisme avec une identité unique (*seed*, traits de personnalité, valeurs).  
- **Corps** : ses *skills* (petites fonctions de code) représentent ses muscles et organes.  
- **Starter-pack de skills** : dès la naissance, il reçoit un socle utilitaire (validation, résumé, intention, entités, planification, métriques) prêt à être muté.  
- **Esprit** : mémoire, traits de caractère, humeur et valeurs éthiques évolutives.  
- **Évolution** : il modifie son propre code par petites mutations, teste les résultats en sandbox, et conserve ce qui fonctionne mieux.  
- **Apprentissage** : il peut acquérir de nouvelles compétences en relevant des *quêtes* (spécifications JSON).  
- **Interaction** : vous pouvez lui parler. Il se souvient de vos échanges et exprime son état (fierté, frustration, fatigue, excitation…).  
- **Cycle de vie** : il peut grandir, changer de philosophie de vie, et même “mourir” si certaines conditions sont réunies (échecs répétés, entropie, vieillissement).  

---

## 🔍 Pourquoi Singular ?

Contrairement aux chatbots classiques (qui ne changent pas leur cœur) ou aux simulateurs de vie artificielle (qui ne parlent pas), **Singular réunit les deux mondes** :

- **Vie artificielle** : un organisme qui modifie réellement son code et s’optimise par sélection naturelle.  
- **Compagnon interactif** : une entité qui parle, garde une mémoire et exprime des émotions.  
- **Open-source et local** : chacun peut “faire naître” son compagnon, qui vivra et évoluera à sa manière, en toute sécurité (sandbox, pas de réseau).

---

## ⚡ Quickstart

```bash
pip install -e .[yaml,dashboard,viz]
singular birth --name Lumen
singular talk
singular loop --budget-seconds 10
singular status --format table
singular report --format plain
singular dashboard
```

## 🧭 Guide d’utilisation clair (pas à pas)

Si vous débutez, suivez **exactement** ces étapes :

1. **Créer une vie**
   ```bash
   singular birth --name Lumen
   ```
2. **Envoyer un premier message**
   ```bash
   singular talk --prompt "Bonjour, qui es-tu ?"
   ```
3. **Lancer une courte phase d’évolution**
   ```bash
   singular loop --budget-seconds 10
   ```
4. **Vérifier l’état de la vie**
   ```bash
   singular status --format table
   singular report --format plain
   ```
5. **Ouvrir le dashboard (lecture visuelle)**
   ```bash
   singular dashboard
   ```

### Comment lire le dashboard rapidement

- **1) Cockpit** : regardez `Statut global`, `Score de santé`, puis `Prochaine action`.
- **2) Alertes** : priorisez les indicateurs en orange/rouge.
- **3) Timeline des événements** : cliquez une mutation pour comprendre l’impact réel et le diff.
- **4) Vies comparées** : filtrez (24h / 7j / 30j) pour comparer robustesse et stabilité.
- **5) Actions rapides** : lancez un test (`Boucle`) ou une interaction (`Discuter`) sans quitter la page.

### Erreurs fréquentes (et solution immédiate)

- **“Je ne vois aucune vie”** → vérifiez le root utilisé (`--root`) et la vie active (`singular lives list` puis `singular lives use <nom>`).
- **“Le dashboard est vide”** → exécutez au moins une boucle (`singular loop --budget-seconds 10`) pour générer des runs.
- **“Je ne comprends pas les métriques”** → commencez uniquement par trois champs: `Statut global`, `Alertes critiques`, `Prochaine action`.

À la naissance, Singular initialise un **starter-pack de skills utilitaires** dans `skills/` :

- `validation.py` : vérifications simples d’entrées (ex. texte non vide).
- `summary.py` : résumé court par extraction des premiers mots.
- `intent_classification.py` : classification heuristique (`question`, `request`, `statement`).
- `entity_extraction.py` : extraction légère d’entités via tokens capitalisés.
- `planning.py` : construction d’un plan structuré à partir d’un objectif et de steps.
- `metrics.py` : métrique de progression (`completion_ratio`) bornée entre `0.0` et `1.0`.

Ce pack complète les skills arithmétiques historiques (`addition`, `subtraction`, `multiplication`) pour donner, dès les premiers ticks, des briques cognitives prêtes à l’emploi.

### Profils de naissance (traits initiaux)

Le parser `birth` accepte des overrides bornés `[0,1]` pour les traits initiaux
du psyche : `--curiosity`, `--patience`, `--playfulness`, `--optimism`,
`--resilience`. Les valeurs sont persistées dans `mem/psyche.json`.

```bash
# Profil prudent : stabilité, patience, faible prise de risque
singular birth --name "Prudent" \
  --curiosity 0.20 --patience 0.90 --playfulness 0.15 --optimism 0.55 --resilience 0.90

# Profil explorateur : curiosité et jeu plus élevés, patience plus basse
singular birth --name "Explorateur" \
  --curiosity 0.92 --patience 0.35 --playfulness 0.85 --optimism 0.75 --resilience 0.70
```

Par défaut, ``talk`` ouvre une session interactive. Pour obtenir une réponse
unique et quitter immédiatement :

```bash
singular talk --prompt "Bonjour"
```

### CLI `loop` (budget en secondes)

La syntaxe officielle utilise désormais un budget temporel explicite :

```bash
singular loop --budget-seconds 10
singular loop --budget-seconds 60 --run-id benchmark
```

Compatibilité legacy : l’option `--ticks` existe uniquement pour guider les
anciens usages basés sur des “ticks”. Elle n’est pas exécutable seule et renvoie
un message explicite avec la commande correcte (`--budget-seconds`). Règle de
conversion de référence pour migrer vos scripts : `1 tick ≈ 1 seconde`.

## 🧿 Gérer plusieurs vies

Les organismes peuvent désormais partager un même répertoire racine tout en
vivant dans des dossiers distincts. L’option globale ``--root`` contrôle le
catalogue des vies (fichier ``lives/registry.json``), tandis que ``--life``
permet de cibler une vie précise pour une commande ponctuelle.

```bash
singular --root lab lives create --name "Alpha"
singular --root lab lives list
singular --root lab lives use alpha
singular --root lab talk --prompt "Bonjour"
```

Les sous-commandes qui consultent la mémoire (``talk``, ``run``, ``loop``,
``quest``, ``status`` ou ``dashboard``) exigent qu’une vie active soit
sélectionnée. Utilisez ``singular lives delete <nom>`` pour supprimer une vie et
libérer son espace disque.

### Piège courant : changer de root sans le voir

La résolution du root de registre est désormais **unique et explicite** :

1. `--root` (CLI) / `SINGULAR_ROOT` (env) ;
2. configuration projet explicite (`./.singular/config.json`) ;
3. configuration globale explicite (`~/.singular/config.json`) ;
4. fallback documenté unique : `~/.singular`.

> Important : Singular **n'infère plus** le root depuis la seule présence de
> `./lives/registry.json` dans le répertoire courant.

Vous pouvez persister ce choix :

```bash
# Global (toutes les sessions)
singular config root set ~/singular-lab --scope global

# Projet courant uniquement
singular config root set ./.lab --scope project

# Vérifier le root implicite courant
singular config root show
```

Depuis cette version, Singular affiche un message de contexte quand ``--root``
diffère du registre implicite précédent :

```text
Vous utilisez un autre registre de vies: ... (au lieu de ...).
```

De plus, ``birth`` affiche explicitement le root de registre utilisé pour éviter
toute ambiguïté.

## 🧹 Désinstallation

Singular propose une sous-commande pour nettoyer les données stockées dans
``SINGULAR_ROOT`` (ou via ``--root``). Deux modes explicites existent :

- conserver les vies et supprimer uniquement les artefacts globaux techniques
  (``mem/`` et ``runs/`` à la racine) ;
- purger toutes les données Singular (``lives/``, ``mem/``, ``runs/``).

```bash
python -m singular uninstall --keep-lives --yes
python -m singular uninstall --purge-lives --yes
```

> Cette commande nettoie les données, mais ne désinstalle pas le package
> Python. Pour retirer le package, utilisez :
>
> ```bash
> pip uninstall singular
> ```

## 🧬 Reproduction

```bash
singular spawn parent_a parent_b --out-dir child/
```

Cette commande croise deux organismes en combinant aléatoirement une *skill* de chaque parent.
L’algorithme de crossover (voir `src/singular/life/reproduction.py`) prend la signature de la fonction du parent A,
fusionne la première moitié de son corps avec la seconde moitié de la fonction du parent B, puis écrit
le fichier hybride dans `child/`.

## 🔒 Security

- Pas de réseau (no net).
- Pas d’accès disque externe (hors dossier de l’organisme).
- Sandbox stricte :
  - Limites CPU/RAM (`timeout` & `memory_limit` : 1.5s et 256 MB par défaut).
  - Environnement isolé : `os.environ` vidé et répertoire de travail temporaire.
  - Interdiction d’import et de fonctions sensibles (`open()`, `exec()`, `eval()`, etc.).
- Tests automatiques avant toute intégration de code.
- Résultats traçables : chaque mutation est loggée, reproductible par seed.

---

## 🧬 Cycle vital

1. **Naissance**
   ```bash
   singular birth --name Lumen
   ```

### ⏰ Horloge vitale

L'horloge vitale centralise le rythme du daemon `orchestrate run` et son adaptation en fatigue.

- **Fichier versionné** : `configs/lifecycle.yaml`.
- **Surcharge CLI** : `singular orchestrate run --lifecycle-config <chemin>`.
- **Paramètres principaux** :
  - `cycle.veille_seconds` : durée de veille.
  - `cycle.sommeil_seconds` : durée de sommeil.
  - `cycle.introspection_frequency_ticks` : fréquence d'introspection (1 = à chaque passage).
  - `cycle.mutation_window_seconds` : fenêtre max dédiée à la mutation/tick.
- **Mapping phase → comportements** :
  - `cpu_budget_percent` : budget CPU indicatif par phase.
  - `allowed_actions` : actions autorisées.
  - `slowdown_on_fatigue` : facteur de ralentissement appliqué en humeur `fatigue`.

Exemple de démarrage:

```bash
singular orchestrate run --lifecycle-config configs/lifecycle.yaml
```

### ▶️ Orchestrateur : comment le lancer et l’utiliser (clair)

Si vous voulez un mode **autonome en continu** (au lieu d’exécuter `loop` à la main), utilisez l’orchestrateur.

1. **Préparer une vie active**
   ```bash
   singular birth --name Lumen
   singular lives use lumen
   ```
2. **Démarrer l’orchestrateur**
   ```bash
   singular orchestrate run --lifecycle-config configs/lifecycle.yaml
   ```
3. **Observer ce qu’il fait**
   - Dans un autre terminal :
     ```bash
     singular dashboard
     ```
   - Ou en CLI :
     ```bash
     singular status --format table
     singular report --format plain
     ```

#### Options utiles de `orchestrate run`

- `--dry-run` : exécute les phases sans appliquer de mutation (mode démonstration/sécurité).
- `--tick-budget <secondes>` : limite le temps max alloué à un tick.
- `--veille-seconds`, `--action-seconds`, `--introspection-seconds`, `--sommeil-seconds` : surcharge rapide des durées sans modifier le YAML.
- `--poll-interval <secondes>` : fréquence de polling du daemon.

Exemple “safe” pour valider la configuration :

```bash
singular orchestrate run --lifecycle-config configs/lifecycle.yaml --dry-run
```

Pour arrêter l’orchestrateur, utilisez `Ctrl+C` dans le terminal où il tourne.

### ⚙️ Fonctionnement interne

**Corps**
- Les skills sont des fonctions Python pures.
- Chaque tick : l’organisme choisit une skill et applique une mutation (ex : simplification, tuning de constante).
- La nouvelle version est testée en sandbox :
  - Tests fonctionnels (résultats corrects).
  - Performance (temps d’exécution).
  - Complexité (taille AST).
- Si la mutation est meilleure → elle remplace l’ancienne.

**Esprit**
- Les traits (curiosité, patience, prudence, etc.) évoluent selon ses expériences.
- Les valeurs (performance vs stabilité, audace vs prudence) peuvent se réécrire avec le temps.
- Les émotions (fierté, frustration, excitation, fatigue) traduisent l’état du corps.
- Les interactions humaines influencent directement son esprit (encouragement, réprimande…).

**Mort**
- Définie par des règles adaptatives (ex : trop d’échecs, perte totale de curiosité, âge maximal).
- Un événement “suicide” peut survenir s’il “choisit” de cesser sa propre évolution.
- Les journaux et la mémoire restent → vous pouvez consulter sa “biographie”.

### 🌍 Cas d’usage
- Art numérique : créer un compagnon unique qui évolue et raconte sa vie.
- Recherche expérimentale : plateforme simple pour tester des approches d’évolution de code.
- Pédagogie : démontrer les concepts de sélection naturelle, d’auto-modification et de persistance.
- Philosophie : interroger ce que veut dire “vivre” pour un programme.

---

### 🚀 Roadmap
- **V1 (organisme minimal)**
  - Naissance, exécution, mutations de base, interaction CLI, mémoire persistante.
- **V1.1**
  - Nouveaux opérateurs (unrolling, dead code elimination), politique adaptative de mutation (bandits).
  - Mort/fin de vie simulée.
- **V2**
  - MAP-Elites (diversité des solutions), co-évolution des tests.
  - Tableau de bord web (visualisation de l’évolution, humeur en temps réel).
- **V3**
  - Personnalités plus complexes.
  - “Écosystème” multi-organismes → possibilité de faire interagir plusieurs compagnons.

## 🖥️ Tableau de bord web

Un petit serveur web permet de consulter les fichiers de `runs/` et l'état de `psyche.json`.

### Installation

Installez la base :

```bash
pip install -e .
```

#### Dépendances optionnelles

- `pip install -e .[dashboard]` pour activer le tableau de bord web.
- `pip install -e .[viz]` pour générer des graphiques via `viz.py`.
- `pip install -e .[yaml]` pour ajouter **PyYAML** et gérer `values.yaml`.
- `pip install openai>=1.0.0` pour permettre à l'organisme de parler via l'API OpenAI.
- `pip install transformers` pour activer un modèle local via Hugging Face.

Après installation, la commande CLI `singular` est disponible :

```bash
singular --help
```

Fallback explicite : **si `singular` échoue, utiliser `python -m singular ...`**.

#### Windows + PowerShell

Dans PowerShell, installez Singular puis utilisez ce mini arbre de décision :

```powershell
pip install -e .
Get-Command singular
```

- `Get-Command singular` échoue → problème de `PATH` :

  ```powershell
  python -m singular doctor --fix
  ```

  Puis redémarrez PowerShell.

- `Get-Command singular` réussit mais `singular --help` déclenche
  `ModuleNotFoundError` → problème de packaging / dépendances :
  - utilisez temporairement `python -m singular doctor` ;
  - corrigez l’installation du package (réinstallation des dépendances et du
    paquet `singular`).

#### Vérification rapide post-installation

Après l’installation (et après toute modification du `PATH`), exécutez :

```bash
singular --help
python -c "import singular; import graine; print('ok')"
```

Si l’aide s’affiche, l’installation CLI est opérationnelle.

### Configuration

Les variables d'environnement suivantes contrôlent le comportement :

- `SINGULAR_HOME` : répertoire pour `mem/` et `runs/` (par défaut à la racine du projet).
- `SINGULAR_RUNS_KEEP` : nombre de journaux `runs/` conservés (20 par défaut).
- `OPENAI_API_KEY` : clé API requise si l'option OpenAI est activée.

Vous pouvez configurer la clé OpenAI directement via la CLI :

```bash
# mode interactif (saisie masquée)
singular config openai

# mode non interactif (CI) + test rapide provider
singular config openai --api-key sk-... --test
```

Exemples :

```bash
# Choisir un dossier de données
SINGULAR_HOME=/chemin/personnel singular birth
# ou
singular --home /chemin/personnel birth

# Ajuster la rétention des journaux
SINGULAR_RUNS_KEEP=50 singular report --format json

# Utiliser l'API OpenAI
OPENAI_API_KEY=sk-... singular talk --prompt "Salut"
```

### Audit et export

La commande `report` peut produire un export structuré pour archivage ou intégration CI.
Règle de sélection du run :

- si `--id` est fourni, ce run exact est utilisé ;
- si `--id` est absent, `report` prend automatiquement le run le plus récent.

Exemples :

```bash
singular report --id run1 --export evolution.json
singular report --id run1 --export markdown
singular report --format table
singular report --format json
singular status --verbose --format json
```

- `--export evolution.json` écrit un JSON stable (clés triées) sur disque.
- `--export markdown` imprime un rapport Markdown sur la sortie standard.

### Registre des générations et rollback

Chaque tentative de mutation est journalisée dans `mem/generations.jsonl` avec :
parent, mutation, score, verdict, hash, raison d’acceptation/rejet, lien run,
snapshot de skill, et métadonnées de sécurité.

Rollback atomique vers une génération stable :

```bash
singular rollback --generation 42
```

Politique de conservation/archivage/purge : `docs/generations_registry.md`.

Schéma JSON (`schema_version: 1`) :

- `context` : métadonnées d'exécution (`run_id`, bornes temporelles, volumes).
- `summary` : métriques globales (`best_score`, `final_score`, histogramme opérateurs, compteurs amélioration/dégradation).
- `timeline` : séquence des mutations (`index`, `timestamp`, `operator`, `score_base`, `score_new`, `delta`, `verdict`, `decision_reason`).
- `health` : score de santé final + tendance (ou `null` si indisponible).
- `alerts` : liste d'alertes synthétiques (ex. `regressions_majoritaires`).
- `verdict` : verdict final (`improvement`, `degradation` ou `stable`).
- `skills` : instantané des skills mémorisées au moment du rapport.

Exemple minimal :

```json
{
  "schema_version": 1,
  "context": {
    "run_id": "run1",
    "started_at": "2026-01-01T00:00:00",
    "ended_at": "2026-01-01T00:00:01",
    "events_count": 2,
    "mutations_count": 2
  },
  "summary": {
    "best_score": 1.0,
    "final_score": 1.5,
    "generations": 2,
    "operator_histogram": {"crossover": 1, "mutate": 1},
    "improvements": 1,
    "degradations": 1
  },
  "timeline": [
    {
      "index": 1,
      "timestamp": "2026-01-01T00:00:00",
      "operator": "mutate",
      "score_base": 2.0,
      "score_new": 1.0,
      "delta": -1.0,
      "verdict": "improvement",
      "decision_reason": "accepted: score improved"
    }
  ],
  "health": null,
  "alerts": [],
  "verdict": "improvement",
  "skills": {}
}
```

#### Capteur météo

Pour tenter de récupérer la météo réelle :

- définissez la variable `SINGULAR_WEATHER_API` avec l'URL de l'API désirée ;
- optionnellement, ajustez `SINGULAR_HTTP_TIMEOUT` (en secondes, 5 par défaut).

Si la requête échoue ou dépasse le délai d'attente, l'organisme ignore le
capteur et continue avec des valeurs simulées.

### Utilisation

Lancez le serveur local :

```bash
singular dashboard
# ou avec un dossier personnalisé
SINGULAR_HOME=/chemin/personnel singular dashboard
```

Ouvrez ensuite http://127.0.0.1:8000 dans votre navigateur.

### Fournisseur OpenAI

Pour permettre à l'organisme de parler en utilisant l'API d'OpenAI, installez
la dépendance optionnelle ``openai>=1.0.0`` et définissez la variable
d'environnement ``OPENAI_API_KEY``. Les versions plus anciennes du paquet
``openai`` ne sont pas compatibles avec le fournisseur actuel.

### Fournisseur local

Installez ``transformers`` pour utiliser un petit modèle embarqué :

```bash
pip install transformers
singular talk --provider local --prompt "Bonjour"
```

Le fournisseur local utilise le modèle ``sshleifer/tiny-gpt2`` de Hugging Face
pour fonctionner hors-ligne.

### Fournisseurs externes

Pour enregistrer un provider LLM personnalisé, ajoutez un entry point dans le
``pyproject.toml`` de votre paquet :

```toml
[project.entry-points."singular.llm"]
mon_provider = "mon_package.module:generate_reply"
```

Une fois le paquet installé, ``singular`` peut le charger via
``--provider mon_provider``.
