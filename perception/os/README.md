# perception.os

Pipeline de perception OS orientée contexte:

- fenêtre active (`application`, `title`),
- état d'entrée utilisateur (position souris + activité clavier agrégée, sans keylogging brut),
- notifications système capturables,
- état hôte (réseau, batterie, charge CPU).

## Événements produits

`OSPerceptionPipeline.collect()` émet deux `PerceptEvent`:

1. `os_state`: snapshot brut compact,
2. `os_semantic`: événements dérivés (ex: `user.in_meeting`, `workspace.coding_active`).

## Confidentialité

- Aucun enregistrement de frappes clavier brutes.
- Les notifications sont réduites à un aperçu (`body_preview`).
- Le provider par défaut est **best effort** sans dépendances système obligatoires.

## Extension

Sous-classez `BestEffortOSSnapshotProvider` pour brancher des APIs natives (Windows/macOS/Linux)
et fournir:

- détection réelle de fenêtre active,
- état clavier/idle robuste,
- flux notifications natif.
