# Registre des générations

Le système enregistre chaque tentative de mutation dans `mem/generations.jsonl`.

## Schéma enregistré

Chaque entrée contient :

- `generation_id` et `parent_generation_id`
- lien au run (`run_id`, `iteration`, `ts`)
- mutation (`operator`, `diff`)
- score (`base`, `new`)
- `verdict` (`accepted`/`rejected`)
- hash (`parent`, `candidate`)
- raison de décision (`reason`)
- métadonnées de sécurité (`security`)
- snapshot de code (`snapshot`)

Les snapshots sont stockés sous `runs/<run_id>/generations/gen-<id>.py`.

## Rollback atomique

Commande:

```bash
singular rollback --generation <id>
```

Le rollback est autorisé uniquement pour une génération stable (`stable=true`, i.e. acceptée),
et restaure atomiquement le fichier de skill depuis le snapshot.

## Rétention: paramètres, défauts, garanties

La politique de rétention unifiée expose les paramètres suivants :

- `max_runs` (défaut: `20`)
- `max_run_age_days` (défaut: `30`)
- `max_total_runs_size_mb` (défaut: `512`)
- `max_episodic_lines` (défaut: `20000`)
- `max_episodic_days` (défaut: `90`)
- `max_generations_lines` (défaut: `50000`)
- `max_generations_days` (défaut: `365`)

Résolution des paramètres (priorité décroissante) :

1. variables d’environnement `SINGULAR_RETENTION_*`;
2. fichier `mem/retention_policy.json`;
3. valeurs par défaut intégrées.

Exemples de variables d’environnement :

```bash
SINGULAR_RETENTION_MAX_RUNS=50
SINGULAR_RETENTION_MAX_RUN_AGE_DAYS=14
SINGULAR_RETENTION_MAX_TOTAL_RUNS_SIZE_MB=1024
```

### Garanties (ce qui n’est jamais supprimé automatiquement)

- un run actif est toujours protégé (`.active.lock` ou `.jsonl.tmp`);
- `lives/` n’est pas ciblé par la purge `retention run`;
- `mem/generations.jsonl` n’est pas supprimé automatiquement par la rétention des runs;
- les snapshots de générations (`runs/<run_id>/generations/`) ne sont pas purgés par défaut par ce service;
- en mode `--dry-run`, aucune suppression ni écriture d’état n’est effectuée.

## Commandes de contrôle

```bash
# Afficher les seuils actifs (après résolution env/fichier/défauts)
singular retention config show

# Afficher usage stockage, dépassements et dernière purge
singular retention status

# Simuler sans supprimer
singular retention run --dry-run

# Exécuter la purge réelle
singular retention run
```

Notes opérationnelles :

- la purge réelle est throttlée (intervalle minimal, 15 min par défaut) ;
- la dernière exécution est journalisée dans `mem/retention_state.json`;
- les décisions sont tracées dans `mem/retention.log.jsonl`.

## Migration (utilisateurs existants)

Recommandation de migration progressive :

1. **Mesurer avant d’agir** : `singular retention status`.
2. **Configurer sans risque** : définir d’abord des seuils permissifs.
3. **Toujours valider en simulation** : `singular retention run --dry-run`.
4. **Purger ensuite seulement** : `singular retention run` après revue des `would_delete`.
5. **Mettre à jour les scripts legacy** :
   - ancien: `SINGULAR_RUNS_KEEP=...`
   - nouveau: `SINGULAR_RETENTION_MAX_RUNS=...`

Cette approche évite une purge inattendue lors de la première activation sur un environnement historique.
