# Référence CLI Singular

Cette référence inventorie **tous** les parsers construits par `_build_parser`. Elle est contrôlée automatiquement par `tests/test_cli_reference.py`.

## Portée et options globales

Toutes les syntaxes acceptent avant la commande : `singular [--seed INT] [--root PATH] [--home PATH] [--life NAME] [--format {table,json,plain}] [--safe-mode] …`. Défauts : seed/root/home/life `None` (root/home peuvent venir de l’environnement), format `plain`, safe mode `false`. `--root` choisit le registre; `--home` choisit directement un dossier de vie; `--life` résout une vie dans le registre. `SINGULAR_ROOT`, `SINGULAR_HOME`, `OPENAI_API_KEY` et les variables provider peuvent donc modifier le contexte.

Les chemins ci-dessous sont relatifs au root ou à `SINGULAR_HOME`. Toujours sauvegarder avant une suppression, un reset, un rollback ou une rétention réelle.

<!-- cli-command: embodiment -->
## `embodiment`

**Syntaxe :** `singular embodiment [-h] --config CONFIG [--mode {simulation,dry-run,hardware}] [--steps STEPS] [--audit AUDIT]`

**Arguments et défauts :** `--config` (requis/required); `--mode` (`simulation`; choix/choices: simulation, dry-run, hardware); `--steps` (`None`); `--audit` (`None`)

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular embodiment --config configs/embodiment.yaml`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json embodiment --config configs/embodiment.yaml`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: birth -->
## `birth`

**Syntaxe :** `singular birth [-h] [--name NAME] [--curiosity CURIOSITY] [--patience PATIENCE] [--playfulness PLAYFULNESS] [--optimism OPTIMISM] [--resilience RESILIENCE] [--starter-profile STARTER_PROFILE] [--starter-skill STARTER_SKILL]`

**Arguments et défauts :** `--name` (`New life`); `--curiosity` (`None`); `--patience` (`None`); `--playfulness` (`None`); `--optimism` (`None`); `--resilience` (`None`); `--starter-profile` (`assistant`); `--starter-skill` (`[]`)

**Prérequis :** Root accessible; profil starter valide.

**Root et vie ciblés :** Root résolu; crée et active une nouvelle vie.

**Fichiers lus ou écrits :** Écrit `lives/registry.json` et le dossier `lives/<slug>/` (identité, psyché, skills et mémoire).

**Effets de bord :** Crée des répertoires et positionne `SINGULAR_HOME`; `birth` est dépréciée.

**Exemple minimal :** `singular birth --name Ada`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json birth --name Ada`

**Erreurs usuelles :** Trait hors [0,1], nom/profil invalide, root non inscriptible.

<!-- cli-command: spawn -->
## `spawn`

**Syntaxe :** `singular spawn [-h] [--out-dir OUT_DIR] parent_a parent_b`

**Arguments et défauts :** `parent_a` (requis/required); `parent_b` (requis/required); `--out-dir` (`None`)

**Prérequis :** Entrées demandées présentes et root/vie inscriptible.

**Root et vie ciblés :** Vie active, sauf `spawn` qui cible les chemins parents et la sortie.

**Fichiers lus ou écrits :** Lit les parents/la spec/la mémoire; écrit enfant, skill, mémoire ou génération restaurée selon la commande.

**Effets de bord :** Crée/modifie des artefacts; `rollback` remplace atomiquement l'état actif.

**Exemple minimal :** `singular spawn life/a life/b`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json spawn life/a life/b`

**Erreurs usuelles :** Entrée absente/invalide, génération inconnue, sortie existante ou non inscriptible.

<!-- cli-command: run -->
## `run`

**Syntaxe :** `singular run [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular run`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json run`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: loop -->
## `loop`

**Syntaxe :** `singular loop [-h] [--skills-dir SKILLS_DIR] [--checkpoint CHECKPOINT] [--budget-seconds BUDGET_SECONDS] [--ticks TICKS] [--run-id RUN_ID]`

**Arguments et défauts :** `--skills-dir` (`None`); `--checkpoint` (`None`); `--budget-seconds` (`None`); `--ticks` (`None`); `--run-id` (`loop`)

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular loop --budget-seconds 10`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json loop --budget-seconds 10`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: status -->
## `status`

**Syntaxe :** `singular status [-h] [--verbose] [--format {table,json,plain}]`

**Arguments et défauts :** `--verbose` (`false`); `--format` (`None`; choix/choices: table, json, plain)

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular status`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json status`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: talk -->
## `talk`

**Syntaxe :** `singular talk [-h] [--provider PROVIDER] [--prompt PROMPT] [--life TALK_LIFE] [--live TALK_LIFE_LEGACY]`

**Arguments et défauts :** `--provider` (`None`); `--prompt` (`None`); `--life` (`None`); `--live` (`None`)

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular talk --prompt "Bonjour"`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json talk --prompt "Bonjour"`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: quest -->
## `quest`

**Syntaxe :** `singular quest create [-h] [--example] [--schema] [--life LIFE] [spec]`

**Arguments et défauts :** `spec` (`None`); `--example` (`false`); `--schema` (`false`)

**Prérequis :** Entrées demandées présentes et root/vie inscriptible.

**Root et vie ciblés :** Vie active, sauf `spawn` qui cible les chemins parents et la sortie.

**Fichiers lus ou écrits :** Lit les parents/la spec/la mémoire; écrit enfant, skill, mémoire ou génération restaurée selon la commande.

**Effets de bord :** Crée/modifie des artefacts; `rollback` remplace atomiquement l'état actif.

**Exemple minimal :** `singular quest create --example`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json quest create --example`

**Erreurs usuelles :** Entrée absente/invalide, génération inconnue, sortie existante ou non inscriptible.

<!-- cli-command: skills -->
## `skills`

**Syntaxe :** `singular skills ACTION`

**Arguments et défauts :** `ACTION` (requis/required)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular skills list`

**Exemple avancé :** `singular --root /srv/singular --life ada skills list`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: skills list -->
## `skills list`

**Syntaxe :** `singular skills list [--life LIFE]`

**Arguments et défauts :** `--life` (`None`)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular skills list --life ada`

**Exemple avancé :** `singular --root /srv/singular --life ada skills list --life ada`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: quest create -->
## `quest create`

**Syntaxe :** `singular quest create [--example] [--schema] [--life LIFE] [spec]`

**Arguments et défauts :** `spec` (`None`); options (`false`)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular quest create --example`

**Exemple avancé :** `singular --root /srv/singular --life ada quest create --example`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: quest list -->
## `quest list`

**Syntaxe :** `singular quest list [--life LIFE]`

**Arguments et défauts :** `--life` (`None`)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular quest list --life ada`

**Exemple avancé :** `singular --root /srv/singular --life ada quest list --life ada`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: social -->
## `social`

**Syntaxe :** `singular social ACTION`

**Arguments et défauts :** `ACTION` (requis/required)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular social interact bob cooperation`

**Exemple avancé :** `singular --root /srv/singular --life ada social interact bob cooperation`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: social interact -->
## `social interact`

**Syntaxe :** `singular social interact TARGET EVENT [--life LIFE]`

**Arguments et défauts :** `TARGET`, `EVENT` (requis/required); `--life` (`None`)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular social interact bob cooperation --life ada`

**Exemple avancé :** `singular --root /srv/singular --life ada social interact bob cooperation --life ada`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: self-narrative -->
## `self-narrative`

**Syntaxe :** `singular self-narrative ACTION`

**Arguments et défauts :** `ACTION` (requis/required)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular self-narrative summarize`

**Exemple avancé :** `singular --root /srv/singular --life ada self-narrative summarize`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: self-narrative summarize -->
## `self-narrative summarize`

**Syntaxe :** `singular self-narrative summarize [--long] [--life LIFE]`

**Arguments et défauts :** `--long` (`false`); `--life` (`None`)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular self-narrative summarize --life ada`

**Exemple avancé :** `singular --root /srv/singular --life ada self-narrative summarize --life ada`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: cognition -->
## `cognition`

**Syntaxe :** `singular cognition ACTION`

**Arguments et défauts :** `ACTION` (requis/required)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular cognition self-observe`

**Exemple avancé :** `singular --root /srv/singular --life ada cognition self-observe`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: cognition self-observe -->
## `cognition self-observe`

**Syntaxe :** `singular cognition self-observe [--life LIFE]`

**Arguments et défauts :** `--life` (`None`)

**Prérequis :** Une vie active pour les actions.

**Root et vie ciblés :** `--life` global ou local; l'option locale est prioritaire.

**Fichiers lus ou écrits :** Lit ou écrit les artefacts de la vie active.

**Effets de bord :** L'action peut actualiser la mémoire de la vie.

**Exemple minimal :** `singular cognition self-observe --life ada`

**Exemple avancé :** `singular --root /srv/singular --life ada cognition self-observe --life ada`

**Erreurs usuelles :** Sous-commande/argument manquant ou vie introuvable.

<!-- cli-command: synthesize -->
## `synthesize`

**Syntaxe :** `singular synthesize [-h] code`

**Arguments et défauts :** `code` (requis/required)

**Prérequis :** Entrées demandées présentes et root/vie inscriptible.

**Root et vie ciblés :** Vie active, sauf `spawn` qui cible les chemins parents et la sortie.

**Fichiers lus ou écrits :** Lit les parents/la spec/la mémoire; écrit enfant, skill, mémoire ou génération restaurée selon la commande.

**Effets de bord :** Crée/modifie des artefacts; `rollback` remplace atomiquement l'état actif.

**Exemple minimal :** `singular synthesize "result = 1"`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json synthesize "result = 1"`

**Erreurs usuelles :** Entrée absente/invalide, génération inconnue, sortie existante ou non inscriptible.

<!-- cli-command: report -->
## `report`

**Syntaxe :** `singular report [-h] [--id ID] [--format {table,json,plain}] [--export EXPORT]`

**Arguments et défauts :** `--id` (`None`); `--format` (`None`; choix/choices: table, json, plain); `--export` (`None`)

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular report`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json report`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: rollback -->
## `rollback`

**Syntaxe :** `singular rollback [-h] --generation GENERATION`

**Arguments et défauts :** `--generation` (requis/required)

**Prérequis :** Entrées demandées présentes et root/vie inscriptible.

**Root et vie ciblés :** Vie active, sauf `spawn` qui cible les chemins parents et la sortie.

**Fichiers lus ou écrits :** Lit les parents/la spec/la mémoire; écrit enfant, skill, mémoire ou génération restaurée selon la commande.

**Effets de bord :** Crée/modifie des artefacts; `rollback` remplace atomiquement l'état actif.

**Exemple minimal :** `singular rollback --generation 2`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json rollback --generation 2`

**Erreurs usuelles :** Entrée absente/invalide, génération inconnue, sortie existante ou non inscriptible.

<!-- cli-command: dashboard -->
## `dashboard`

**Syntaxe :** `singular dashboard [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular dashboard`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json dashboard`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: quickstart -->
## `quickstart`

**Syntaxe :** `singular quickstart [-h] [--name NAME]`

**Arguments et défauts :** `--name` (`None`)

**Prérequis :** Entrées demandées présentes et root/vie inscriptible.

**Root et vie ciblés :** Vie active, sauf `spawn` qui cible les chemins parents et la sortie.

**Fichiers lus ou écrits :** Lit les parents/la spec/la mémoire; écrit enfant, skill, mémoire ou génération restaurée selon la commande.

**Effets de bord :** Crée/modifie des artefacts; `rollback` remplace atomiquement l'état actif.

**Exemple minimal :** `singular quickstart --name Ada`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json quickstart --name Ada`

**Erreurs usuelles :** Entrée absente/invalide, génération inconnue, sortie existante ou non inscriptible.

<!-- cli-command: monitor -->
## `monitor`

**Syntaxe :** `singular monitor [-h] [--verbose]`

**Arguments et défauts :** `--verbose` (`false`)

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular monitor`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json monitor`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: watch -->
## `watch`

**Syntaxe :** `singular watch [-h] [--interval INTERVAL] [--sources SOURCES] [--cpu-budget CPU_BUDGET] [--memory-budget MEMORY_BUDGET] [--watch-dir WATCH_DIR] [--dry-run]`

**Arguments et défauts :** `--interval` (`5.0`); `--sources` (`file,weather,runs,folder`); `--cpu-budget` (`50.0`); `--memory-budget` (`512.0`); `--watch-dir` (`None`); `--dry-run` (`false`)

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular watch --dry-run`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json watch --dry-run`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: orchestrate -->
## `orchestrate`

**Syntaxe :** `singular orchestrate [-h] {run} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular orchestrate run --dry-run`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json orchestrate run --dry-run`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: orchestrate run -->
## `orchestrate run`

**Syntaxe :** `singular orchestrate run [-h] [--veille-seconds VEILLE_SECONDS] [--action-seconds ACTION_SECONDS] [--introspection-seconds INTROSPECTION_SECONDS] [--sommeil-seconds SOMMEIL_SECONDS] [--poll-interval POLL_INTERVAL] [--tick-budget TICK_BUDGET] [--lifecycle-config LIFECYCLE_CONFIG] [--dry-run]`

**Arguments et défauts :** `--veille-seconds` (`None`); `--action-seconds` (`None`); `--introspection-seconds` (`None`); `--sommeil-seconds` (`None`); `--poll-interval` (`None`); `--tick-budget` (`None`); `--lifecycle-config` (`None`); `--dry-run` (`false`)

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular orchestrate run --dry-run`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json orchestrate run --dry-run`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: daemon -->
## `daemon`

**Syntaxe :** `singular daemon [-h] --life LIFE [--interval INTERVAL] [--budget-seconds BUDGET_SECONDS] [--max-errors MAX_ERRORS] [--dashboard] [--dry-run]`

**Arguments et défauts :** `--life` (requis/required); `--interval` (`5.0`); `--budget-seconds` (`None`); `--max-errors` (`3`); `--dashboard` (`false`); `--dry-run` (`false`)

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular daemon --life ada --budget-seconds 30 --dry-run`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json daemon --life ada --budget-seconds 30 --dry-run`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: diagnose -->
## `diagnose`

**Syntaxe :** `singular diagnose [-h] {sandbox,evolution} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular diagnose sandbox`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json diagnose sandbox`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: diagnose sandbox -->
## `diagnose sandbox`

**Syntaxe :** `singular diagnose sandbox [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular diagnose sandbox`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json diagnose sandbox`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: diagnose evolution -->
## `diagnose evolution`

**Syntaxe :** `singular diagnose evolution [-h] [--life LIFE]`

**Arguments et défauts :** `--life` (`None`)

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular diagnose evolution`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json diagnose evolution`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: retention -->
## `retention`

**Syntaxe :** `singular retention [-h] {run,status,config} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular retention status`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json retention status`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: retention run -->
## `retention run`

**Syntaxe :** `singular retention run [-h] [--dry-run]`

**Arguments et défauts :** `--dry-run` (`false`)

**Prérequis :** Droits d'écriture; confirmation/option destructive appropriée.

**Root et vie ciblés :** Root global pour config/rétention/désinstallation; vie active pour croyances.

**Fichiers lus ou écrits :** Écrit/supprime configuration, `runs/`, `mem/`, croyances ou `lives/` selon la commande.

**Effets de bord :** Effet persistant; purge/reset/uninstall peuvent être irréversibles. Utiliser dry-run quand disponible.

**Exemple minimal :** `singular retention run --dry-run`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json retention run --dry-run`

**Erreurs usuelles :** Option requise absente, clé/valeur invalide, confirmation refusée, protection du repo, permissions.

<!-- cli-command: retention status -->
## `retention status`

**Syntaxe :** `singular retention status [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular retention status`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json retention status`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: retention config -->
## `retention config`

**Syntaxe :** `singular retention config [-h] {show} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular retention config show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json retention config show`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: retention config show -->
## `retention config show`

**Syntaxe :** `singular retention config show [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular retention config show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json retention config show`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: doctor -->
## `doctor`

**Syntaxe :** `singular doctor [-h] [--fix]`

**Arguments et défauts :** `--fix` (`false`)

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular doctor`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json doctor`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: config -->
## `config`

**Syntaxe :** `singular config [-h] {openai,providers,root} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular config root show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json config root show`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: config openai -->
## `config openai`

**Syntaxe :** `singular config openai [-h] [--api-key API_KEY] [--shell-profile SHELL_PROFILE] [--test]`

**Arguments et défauts :** `--api-key` (`None`); `--shell-profile` (`None`); `--test` (`false`)

**Prérequis :** Droits d'écriture; confirmation/option destructive appropriée.

**Root et vie ciblés :** Root global pour config/rétention/désinstallation; vie active pour croyances.

**Fichiers lus ou écrits :** Écrit/supprime configuration, `runs/`, `mem/`, croyances ou `lives/` selon la commande.

**Effets de bord :** Effet persistant; purge/reset/uninstall peuvent être irréversibles. Utiliser dry-run quand disponible.

**Exemple minimal :** `singular config openai --api-key sk-example-key`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json config openai --api-key sk-example-key`

**Erreurs usuelles :** Option requise absente, clé/valeur invalide, confirmation refusée, protection du repo, permissions.

<!-- cli-command: config providers -->
## `config providers`

**Syntaxe :** `singular config providers [-h] {doctor,setup} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular config providers doctor`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json config providers doctor`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: config providers doctor -->
## `config providers doctor`

**Syntaxe :** `singular config providers doctor [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular config providers doctor`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json config providers doctor`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: config root -->
## `config root`

**Syntaxe :** `singular config root [-h] {set,show,install-systemd} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular config root show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json config root show`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: config root set -->
## `config root set`

**Syntaxe :** `singular config root set [-h] [--scope {global,project}] path`

**Arguments et défauts :** `path` (requis/required); `--scope` (`global`; choix/choices: global, project)

**Prérequis :** Droits d'écriture; confirmation/option destructive appropriée.

**Root et vie ciblés :** Root global pour config/rétention/désinstallation; vie active pour croyances.

**Fichiers lus ou écrits :** Écrit/supprime configuration, `runs/`, `mem/`, croyances ou `lives/` selon la commande.

**Effets de bord :** Effet persistant; purge/reset/uninstall peuvent être irréversibles. Utiliser dry-run quand disponible.

**Exemple minimal :** `singular config root set /srv/singular`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json config root set /srv/singular`

**Erreurs usuelles :** Option requise absente, clé/valeur invalide, confirmation refusée, protection du repo, permissions.

<!-- cli-command: config root show -->
## `config root show`

**Syntaxe :** `singular config root show [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular config root show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json config root show`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: config root install-systemd -->
## `config root install-systemd`

**Syntaxe :** `singular [--root PATH] [--life NOM] config root install-systemd [--user USER] [--group GROUP] [--binary PATH] [--environment-file PATH] [--unit-file PATH]`

**Arguments et défauts :** utilisateur/groupe `singular`; environnement `/etc/singular/singular.env`; unité `/etc/systemd/system/singular.service`; binaire trouvé dans `PATH`.

**Prérequis :** Une vie active existante, un binaire `singular`, `mem/` et `runs/` inscriptibles par l'utilisateur du service, les droits d'écriture dans `/etc` et systemd.

**Root et vie ciblés :** Le root résolu et la vie active (ou `--life`) sont figés respectivement dans `SINGULAR_ROOT` et `SINGULAR_HOME`.

**Fichiers lus ou écrits :** Génère atomiquement le fichier d'environnement non secret et l'unité rendue. Les variables provider non secrètes (`LLM_PROVIDER`, modèles et configuration Ollama) sont conservées; les clés API sont exclues.

**Effets de bord :** Exécute `systemctl daemon-reload`; l'activation reste explicite avec `systemctl enable --now singular`.

**Exemple minimal :** `sudo singular --root /var/lib/singular config root install-systemd`

**Exemple avancé :** `sudo singular --root /srv/singular --life ada config root install-systemd --user singular --group singular --binary /srv/app/.venv/bin/singular`

**Diagnostic :** `systemctl cat singular`; `cat /etc/singular/singular.env`; `sudo -u singular test -w <vie>/mem -a -w <vie>/runs`; `sudo -u singular SINGULAR_ROOT=<root> singular lives list`.

**Erreurs usuelles :** Vie ou répertoire absent, binaire introuvable, compte inconnu ou droits incompatibles; le diagnostic indique la commande ou le chemin à corriger et aucun fichier n'est installé.

<!-- cli-command: lives -->
## `lives`

**Syntaxe :** `singular lives [-h] {list,create,use,delete,archive,memorial,clone,reproduce,relations,ally,rival,reconcile,proximity} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular lives list`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives list`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: lives list -->
## `lives list`

**Syntaxe :** `singular lives list [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Affichage uniquement.

**Exemple minimal :** `singular lives list`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives list`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives create -->
## `lives create`

**Syntaxe :** `singular lives create [-h] [--name NAME] [--curiosity CURIOSITY] [--patience PATIENCE] [--playfulness PLAYFULNESS] [--optimism OPTIMISM] [--resilience RESILIENCE] [--starter-profile STARTER_PROFILE] [--starter-skill STARTER_SKILL]`

**Arguments et défauts :** `--name` (`New life`); `--curiosity` (`None`); `--patience` (`None`); `--playfulness` (`None`); `--optimism` (`None`); `--resilience` (`None`); `--starter-profile` (`assistant`); `--starter-skill` (`[]`)

**Prérequis :** Root accessible; profil starter valide.

**Root et vie ciblés :** Root résolu; crée et active une nouvelle vie.

**Fichiers lus ou écrits :** Écrit `lives/registry.json` et le dossier `lives/<slug>/` (identité, psyché, skills et mémoire).

**Effets de bord :** Crée des répertoires et positionne `SINGULAR_HOME`; `birth` est dépréciée.

**Exemple minimal :** `singular lives create --name Ada`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives create --name Ada`

**Erreurs usuelles :** Trait hors [0,1], nom/profil invalide, root non inscriptible.

<!-- cli-command: lives use -->
## `lives use`

**Syntaxe :** `singular lives use [-h] name`

**Arguments et défauts :** `name` (requis/required)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives use ada`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives use ada`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives delete -->
## `lives delete`

**Syntaxe :** `singular lives delete [-h] name`

**Arguments et défauts :** `name` (requis/required)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives delete ada`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives delete ada`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives archive -->
## `lives archive`

**Syntaxe :** `singular lives archive [-h] name`

**Arguments et défauts :** `name` (requis/required)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives archive ada`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives archive ada`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives memorial -->
## `lives memorial`

**Syntaxe :** `singular lives memorial [-h] [--message MESSAGE] name`

**Arguments et défauts :** `name` (requis/required); `--message` (`Merci pour ce cycle de vie.`)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives memorial ada`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives memorial ada`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives clone -->
## `lives clone`

**Syntaxe :** `singular lives clone [-h] [--new-name NEW_NAME] name`

**Arguments et défauts :** `name` (requis/required); `--new-name` (`None`)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives clone ada`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives clone ada`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives reproduce -->
## `lives reproduce`

**Syntaxe :** `singular lives reproduce [-h] [--new-name NEW_NAME] parent_a parent_b`

**Arguments et défauts :** `parent_a` (requis/required); `parent_b` (requis/required); `--new-name` (`None`)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives reproduce ada bob`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives reproduce ada bob`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives relations -->
## `lives relations`

**Syntaxe :** `singular lives relations [-h] [--name NAME]`

**Arguments et défauts :** `--name` (`None`)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Affichage uniquement.

**Exemple minimal :** `singular lives relations`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives relations`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives ally -->
## `lives ally`

**Syntaxe :** `singular lives ally [-h] name other`

**Arguments et défauts :** `name` (requis/required); `other` (requis/required)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives ally ada bob`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives ally ada bob`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives rival -->
## `lives rival`

**Syntaxe :** `singular lives rival [-h] name other`

**Arguments et défauts :** `name` (requis/required); `other` (requis/required)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives rival ada bob`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives rival ada bob`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives reconcile -->
## `lives reconcile`

**Syntaxe :** `singular lives reconcile [-h] name other`

**Arguments et défauts :** `name` (requis/required); `other` (requis/required)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives reconcile ada bob`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives reconcile ada bob`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: lives proximity -->
## `lives proximity`

**Syntaxe :** `singular lives proximity [-h] --score SCORE name`

**Arguments et défauts :** `name` (requis/required); `--score` (requis/required)

**Prérequis :** Registre existant; les noms cités doivent exister.

**Root et vie ciblés :** Root résolu; vie(s) indiquée(s), ou vie active pour `relations`.

**Fichiers lus ou écrits :** Lit/écrit `lives/registry.json` et les dossiers de vie concernés.

**Effets de bord :** Modifie le registre et/ou les données de vie; `delete` supprime définitivement.

**Exemple minimal :** `singular lives proximity ada --score 0.7`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json lives proximity ada --score 0.7`

**Erreurs usuelles :** Vie introuvable/ambiguë, reproduction non éligible, score hors [0,1], suppression active refusée.

<!-- cli-command: values -->
## `values`

**Syntaxe :** `singular values [-h] {show} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular values show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json values show`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: values show -->
## `values show`

**Syntaxe :** `singular values show [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular values show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json values show`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: policy -->
## `policy`

**Syntaxe :** `singular policy [-h] {show,set} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular policy show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json policy show`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: policy show -->
## `policy show`

**Syntaxe :** `singular policy show [-h]`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular policy show`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json policy show`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: policy set -->
## `policy set`

**Syntaxe :** `singular policy set [-h] --key {autonomy.auto_rollback_cost_threshold,autonomy.auto_rollback_failure_threshold,autonomy.circuit_breaker_cooldown_seconds,autonomy.circuit_breaker_threshold,autonomy.circuit_breaker_window_seconds,autonomy.mutation_quota_per_window,autonomy.mutation_quota_window_seconds,autonomy.runtime_blacklisted_capabilities,autonomy.runtime_call_quota_per_hour,autonomy.safe_mode,autonomy.safe_mode_review_required_skill_families,autonomy.skill_circuit_breaker_cooldown_seconds,autonomy.skill_circuit_breaker_cost_threshold,autonomy.skill_circuit_breaker_failure_threshold,forgetting.enabled,forgetting.max_episodic_entries,memory.preserve_threshold,permissions.forbidden_paths,permissions.force_allow_paths,permissions.modifiable_paths,permissions.review_required_paths} --value VALUE`

**Arguments et défauts :** `--key` (requis/required; choix/choices: autonomy.auto_rollback_cost_threshold, autonomy.auto_rollback_failure_threshold, autonomy.circuit_breaker_cooldown_seconds, autonomy.circuit_breaker_threshold, autonomy.circuit_breaker_window_seconds, autonomy.mutation_quota_per_window, autonomy.mutation_quota_window_seconds, autonomy.runtime_blacklisted_capabilities, autonomy.runtime_call_quota_per_hour, autonomy.safe_mode, autonomy.safe_mode_review_required_skill_families, autonomy.skill_circuit_breaker_cooldown_seconds, autonomy.skill_circuit_breaker_cost_threshold, autonomy.skill_circuit_breaker_failure_threshold, forgetting.enabled, forgetting.max_episodic_entries, memory.preserve_threshold, permissions.forbidden_paths, permissions.force_allow_paths, permissions.modifiable_paths, permissions.review_required_paths); `--value` (requis/required)

**Prérequis :** Droits d'écriture; confirmation/option destructive appropriée.

**Root et vie ciblés :** Root global pour config/rétention/désinstallation; vie active pour croyances.

**Fichiers lus ou écrits :** Écrit/supprime configuration, `runs/`, `mem/`, croyances ou `lives/` selon la commande.

**Effets de bord :** Effet persistant; purge/reset/uninstall peuvent être irréversibles. Utiliser dry-run quand disponible.

**Exemple minimal :** `singular policy set --key autonomy.safe_mode --value true`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json policy set --key autonomy.safe_mode --value true`

**Erreurs usuelles :** Option requise absente, clé/valeur invalide, confirmation refusée, protection du repo, permissions.

<!-- cli-command: ecosystem -->
## `ecosystem`

**Syntaxe :** `singular ecosystem [-h] {run} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular ecosystem run --life ada --budget-seconds 10`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json ecosystem run --life ada --budget-seconds 10`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: ecosystem run -->
## `ecosystem run`

**Syntaxe :** `singular ecosystem run [-h] [--life ECOSYSTEM_LIVES] [--life-group ECOSYSTEM_GROUPS] [--checkpoint CHECKPOINT] --budget-seconds BUDGET_SECONDS [--run-id RUN_ID]`

**Arguments et défauts :** `--life` (`[]`); `--life-group` (`[]`); `--checkpoint` (`None`); `--budget-seconds` (requis/required); `--run-id` (`ecosystem`)

**Prérequis :** Vie active et configuration/fournisseur requis par le mode; budget positif lorsqu'il est requis.

**Root et vie ciblés :** Vie choisie par `--home`/`--life`; `ecosystem run` cible toutes les vies listées.

**Fichiers lus ou écrits :** Lit la configuration et la mémoire; écrit événements, checkpoints et runs sous la vie. `embodiment` lit `--config`; `dashboard` sert ces données.

**Effets de bord :** Peut appeler un LLM/capteur, muter des skills, écrire des logs ou lancer un service; `--dry-run` limite les mutations.

**Exemple minimal :** `singular ecosystem run --life ada --budget-seconds 10`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json ecosystem run --life ada --budget-seconds 10`

**Erreurs usuelles :** Vie/provider/config absent, budget/intervalle invalide, capteur indisponible, trop d'erreurs daemon.

<!-- cli-command: config providers setup -->
## `config providers setup`

**Syntaxe :** `singular config providers setup [-h] [--model MODEL] [--non-interactive] [--pull] [--timeout TIMEOUT] {ollama}`

**Arguments et défauts :** provider `ollama` (requis); `--model` (`OLLAMA_MODEL`, sinon le défaut du provider); `--non-interactive` (`false`); `--pull` (`false`); `--timeout` (`120.0`).

**Prérequis :** service `ollama serve` joignable. La commande affiche `/api/tags`, demande confirmation avant `ollama pull`, puis effectue une génération minimale. `--non-interactive --pull` convient aux installations automatisées; sans `--pull`, le mode non interactif ne télécharge rien.

**Root et vie ciblés :** Aucun root ni vie; utilise uniquement le service défini par `OLLAMA_HOST`.

**Fichiers lus ou écrits :** Aucun fichier Singular; Ollama stocke le modèle téléchargé dans son propre espace.

**Effets de bord :** le téléchargement n'est possible que dans cette action explicite et après confirmation ou `--pull`; `singular talk` ne télécharge jamais de modèle.

**Exemple minimal :** `singular config providers setup ollama`

**Exemple avancé :** `singular config providers setup ollama --non-interactive --pull --model llama3.2`

**Erreurs usuelles :** `service_stopped`, `command_missing`, `model_missing`, `download_incomplete`, `timeout`, `invalid_generation`. Chaque sortie inclut `Remédiation:` avec la commande à exécuter.

<!-- cli-command: beliefs -->
## `beliefs`

**Syntaxe :** `singular beliefs [-h] {audit,reset} ...`

**Arguments et défauts :** Aucune / None.

**Prérequis :** Aucun; choisir une sous-commande.

**Root et vie ciblés :** Root de registre; aucune vie tant que la sous-commande n'est pas choisie.

**Fichiers lus ou écrits :** Aucun fichier directement.

**Effets de bord :** Affiche l'aide ou délègue; aucun effet direct.

**Exemple minimal :** `singular beliefs audit`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json beliefs audit`

**Erreurs usuelles :** Sous-commande absente.

<!-- cli-command: beliefs audit -->
## `beliefs audit`

**Syntaxe :** `singular beliefs audit [-h] [--limit LIMIT]`

**Arguments et défauts :** `--limit` (`25`)

**Prérequis :** Vie active pour les diagnostics liés à une vie; dépendances correspondantes disponibles.

**Root et vie ciblés :** `SINGULAR_HOME`/vie sélectionnée; `doctor` et `config root show` sont globaux.

**Fichiers lus ou écrits :** Lit selon la commande: registre, `mem/`, `runs/`, `skills/`, politique ou configuration; `report --export` écrit le fichier demandé.

**Effets de bord :** Affichage seulement, sauf export de rapport et `doctor --fix` (PATH utilisateur Windows).

**Exemple minimal :** `singular beliefs audit`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json beliefs audit`

**Erreurs usuelles :** Vie/run/fichier absent, JSON invalide, skill sandbox KO, format/export invalide.

<!-- cli-command: beliefs reset -->
## `beliefs reset`

**Syntaxe :** `singular beliefs reset [-h] (--hypothesis HYPOTHESIS | --prefix PREFIX | --all)`

**Arguments et défauts :** `--hypothesis` (`None`); `--prefix` (`None`); `--all` (`false`)

**Prérequis :** Droits d'écriture; confirmation/option destructive appropriée.

**Root et vie ciblés :** Root global pour config/rétention/désinstallation; vie active pour croyances.

**Fichiers lus ou écrits :** Écrit/supprime configuration, `runs/`, `mem/`, croyances ou `lives/` selon la commande.

**Effets de bord :** Effet persistant; purge/reset/uninstall peuvent être irréversibles. Utiliser dry-run quand disponible.

**Exemple minimal :** `singular beliefs reset --hypothesis test`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json beliefs reset --hypothesis test`

**Erreurs usuelles :** Option requise absente, clé/valeur invalide, confirmation refusée, protection du repo, permissions.

<!-- cli-command: uninstall -->
## `uninstall`

**Syntaxe :** `singular uninstall [-h] (--keep-lives | --purge-lives) [--yes] [--force]`

**Arguments et défauts :** `--keep-lives` (`false`); `--purge-lives` (`false`); `--yes` (`false`); `--force` (`false`)

**Prérequis :** Droits d'écriture; confirmation/option destructive appropriée.

**Root et vie ciblés :** Root global pour config/rétention/désinstallation; vie active pour croyances.

**Fichiers lus ou écrits :** Écrit/supprime configuration, `runs/`, `mem/`, croyances ou `lives/` selon la commande.

**Effets de bord :** Effet persistant; purge/reset/uninstall peuvent être irréversibles. Utiliser dry-run quand disponible.

**Exemple minimal :** `singular uninstall --keep-lives --yes`

**Exemple avancé :** `singular --root /srv/singular --life ada --format json uninstall --keep-lives --yes`

**Erreurs usuelles :** Option requise absente, clé/valeur invalide, confirmation refusée, protection du repo, permissions.

## Alias et aide

`veille` est un alias exact de `watch`; `talk --live` est un alias déprécié de `talk --life`; `birth` peut être désactivé avec `SINGULAR_ENABLE_BIRTH_ALIAS=0`. `singular <commande> --help` reste la source exécutable pour le détail des metavars.

<!-- cli-command: governance -->
## `governance`
Commandes de diagnostic et de récupération de la gouvernance.


**Syntaxe :** `singular governance [-h]`

**Arguments et défauts :** Voir `--help`; aucun argument implicite non documenté.

**Prérequis :** Registre accessible et autorisation opérateur pour la récupération.

**Root et vie ciblés :** Root du registre sélectionné; aucune vie implicite.

**Fichiers lus ou écrits :** Lit et peut mettre à jour l'état de gouvernance.

**Effets de bord :** Le diagnostic est en lecture seule; la récupération est auditée.

**Exemple minimal :** `singular governance`

**Exemple avancé :** `singular --root /srv/singular governance`

**Erreurs usuelles :** Root absent, justification ou autorisation manquante.
<!-- cli-command: governance diagnose -->
## `governance diagnose`
Affiche l'état auditable des coupe-circuits de gouvernance.


**Syntaxe :** `singular governance diagnose [-h]`

**Arguments et défauts :** Voir `--help`; aucun argument implicite non documenté.

**Prérequis :** Registre accessible et autorisation opérateur pour la récupération.

**Root et vie ciblés :** Root du registre sélectionné; aucune vie implicite.

**Fichiers lus ou écrits :** Lit et peut mettre à jour l'état de gouvernance.

**Effets de bord :** Le diagnostic est en lecture seule; la récupération est auditée.

**Exemple minimal :** `singular governance diagnose`

**Exemple avancé :** `singular --root /srv/singular governance diagnose`

**Erreurs usuelles :** Root absent, justification ou autorisation manquante.
<!-- cli-command: governance recover -->
## `governance recover`
Récupère la gouvernance avec une justification opérateur explicite.


**Syntaxe :** `singular governance recover [-h]`

**Arguments et défauts :** Voir `--help`; aucun argument implicite non documenté.

**Prérequis :** Registre accessible et autorisation opérateur pour la récupération.

**Root et vie ciblés :** Root du registre sélectionné; aucune vie implicite.

**Fichiers lus ou écrits :** Lit et peut mettre à jour l'état de gouvernance.

**Effets de bord :** Le diagnostic est en lecture seule; la récupération est auditée.

**Exemple minimal :** `singular governance recover`

**Exemple avancé :** `singular --root /srv/singular governance recover`

**Erreurs usuelles :** Root absent, justification ou autorisation manquante.
<!-- cli-command: diagnose governance -->
## `diagnose governance`
Alias de diagnostic disponible sous la commande générale `diagnose`.

**Syntaxe :** `singular diagnose governance [-h]`

**Arguments et défauts :** Voir `--help`; aucun argument implicite non documenté.

**Prérequis :** Registre accessible et autorisation opérateur pour la récupération.

**Root et vie ciblés :** Root du registre sélectionné; aucune vie implicite.

**Fichiers lus ou écrits :** Lit et peut mettre à jour l'état de gouvernance.

**Effets de bord :** Le diagnostic est en lecture seule; la récupération est auditée.

**Exemple minimal :** `singular diagnose governance`

**Exemple avancé :** `singular --root /srv/singular diagnose governance`

**Erreurs usuelles :** Root absent, justification ou autorisation manquante.
