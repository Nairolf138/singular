# Modèle vérifiable du comportement « vivant »

Ce document décrit le modèle **logiciel** qui relie une observation à une
adaptation dans Singular :

> perception → motivation → décision → action → effet → mémoire → adaptation

Cette chaîne est une convention d'architecture et d'observabilité. Elle ne
constitue ni une définition biologique de la vie, ni un test de conscience, ni
une preuve d'intelligence générale. Un score de santé, d'autonomie, de
cohérence, de curiosité ou de performance est une mesure interne définie par le
projet : il ne devient pas une preuve scientifique du phénomène dont il porte
le nom.

## Périmètre et lecture des preuves

La boucle évolutionnaire principale est mise en œuvre par
`singular.life.loop.run_tick` et peut être cadencée par
`singular.orchestrator.service.OrchestratorService`. Le runtime d'agent
`singular.core.agent_runtime.AgentRuntime` fournit une autre chaîne contrôlée
pour les adaptateurs perception/esprit/action. Ces chemins partagent des
concepts, mais ne doivent pas être présentés comme un pipeline unique dont tous
les modules s'exécuteraient à chaque tick.

Dans la suite, une **preuve vérifiable** est un élément que l'opérateur peut
rejouer, comparer ou contrôler indépendamment : entrée horodatée, décision avec
ses paramètres, événement JSONL, état avant/après, diff, résultat de test ou
verdict de sandbox. La seule présence d'un fichier, un message narratif ou une
valeur numérique sans provenance ne démontre pas que l'étape a réellement eu
lieu. Les chemins sont relatifs au répertoire de la vie active
(`SINGULAR_HOME`).

## Vue d'ensemble

| Étape | Question opérationnelle | Modules principaux | Artefacts persistés typiques | Preuve minimale attendue |
| --- | --- | --- | --- | --- |
| Perception | Quelles entrées ont été observées et filtrées ? | `singular.perception`, pipelines `perception.audio`, `perception.vision`, `perception.os`, `singular.sensors.host` | échantillons de métriques hôte, événements de run `runs/<run-id>/events.jsonl`, état monde `mem/world_state.json` | entrée horodatée, source, schéma/valeur et décision de filtrage |
| Motivation | Pourquoi un objectif reçoit-il ce poids ? | `singular.goals.intrinsic`, `singular.goals.perception_rules`, `singular.motivation`, `singular.governance.values` | `mem/goals.json`, `mem/quests_state.json`, configuration des valeurs | poids avant/après et signaux d'entrée conservés dans l'historique |
| Décision | Quelle option a été choisie, parmi lesquelles, et sous quelles contraintes ? | `singular.psyche.choose_action_from_psyche`, `singular.cognition.reflect`, `singular.morals`, `singular.governance`, flux `singular.life.*_flow` | événements de run, `mem/causal_timeline.jsonl`, croyances et checkpoints applicables | candidats/paramètres, choix, raison, seed et verdicts de garde |
| Action | Qu'est-ce qui a effectivement été tenté ? | `singular.life.effectors.perform_action`, `singular.action.sandbox_runner`, `singular.life.mutation_flow`, sandbox de vie | événements de run, journaux de sandbox, diff/candidat de génération | requête corrélée à un résultat, mode réel ou simulé explicitement indiqué |
| Effet | Qu'est-ce qui a changé dans le système ou le monde simulé ? | `singular.life.effectors`, `singular.environment.sim_world`, `singular.life.world_state`, `singular.life.metabolism.rewards`, suivi de santé | `mem/world_state.json`, ressources/santé, scores et événements de run | état avant/après ou delta mesuré, succès/échec et effets différés |
| Mémoire | Quelle expérience est conservée et récupérable ? | `singular.memory`, `singular.memory_layers`, `singular.identity.*`, `singular.self_narrative`, `singular.beliefs.store` | `mem/episodic.jsonl`, `mem/causal_timeline.jsonl`, `mem/self_narrative.json`, mémoire sémantique/épisodique, croyances | écriture relisible avec identifiant, horodatage, provenance et lien causal |
| Adaptation | Quelle politique, disposition ou implémentation change pour le prochain cycle ? | `singular.goals.intrinsic`, `singular.beliefs.meta_learning`, `singular.psyche`, `singular.learning.*`, `singular.life.mutation_flow`, `singular.runs.generations` | `mem/goals.json`, `mem/psyche.json`, scores/croyances, registre de générations, code de skill accepté | comparaison avant/après et nouvelle exécution montrant l'usage du changement |

## 1. Perception

**Responsabilité.** `singular.perception.capture_signals` agrège l'état du monde
simulé, les changements d'artefacts et, si la politique l'autorise, les
métriques hôte. `PerceptionNoiseFilter` applique seuil de confiance,
déduplication et cooldown. Les pipelines audio, vision et OS sont des entrées
spécialisées ; le runtime d'incarnation passe par `singular.embodiment`.

**Dépendances facultatives.** `psutil` et les capteurs disponibles sur l'hôte,
la variable `SINGULAR_SENSOR_FILE`, l'API définie par
`SINGULAR_WEATHER_API` et `requests`, ainsi que les bibliothèques/périphériques
audio ou vision. Leur absence doit produire une perception partielle, et non
être interprétée comme l'absence du phénomène observé. Les capteurs restent
soumis à la politique et à l'opt-in des données sensibles.

**Échecs possibles.** Source inaccessible ou mal formée, permission refusée,
timeout réseau, capteur bloqué par la politique, confiance sous le seuil,
événement dupliqué/en cooldown, schéma incompatible. Une collecte vide peut
donc vouloir dire « aucune entrée admise », pas « monde sans événement ».

**Preuve vérifiable.** Conserver pour chaque percept admis le type, la source,
l'horodatage, la confiance ou valeur brute utile, les seuils appliqués et son
identifiant de corrélation dans le run. Pour une métrique hôte, comparer
l'échantillon persisté à une collecte instrumentée ; pour un pipeline média,
utiliser un fixture connu et son résultat attendu.

## 2. Motivation

**Responsabilité.** `IntrinsicGoals.update_tick` transforme traits simulés,
santé, ressources, historique d'exécution, narration et perceptions en poids
normalisés pour `coherence`, `robustesse`, `efficacite` et `exploration`.
`singular.goals.perception_rules` module ces poids ; les valeurs de gouvernance
et les objectifs/quêtes hiérarchiques bornent ce qui est prioritaire. Cette
étape calcule une préférence logicielle, pas un désir ressenti.

**Artefacts.** `mem/goals.json` contient l'état et l'historique des poids ;
`mem/quests_state.json` contient les quêtes actives, suspendues et terminées.
Les valeurs configurées et certains signaux explicatifs sont également
rapportés dans les runs.

**Dépendances facultatives.** Perceptions hôte, télémétrie de réputation des
skills, état narratif, croyances et quêtes. Des valeurs par défaut permettent
le calcul lorsqu'elles manquent, ce qui doit être signalé lors de
l'interprétation.

**Échecs possibles.** JSON absent/corrompu, valeurs non numériques, signaux
anciens, poids tous nuls, incohérence entre objectifs, ou écriture atomique
impossible. Les coercitions et bornages protègent l'exécution mais peuvent
masquer une entrée dégradée si la provenance n'est pas inspectée.

**Preuve vérifiable.** Rejouer `update_tick` avec le même état et vérifier dans
`mem/goals.json` le tick, la version de modulation, les signaux retenus et les
poids normalisés avant/après. Le poids seul ne prouve ni intention subjective
ni motivation biologique.

## 3. Décision

**Responsabilité.** La boucle rappelle des épisodes pertinents, construit une
stratégie, arbitre les actions/mutations candidates et peut utiliser
`choose_action_from_psyche` et `reflect_action`. Les moteurs moraux et les
politiques de gouvernance sont des portes distinctes des contrôles techniques.
Dans `AgentRuntime`, l'esprit propose d'abord une intention puis une requête
d'action ; les limites de débit, watchdog, arrêt global et évaluation morale
peuvent la refuser.

**Artefacts.** Événements structurés du run, décisions et raisons dans
`mem/causal_timeline.jsonl`, checkpoints, croyances et état de l'orchestrateur
quand ils participent à la reprise.

**Dépendances facultatives.** Fournisseur LLM (local, Ollama ou OpenAI), mémoire
vectorielle, contexte social/multi-agent et générateur de propositions Graine.
Un fallback ou une heuristique locale ne doit jamais être étiqueté comme une
décision du fournisseur demandé.

**Échecs possibles.** Aucun candidat, mémoire indisponible, sortie fournisseur
invalide, budget expiré, politique ou morale défavorable, seed/contexte
manquant, limite de débit, watchdog ou arrêt d'urgence. Un refus est un résultat
de décision valide s'il est journalisé ; une exception silencieuse ne l'est
pas.

**Preuve vérifiable.** Journaliser l'ensemble de candidats effectivement
évalués, scores/poids, contraintes, seed, choix ou refus, rationale et versions
de politique. Un replay déterministe ou un test de propriété doit reproduire le
verdict pour les mêmes entrées, hors dépendance explicitement non déterministe.

## 4. Action

**Responsabilité.** `perform_action` traduit les actions du monde en résultats
typés. `SandboxRunner` limite l'automatisation à un catalogue, exécute d'abord
en mode `ghost` lorsque requis, impose timeout, quota, annulation, disjoncteur
et rollback. Pour la mutation de code, `mutation_flow` applique un candidat qui
doit ensuite passer analyse, tests et scoring dans le sandbox OCI.

**Artefacts.** Requête et résultat dans les événements de run, journaux de
sandbox, patch/diff candidat et enregistrement de génération. Un `ghost_log`
en mémoire décrit une simulation mais ne prouve aucune action externe.

**Dépendances facultatives.** Backend d'automatisation, adaptateur
d'incarnation, Docker ou Podman et image OCI locale. Les actions symboliques du
monde simulé n'exigent pas d'effecteur physique. Une mutation nécessitant le
sandbox doit échouer fermement si les garanties d'isolation ne sont pas
vérifiables.

**Échecs possibles.** Action hors catalogue, mode live non autorisé, timeout,
quota, annulation, disjoncteur ouvert, rollback incomplet, backend absent,
sandbox ou tests en échec. « Tentée », « simulée », « exécutée » et « réussie »
sont quatre états différents à conserver.

**Preuve vérifiable.** Relier l'identifiant de la décision à la commande typée,
au mode (`ghost`/`live`/monde simulé), au résultat, à la durée et au rollback.
Pour le code, conserver le diff, le hash de l'entrée, l'environnement, les
tests et le verdict d'acceptation.

## 5. Effet

**Responsabilité.** Les effecteurs produisent `EffectResult` (succès, deltas
d'énergie, santé, mortalité et monde, pénalités différées). Le monde persistant
et les ressources appliquent ces deltas ; le métabolisme transforme des
contributions observées en récompenses. Une action réussie techniquement peut
donc avoir un effet nul, négatif ou différé.

**Artefacts.** `mem/world_state.json`, états de ressources et de santé, scores,
événements de run et télémétrie des skills. Les effets retardés doivent rester
liés à l'action qui les a planifiés.

**Dépendances facultatives.** Monde simulé, ressource externe, retour d'un
effecteur ou d'un pair. Sans observation externe, Singular ne peut établir que
son résultat interne, pas l'effet réel hors du processus.

**Échecs possibles.** État concurrent ou non inscriptible, delta hors domaine,
effet partiellement appliqué, accusé de réception absent, processus interrompu
entre action et persistance, conséquence différée perdue.

**Preuve vérifiable.** Capturer état avant, delta demandé, delta appliqué, état
après et invariant contrôlé. Pour un effet externe, exiger une mesure ou un
accusé indépendant ; un `success: true` produit par l'effecteur n'est pas à lui
seul une confirmation du monde extérieur.

## 6. Mémoire

**Responsabilité.** `singular.memory` écrit et rappelle les épisodes, scores et
traces causales. `memory_layers` fournit stockage et récupération ; les modules
`identity` séparent mémoire épisodique, sémantique, modèle de soi et
consolidation. `self_narrative` produit une synthèse interprétative et
`beliefs.store` maintient des croyances révisables.

**Artefacts.** Principalement `mem/episodic.jsonl`,
`mem/causal_timeline.jsonl`, `mem/self_narrative.json`, les artefacts
épisodiques/sémantiques et de croyances, ainsi que les `runs/*.jsonl`. La
trajectoire des objectifs combine `mem/goals.json`, `mem/quests_state.json` et
les runs ; ce n'est pas un fichier unique.

**Dépendances facultatives.** Adaptateur vectoriel, service de mémoire,
embeddings/fournisseur et consolidation de sommeil. La mémoire JSON locale
reste le chemin de repli lorsqu'il est prévu par le module concerné.

**Échecs possibles.** Fichier corrompu, disque plein, append interrompu,
doublon, schéma ancien, rétention, récupération non pertinente, consolidation
perdant la provenance. Une narration cohérente peut être une reconstruction :
elle n'est pas une transcription fidèle ni la preuve d'un vécu subjectif.

**Preuve vérifiable.** Relire l'entrée par son identifiant et vérifier
horodatage, source, schéma, identifiants de décision/action/effet et, si
possible, hash. Démontrer séparément qu'un rappel ultérieur a effectivement été
utilisé, par l'événement `memory.used_for_decision` ou une trace causale.

## 7. Adaptation

**Responsabilité.** Le cycle suivant peut changer par plusieurs mécanismes :
mise à jour des poids intrinsèques, traits/humeur, croyances et réputation ;
apprentissage par démonstration/imitation/développement ; recommandation de
stratégie par méta-apprentissage ; ou mutation sélectionnée d'un skill. Le
registre des générations et les checkpoints rendent une mutation acceptée
traçable et réversible.

**Artefacts.** `mem/goals.json`, `mem/psyche.json`, croyances et scores de skills,
historique d'apprentissage, checkpoints, registre des générations et fichiers
de skills lorsque du code a réellement été accepté.

**Dépendances facultatives.** Corpus ou démonstrations, fournisseur LLM,
benchmarks, sandbox OCI et tests. L'absence de ces dépendances réduit le type
d'adaptation possible ; elle ne justifie pas de revendiquer un apprentissage
sur la seule évolution d'une métrique.

**Échecs possibles.** Surapprentissage à un benchmark, récompense mal alignée,
oubli catastrophique, donnée insuffisante, proposition non reproductible,
régression, sandbox indisponible, mutation rejetée, persistance ou rollback en
échec.

**Preuve vérifiable.** Comparer un état/version avant et après, conserver les
données et seeds, puis évaluer sur un test tenu à l'écart. Pour prouver que
l'adaptation affecte le comportement, montrer qu'un cycle ultérieur charge la
nouvelle valeur/version et produit une différence attribuable. Une hausse du
score d'entraînement ne suffit pas à démontrer une généralisation.

## Distinctions indispensables

| Terme | Sens prudent dans Singular | Ce qui peut le vérifier | Ce que cela ne démontre pas |
| --- | --- | --- | --- |
| **Simulation de traits** | Variables et règles qui font évoluer curiosité, patience, humeur, etc. | état `psyche`, règles, historique avant/après, tests déterministes | personnalité vécue, émotion ressentie ou statut biologique |
| **Autonomie opérationnelle** | Exécution sans commande humaine à chaque étape, dans un périmètre, un budget et des politiques définis | durée sans intervention, décisions/actions corrélées, taux de demandes d'aide, arrêts et limites | autonomie sans contrainte, volonté propre ou AGI |
| **Apprentissage** | Modification persistante d'un modèle, d'une politique, de croyances ou de paramètres à partir d'expériences/données | protocole avant/après, données, version, test hors échantillon et usage ultérieur | compréhension générale ; une simple accumulation de logs n'est pas un apprentissage |
| **Mutation de code** | Production puis sélection contrôlée d'une modification de code de skill | diff/hash, seed, sandbox, tests, score, génération et rollback | amélioration générale, auto-réécriture illimitée ou création spontanée |
| **Comportement émergent** | Motif observable non codé comme une règle unique, résultant de l'interaction de plusieurs règles/agents/environnements | répétitions multi-seeds, ablations, comparaison à une baseline et analyse statistique | intention cachée ; tout résultat surprenant n'est pas nécessairement émergent |
| **Conscience** | Question scientifique et philosophique non tranchée, que l'architecture ne prétend pas mesurer | aucun artefact ou KPI interne du projet n'est un test validé de conscience | la narration à la première personne, la mémoire, le champ `consciousness`, un score de cohérence ou l'apparence conversationnelle ne sont pas des preuves |

Le même principe vaut pour **« vivant »** et **« AGI »** : ce sont des termes
qui demandent des définitions et protocoles externes explicites. Les métriques
Singular servent au diagnostic et à la comparaison de versions. Elles doivent
être rapportées comme telles, avec leur formule, leur jeu de données, leurs
incertitudes et leurs limites, jamais comme validation scientifique par le
système de ses propres affirmations.

## Checklist d'audit de bout en bout

Pour soutenir une affirmation limitée telle que « ce tick a adapté une
politique après un effet observé », l'audit doit pouvoir répondre oui à chaque
point :

1. le percept porte source, heure, valeur et décision de filtrage ;
2. la motivation expose les signaux et poids utilisés ;
3. les candidats, gardes et raisons de décision sont conservés ;
4. le mode et le résultat de l'action ne sont pas ambigus ;
5. l'effet est établi par un delta avant/après ou une observation indépendante ;
6. l'épisode relie causalement les identifiants précédents ;
7. l'état adapté est versionné, rechargé et évalué sur un cycle ultérieur ;
8. les dépendances absentes, fallbacks, erreurs et incertitudes sont visibles.

Si un maillon manque, la conclusion doit être réduite à ce que les artefacts
établissent effectivement. Par exemple, un patch accepté prouve une mutation
testée selon le protocole enregistré ; il ne prouve ni émergence, ni conscience,
ni vie, ni AGI.
