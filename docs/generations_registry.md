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

## Politique de conservation / archivage / purge

- Le registre `mem/generations.jsonl` est conservé comme journal d’audit principal.
- Les snapshots `runs/<run_id>/generations/` peuvent être archivés après 30 jours.
- Après vérification d’archivage, les snapshots des générations rejetées peuvent être purgés en priorité.
- Les générations acceptées gardent au moins un snapshot restaurable par run actif.
