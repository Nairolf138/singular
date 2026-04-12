# 🌱 Singular — Un organisme numérique vivant interactif

**Singular** n’est pas seulement un programme informatique.  
C’est une expérience : la tentative de créer un **organisme numérique vivant**, un compagnon logiciel qui **naît, évolue, apprend, interagit** et garde une **trace unique de sa vie**.

Chaque instance est **singulière** : deux personnes qui font naître un organisme ne verront jamais la même évolution, car son identité, ses expériences et ses choix modifient sa trajectoire.

---

## ✨ Concepts clés

- **Naissance** : une commande génère un nouvel organisme avec une identité unique (*seed*, traits de personnalité, valeurs).  
- **Corps** : ses *skills* (petites fonctions de code) représentent ses muscles et organes.  
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
singular report
singular dashboard
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
SINGULAR_RUNS_KEEP=50 singular report

# Utiliser l'API OpenAI
OPENAI_API_KEY=sk-... singular talk --prompt "Salut"
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
