# Critères de sortie — Release v2

Ce document définit les garde-fous de sortie pour publier **v2** en réduisant les régressions produit et les risques de sécurité.

## 1) Qualité automatique (CI)

- **Pipeline vert obligatoire** sur la matrice Python `3.10 / 3.11 / 3.12`.
- Jobs séparés:
  - `lint` (Ruff + Black)
  - `typecheck` (mypy)
  - `tests` (pytest)
- Aucun merge si un job échoue.

## 2) Couverture de tests

- **Seuil global minimal**: `>= 85%` sur `src/singular`.
- **Seuil minimal fichiers critiques CLI** (`src/singular/cli.py`, `src/singular/lives.py`): `>= 90%`.
- Toute baisse de couverture sur un module critique doit être explicitement justifiée dans la PR.

## 3) Scénarios CLI critiques à valider

Les parcours suivants sont bloquants avant release:

1. **birth**
   - création d'une vie valide,
   - initialisation des dossiers et registres attendus.
2. **talk**
   - conversation simple (`--prompt`) avec persistance mémoire,
   - fallback robuste si provider indisponible.
3. **loop**
   - exécution avec `--budget-seconds`,
   - écriture checkpoint + traces d'exécution.
4. **lives**
   - create / list / use / delete,
   - activation cohérente de la vie courante.
5. **uninstall**
   - mode `--keep-lives` (préserve `lives/`),
   - mode `--purge-lives` (purge complète) avec confirmations de sécurité.

## 4) Checklist sécurité sandbox

Avant release, vérifier systématiquement:

- [ ] Exécution de code utilisateur dans un environnement sandboxé (pas d'exécution arbitraire hors cadre).
- [ ] Restrictions réseau appliquées côté sandbox quand requis.
- [ ] Limites CPU / temps d'exécution configurées pour éviter les boucles non bornées.
- [ ] Écritures disque bornées aux répertoires autorisés.
- [ ] Aucune clé/API secret en clair dans logs, erreurs, ou artefacts de test.
- [ ] Messages d'erreur explicites en cas de violation sandbox (pas de stacktrace sensible exposée).

## 5) Critères de validation manuelle

- Smoke test local sur Linux/macOS/Windows (au moins un mainteneur par plateforme).
- Vérification de la documentation utilisateur sur les commandes critiques.
- Validation d'un scénario de rollback (retour version précédente + intégrité des données utilisateurs).
