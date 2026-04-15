# Plan de delivery — Dashboard Recovery

## Objectif
Rétablir rapidement la lisibilité opérationnelle du dashboard, puis renforcer l’observabilité et la fiabilité produit sur trois horizons temporels.

---

## Phase 48h — Stabilisation

### Périmètre
- Corriger l’affichage des vies dans le registre lorsqu’aucun run n’est présent.
- Corriger la résolution des chemins de runs en contexte multi-vies.
- Rendre disponibles les capteurs CPU, RAM et disque au minimum.
- Ajouter un message d’état vide explicatif, avec action de reset des filtres.

### Livrables attendus
- Correctif UI/API pour visibilité des vies sans run.
- Correctif de mapping/lookup des chemins de runs multi-vies.
- Pipeline de collecte des métriques hôte avec fallback explicite si un capteur est indisponible.
- Composant d’état vide avec CTA "Réinitialiser les filtres".

### Vérification
- Test manuel sur un environnement avec et sans runs.
- Vérification des métriques en temps réel (CPU/RAM/disque).
- Validation UX de l’état vide et du reset des filtres.

### Critère de sortie
**Une vie visible + KPI cohérents + au moins 3 capteurs renseignés.**

---

## Phase 7 jours — Observabilité

### Périmètre
- Mettre en place un journal d’évolution du code par vie.
- Ajouter un `trace_id` de bout en bout (ingestion → traitement → UI).
- Créer un panneau “preuves de vie”.

### Livrables attendus
- Timeline ou log consolidé par vie (événements de code, changements significatifs).
- Propagation systématique du `trace_id` dans logs, événements et vues dashboard.
- Nouveau panneau synthétique listant signaux, actions, impacts et anomalies.

### Vérification
- Démonstration de traçage d’un événement complet par `trace_id`.
- Relecture opérateur sur 2–3 vies pour vérifier la compréhension rapide.
- Contrôle de cohérence entre journal d’évolution et panneau de preuves.

### Critère de sortie
**Un opérateur peut expliquer en 2 minutes “ce que la vie a fait et amélioré”.**

---

## Phase 30 jours — Fiabilité produit

### Périmètre
- Harmoniser le contrat KPI global.
- Refonte du mode essentiel orientée opération.
- Construire une matrice de non-régression par capacité.

### Livrables attendus
- Spécification unique des KPI (définitions, source de vérité, unités, fréquence).
- Nouveau mode essentiel centré sur les décisions opérateur et les alertes actionnables.
- Matrice de tests de non-régression couvrant les capacités critiques.

### Vérification
- Revue croisée produit/tech sur le contrat KPI.
- Tests UX opérateur sur scénarios de diagnostic et de décision.
- Exécution automatisée régulière de la matrice de non-régression.

### Critère de sortie
**Les tests smoke couvrent toutes les fonctions critiques mentionnées.**

---

## Gouvernance de delivery

### Rythme recommandé
- Point quotidien (15 min) durant la phase 48h.
- Point tri-hebdomadaire durant la phase 7 jours.
- Revue hebdomadaire orientée risques pour la phase 30 jours.

### Risques clés à suivre
- Dette de données historiques empêchant la cohérence KPI.
- Variabilité d’environnement (capteurs non disponibles selon host/permissions).
- Effet tunnel sur la technique au détriment de la lisibilité opérateur.

### Indicateurs de pilotage
- % de vies visibles sans intervention manuelle.
- % de runs correctement résolus en multi-vies.
- Couverture capteurs disponibles (CPU/RAM/disque).
- Temps moyen pour expliquer l’activité d’une vie (objectif ≤ 2 min).
- Couverture smoke tests sur fonctions critiques.
