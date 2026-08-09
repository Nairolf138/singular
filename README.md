<p align="center">
  <img src="docs/assets/branding/singular-logo-github.png" alt="Singular" width="700" height="215">
</p>

# 🌱 Singular — Un organisme numérique vivant interactif

**Singular** est un laboratoire open-source de vies numériques persistantes, capables d’évoluer d’abord en simulation, puis de s’incarner progressivement dans le monde réel à travers des capteurs, un corps robotique et une gouvernance de sécurité.

**Singular** n’est pas seulement un programme informatique.  
C’est une expérience : la tentative de créer un **organisme numérique vivant**, un compagnon logiciel qui **naît, évolue, apprend, interagit** et garde une **trace unique de sa vie**.

Chaque instance est **singulière** : deux personnes qui font naître un organisme ne verront jamais la même évolution, car son identité, ses expériences et ses choix modifient sa trajectoire.

---

## ✨ Concepts clés

La taxonomie canonique (`stable`, `experimental`, `optional`, `target-only`,
`deprecated`) et le registre d'acceptation des fonctions stables sont dans
[`docs/README.md`](docs/README.md#taxonomie-de-statut).
La chaîne perception → motivation → décision → action → effet → mémoire →
adaptation, ses preuves et les limites des termes « vivant », apprentissage,
émergence et conscience sont détaillées dans le
[modèle vérifiable du comportement vivant](docs/living-behavior-model.fr.md).

- **Naissance — `stable`** : une commande génère un nouvel organisme avec une identité unique (*seed*, traits de personnalité, valeurs).
- **Corps et starter-pack de skills — `stable`** : la naissance initialise des fonctions utilitaires et arithmétiques dans `skills/`.
- **Esprit et mémoire — `experimental`** : traits, humeur, valeurs et couches de mémoire évoluent encore avec les schémas runtime.
- **Évolution et mutation sandboxée — `experimental`** : la boucle propose, teste et sélectionne de petites mutations ; son résultat dépend du sandbox OCI.
- **Quêtes et apprentissage — `experimental`** : les spécifications JSON pilotent l'acquisition de compétences sans garantie de généralisation.
- **Interaction — `stable`** : `talk` fournit une conversation avec fallback provider et persistance locale.
- **Cycle vital avancé — `experimental`** : croissance, sommeil, reproduction et mort restent des modèles évolutifs.

### Capacités stables : accès et acceptation

| Capacité | Entrée | Prérequis | Acceptation |
| --- | --- | --- | --- |
| Naissance / sélection | `singular lives create --name Lumen`, `singular lives use lumen` | Python 3.10+, installation éditable, root inscriptible | `pytest -q tests/test_cli_lives.py tests/test_lives.py` |
| Starter-pack de skills | `singular lives create --name Lumen --starter-profile assistant` | Même prérequis ; profil `assistant` inclus | `pytest -q tests/test_birth_starter_profiles.py tests/test_living_starter_integration.py` |
| Consultation des vies et état | `singular lives list`, `singular status --format table` | Root initialisé ; vie active pour `status` | `pytest -q tests/test_cli_lives.py tests/test_life_status.py` |
| Conversation | `singular talk --prompt "Bonjour"` | Vie active ; fallback `dummy` disponible sans service | `pytest -q tests/test_end_to_end.py tests/providers/test_llm_fallback_chain.py` |
| Rapport | `singular report --format plain` | Vie active et run pour un résultat non vide | `pytest -q tests/test_report.py` |
| Diagnostic | `singular doctor` | Aucun service externe obligatoire | `pytest -q tests/test_cli_doctor.py tests/providers/test_provider_doctor.py` |
| Rétention | `singular retention status`, `singular retention run --dry-run` | Root accessible ; revue avant suppression réelle | `pytest -q tests/test_cli_retention.py tests/test_retention.py` |

Le [registre canonique](docs/README.md#registre-des-capacités-stable) doit être mis
à jour avant toute nouvelle déclaration `stable`.

---

## 🔍 Pourquoi Singular ?

Contrairement aux chatbots classiques (qui ne changent pas leur cœur) ou aux simulateurs de vie artificielle (qui ne parlent pas), **Singular réunit les deux mondes** :

- **Vie artificielle** : un organisme qui modifie réellement son code et s’optimise par sélection naturelle.  
- **Compagnon interactif** : une entité qui parle, garde une mémoire et exprime des émotions.  
- **Open-source et local** : chacun peut “faire naître” son compagnon, qui vivra et évoluera à sa manière. Le code non fiable n'est exécuté que si un runtime OCI compatible fournit l'isolation décrite ci-dessous.

---

## ⚡ Quickstart

```bash
pip install -e .[yaml,dashboard,viz]
singular lives create --name Lumen
singular talk
singular loop --budget-seconds 10
singular status --format table
singular report --format plain
singular dashboard
```

### Préparer Ollama explicitement

La conversation ne télécharge jamais de modèle implicitement. Avant d'utiliser
Ollama, lancez l'assistant dédié; il vérifie le service, affiche les modèles,
demande confirmation avant le téléchargement et valide une génération courte :

```bash
ollama serve
singular config providers setup ollama
```

Le modèle est résolu depuis `OLLAMA_MODEL`, puis utilise le défaut unique du
provider (`llama3.2`). En CI, aucune question n'est posée et le téléchargement
doit être autorisé explicitement :

```bash
singular config providers setup ollama --non-interactive --pull --model llama3.2
```

Les échecs distinguent `service_stopped`, `command_missing`, `model_missing`,
`download_incomplete`, `timeout` et `invalid_generation`; chaque diagnostic
affiche une commande de remédiation. Sans `--pull`, même l'action de setup reste
un contrôle sans téléchargement.

## 📚 Tutoriels et gouvernance

Index complet par type de document : [`docs/README.md`](docs/README.md).

### Parcours par objectif

| Parcours | Point de départ | Commandes de référence |
|---|---|---|
| Découverte | [Quickstart](#-quickstart) | [`quickstart`, `lives create`, `status`](docs/cli-reference.fr.md#quickstart) |
| Conversation | [Guide d’utilisation](#-guide-dutilisation-clair-pas-à-pas) | [`talk`](docs/cli-reference.fr.md#talk) |
| Évolution | [CLI `loop`](#cli-loop-budget-en-secondes) | [`loop`, `quest`, `synthesize`](docs/cli-reference.fr.md#loop) |
| Supervision permanente | [Exécution permanente](#-exécution-permanente-systemd-ou-docker) | [`watch`, `daemon`, `orchestrate run`](docs/cli-reference.fr.md#watch) |
| Diagnostic | [Lecture du dashboard](#comment-lire-le-dashboard-rapidement) | [`status`, `report`, `diagnose`, `doctor`](docs/cli-reference.fr.md#diagnose) |
| Gouvernance | [Sécurité](#-security) | [`policy`, `values`, `beliefs`](docs/cli-reference.fr.md#policy) |
| Reproduction | [Reproduction](#-reproduction) | [`spawn`, `lives reproduce`](docs/cli-reference.fr.md#lives-reproduce) |
| Écosystème | [Gérer plusieurs vies](#-gérer-plusieurs-vies) | [`ecosystem run`, relations entre vies](docs/cli-reference.fr.md#ecosystem-run) |
| Sauvegarde | [Registre des générations et rollback](#registre-des-générations-et-rollback) | [`report --export`, `rollback`, `lives archive`](docs/cli-reference.fr.md#rollback) |
| Suppression | [Désinstallation](#-désinstallation) | [`retention run`, `lives delete`, `uninstall`](docs/cli-reference.fr.md#uninstall) |

La [référence CLI française](docs/cli-reference.fr.md) et sa [version anglaise](docs/cli-reference.en.md) détaillent, pour chaque sous-commande, la syntaxe, les défauts, les fichiers et les effets de bord.

- [Tutoriel FR — créer une vie, ajouter une compétence, lancer un tick et lire les logs](docs/tutorial_create_life.fr.md)
- [Tutorial EN — create a life, add a skill, run a tick and read logs](docs/tutorial_create_life.en.md)
- [Guide de personnalisation de la gouvernance `policy.yaml`](docs/policy_customization.md)

## 🚀 Exécution permanente (systemd ou Docker)

**Statut : `optional`** — requiert systemd ou un runtime Docker/Compose externe.

Les deux déploiements utilisent un répertoire d'état durable et transmettent
`SIGTERM` à l'orchestrateur afin qu'il puisse terminer proprement. Avant le
premier démarrage, créez et sélectionnez une vie dans le même root, par exemple
`sudo -u singular SINGULAR_ROOT=/var/lib/singular singular lives create --name Lumen`.

### Service systemd

Le modèle [`deploy/systemd/singular.service`](deploy/systemd/singular.service) est
rendu avec les chemins réels par la CLI. Celle-ci refuse l'installation si la
vie active, le binaire ou les répertoires inscriptibles `mem/` et `runs/` ne sont
pas utilisables par le compte de service. Elle écrit atomiquement le contexte
non secret dans `/etc/singular/singular.env`, puis lance `systemctl daemon-reload` :

```bash
sudo useradd --system --home /var/lib/singular --create-home singular
sudo git clone <URL_DU_DEPOT> /opt/singular
sudo python3 -m venv /opt/singular/.venv
sudo /opt/singular/.venv/bin/pip install /opt/singular
sudo chown -R singular:singular /opt/singular /var/lib/singular
sudo -u singular SINGULAR_ROOT=/var/lib/singular /opt/singular/.venv/bin/singular lives create --name Lumen
sudo SINGULAR_ROOT=/var/lib/singular /opt/singular/.venv/bin/singular \
  config root install-systemd --binary /opt/singular/.venv/bin/singular
sudo systemctl enable --now singular.service
```

La vie démarrée est celle inscrite comme `SINGULAR_HOME` dans le fichier
d'environnement au moment de l'installation. Diagnostiquez toute divergence avec
`sudo systemctl cat singular`, `sudo cat /etc/singular/singular.env`,
`sudo -u singular test -w <vie>/mem -a -w <vie>/runs` et
`sudo -u singular SINGULAR_ROOT=<root> singular lives list`.

Consultez l'état et les journaux avec `systemctl status singular` et
`journalctl -u singular -f`. Pour mettre à niveau : arrêtez le service, faites
une sauvegarde, mettez le dépôt à jour, réinstallez le paquet dans le venv puis
redémarrez :

```bash
sudo systemctl stop singular
sudo tar -C /var/lib -czf "singular-$(date +%F-%H%M).tgz" singular
sudo git -C /opt/singular pull --ff-only
sudo /opt/singular/.venv/bin/pip install --upgrade /opt/singular
sudo systemctl start singular
```

Après un crash, `Restart=on-failure` relance le processus après 10 secondes et
celui-ci reprend l'identité et la progression présentes dans
`/var/lib/singular`. Si l'état est endommagé, arrêtez le service, déplacez le
répertoire concerné, restaurez l'archive dans `/var/lib`, corrigez ses droits
(`chown -R singular:singular /var/lib/singular`) puis redémarrez.

### Docker Compose

Docker est supporté par le `Dockerfile` et `compose.yaml`. Les volumes nommés
conservent `mem/`, `runs/`, les vies (donc leur identité) et la configuration;
Compose applique aussi un healthcheck et des limites CPU/mémoire.

```bash
docker compose build
docker compose run --rm singular singular lives create --name Lumen
docker compose up -d
docker compose logs -f singular
```

Mise à niveau et sauvegarde (ne supprimez jamais les volumes avec `down -v`) :

```bash
docker compose down
docker run --rm -v singular_singular-lives:/data -v "$PWD":/backup \
  alpine tar -czf /backup/singular-lives.tgz -C /data .
docker compose build --pull
docker compose up -d
```

Sauvegardez de la même façon les volumes `singular-mem`, `singular-runs` et
`singular-config`. Pour récupérer après un crash, examinez d'abord
`docker compose logs`, laissez `restart: unless-stopped` relancer le conteneur,
ou faites `docker compose down`, restaurez chaque archive dans son volume puis
`docker compose up -d`. L'état persistant n'est pas réinitialisé par la
reconstruction de l'image.

Validez statiquement les manifestes avec
`python scripts/check_deployment_manifests.py`. Le test de reprise accepte une
commande injectable (placeholder `{root}`), utile pour tester un wrapper ou un
superviseur réel :

```bash
SINGULAR_INTEGRATION_COMMAND='mon-wrapper --root {root}' \
  pytest -m integration tests/test_deployment.py
```

## 🧭 Guide d’utilisation clair (pas à pas)

Si vous débutez, suivez **exactement** ces étapes :

1. **Créer une vie**
   ```bash
   singular lives create --name Lumen
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

Le profil `assistant`, sélectionné par défaut, fournit le pack complet décrit ci-dessous
ainsi que les skills arithmétiques historiques. Utilisez `--starter-profile minimal`
pour ne créer que ces trois skills arithmétiques.

- `validation.py` : vérifications simples d’entrées (ex. texte non vide).
- `summary.py` : résumé court par extraction des premiers mots.
- `intent_classification.py` : classification heuristique (`question`, `request`, `statement`).
- `entity_extraction.py` : extraction légère d’entités via tokens capitalisés.
- `planning.py` : construction d’un plan structuré à partir d’un objectif et de steps.
- `metrics.py` : métrique de progression (`completion_ratio`) bornée entre `0.0` et `1.0`.

Ce pack complète les skills arithmétiques historiques (`addition`, `subtraction`, `multiplication`) pour donner, dès les premiers ticks, des briques cognitives prêtes à l’emploi.

### Profils de naissance (traits initiaux)

La commande `lives create` accepte des overrides bornés `[0,1]` pour les traits initiaux
du psyche : `--curiosity`, `--patience`, `--playfulness`, `--optimism`,
`--resilience`. Les valeurs sont persistées dans `mem/psyche.json`.

```bash
# Profil prudent : stabilité, patience, faible prise de risque
singular lives create --name "Prudent" \
  --curiosity 0.20 --patience 0.90 --playfulness 0.15 --optimism 0.55 --resilience 0.90

# Profil explorateur : curiosité et jeu plus élevés, patience plus basse
singular lives create --name "Explorateur" \
  --curiosity 0.92 --patience 0.35 --playfulness 0.85 --optimism 0.75 --resilience 0.70
```

Par défaut, ``talk`` ouvre une session interactive. Pour obtenir une réponse
unique et quitter immédiatement :
```bash
singular talk --prompt "Bonjour"
```

### Utiliser Ollama comme fournisseur LLM local

**Statut : `optional`** — requiert un serveur Ollama accessible et un modèle local.

Si Ollama tourne sur votre machine (API HTTP locale par défaut sur
``http://127.0.0.1:11434``), sélectionnez le provider ``ollama`` avec
``LLM_PROVIDER`` :

```bash
LLM_PROVIDER=ollama singular talk --prompt "Bonjour, qui es-tu ?"
```

Configuration utile :

- ``OLLAMA_HOST`` : URL de l'API Ollama (défaut : ``http://127.0.0.1:11434``) ;
- ``OLLAMA_MODEL`` : modèle de génération (défaut : ``llama3.2``) ;
- ``OLLAMA_EMBED_MODEL`` : modèle d'embeddings si différent du modèle de génération.

La chaîne de fallback intégrée essaie ``local``, ``ollama``, ``openai`` puis
``dummy``. Vous pouvez la personnaliser avec ``LLM_PROVIDER_FALLBACK`` (ex.
``LLM_PROVIDER_FALLBACK=ollama,dummy``).

### CLI `loop` (budget en secondes)

**Statut : `experimental`.** L'ancienne option `--ticks` est `deprecated` et doit
être remplacée par `--budget-seconds`.

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

**Statut : `experimental`.** Le registre unitaire est stable, mais l'orchestration
et les interactions entre plusieurs vies restent expérimentales.

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

### Format de quête auto-documenté

La commande ``quest`` synthétise une compétence depuis une specification JSON.
Pour découvrir le format sans modifier le disque ni sélectionner de vie active,
utilisez les sorties intégrées :

```bash
singular quest create --example
singular quest create --schema
```

Un exemple complet versionné est également disponible dans
``examples/quest/complete_quest.json``. Les champs obligatoires sont ``name``,
``signature``, ``examples`` et ``constraints``. Chaque erreur de validation
indique le champ concerné, le type attendu et un exemple minimal. Une
spécification invalide est rejetée avant toute création de mémoire ou de fichier
de compétence.

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

De plus, ``lives create`` affiche explicitement le root de registre utilisé pour éviter
toute ambiguïté.

## 🧹 Désinstallation

**Statut : `experimental`** — toujours prévisualiser la portée avant une purge.

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

**Statut : `experimental`.** La reproduction n'est pas une capacité stable.

```bash
singular spawn parent_a parent_b --out-dir child/
```

Cette commande croise deux organismes en combinant aléatoirement une *skill* de chaque parent.
L’algorithme de crossover (voir `src/singular/life/reproduction.py`) prend la signature de la fonction du parent A,
fusionne la première moitié de son corps avec la seconde moitié de la fonction du parent B, puis écrit
le fichier hybride dans `child/`.

## 🔒 Security

- **Frontières de confiance** : le processus hôte orchestre les appels et peut lire la
  mémoire ; les fournisseurs LLM sont des services séparés ; le code produit par les
  mutations est non fiable et n'est exécuté que dans le sandbox OCI.
- Le fournisseur OpenAI transmet ses prompts au service externe d'OpenAI. Selon le
  flux appelant, un prompt peut contenir des secrets ou des souvenirs sensibles :
  inspectez/minimisez les données avant d'activer ce fournisseur.
- Ollama n'est « local » que si `OLLAMA_HOST` pointe réellement vers une adresse
  loopback. `OLLAMA_NETWORK_POLICY=local` (valeur restrictive par défaut) le vérifie,
  y compris après une redirection HTTP ; `disabled` interdit tout appel et
  `unrestricted` autorise explicitement les hôtes distants.
- Le code muté n'a pas de réseau : `SINGULAR_SANDBOX_NETWORK_POLICY=none` (défaut).
  Toute demande d'un autre mode est refusée plutôt que silencieusement affaiblie.
- Pas d’accès disque externe (hors dossier de l’organisme).
- Sandbox stricte :
  - Limites CPU/RAM (`timeout` & `memory_limit` : 1.5s et 256 MB par défaut).
  - Environnement isolé : `os.environ` vidé et répertoire de travail temporaire.
  - Interdiction d’import et de fonctions sensibles (`open()`, `exec()`, `eval()`, etc.).
- Tests automatiques avant toute intégration de code.
- Résultats traçables : chaque mutation est loggée, reproductible par seed.

---

## 🧬 Cycle vital

**Statut : `experimental`.** Les règles et artefacts du cycle peuvent évoluer.
Pour relier chaque phase à ses modules, artefacts, dépendances, échecs et preuves,
consultez le [modèle de comportement de bout en bout](docs/living-behavior-model.fr.md).

1. **Naissance**
   ```bash
   singular lives create --name Lumen
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
   singular lives create --name Lumen
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
- Le filtre AST est une validation fonctionnelle et une défense complémentaire, **pas une frontière de sécurité**. L'exécution repose sur Docker ou Podman sous Linux : conteneur sans réseau, utilisateur non privilégié, racine en lecture seule et `/tmp` isolé, aucune capability, limites de processus/CPU/mémoire, `no-new-privileges` et seccomp actif. Si ces garanties (y compris les limites `resource`) ne peuvent pas être vérifiées, Singular refuse l'exécution au lieu de revenir à un processus local moins isolé. L'image, déjà présente localement (aucun pull automatique), est configurable avec `SINGULAR_SANDBOX_IMAGE`.
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

**Statut : `target-only`.** Cette liste exprime des directions, pas des fonctions
disponibles.
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

**Statut : `optional`** — requiert l'extra `dashboard`; son interface peut évoluer
indépendamment des points d'entrée CLI stables.

Le dashboard expose des mesures internes et des traces opérateur : lisez les
[règles de preuve et d'interprétation](docs/living-behavior-model.fr.md#périmètre-et-lecture-des-preuves)
avant d'en tirer une conclusion sur l'autonomie, l'apprentissage ou le caractère
« vivant » du système.

Un petit serveur web permet de consulter les fichiers de `runs/` et l'état de `psyche.json`.

### Installation

Installez la base :

```bash
pip install -e .
```

#### Dépendances optionnelles

- `pip install -e '.[test]'` est la commande canonique pour installer
  l'environnement de contribution et la suite obligatoire (pytest, couverture,
  lint, formatage et typage), sans installer d'intégration facultative.
- `pip install -e .[dashboard]` pour activer le tableau de bord web.
- `pip install -e .[viz]` pour générer des graphiques via `viz.py`.
- `pip install -e .[yaml]` pour ajouter **PyYAML** et gérer `values.yaml`.
- `pip install -e '.[llm-openai]'` pour permettre à l'organisme de parler via l'API OpenAI.
- `pip install -e '.[llm-local]'` pour activer un modèle local via Hugging Face.
- `pip install -e '.[ros2]'` dans un environnement ROS2 préalablement sourcé
  pour activer le bridge ROS2.
- `pip install -e '.[sandbox]'` documente le sandbox conteneurisé ; un exécutable
  Podman ou Docker compatible reste requis sur l'hôte.

La suite obligatoire exacte, identique à celle de la CI, s'exécute avec :

```bash
pytest -m "not integration" --cov=src/singular --cov-fail-under=85 --cov-report=term-missing --cov-report=xml:coverage.xml
```

Les extras `dashboard`, `llm-openai`, `llm-local`, `ros2` et `sandbox` restent
volontairement séparés de `test` : leurs tests de contrat sont facultatifs et
peuvent nécessiter un service, des identifiants, une distribution ROS2 ou un
runtime de conteneurs.

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
SINGULAR_HOME=/chemin/personnel singular lives create
# ou
singular --home /chemin/personnel lives create

# Ajuster la rétention (priorité env > fichier mem/retention_policy.json > défauts)
SINGULAR_RETENTION_MAX_RUNS=50 singular retention status

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

### Rétention des artefacts (nouveaux paramètres)

La rétention est pilotée par 7 paramètres (`retention config show`) :

- `max_runs` (défaut: `20`)
- `max_run_age_days` (défaut: `30`)
- `max_total_runs_size_mb` (défaut: `512`)
- `max_episodic_lines` (défaut: `20000`)
- `max_episodic_days` (défaut: `90`)
- `max_generations_lines` (défaut: `50000`)
- `max_generations_days` (défaut: `365`)

Ordre de résolution des valeurs: variables d’environnement `SINGULAR_RETENTION_*`,
puis `mem/retention_policy.json`, puis défauts intégrés.

Garanties (suppression automatique) :

- un run actif (verrou `.active.lock` ou fichier temporaire `.jsonl.tmp`) n’est jamais supprimé ;
- les données `lives/` ne sont jamais supprimées par `singular retention run` ;
- les snapshots/registre de générations ne sont pas supprimés automatiquement par ce service ;
- `--dry-run` n’écrit rien et ne supprime rien.

Commandes de contrôle :

```bash
# Voir les seuils effectivement actifs
singular retention config show

# Voir usage, dépassements et dernière purge
singular retention status

# Simuler les suppressions (fortement recommandé)
singular retention run --dry-run

# Appliquer la purge réelle
singular retention run
```

### Migration (utilisateurs existants)

1. **Audit initial** : exécutez `singular retention status`.
2. **Activation progressive** : définissez d’abord des seuils permissifs (ex. `MAX_RUNS` élevé), puis resserrez par étapes.
3. **Dry-run obligatoire en pratique** : lancez `singular retention run --dry-run` avant toute purge réelle.
4. **Purge réelle** : exécutez `singular retention run` uniquement après validation de la liste `would_delete`.
5. **Compatibilité legacy** : remplacez `SINGULAR_RUNS_KEEP` par `SINGULAR_RETENTION_MAX_RUNS` dans vos scripts CI/shell.

Politique de conservation/archivage/purge détaillée : `docs/generations_registry.md`.

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

**Statut : `optional`** — requiert des identifiants et un service externe.

Pour permettre à l'organisme de parler en utilisant l'API d'OpenAI, installez
la dépendance optionnelle avec ``pip install -e '.[llm-openai]'`` et définissez la variable
d'environnement ``OPENAI_API_KEY``. Les versions plus anciennes du paquet
``openai`` ne sont pas compatibles avec le fournisseur actuel.

### Fournisseur local

**Statut : `optional`** — dépend du runtime et du modèle installés localement.

Installez l'extra dédié pour utiliser un petit modèle embarqué :

```bash
pip install -e '.[llm-local]'
singular talk --provider local --prompt "Bonjour"
```

Le fournisseur local utilise le modèle ``sshleifer/tiny-gpt2`` de Hugging Face
pour fonctionner hors-ligne.

### Fournisseurs externes

**Statut : `optional`** — chaque provider dépend de son paquet ou service propre.

Pour enregistrer un provider LLM personnalisé, ajoutez un entry point dans le
``pyproject.toml`` de votre paquet :

```toml
[project.entry-points."singular.llm"]
mon_provider = "mon_package.module:generate_reply"
```

Une fois le paquet installé, ``singular`` peut le charger via
``--provider mon_provider``.
