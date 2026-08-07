# Audit des modules runtime à la racine

Les anciens répertoires racine `action/`, `interaction/`, `mind/`, `perception/` et
`observability/` contenaient des composants runtime publics : exécution sandboxée,
synthèse vocale, modèle d'état, pipelines de perception et journal d'audit. Comme
ces modules sont utilisés par l'API ou ses tests d'intégration, ils font désormais
partie du paquet installable sous les espaces de noms suivants :

- `singular.action`
- `singular.interaction`
- `singular.mind`
- `singular.perception`
- `singular.observability`

Aucun composant Python de ces anciens répertoires n'est volontairement maintenu
hors du paquet. Les fichiers README des pipelines de perception restent de la
documentation de développement et ne sont pas requis à l'exécution.
