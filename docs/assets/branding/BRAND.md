# Singular — identité visuelle v2

Le répertoire `docs/assets/branding/` est la source canonique de toutes les
ressources de marque. Les fichiers présents dans l'application, notamment dans
le dashboard, sont des copies générées et ne doivent pas être modifiés
directement.

Après toute modification de `singular-icon.svg` ou `singular-logo.svg`,
synchroniser les copies applicatives depuis la racine du dépôt :

```console
python scripts/sync_dashboard_branding.py
```

Le contrôle statique du dashboard compare les fichiers octet par octet et
échoue si une copie diverge de sa source canonique.

## Palette

- Indigo profond : `#0A1BFF`
- Bleu électrique : `#2D6BFF`
- Bleu clair : `#00A7FF`
- Cyan numérique : `#00E0D1`
- Navy : `#0B1124`
- Blanc : `#FFFFFF`

Dégradé principal : `#0A1BFF → #2D6BFF → #00A7FF → #00E0D1`.

## Fichiers

- `singular-logo.svg` : source vectorielle canonique du logo horizontal pour les fonds blancs ou très clairs.
- `singular-logo-light.svg` : variante horizontale claire, avec libellé blanc et signature bleu clair, pour les fonds sombres.
- `singular-logo-stacked.svg` : version verticale pour les fonds blancs ou très clairs.
- `singular-logo-stacked-light.svg` : version verticale claire pour les fonds sombres.
- `singular-logo-github.png` : export horizontal en 1 400 × 430 px (affiché à 700 × 215 px, soit 2×), sur fond blanc explicite pour préserver la lisibilité dans les thèmes clair et sombre ; variante recommandée pour les README rendus par GitHub.
- `singular-icon.svg` : symbole seul, recommandé pour favicon, app icon et espaces compacts.

Tous les libellés des SVG sont des tracés vectoriels : leur rendu ne requiert aucune police installée et ne dépend pas de CSS externe.

## Contraste et choix de variante

Les SVG restent transparents afin de pouvoir être composés librement. Le choix du fichier garantit le contraste sans héritage du thème de la page hôte :

- sur fond blanc ou clair, utiliser `singular-logo.svg` ou `singular-logo-stacked.svg` (libellé navy `#0B1124`) ;
- sur fond noir, navy ou sombre, utiliser `singular-logo-light.svg` ou `singular-logo-stacked-light.svg` (libellé blanc `#FFFFFF`) ;
- sur un fond transparent ou inconnu, placer explicitement le logo dans un conteneur blanc et utiliser la variante standard, ou dans un conteneur navy et utiliser la variante claire ; ne pas choisir une variante au moyen de CSS appliqué à l'intérieur du SVG ;
- conserver une zone de respiration au moins égale à la hauteur du « I » autour du logo et ne pas poser les libellés sur une zone d'image chargée.

Le dashboard embarque des copies synchronisées de l'icône et du logo canonique
sous `src/singular/dashboard/static/`. La variante horizontale claire reste
disponible séparément sous le nom `singular-logo-light.svg` pour les usages sur
fond sombre.

## Tailles et contrôle visuel

Tailles principales recommandées : 350 × 108 px pour le logo horizontal du dashboard, 700 × 215 px dans la documentation et 200 × 225 px pour le logo vertical. À petite taille, préférer le symbole seul en dessous de 160 px de large ; si le logotype complet est requis, ne pas descendre sous 120 px de large (horizontal) ou 96 px (vertical).

Avant publication, vérifier chaque variante aux tailles principale et minimale sur des fonds blanc (`#FFFFFF`), noir (`#000000`) et transparent (visualisé sur un damier). Sur fond transparent, contrôler séparément la composition claire et la composition sombre décrites ci-dessus. Vérifier notamment que « SINGULAR » et « DIGITAL LIFE » restent lisibles, que le dégradé n'est pas écrêté et qu'aucune police de remplacement n'apparaît.
