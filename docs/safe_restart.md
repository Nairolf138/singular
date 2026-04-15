# Procédure de reprise sécurisée (« safe restart »)

Cette procédure permet de redémarrer l’agent après arrêt d’urgence (hotkey global, watchdog, dépassement de débit d’actions, ou auto-désactivation sur erreurs critiques) avec **un état minimal**.

## 1) Préconditions

- Agent arrêté.
- Cause d’arrêt identifiée dans les événements runtime (`runtime.global_stop`, `runtime.watchdog_stopped`, `runtime.rate_limited`, `runtime.auto_disabled`).
- Aucun processus concurrent n’écrit dans le même répertoire de mémoire.

## 2) État minimal à conserver

Conserver uniquement les artefacts suivants :

1. `checkpoint.json` (ou le fichier de checkpoint actif) pour reprendre l’itération.
2. Les skills sources (`skills/*.py`) dans leur dernier état validé.
3. Le dernier état mémoire strictement nécessaire aux décisions:
   - `mem/world_state.json` si utilisé par la boucle,
   - `mem/skills.json` pour l’historique de score minimal.

Tous les autres artefacts (logs volumineux, exports intermédiaires, traces temporaires) peuvent rester archivés hors du chemin de reprise.

## 3) Reset de sécurité avant redémarrage

1. Vérifier/corriger la cause racine:
   - hotkey activée par erreur,
   - boucle d’action répétitive (watchdog),
   - plafond d’actions/min trop bas,
   - série d’erreurs critiques non traitées.
2. Si nécessaire, ajuster les paramètres de sécurité du runtime:
   - `max_actions_per_minute`,
   - `watchdog_window_size`,
   - `watchdog_repeat_action_threshold`,
   - `max_critical_errors`.
3. Redémarrer avec un budget court (ex: 30–60s) pour validation.

## 4) Séquence de « safe restart »

1. Charger le checkpoint minimal.
2. Réinitialiser les compteurs volatils runtime (fenêtre d’actions/minute, buffer watchdog, compteurs d’erreurs en mémoire).
3. Exécuter un run de validation court.
4. Contrôler que:
   - aucun arrêt de sécurité n’est relancé immédiatement,
   - la progression d’itération reprend,
   - les actions restent sous le seuil/minute.
5. Reprendre le run nominal.

## 5) Critères d’acceptation post-reprise

- L’agent tient au moins un cycle de validation complet.
- Aucun événement `runtime.auto_disabled` sur le cycle de validation.
- Les checkpoints se réécrivent correctement.
- Les actions produites ne réactivent pas le watchdog.

## 6) Plan de rollback

Si la reprise échoue:

1. Stopper immédiatement via hotkey global.
2. Restaurer le dernier checkpoint sain.
3. Désactiver temporairement la mutation/action à risque.
4. Rejouer en mode dégradé (budget court + monitoring renforcé).
