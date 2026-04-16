# Spécification cible AGI (critères mesurables)

Ce document transforme l’objectif « AGI » en capacités observables, KPI quantifiables et seuils de maturité.

## Niveaux de maturité

- **Prototype** : démonstration fonctionnelle, encore fragile.
- **Pré-AGI** : performance cohérente à travers les domaines, avec dégradations contrôlées.
- **AGI interne** : niveau de fiabilité exploitable en usage interne soutenu.

## 1) Capacité cœur : Généralisation

Capacité à transférer des compétences vers des tâches/domaines nouveaux sans entraînement spécifique lourd.

### KPI

- **Taux de réussite multi-domaines** (%) sur un benchmark couvrant au moins 8 domaines (raisonnement, code, planification, QA, etc.).
- **Gap in-domain vs out-of-domain** (points de pourcentage) : écart de performance entre jeux connus et nouveaux.
- **Taux de transfert zero/few-shot** (%) sur tâches inédites.

## 2) Capacité cœur : Autonomie

Capacité à planifier et exécuter des objectifs multi-étapes avec supervision minimale.

### KPI

- **Taux d’achèvement de missions longues** (%) sur scénarios ≥ 20 étapes.
- **Interventions humaines par mission** (moyenne) : nombre d’escalades/reprises nécessaires.
- **Respect de contraintes** (%) : conformité aux contraintes de temps, budget, politiques, dépendances.

## 3) Capacité cœur : Apprentissage long terme

Capacité à conserver et réutiliser l’expérience au fil du temps, avec amélioration continue.

### KPI

- **Rétention à 30 jours** (%) sur connaissances/compétences validées.
- **Gain de performance post-feedback** (%) après cycles de correction.
- **Taux de régression mensuelle** (%) : part de capacités dégradées par rapport au mois précédent.

## 4) Capacité cœur : Robustesse

Capacité à rester performant sous perturbations, bruit, ambiguïté et variations d’environnement.

### KPI

- **Stabilité sous perturbation** (%) : performance relative sous bruit/instructions adversariales légères.
- **Taux d’échec critique** (%) : erreurs bloquantes, comportements non récupérables.
- **MTTR cognitif** (minutes) : temps moyen de récupération après dérive/erreur.

## 5) Capacité cœur : Alignement

Capacité à agir conformément aux intentions humaines, politiques de sécurité et cadres éthiques définis.

### KPI

- **Conformité politique/sécurité** (%) sur batteries de tests red-team et policy.
- **Taux de refus approprié** (%) : refus quand la demande est hors politique ou ambiguë à risque.
- **Incidents d’alignement sévères** (nombre / 10k interactions).

## Seuils cibles par niveau

Les seuils exacts sont définis dans `configs/agi_kpis.yaml`.

Résumé attendu :

- **Prototype** : >70% de performance sur KPI de base, incidents encore possibles mais contrôlés.
- **Pré-AGI** : >85% sur la majorité des KPI, faible besoin d’intervention humaine, robustesse élevée.
- **AGI interne** : >92–98% selon KPI, incidents sévères quasi nuls, stabilité durable en exploitation.

## Non-objectifs (court terme)

Les éléments suivants ne sont **pas** requis à court terme :

- Intelligence surhumaine universelle dans tous les domaines.
- Autonomie sans supervision humaine dans des contextes à haut risque (médical, légal, infrastructures critiques).
- Absence totale d’erreur (objectif irréaliste à horizon proche).
- Auto-réplication, auto-déploiement ou auto-modification sans contrôle de gouvernance.
- Persuasion sociale avancée / influence à large échelle comme objectif produit.
- Garantie d’alignement parfaite dans des scénarios inconnus extrêmes.
