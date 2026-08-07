# Critères d’acceptation — cycle de vie persistant de Victor

Le scénario automatisé `tests/test_victor_lifecycle_acceptance.py` documente les
fonctionnalités illustrées par les captures du cycle de vie. Il est statiquement
isolé : tous les chemins sont placés sous `tmp_path`, l’horloge narrative est
injectée et aucune attente réelle ni service réseau n’est utilisé.

## Critères vérifiés

1. **Naissance et identité** — Victor reçoit un identifiant durable. Après
   reconstruction des services, cet identifiant et l’engagement « tenir mes
   promesses » sont inchangés.
2. **Action, introspection et sommeil** — trois cycles produisent des épisodes,
   des instantanés narratifs et une récupération d’énergie sans mutation de
   l’identité.
3. **Mémoire** — les faits sont consolidés dans la couche sémantique et les
   épisodes deviennent rappelables depuis la mémoire à long terme.
4. **Narration et objectifs** — le cap, les trois périodes et leur chronologie
   évoluent; les objectifs `learn` et `protect` restent pondérés à 60 % et 40 %.
5. **Vie sociale et morale** — la confiance acquise conduit Victor à aider
   Alice; une action irréversible violant ses droits et l’engagement de soin
   reçoit un veto explicite.
6. **Sûreté des compétences** — une compétence défaillante est mise en
   quarantaine avec une raison persistée et le reste après redémarrage.
7. **Reprise** — psyché, identité, mémoire et graphe social sont recréés à
   partir des seuls fichiers et restituent les mêmes décisions et souvenirs.
8. **Mort contrôlée** — autopsie, biographie finale et registre de génération
   portent le même identifiant. La dernière entrée de chronologie nomme Victor;
   tous ces artefacts restent décodables après une nouvelle initialisation.

Le test constitue la spécification exécutable : une assertion en échec signifie
que le critère correspondant n’est plus satisfait par les fichiers persistés.
