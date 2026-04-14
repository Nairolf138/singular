# `perception_signals` — objectifs intrinsèques (modulation v2)

Ce document décrit les nouveaux champs consommés par:

- `IntrinsicGoals.update_tick`
- `IntrinsicGoals.derive_execution_strategy`

Version de logique: **`intrinsic-mod-v2`**.

## Champs narratifs

Sous-clé: `perception_signals["narrative_indicators"]`

- `risk_aversion_by_action_family: dict[str, float]`
  - Aversion au risque par famille d’actions (valeurs attendues entre `0.0` et `1.0`).
  - Effet: augmente `robustesse`, réduit `exploration`.
- `accumulated_confidence_by_action_family: dict[str, float]`
  - Confiance accumulée par famille d’actions (entre `0.0` et `1.0`).
  - Effet: augmente `efficacite` et `exploration`.
- `accumulated_confidence: float`
  - Fallback global si la version par famille n’est pas fournie.

## Historique blessures / succès / échecs répétés

Sous-clé: `perception_signals["execution_history"]`

- `recent_injuries: float | int`
  - Intensité/compte des blessures récentes.
  - Effet: augmente `robustesse`.
- `recent_successes: float | int`
  - Compte des succès récents.
  - Effet: augmente `efficacite`.
- `repeated_failure_pressure: float`
  - Pénalité “déjà vécu” pour un schéma d’échec répété (`0.0` à `1.0`).
  - Effet:
    - réduit `exploration` et partiellement `efficacite`,
    - augmente `robustesse`,
    - force une stratégie `cautious` dans `derive_execution_strategy` quand élevée.

## Versionnage de modulation

La version active est exposée et historisée sous:

- `history[-1]["signals"]["intrinsic_modulation_version"]`
- `derive_execution_strategy(...).intrinsic_modulation_version`

Valeur actuelle: `intrinsic-mod-v2`.
