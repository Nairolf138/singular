# Profil de démarrage `living`

Le profil `living` fournit huit capacités élémentaires : observation, évaluation
des besoins, choix d'objectif, planification, action, vérification du résultat,
interaction et réflexion. Ce ne sont **pas** les étapes d'une nouvelle boucle.
Ce sont des skills sélectionnables par `SkillRuntime`, comme les autres skills.

## Raccordement au cycle existant

À chaque exécution, le runtime ajoute au contexte une copie JSON en lecture seule
de `mem/world_state.json`, `mem/goals.json` (objectifs intrinsèques) et
`mem/psyche.json`. Le skill ne peut ni ouvrir ces fichiers ni les modifier. Une
action réussie continue d'utiliser le mapping d'effets de `sim_world`, publie les
événements `skill.execution.*` et `world.effect.applied`, puis une capacité
`living.*` publie `living.stage.completed` et écrit le même résultat dans
`mem/episodic.jsonl`. L'orchestrateur, la perception, l'arbitrage des objectifs et
la consolidation de mémoire restent donc les propriétaires du cycle de vie.

## Garanties et limites

### Déterministe

* La résolution du profil, l'ordre des huit fichiers générés, l'extraction des
  métadonnées du catalogue et le filtrage par capacité sont déterministes pour
  des fichiers d'entrée identiques.
* Les huit fonctions de départ sont des règles locales : elles testent seulement
  la présence de données explicites dans leur contexte et renvoient `0.0` ou
  `1.0`. Elles ne font aucun appel réseau et aucun échantillonnage.
* Le seed de naissance stabilise le nom généré et le `soulseed`. Les horodatages,
  identifiants de naissance et détails d'exécution propres à la plateforme ne
  sont pas promis identiques bit à bit.
* Le test d'intégration remplace uniquement la frontière du conteneur sandbox par
  un exécuteur Python local déterministe. Il exerce les vrais fichiers de
  naissance, le catalogue, le runtime, le bus, les conséquences du monde et la
  mémoire épisodique.

### Dépendant d'un fournisseur LLM

Les skills de ce profil n'appellent pas de LLM. Si l'orchestrateur fournit un
objectif, un plan, une action, une interaction ou une réflexion produits par son
adaptateur LLM, leur **contenu** et leur reproductibilité dépendent du fournisseur,
du modèle, de sa version, du prompt, des paramètres d'échantillonnage et de sa
disponibilité. Le profil ne présente pas ces sorties comme déterministes et ne
contourne pas l'adaptateur existant.

### Ce qui peut réellement évoluer

Peuvent évoluer par les mécanismes existants : les poids et l'historique des
objectifs intrinsèques, les traits et l'état social de la psyché, les ressources
et effets de `world_state.json`, les métriques et états de cycle de vie des
skills, ainsi que les épisodes ensuite consolidés. Les huit sources générées et
leurs métadonnées ne s'auto-modifient pas : elles ne changent que par mutation de
skill, configuration ou mise à jour du logiciel déjà gouvernée par Singular.

