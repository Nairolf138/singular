# Statut de vie: source de vérité

Ce document définit la sémantique officielle du statut d'une **vie** dans Singular.

## Source de vérité

La source de vérité est le champ `status` de chaque entrée dans `lives/registry.json`.

Valeurs supportées:

- `active`: la vie est considérée active dans le registre.
- `extinct`: la vie est marquée comme éteinte dans le registre.

Ce statut est porté par `LifeMetadata.status` dans `src/singular/lives.py`, persisté via `save_registry()`, et modifié via `set_life_status()`.

## Distinction des notions

Le dashboard distingue désormais:

- **Vie sélectionnée**: correspond à la clé racine `active` du registre (`registry["active"]`).
- **Vie active dans le registre**: correspond à `life.status == "active"`.
- **Run terminé**: information de run-level (ex: dernier événement `death`).
- **Extinction détectée**: information observée dans les événements de run (présence d'au moins un `event == "death"`).

## Règle d'agrégation dashboard

Le dashboard n'infère plus un statut de vie uniquement à partir des runs:

1. Il lit d'abord `status` depuis le registre (source de vérité).
2. Il calcule en parallèle des indicateurs run-level (`extinction_seen_in_runs`, `run_terminated`, `has_recent_activity`).
3. Si une extinction est détectée dans les runs pour une vie enregistrée, il synchronise le registre via `set_life_status(slug, "extinct")`.
