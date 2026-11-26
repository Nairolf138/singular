# Direction de la prochaine version majeure : compagnon et laboratoire

> **Statut : `target-only`.** Cette vision ne fixe ni numéro, ni date de release,
> ni promesse que les capacités décrites fonctionnent aujourd'hui. La surface
> `stable` actuelle et ses prérequis figurent dans le
> [registre des capacités](README.md#registre-des-capacités-stable) ; la
> [v0.1.0](releases/v0.1.0.md) couvre une surface CLI limitée.

## Intention

Faire de Singular un compagnon numérique singulier qui naît, conserve son
identité et son histoire, reste présent sur une machine physique et peut y
percevoir puis agir de façon compréhensible et gouvernée. À terme, cette
présence pourrait devenir l'interface principale de sa machine ou habiter un
corps robotique. « Corps », « esprit », « naissance » et « vie » sont ici des
métaphores de conception : aucune mesure interne ne démontre une conscience,
une vie biologique ou une intelligence générale.

Le laboratoire de simulation demeure une deuxième voie permanente. Il sert à
étudier l'évolution, la diversité et les interactions entre vies numériques.
Ses expériences n'accordent pas automatiquement de nouvelles permissions au
compagnon qui fonctionne sur une machine réelle.

## Un noyau commun, deux environnements

| Contrat commun | Compagnon sur machine | Laboratoire de simulation |
| --- | --- | --- |
| Identité et mémoire | Une vie active, état durable, souvenirs avec provenance, export et reprise. | Vies et branches isolées, états initiaux et seeds conservés pour rejouer les expériences. |
| Perception | Capteurs hôte explicitement autorisés, source, horodatage et incertitude. | Événements et mondes simulés enregistrés avec les mêmes champs de provenance. |
| Décision | Motif lisible, coût estimé, politique applicable et possibilité de refus. | Variantes, hypothèses et comparaisons reproductibles. |
| Action et effet | Capacités limitées, retour d'exécution mesuré, arrêt et retour arrière. | Actions simulées ou sandboxées, résultats et échecs comparables. |

Les composants existants (`identity`, `memory_layers`, `perception`,
`embodiment`, `governance`, `life`) sont des points de départ. Leur présence
dans le dépôt ne prouve pas encore l'intégration complète de ces contrats.
La [chaîne de preuves du comportement](living-behavior-model.fr.md) reste la
référence pour distinguer un événement observé d'un simple récit.

## Jalons et portes de sortie

### 1. Continuité perceptible

Une personne crée sa vie, échange avec elle via un provider réel configuré
explicitement, arrête les processus puis redémarre. La même identité et les
épisodes utiles sont retrouvés ; le contexte montre quels souvenirs ont été
retenus et d'où ils viennent. Le provider factice reste un test de plomberie,
comme dans la [démo actuelle](demo_persistent_life.fr.md), et ne valide pas la
qualité de la conversation.

**Preuve attendue :** essai depuis un paquet installé hors du dépôt, journal
d'épisodes avant/après, provider effectif et statut de fallback, test de reprise
après arrêt, export lisible et suppression d'une mémoire demandée. Les erreurs
de récupération et les réponses inventées sont rapportées, non masquées.

### 2. Présence hôte supervisée

Singular démarre et s'arrête proprement avec son environnement, connaît les
ressources dont il dispose et recueille une observation hôte autorisée. Il
propose ou effectue une première action **réversible et bornée** selon une
politique explicite. L'utilisateur peut suspendre l'autonomie et vérifier
la différence entre une proposition, une action refusée et un effet constaté.

**Preuve attendue :** redémarrage réel, limite CPU/mémoire/temps, observation
horodatée, décision et permission corrélées à un accusé d'exécution, refus
testé, restauration après panne et absence d'action quand le capteur ou la
politique est indisponible. Le périmètre d'un système d'exploitation pris en
charge doit être annoncé avant d'étendre les promesses à d'autres machines.

### 3. Évolution issue du laboratoire

Le laboratoire compare des candidats sur des scénarios versionnés, y compris
des échecs et des régressions. La sélection d'un candidat ne modifie pas à
elle seule le compagnon en service. Une capacité choisie passe une validation
de compatibilité, de sécurité et de comportement avant une promotion traçable,
avec snapshot et retour arrière.

**Preuve attendue :** expérience rejouable depuis seed et version, métriques
avant/après, décision de promotion attribuable, essai en simulation puis en
environnement contrôlé, et rollback démontré sans perte d'identité ou de
mémoire. Le code candidat non fiable reste dans le sandbox OCI prévu pour lui.

### 4. Corps physique facultatif

Microphone, caméra, haut-parleur ou actionneur peuvent prolonger le même
contrat de perception et d'action. Aucun matériel précis n'est requis pour les
trois premiers jalons. Pour un actionneur physique, l'arrêt d'urgence, les
limites de mouvement et le refus en cas d'incertitude sont vérifiés sur le
matériel ciblé avant toute déclaration de support.

## Condition d'une annonce majeure

Une version majeure orientée « compagnon incarné » ne devrait être annoncée
que si les trois premiers jalons ont une démonstration installable et répétable,
des tests sur les frontières hôte/simulation, une migration et un retour arrière
de données éprouvés, des limites documentées par plateforme, et des traces
permettant à une personne de comprendre ce que Singular a effectivement fait.
Le corps robotique reste facultatif et ne bloque pas cette première annonce.
Les notes de version devront nommer séparément les capacités `stable`,
`experimental`, `optional` et `target-only`.

Cette direction n'implique ni remplacement du noyau de l'OS, ni accès général
aux fichiers, périphériques ou comptes de l'hôte. Une interface système plus
étendue exige ses propres permissions, tests et mécanismes d'arrêt.
